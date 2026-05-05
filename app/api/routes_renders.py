from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

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
from app.api.errors import (
    LimitExceededAPIError,
    QueueSaturatedAPIError,
    RendererCapabilityAPIError,
    StorageError,
)
from app.core.config import Settings
from app.db import render_crud
from app.db.models import Render as RenderRecord
from app.models.composition import Composition
from app.models.errors import (
    AUTH_ERROR_RESPONSES,
    CONFLICT_ERROR,
    NOT_FOUND_ERROR,
    QUEUE_SATURATED_ERROR,
    QUEUE_UNAVAILABLE_ERROR,
    RENDERER_CAPABILITY_ERROR,
    REQUEST_SIZE_ERROR,
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
from app.renderers.capabilities import (
    RendererCapabilityError,
    validate_renderer_capabilities,
)
from app.services.limits import LimitExceededError, validate_composition_limits
from app.services.queue_admission import (
    QueueAdmissionUnavailableError,
    QueueSaturatedError,
    admit_render_queue,
)
from app.storage.base import ArtifactType, artifact_filename, artifact_media_type
from app.workers.render_worker import enqueue_render

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["renders"])


@dataclass(frozen=True)
class _RenderArtifactDownload:
    artifact_uri: str
    artifact_type: ArtifactType
    filename: str
    disposition: str
    media_type: str | None = None


@router.post(
    "/renders",
    response_model=CreateRenderResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        **AUTH_ERROR_RESPONSES,
        413: REQUEST_SIZE_ERROR,
        422: RENDERER_CAPABILITY_ERROR,
        429: QUEUE_SATURATED_ERROR,
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
    try:
        renderer_selection = validate_renderer_capabilities(composition)
    except RendererCapabilityError as exc:
        raise RendererCapabilityAPIError.from_capability_error(exc) from exc

    try:
        validate_composition_limits(composition, settings)
    except LimitExceededError as exc:
        raise LimitExceededAPIError.from_violation(exc.violation) from exc

    if settings.render_mode == "async":
        if arq_pool is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Render queue pool not initialized.",
            )
        await _admit_queue_or_raise(settings=settings, arq_pool=arq_pool)
        return await _create_render_async(
            composition,
            session,
            arq_pool,
            storage,
            selected_renderer=renderer_selection.renderer,
        )
    return await _create_render_sync(composition, render_service, session)


async def _admit_queue_or_raise(
    *,
    settings: Settings,
    arq_pool: ArqRedis,
) -> None:
    try:
        await admit_render_queue(settings=settings, arq_pool=arq_pool)
    except QueueSaturatedError as exc:
        raise QueueSaturatedAPIError(
            depth=exc.depth,
            max_depth=exc.max_depth,
            retry_after=exc.retry_after,
        ) from exc
    except QueueAdmissionUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Render queue is unavailable. Please retry later.",
        ) from exc


async def _create_render_async(
    composition: Composition,
    session: DBSessionDep,
    arq_pool: ArqRedis,
    storage: StorageDep,
    *,
    selected_renderer: str,
) -> CreateRenderResponse:
    """Async path: create record, persist input, enqueue job."""
    callback_url = str(composition.callback) if composition.callback else None
    render = await render_crud.create_render(
        session,
        callback_url=callback_url,
        renderer=selected_renderer,
    )
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

    await logger.ainfo(
        "render_enqueued",
        render_id=render_id,
        renderer=selected_renderer,
    )
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
    responses={
        **AUTH_ERROR_RESPONSES,
        422: VALIDATION_ERROR,
    },
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
        **AUTH_ERROR_RESPONSES,
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
        **AUTH_ERROR_RESPONSES,
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
    output = await url_resolver.output_metadata(render)
    captions = await url_resolver.caption_metadata(render)
    poster_metadata = await url_resolver.poster_metadata(render)

    return RenderResponse(
        id=render.id,
        status=render_status,
        stage=render.stage,
        progress=render.progress,
        url=url,
        poster=poster,
        output=output,
        captions=captions,
        poster_metadata=poster_metadata,
        duration=render.output_duration_seconds,
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
        **AUTH_ERROR_RESPONSES,
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
        filename=render.output_filename or f"{render_id}.mp4",
        disposition="attachment",
        media_type=render.output_media_type,
    )


@router.head(
    "/renders/{render_id}/download",
    responses={
        **AUTH_ERROR_RESPONSES,
        404: NOT_FOUND_ERROR,
        422: VALIDATION_ERROR,
    },
)
async def head_download_render(
    render_id: str,
    session: DBSessionDep,
    storage: StorageDep,
    url_resolver: StorageUrlResolverDep,
) -> Response:
    """Return rendered output file headers without streaming the body."""
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
        filename=render.output_filename or f"{render_id}.mp4",
        disposition="attachment",
        media_type=render.output_media_type,
        stream_body=False,
    )


@router.get(
    "/renders/{render_id}/poster",
    responses={
        **AUTH_ERROR_RESPONSES,
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


@router.get(
    "/renders/{render_id}/captions",
    responses={
        **AUTH_ERROR_RESPONSES,
        404: NOT_FOUND_ERROR,
        422: VALIDATION_ERROR,
    },
)
async def download_captions(
    render_id: str,
    session: DBSessionDep,
    storage: StorageDep,
    url_resolver: StorageUrlResolverDep,
) -> Response:
    """Stream or redirect the render caption sidecar artifact."""
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

    if not render.caption_sidecar_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No caption sidecar for render {render_id}",
        )

    return await _artifact_response(
        render_id=render_id,
        artifact_uri=render.caption_sidecar_path,
        artifact_type=ArtifactType.CAPTION_SIDECAR,
        storage=storage,
        url_resolver=url_resolver,
        filename=render.caption_sidecar_filename or f"{render_id}-captions.srt",
        disposition="attachment",
        media_type=render.caption_sidecar_media_type,
    )


@router.get(
    "/renders/{render_id}/artifacts/{artifact_name}",
    responses={
        **AUTH_ERROR_RESPONSES,
        404: NOT_FOUND_ERROR,
        422: VALIDATION_ERROR,
    },
)
async def download_render_artifact(
    render_id: str,
    artifact_name: str,
    session: DBSessionDep,
    storage: StorageDep,
    url_resolver: StorageUrlResolverDep,
) -> Response:
    """Stream or redirect a safe render artifact by deterministic name."""
    render = await render_crud.get_render_by_id(session, render_id)
    if render is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Render {render_id} not found",
        )

    artifact = _resolve_render_artifact(render, artifact_name)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact {artifact_name} not found for render {render_id}",
        )

    return await _artifact_response(
        render_id=render_id,
        artifact_uri=artifact.artifact_uri,
        artifact_type=artifact.artifact_type,
        storage=storage,
        url_resolver=url_resolver,
        filename=artifact.filename,
        disposition=artifact.disposition,
        media_type=artifact.media_type,
    )


def _resolve_render_artifact(
    render: RenderRecord,
    artifact_name: str,
) -> _RenderArtifactDownload | None:
    """Resolve supported deterministic artifact names from persisted render paths."""
    artifacts: dict[str, _RenderArtifactDownload] = {}

    def add_artifact(
        *,
        artifact_type: ArtifactType,
        artifact_uri: str | None,
        filename: str,
        disposition: str,
        media_type: str | None = None,
        aliases: tuple[str, ...] = (),
    ) -> None:
        if not artifact_uri:
            return
        descriptor = _RenderArtifactDownload(
            artifact_uri=artifact_uri,
            artifact_type=artifact_type,
            filename=filename,
            disposition=disposition,
            media_type=media_type,
        )
        for alias in aliases:
            if alias:
                artifacts.setdefault(alias, descriptor)

    render_id = str(render.id)
    output_path = render.output_path
    output_filename = render.output_filename or f"{render_id}.mp4"
    output_storage_filename = _artifact_filename_from_uri(output_path)
    add_artifact(
        artifact_type=ArtifactType.OUTPUT,
        artifact_uri=output_path,
        filename=output_filename,
        disposition="attachment",
        media_type=render.output_media_type,
        aliases=(
            ArtifactType.OUTPUT.value,
            output_storage_filename,
            output_filename,
        ),
    )
    add_artifact(
        artifact_type=ArtifactType.INPUT,
        artifact_uri=render.input_path,
        filename=ArtifactType.INPUT.value,
        disposition="inline",
        media_type=artifact_media_type(ArtifactType.INPUT),
        aliases=("input", ArtifactType.INPUT.value),
    )
    add_artifact(
        artifact_type=ArtifactType.EXPANDED,
        artifact_uri=render.expanded_path,
        filename=ArtifactType.EXPANDED.value,
        disposition="inline",
        media_type=artifact_media_type(ArtifactType.EXPANDED),
        aliases=("expanded", ArtifactType.EXPANDED.value),
    )
    add_artifact(
        artifact_type=ArtifactType.COMPILED,
        artifact_uri=render.compiled_path,
        filename=ArtifactType.COMPILED.value,
        disposition="inline",
        media_type=artifact_media_type(ArtifactType.COMPILED),
        aliases=("compiled", ArtifactType.COMPILED.value),
    )
    add_artifact(
        artifact_type=ArtifactType.MANIFEST,
        artifact_uri=render.output_manifest_path,
        filename=ArtifactType.MANIFEST.value,
        disposition="inline",
        media_type=artifact_media_type(ArtifactType.MANIFEST),
        aliases=("manifest", ArtifactType.MANIFEST.value),
    )

    poster_path = render.poster_path
    poster_filename = render.poster_filename or f"{render_id}.jpg"
    add_artifact(
        artifact_type=ArtifactType.POSTER,
        artifact_uri=poster_path,
        filename=poster_filename,
        disposition="inline",
        media_type=render.poster_media_type,
        aliases=(
            "poster",
            ArtifactType.POSTER.value,
            _artifact_filename_from_uri(poster_path),
            poster_filename,
        ),
    )

    caption_path = render.caption_sidecar_path
    caption_filename = render.caption_sidecar_filename or f"{render_id}-captions.srt"
    add_artifact(
        artifact_type=ArtifactType.CAPTION_SIDECAR,
        artifact_uri=caption_path,
        filename=caption_filename,
        disposition="attachment",
        media_type=render.caption_sidecar_media_type,
        aliases=(
            ArtifactType.CAPTION_SIDECAR.value,
            _artifact_filename_from_uri(caption_path),
            caption_filename,
        ),
    )
    add_artifact(
        artifact_type=ArtifactType.REPLAY,
        artifact_uri=render.replay_path,
        filename=ArtifactType.REPLAY.value,
        disposition="inline",
        media_type=artifact_media_type(ArtifactType.REPLAY),
        aliases=("replay", ArtifactType.REPLAY.value),
    )
    add_artifact(
        artifact_type=ArtifactType.LOG,
        artifact_uri=render.log_path,
        filename=ArtifactType.LOG.value,
        disposition="inline",
        media_type=artifact_media_type(ArtifactType.LOG),
        aliases=("logs", ArtifactType.LOG.value),
    )

    return artifacts.get(artifact_name)


def _artifact_filename_from_uri(artifact_uri: str | None) -> str:
    if not artifact_uri:
        return ""
    parsed = urlsplit(artifact_uri)
    path = parsed.path if parsed.scheme else artifact_uri
    filename = PurePosixPath(unquote(path)).name
    return filename or artifact_filename(ArtifactType.OUTPUT)


async def _artifact_response(
    *,
    render_id: str,
    artifact_uri: str,
    artifact_type: ArtifactType,
    storage: StorageDep,
    url_resolver: StorageUrlResolverDep,
    filename: str,
    disposition: str,
    media_type: str | None = None,
    stream_body: bool = True,
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
    resolved_media_type = media_type or artifact_media_type(artifact_type)
    if not stream_body:
        return Response(
            status_code=status.HTTP_200_OK,
            media_type=resolved_media_type,
            headers=headers,
        )

    return StreamingResponse(
        storage.iter_uri(artifact_uri),
        media_type=resolved_media_type,
        headers=headers,
    )
