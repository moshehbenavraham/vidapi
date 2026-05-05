from __future__ import annotations

import json

import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError

from app.api.deps import (
    ArqPoolDep,
    DBSessionDep,
    SettingsDep,
    StorageDep,
    TemplateServiceDep,
)
from app.api.errors import StorageError
from app.db import render_crud
from app.db.template_models import TemplateVersion
from app.models.errors import (
    CONFLICT_ERROR,
    NOT_FOUND_ERROR,
    QUEUE_UNAVAILABLE_ERROR,
    VALIDATION_ERROR,
)
from app.models.render import RenderStatus
from app.models.template import (
    CreateTemplateRequest,
    CreateTemplateResponse,
    TemplateListItem,
    TemplateListResponse,
    TemplateRenderRequest,
    TemplateRenderResponse,
    TemplateResponse,
    TemplateVersionResponse,
    UpdateTemplateRequest,
)
from app.services.template_engine import (
    TemplateExpansionError,
    TemplateVariableError,
)
from app.services.template_service import (
    TemplateAlreadyDeletedError,
    TemplateDeletedError,
    TemplateNotFoundError,
)
from app.storage.base import ArtifactType
from app.workers.render_worker import enqueue_render

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["templates"])


def _build_version_response(version: TemplateVersion) -> TemplateVersionResponse:
    composition_data = json.loads(version.composition)
    variable_schema_data = (
        json.loads(version.variable_schema)
        if version.variable_schema is not None
        else None
    )
    return TemplateVersionResponse(
        id=version.id,
        version_number=version.version_number,
        composition=composition_data,
        variable_schema=variable_schema_data,
        created_at=version.created_at,
    )


@router.post(
    "/templates",
    response_model=CreateTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={422: VALIDATION_ERROR},
)
async def create_template(
    body: CreateTemplateRequest,
    template_service: TemplateServiceDep,
    session: DBSessionDep,
) -> CreateTemplateResponse:
    """Create a new template with an initial version."""
    template, version = await template_service.create_template(
        session,
        name=body.name,
        composition=body.composition,
        description=body.description,
        variable_schema=body.variable_schema,
    )

    return CreateTemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        active_version=_build_version_response(version),
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@router.get(
    "/templates",
    response_model=TemplateListResponse,
    responses={422: VALIDATION_ERROR},
)
async def list_templates(
    session: DBSessionDep,
    template_service: TemplateServiceDep,
    offset: int = 0,
    limit: int = 20,
) -> TemplateListResponse:
    """Return paginated list of templates excluding soft-deleted ones."""
    if limit < 1:
        limit = 1
    if limit > 100:
        limit = 100
    if offset < 0:
        offset = 0

    items_with_counts, total = await template_service.list_templates(
        session, offset=offset, limit=limit
    )

    return TemplateListResponse(
        items=[
            TemplateListItem(
                id=tmpl.id,
                name=tmpl.name,
                description=tmpl.description,
                active_version_id=tmpl.active_version_id,
                version_count=count,
                created_at=tmpl.created_at,
                updated_at=tmpl.updated_at,
            )
            for tmpl, count in items_with_counts
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/templates/{template_id}",
    response_model=TemplateResponse,
    responses={
        404: NOT_FOUND_ERROR,
        422: VALIDATION_ERROR,
    },
)
async def get_template(
    template_id: str,
    template_service: TemplateServiceDep,
    session: DBSessionDep,
) -> TemplateResponse:
    """Return a template with its active version composition."""
    try:
        template, active_version = await template_service.get_template(
            session, template_id
        )
    except TemplateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template {template_id} not found",
        ) from exc

    version_response = (
        _build_version_response(active_version) if active_version else None
    )

    return TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        active_version=version_response,
        is_deleted=template.is_deleted,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@router.put(
    "/templates/{template_id}",
    response_model=TemplateResponse,
    responses={
        404: NOT_FOUND_ERROR,
        409: CONFLICT_ERROR,
        422: VALIDATION_ERROR,
    },
)
async def update_template(
    template_id: str,
    body: UpdateTemplateRequest,
    template_service: TemplateServiceDep,
    session: DBSessionDep,
) -> TemplateResponse:
    """Update a template, creating a new immutable version if composition changes."""
    try:
        template, new_version = await template_service.update_template(
            session,
            template_id,
            name=body.name,
            description=body.description,
            composition=body.composition,
            variable_schema=body.variable_schema,
        )
    except TemplateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template {template_id} not found",
        ) from exc
    except TemplateDeletedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Template {template_id} is deleted and cannot be updated",
        ) from exc

    active_version_data = None
    if new_version is not None:
        active_version_data = _build_version_response(new_version)
    elif template.active_version_id is not None:
        from app.db import template_crud

        active_ver = await template_crud.get_active_version(session, template)
        if active_ver is not None:
            active_version_data = _build_version_response(active_ver)

    return TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        active_version=active_version_data,
        is_deleted=template.is_deleted,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@router.delete(
    "/templates/{template_id}",
    status_code=status.HTTP_200_OK,
    responses={
        404: NOT_FOUND_ERROR,
        409: CONFLICT_ERROR,
        422: VALIDATION_ERROR,
    },
)
async def delete_template(
    template_id: str,
    template_service: TemplateServiceDep,
    session: DBSessionDep,
) -> dict[str, str]:
    """Soft-delete a template without destroying data."""
    try:
        template = await template_service.delete_template(session, template_id)
    except TemplateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template {template_id} not found",
        ) from exc
    except TemplateAlreadyDeletedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Template {template_id} is already deleted",
        ) from exc

    return {
        "id": template.id,
        "status": "deleted",
        "detail": "Template soft-deleted successfully",
    }


@router.post(
    "/templates/{template_id}/renders",
    response_model=TemplateRenderResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        404: NOT_FOUND_ERROR,
        409: CONFLICT_ERROR,
        422: VALIDATION_ERROR,
        503: QUEUE_UNAVAILABLE_ERROR,
    },
)
async def render_template(
    template_id: str,
    body: TemplateRenderRequest,
    template_service: TemplateServiceDep,
    session: DBSessionDep,
    settings: SettingsDep,
    arq_pool: ArqPoolDep,
    storage: StorageDep,
) -> TemplateRenderResponse:
    """Render a template with merge data.

    Validates merge variables, expands the template composition via Jinja2,
    creates a render record with template references, and enqueues for
    processing.
    """
    try:
        (
            expanded_composition,
            tmpl_id,
            version_id,
            expanded_dict,
        ) = await template_service.render_from_template(
            session, template_id, body.merge
        )
    except TemplateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template {template_id} not found",
        ) from exc
    except TemplateDeletedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Template {template_id} is deleted and cannot be rendered",
        ) from exc
    except TemplateVariableError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "errors": exc.errors},
        ) from exc
    except TemplateExpansionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "details": exc.details},
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Expanded composition failed validation",
                "errors": [str(e) for e in exc.errors()],
            },
        ) from exc

    if body.callback:
        expanded_dict["callback"] = body.callback

    render = await render_crud.create_render(
        session,
        template_id=tmpl_id,
        template_version_id=version_id,
        callback_url=body.callback,
    )
    render_id = render.id

    try:
        input_uri = await storage.publish_bytes(
            render_id,
            ArtifactType.INPUT,
            expanded_composition.model_dump_json(indent=2).encode("utf-8"),
        )
        expanded_uri = await storage.publish_bytes(
            render_id,
            ArtifactType.EXPANDED,
            json.dumps(expanded_dict, indent=2, ensure_ascii=True).encode("utf-8"),
        )
        await render_crud.update_render_paths(
            session,
            render_id,
            input_path=input_uri,
            expanded_path=expanded_uri,
        )
    except (OSError, StorageError) as exc:
        await render_crud.update_render_status(
            session,
            render_id,
            RenderStatus.FAILED,
            error_code="STORAGE_ERROR",
            error_message="Failed to persist template render input",
            stage="failed",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist template render input.",
        ) from exc

    if settings.render_mode == "async":
        if arq_pool is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Render queue pool not initialized.",
            )
        try:
            await enqueue_render(arq_pool, render_id)
        except (RedisConnectionError, OSError) as exc:
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

    return TemplateRenderResponse(
        id=render.id,
        status=RenderStatus.QUEUED.value,
        progress=0,
        template_id=tmpl_id,
        template_version_id=version_id,
        created_at=render.created_at,
    )
