from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import ArqPoolDep, DBSessionDep, SettingsDep
from app.core.logging import safe_log_excerpt
from app.db import render_crud, webhook_crud
from app.db.models import Render
from app.db.webhook_models import WebhookAttempt
from app.models.errors import (
    AUTH_ERROR_RESPONSES,
    OPS_ERROR_RESPONSES,
    VALIDATION_ERROR,
)
from app.models.ops import (
    OpsRendererFailureCount,
    OpsRendererFailureCountsResponse,
    OpsRenderFailureItem,
    OpsRenderFailureListResponse,
    OpsRenderItem,
    OpsRenderListResponse,
    OpsStatusCount,
    OpsStatusCountsResponse,
    OpsWebhookAttemptItem,
    OpsWebhookAttemptsResponse,
    OpsWebhookOutcomeCount,
    OpsWebhookOutcomeCountsResponse,
)
from app.models.render import RenderStatus
from app.services.metrics import collect_metrics_snapshot, format_prometheus_metrics

router = APIRouter(prefix="/ops", tags=["operations"])

DEFAULT_OPS_LIMIT = 20
MAX_OPS_LIMIT = 100
MAX_OPS_EXCERPT_CHARS = 300


def clamp_pagination(offset: int, limit: int) -> tuple[int, int]:
    """Clamp operational pagination to bounded deterministic values."""
    return max(0, offset), min(MAX_OPS_LIMIT, max(1, limit))


def parse_status_filter(status_filter: str | None) -> RenderStatus | None:
    """Parse an optional status filter into the public enum."""
    if status_filter is None:
        return None
    try:
        return RenderStatus(status_filter)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status filter: {status_filter}",
        ) from exc


@router.get(
    "/renders",
    response_model=OpsRenderListResponse,
    responses={**AUTH_ERROR_RESPONSES, 422: VALIDATION_ERROR},
)
async def list_operational_renders(
    session: DBSessionDep,
    offset: int = 0,
    limit: int = DEFAULT_OPS_LIMIT,
    status_filter: str | None = None,
) -> OpsRenderListResponse:
    offset, limit = clamp_pagination(offset, limit)
    parsed_status = parse_status_filter(status_filter)
    try:
        items, total = await render_crud.list_renders(
            session,
            offset=offset,
            limit=limit,
            status_filter=parsed_status,
        )
    except SQLAlchemyError as exc:
        raise _ops_unavailable() from exc

    return OpsRenderListResponse(
        items=[_render_item(render) for render in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/renders/failures",
    response_model=OpsRenderFailureListResponse,
    responses={**AUTH_ERROR_RESPONSES, 422: VALIDATION_ERROR},
)
async def list_operational_render_failures(
    session: DBSessionDep,
    offset: int = 0,
    limit: int = DEFAULT_OPS_LIMIT,
) -> OpsRenderFailureListResponse:
    offset, limit = clamp_pagination(offset, limit)
    try:
        items, total = await render_crud.list_recent_failed_renders(
            session,
            offset=offset,
            limit=limit,
        )
    except SQLAlchemyError as exc:
        raise _ops_unavailable() from exc

    return OpsRenderFailureListResponse(
        items=[_render_failure_item(render) for render in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/renders/status-counts",
    response_model=OpsStatusCountsResponse,
    responses={**AUTH_ERROR_RESPONSES, **OPS_ERROR_RESPONSES},
)
async def get_operational_render_status_counts(
    session: DBSessionDep,
) -> OpsStatusCountsResponse:
    try:
        counts = await render_crud.count_renders_by_status(session)
    except SQLAlchemyError as exc:
        raise _ops_unavailable() from exc

    by_status = {count.status: count.count for count in counts}
    return OpsStatusCountsResponse(
        counts=[
            OpsStatusCount(status=render_status, count=by_status.get(render_status, 0))
            for render_status in RenderStatus
        ]
    )


@router.get(
    "/renders/renderer-failures",
    response_model=OpsRendererFailureCountsResponse,
    responses={**AUTH_ERROR_RESPONSES, **OPS_ERROR_RESPONSES},
)
async def get_operational_renderer_failure_counts(
    session: DBSessionDep,
) -> OpsRendererFailureCountsResponse:
    try:
        counts = await render_crud.count_renderer_failures(session)
    except SQLAlchemyError as exc:
        raise _ops_unavailable() from exc

    return OpsRendererFailureCountsResponse(
        counts=[
            OpsRendererFailureCount(
                renderer=count.renderer,
                error_code=count.error_code,
                count=count.count,
            )
            for count in counts
        ]
    )


@router.get(
    "/webhooks",
    response_model=OpsWebhookAttemptsResponse,
    responses={**AUTH_ERROR_RESPONSES, 422: VALIDATION_ERROR},
)
async def list_operational_webhook_attempts(
    session: DBSessionDep,
    render_id: str | None = None,
    failures_only: bool = False,
    offset: int = 0,
    limit: int = DEFAULT_OPS_LIMIT,
) -> OpsWebhookAttemptsResponse:
    offset, limit = clamp_pagination(offset, limit)
    try:
        items, total = await webhook_crud.list_recent_attempts(
            session,
            render_id=render_id,
            failures_only=failures_only,
            offset=offset,
            limit=limit,
        )
    except SQLAlchemyError as exc:
        raise _ops_unavailable() from exc

    return OpsWebhookAttemptsResponse(
        items=[_webhook_attempt_item(attempt) for attempt in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/webhooks/outcome-counts",
    response_model=OpsWebhookOutcomeCountsResponse,
    responses={**AUTH_ERROR_RESPONSES, **OPS_ERROR_RESPONSES},
)
async def get_operational_webhook_outcome_counts(
    session: DBSessionDep,
) -> OpsWebhookOutcomeCountsResponse:
    try:
        counts = await webhook_crud.count_webhook_outcomes(session)
    except SQLAlchemyError as exc:
        raise _ops_unavailable() from exc

    return OpsWebhookOutcomeCountsResponse(
        counts=[
            OpsWebhookOutcomeCount(
                webhook_event=count.webhook_event,
                outcome=count.outcome,
                count=count.count,
            )
            for count in counts
        ]
    )


@router.get(
    "/metrics",
    responses={**AUTH_ERROR_RESPONSES, **OPS_ERROR_RESPONSES},
)
async def get_operational_metrics(
    session: DBSessionDep,
    settings: SettingsDep,
    arq_pool: ArqPoolDep,
) -> Response:
    try:
        snapshot = await collect_metrics_snapshot(
            session,
            settings=settings,
            arq_pool=arq_pool,
        )
    except SQLAlchemyError as exc:
        raise _ops_unavailable() from exc

    return Response(
        content=format_prometheus_metrics(snapshot),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


def _render_item(render: Render) -> OpsRenderItem:
    return OpsRenderItem(
        id=render.id,
        status=RenderStatus(render.status),
        progress=render.progress,
        stage=render.stage,
        renderer=render.renderer,
        template_id=render.template_id,
        template_version_id=render.template_version_id,
        created_at=render.created_at,
        updated_at=render.updated_at,
        started_at=render.started_at,
        completed_at=render.completed_at,
    )


def _render_failure_item(render: Render) -> OpsRenderFailureItem:
    return OpsRenderFailureItem(
        id=render.id,
        status=RenderStatus(render.status),
        stage=render.stage,
        renderer=render.renderer,
        error_code=render.error_code,
        error_message_excerpt=safe_log_excerpt(
            render.error_message,
            limit=MAX_OPS_EXCERPT_CHARS,
        ),
        replay_available=render.replay_path is not None,
        log_available=render.log_path is not None,
        created_at=render.created_at,
        updated_at=render.updated_at,
        started_at=render.started_at,
        completed_at=render.completed_at,
    )


def _webhook_attempt_item(attempt: WebhookAttempt) -> OpsWebhookAttemptItem:
    if attempt.id is None:
        raise _ops_unavailable()
    status_code = attempt.status_code
    success = (
        status_code is not None and 200 <= status_code < 300 and attempt.error is None
    )
    return OpsWebhookAttemptItem(
        id=attempt.id,
        render_id=attempt.render_id,
        webhook_event=attempt.event,
        attempt_number=attempt.attempt_number,
        status_code=status_code,
        success=success,
        response_body_excerpt=safe_log_excerpt(
            attempt.response_body_excerpt,
            limit=MAX_OPS_EXCERPT_CHARS,
        ),
        error_excerpt=safe_log_excerpt(
            attempt.error,
            limit=MAX_OPS_EXCERPT_CHARS,
        ),
        scheduled_at=attempt.scheduled_at,
        delivered_at=attempt.delivered_at,
        created_at=attempt.created_at,
        updated_at=attempt.updated_at,
    )


def _ops_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Operational data is unavailable.",
    )
