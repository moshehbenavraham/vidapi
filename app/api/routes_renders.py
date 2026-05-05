from __future__ import annotations

import structlog
from arq.connections import ArqRedis
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from redis.exceptions import ConnectionError as RedisConnectionError

from app.api.deps import (
    ArqPoolDep,
    DBSessionDep,
    RenderServiceDep,
    SettingsDep,
    StorageDep,
    StorageUrlResolverDep,
)
from app.api.errors import StorageError
from app.db import render_crud
from app.models.composition import Composition
from app.models.errors import (
    CONFLICT_ERROR,
    NOT_FOUND_ERROR,
    QUEUE_UNAVAILABLE_ERROR,
    RATE_LIMIT_ERROR,
    VALIDATION_ERROR,
)
from app.models.render import (
    CreateRenderResponse,
    RenderListItem,
    RenderListResponse,
    RenderResponse,
    RenderStatus,
)
from app.models.render import (
    RenderError as RenderErrorModel,
)
from app.storage.base import ArtifactType, artifact_media_type
from app.workers.render_worker import enqueue_render

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["renders"])


@router.post(
    "/renders",
    response_model=CreateRenderResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        422: VALIDATION_ERROR,
        429: RATE_LIMIT_ERROR,
        503: QUEUE_UNAVAILABLE_ERROR,
    },
)
async def create_render(
    composition: Composition,
    render_service: RenderServiceDep,
    session: DBSessionDep,
    settings: SettingsDep,
    arq_pool: ArqPoolDep,
    storage: StorageDep,
) -> CreateRenderResponse:
    """Accept a composition and start rendering.

    When RENDER_MODE=async, creates a DB record, persists the input JSON,
    enqueues to ARQ, and returns 202 immediately.
    When RENDER_MODE=sync, executes the full pipeline inline (dev/test).
    """
    if settings.render_mode == "async":
        if arq_pool is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Render queue pool not initialized.",
            )
        return await _create_render_async(composition, session, arq_pool, storage)
    return await _create_render_sync(composition, render_service, session)


async def _create_render_async(
    composition: Composition,
    session: DBSessionDep,
    arq_pool: ArqRedis,
    storage: StorageDep,
) -> CreateRenderResponse:
    """Async path: create record, persist input, enqueue job."""
    callback_url = str(composition.callback) if composition.callback else None
    render = await render_crud.create_render(session, callback_url=callback_url)
    render_id = render.id

    try:
        input_uri = await storage.publish_bytes(
            render_id,
            ArtifactType.INPUT,
            composition.model_dump_json(indent=2).encode("utf-8"),
        )
        await render_crud.update_render_paths(
            session,
            render_id,
            input_path=input_uri,
        )
    except (OSError, StorageError) as exc:
        await render_crud.update_render_status(
            session,
            render_id,
            RenderStatus.FAILED,
            error_code="STORAGE_ERROR",
            error_message="Failed to persist render input",
            stage="failed",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist render input.",
        ) from exc

    try:
        await enqueue_render(arq_pool, render_id)
    except (RedisConnectionError, OSError) as exc:
        await logger.aerror(
            "redis_enqueue_failed",
            render_id=render_id,
            error=str(exc),
        )
        await render_crud.update_render_status(
            session,
            render_id,
            RenderStatus.FAILED,
            error_code="QUEUE_UNAVAILABLE",
            error_message="Redis is unreachable; cannot enqueue render job",
            stage="failed",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Render queue is unavailable. Please retry later.",
        ) from exc

    await logger.ainfo("render_enqueued", render_id=render_id)
    return CreateRenderResponse(
        id=render.id,
        status=RenderStatus.QUEUED,
        progress=0,
        created_at=render.created_at,
    )


async def _create_render_sync(
    composition: Composition,
    render_service: RenderServiceDep,
    session: DBSessionDep,
) -> CreateRenderResponse:
    """Sync path: execute full pipeline inline (dev/test mode)."""
    render = await render_service.execute_render(composition, session)
    return CreateRenderResponse(
        id=render.id,
        status=RenderStatus(render.status),
        progress=render.progress,
        created_at=render.created_at,
    )


@router.get(
    "/renders",
    response_model=RenderListResponse,
    responses={422: VALIDATION_ERROR},
)
async def list_renders(
    session: DBSessionDep,
    offset: int = 0,
    limit: int = 20,
    status_filter: str | None = None,
) -> RenderListResponse:
    """Return paginated list of render jobs ordered by created_at DESC."""
    if limit < 1:
        limit = 1
    if limit > 100:
        limit = 100
    if offset < 0:
        offset = 0

    parsed_status: RenderStatus | None = None
    if status_filter is not None:
        try:
            parsed_status = RenderStatus(status_filter)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status filter: {status_filter}",
            ) from exc

    items, total = await render_crud.list_renders(
        session,
        offset=offset,
        limit=limit,
        status_filter=parsed_status,
    )

    return RenderListResponse(
        items=[
            RenderListItem(
                id=r.id,
                status=RenderStatus(r.status),
                progress=r.progress,
                template_id=r.template_id,
                template_version_id=r.template_version_id,
                created_at=r.created_at,
                started_at=r.started_at,
                completed_at=r.completed_at,
            )
            for r in items
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.delete(
    "/renders/{render_id}",
    status_code=status.HTTP_200_OK,
    responses={
        404: NOT_FOUND_ERROR,
        409: CONFLICT_ERROR,
        422: VALIDATION_ERROR,
    },
)
async def cancel_render(
    render_id: str,
    session: DBSessionDep,
) -> dict[str, str]:
    """Cancel a render job.

    Queued renders transition immediately to CANCELLED.
    Active renders get cancel_requested_at flag set for cooperative cancellation.
    Already-cancelled renders return success (idempotent).
    Terminal renders (succeeded/failed) return 409.
    """
    render = await render_crud.get_render_by_id(session, render_id)
    if render is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Render {render_id} not found",
        )

    current_status = RenderStatus(render.status)

    if current_status == RenderStatus.CANCELLED:
        return {"id": render_id, "status": "cancelled", "detail": "Already cancelled"}

    if current_status in (RenderStatus.SUCCEEDED, RenderStatus.FAILED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(f"Cannot cancel render in terminal state: {current_status.value}"),
        )

    if current_status == RenderStatus.QUEUED:
        await render_crud.update_render_status(
            session,
            render_id,
            RenderStatus.CANCELLED,
            stage="cancelled",
        )
        return {
            "id": render_id,
            "status": "cancelled",
            "detail": "Cancelled immediately",
        }

    await render_crud.set_cancel_requested(session, render_id)
    return {
        "id": render_id,
        "status": current_status.value,
        "detail": "Cancel requested; worker will stop at next checkpoint",
    }


@router.get(
    "/renders/{render_id}",
    response_model=RenderResponse,
    responses={
        404: NOT_FOUND_ERROR,
        422: VALIDATION_ERROR,
    },
)
async def get_render(
    render_id: str,
    session: DBSessionDep,
    url_resolver: StorageUrlResolverDep,
) -> RenderResponse:
    """Return full render status."""
    render = await render_crud.get_render_by_id(session, render_id)
    if render is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Render {render_id} not found",
        )

    render_status = RenderStatus(render.status)

    error: RenderErrorModel | None = None
    if render.error_code is not None:
        error = RenderErrorModel(
            code=render.error_code,
            message=render.error_message or "Unknown error",
        )

    url = await url_resolver.output_url(render)
    poster = await url_resolver.poster_url(render)

    return RenderResponse(
        id=render.id,
        status=render_status,
        stage=render.stage,
        progress=render.progress,
        url=url,
        poster=poster,
        template_id=render.template_id,
        template_version_id=render.template_version_id,
        created_at=render.created_at,
        started_at=render.started_at,
        completed_at=render.completed_at,
        error=error,
    )


@router.get(
    "/renders/{render_id}/download",
    responses={
        404: NOT_FOUND_ERROR,
        422: VALIDATION_ERROR,
    },
)
async def download_render(
    render_id: str,
    session: DBSessionDep,
    storage: StorageDep,
    url_resolver: StorageUrlResolverDep,
) -> Response:
    """Stream the rendered output file."""
    render = await render_crud.get_render_by_id(session, render_id)
    if render is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Render {render_id} not found",
        )

    render_status = RenderStatus(render.status)
    if render_status != RenderStatus.SUCCEEDED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Render {render_id} is not complete (status: {render_status.value})"
            ),
        )

    if not render.output_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No output file for render {render_id}",
        )

    return await _artifact_response(
        render_id=render_id,
        artifact_uri=render.output_path,
        artifact_type=ArtifactType.OUTPUT,
        storage=storage,
        url_resolver=url_resolver,
        filename=f"{render_id}.mp4",
        disposition="attachment",
    )


@router.get(
    "/renders/{render_id}/poster",
    responses={
        404: NOT_FOUND_ERROR,
        422: VALIDATION_ERROR,
    },
)
async def download_poster(
    render_id: str,
    session: DBSessionDep,
    storage: StorageDep,
    url_resolver: StorageUrlResolverDep,
) -> Response:
    """Stream or redirect the render poster artifact."""
    render = await render_crud.get_render_by_id(session, render_id)
    if render is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Render {render_id} not found",
        )

    if not render.poster_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No poster file for render {render_id}",
        )

    return await _artifact_response(
        render_id=render_id,
        artifact_uri=render.poster_path,
        artifact_type=ArtifactType.POSTER,
        storage=storage,
        url_resolver=url_resolver,
        filename=f"{render_id}.jpg",
        disposition="inline",
    )


async def _artifact_response(
    *,
    render_id: str,
    artifact_uri: str,
    artifact_type: ArtifactType,
    storage: StorageDep,
    url_resolver: StorageUrlResolverDep,
    filename: str,
    disposition: str,
) -> Response:
    redirect_url = await url_resolver.endpoint_redirect_url(
        render_id,
        artifact_uri,
        artifact_type,
    )
    if redirect_url is not None:
        return RedirectResponse(
            redirect_url,
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        )

    try:
        exists = await storage.exists_uri(artifact_uri)
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Artifact storage is unavailable.",
        ) from exc

    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact missing for render {render_id}",
        )

    headers = {
        "Content-Disposition": f'{disposition}; filename="{filename}"',
    }
    return StreamingResponse(
        storage.iter_uri(artifact_uri),
        media_type=artifact_media_type(artifact_type),
        headers=headers,
    )
