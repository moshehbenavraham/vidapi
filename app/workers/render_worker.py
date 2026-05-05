from __future__ import annotations

import asyncio
import contextlib
import time
from datetime import datetime
from typing import Any

import structlog
from arq.connections import ArqRedis

from app.api.errors import StorageError
from app.core.config import get_settings
from app.db import render_crud
from app.db.models import Render
from app.db.session import _get_engine
from app.models.error_codes import ErrorCode, error_code_for_exception
from app.models.render import RenderStatus
from app.renderers.capabilities import (
    RendererCapabilityError,
    validate_renderer_capabilities,
)
from app.services.ffmpeg_progress import compute_progress_percent, parse_time_from_line
from app.services.limits import LimitExceededError, validate_composition_limits
from app.services.render_service import RenderService, RenderServiceError
from app.services.webhook_service import dispatch_webhook
from app.storage.base import ArtifactType
from app.workers.log_collector import RenderLogCollector
from app.workers.workspace import WorkspaceManager

logger = structlog.get_logger(__name__)


async def run_render(ctx: dict[str, Any], render_id: str) -> None:
    """ARQ task: execute the full render pipeline with stage-by-stage transitions.

    Drives status transitions externally (QUEUED -> FETCHING -> COMPILING ->
    RENDERING -> UPLOADING -> SUCCEEDED/FAILED) and manages workspace lifecycle
    and log collection.
    """
    session_factory = ctx["session_factory"]
    render_service: RenderService = ctx["render_service"]
    workspace_mgr: WorkspaceManager = ctx["workspace_manager"]
    settings = get_settings()

    structlog.contextvars.bind_contextvars(render_id=render_id)
    await logger.ainfo("worker_task_start", render_id=render_id)

    log_collector = RenderLogCollector(render_id)
    log_collector.add("init", "Worker task started")

    workspace = None
    timeout = settings.render_timeout_seconds

    # Pre-flight checks
    async with session_factory() as session:
        render = await render_crud.get_render_by_id(session, render_id)
        if render is None:
            await logger.aerror("worker_render_not_found", render_id=render_id)
            return

        if RenderStatus(render.status).is_terminal:
            await logger.awarning(
                "worker_render_already_terminal",
                render_id=render_id,
                status=render.status,
            )
            return

        if render.cancel_requested_at is not None:
            await logger.ainfo(
                "worker_render_cancelled_on_pickup",
                render_id=render_id,
            )
            await render_crud.update_render_status(
                session,
                render_id,
                RenderStatus.CANCELLED,
                stage="cancelled",
            )
            return

        if render.input_path is None:
            await _mark_failed(
                session_factory,
                render_id,
                ErrorCode.NO_INPUT_DATA,
                "Render record has no stored composition",
                log_collector,
                workspace,
            )
            return

        try:
            input_bytes = await render_service.read_artifact_uri(render.input_path)
            input_json = input_bytes.decode("utf-8")
        except FileNotFoundError:
            await _mark_failed(
                session_factory,
                render_id,
                ErrorCode.INPUT_FILE_MISSING,
                "Stored input artifact was not found",
                log_collector,
                workspace,
            )
            return
        except StorageError as exc:
            await _mark_failed(
                session_factory,
                render_id,
                ErrorCode.STORAGE_ERROR,
                "Failed to read stored render input",
                log_collector,
                workspace,
            )
            await logger.aerror(
                "worker_input_storage_read_failed",
                render_id=render_id,
                error=str(exc),
            )
            return

        from pydantic import ValidationError

        from app.models.composition import Composition

        try:
            composition = Composition.model_validate_json(input_json)
        except ValidationError as exc:
            await _mark_failed(
                session_factory,
                render_id,
                ErrorCode.INVALID_COMPOSITION,
                "Stored composition failed validation",
                log_collector,
                workspace,
            )
            await logger.aerror(
                "worker_input_validation_failed",
                render_id=render_id,
                error=str(exc),
            )
            return

        try:
            renderer_selection = validate_renderer_capabilities(composition)
        except RendererCapabilityError as exc:
            await _mark_failed(
                session_factory,
                render_id,
                ErrorCode(exc.code),
                str(exc),
                log_collector,
                workspace,
                renderer=exc.renderer,
            )
            await logger.aerror(
                "worker_renderer_capability_validation_failed",
                render_id=render_id,
                renderer=exc.renderer,
                error_code=exc.code,
                context=exc.to_context(),
            )
            return

        try:
            validate_composition_limits(composition, settings)
        except LimitExceededError as exc:
            await _mark_failed(
                session_factory,
                render_id,
                ErrorCode(exc.violation.code),
                exc.violation.message,
                log_collector,
                workspace,
                renderer=renderer_selection.renderer,
            )
            await logger.aerror(
                "worker_composition_limit_validation_failed",
                render_id=render_id,
                renderer=renderer_selection.renderer,
                error_code=exc.violation.code,
                context=exc.violation.to_context(),
            )
            return

        await render_crud.update_render_renderer(
            session,
            render_id,
            renderer_selection.renderer,
        )
        await logger.ainfo(
            "worker_renderer_selected",
            render_id=render_id,
            renderer=renderer_selection.renderer,
        )

    # Pipeline execution with workspace lifecycle
    try:
        workspace = await workspace_mgr.create(render_id)
        log_collector.add("init", "Workspace created", extra={"path": str(workspace)})

        await _execute_pipeline(
            session_factory=session_factory,
            render_service=render_service,
            render_id=render_id,
            composition=composition,
            workspace=workspace,
            timeout=timeout,
            log_collector=log_collector,
        )

        # Flush logs before cleanup
        log_path = await log_collector.flush(workspace)
        if log_path is not None:
            try:
                async with session_factory() as session:
                    await render_service.publish_artifact_file(
                        render_id,
                        ArtifactType.LOG,
                        log_path,
                        session,
                    )
            except Exception as exc:
                await logger.awarning(
                    "worker_log_publish_failed",
                    render_id=render_id,
                    error=str(exc),
                )

        await workspace_mgr.cleanup_success(workspace)
        await logger.ainfo("worker_task_succeeded", render_id=render_id)

    except Exception as exc:
        error_code = _resolve_error_code(exc)
        error_message = str(exc)[:500]
        renderer_name = _renderer_name_for_exception(exc)

        log_collector.add_error(
            "pipeline",
            f"Pipeline failed: {error_message}",
            extra={"error_code": error_code.value, "renderer": renderer_name},
        )

        # Flush logs before marking failed
        if workspace is not None:
            log_path = await log_collector.flush(workspace)
            if log_path is not None:
                try:
                    async with session_factory() as session:
                        await render_service.publish_artifact_file(
                            render_id,
                            ArtifactType.LOG,
                            log_path,
                            session,
                        )
                except Exception as publish_exc:
                    await logger.awarning(
                        "worker_failure_log_publish_failed",
                        render_id=render_id,
                        error=str(publish_exc),
                    )

        await _mark_failed(
            session_factory,
            render_id,
            error_code,
            error_message,
            log_collector,
            workspace,
            renderer=renderer_name,
        )

        if workspace is not None:
            await workspace_mgr.cleanup_failure(workspace)

    finally:
        structlog.contextvars.unbind_contextvars("render_id")


async def _check_cancelled(session_factory: Any, render_id: str) -> bool:
    """Check if cancel has been requested for this render."""
    async with session_factory() as session:
        render = await render_crud.get_render_by_id(session, render_id)
        if render is None:
            return True
        return render.cancel_requested_at is not None


async def _cancel_render(
    session_factory: Any,
    render_id: str,
    log_collector: RenderLogCollector,
    workspace: Any,
) -> None:
    """Transition render to CANCELLED and clean up."""
    async with session_factory() as session:
        render = await render_crud.get_render_by_id(session, render_id)
        if render is not None and not RenderStatus(render.status).is_terminal:
            await render_crud.update_render_status(
                session,
                render_id,
                RenderStatus.CANCELLED,
                stage="cancelled",
            )
    log_collector.add("cancelled", "Render cancelled by user request")
    _fire_webhook(session_factory, render_id, "render.cancelled")
    await logger.ainfo("worker_render_cancelled", render_id=render_id)


def _make_progress_callback(
    session_factory: Any,
    render_id: str,
    total_duration: float,
    settings: Any,
) -> Any:
    """Build an async progress callback for the renderer.

    Rate-limits DB writes to at most once per progress_update_interval_seconds
    and requires >= 2% delta from last reported progress.
    """
    state = {"last_progress": 0, "last_update_time": 0.0}

    async def _callback(line: str) -> None:
        elapsed = parse_time_from_line(line)
        if elapsed is None:
            return

        percent = compute_progress_percent(elapsed, total_duration)
        delta = percent - state["last_progress"]
        if delta < 2:
            return

        now = time.monotonic()
        interval = settings.progress_update_interval_seconds
        if now - state["last_update_time"] < interval:
            return

        state["last_progress"] = percent
        state["last_update_time"] = now

        try:
            async with session_factory() as session:
                await render_crud.update_render_progress(session, render_id, percent)
        except Exception:
            pass

    return _callback


async def _execute_pipeline(
    *,
    session_factory: Any,
    render_service: RenderService,
    render_id: str,
    composition: Any,
    workspace: Any,
    timeout: int,
    log_collector: RenderLogCollector,
) -> None:
    """Drive all pipeline stages with status transitions and timeout."""
    settings = get_settings()

    async def _inner() -> None:
        # Cancellation checkpoint helper
        async def _checkpoint() -> None:
            if await _check_cancelled(session_factory, render_id):
                await _cancel_render(
                    session_factory, render_id, log_collector, workspace
                )
                raise _PipelineCancelledError()

        # Stage 1: FETCHING - validate and expand
        await _checkpoint()
        async with session_factory() as session:
            updated_render = await render_crud.update_render_status(
                session,
                render_id,
                RenderStatus.FETCHING,
                stage="validating",
                progress=5,
            )
        await _log_stage_transition(
            updated_render,
            status=RenderStatus.FETCHING,
            stage="validating",
            progress=5,
        )
        log_collector.add("fetching", "Status -> FETCHING")

        async with session_factory() as session:
            expanded = await render_service.stage_validate_and_expand(
                composition, render_id, workspace, session
            )
        log_collector.add("fetching", "Validation and expansion complete")

        # Stage 2: COMPILING - resolve assets and compile
        await _checkpoint()
        async with session_factory() as session:
            updated_render = await render_crud.update_render_status(
                session,
                render_id,
                RenderStatus.COMPILING,
                stage="resolving_assets",
                progress=20,
            )
        await _log_stage_transition(
            updated_render,
            status=RenderStatus.COMPILING,
            stage="resolving_assets",
            progress=20,
        )
        log_collector.add("compiling", "Status -> COMPILING")

        async with session_factory() as session:
            compiled = await render_service.stage_resolve_and_compile(
                expanded, render_id, workspace, session
            )
        log_collector.add("compiling", "Compilation complete")

        # Stage 3: RENDERING - render video and store artifacts
        await _checkpoint()
        async with session_factory() as session:
            updated_render = await render_crud.update_render_status(
                session,
                render_id,
                RenderStatus.RENDERING,
                stage="rendering",
                progress=30,
            )
        await _log_stage_transition(
            updated_render,
            status=RenderStatus.RENDERING,
            stage="rendering",
            progress=30,
        )
        log_collector.add("rendering", "Status -> RENDERING")

        # Compute total duration for progress percentage
        from app.renderers.editly import compute_total_duration

        total_duration = compute_total_duration(composition.timeline.tracks)

        progress_cb = _make_progress_callback(
            session_factory, render_id, total_duration, settings
        )

        async def _cancel_check() -> bool:
            return await _check_cancelled(session_factory, render_id)

        async with session_factory() as session:
            await render_service.stage_render_and_store(
                expanded,
                compiled,
                render_id,
                workspace,
                session,
                progress_callback=progress_cb,
                cancel_check=_cancel_check,
            )
        log_collector.add("rendering", "Render and store complete")

        # Stage 4: UPLOADING -> SUCCEEDED
        await _checkpoint()
        async with session_factory() as session:
            updated_render = await render_crud.update_render_status(
                session,
                render_id,
                RenderStatus.UPLOADING,
                stage="finalizing",
                progress=90,
            )
        await _log_stage_transition(
            updated_render,
            status=RenderStatus.UPLOADING,
            stage="finalizing",
            progress=90,
        )
        log_collector.add("uploading", "Status -> UPLOADING")

        async with session_factory() as session:
            updated_render = await render_crud.update_render_status(
                session,
                render_id,
                RenderStatus.SUCCEEDED,
                stage="complete",
                progress=100,
            )
        await _log_stage_transition(
            updated_render,
            status=RenderStatus.SUCCEEDED,
            stage="complete",
            progress=100,
        )
        log_collector.add("complete", "Status -> SUCCEEDED")

        _fire_webhook(session_factory, render_id, "render.succeeded")

    with contextlib.suppress(_PipelineCancelledError):
        await asyncio.wait_for(_inner(), timeout=timeout)


_webhook_tasks: set[asyncio.Task[None]] = set()


def _fire_webhook(
    session_factory: Any,
    render_id: str,
    event: str,
) -> None:
    """Schedule a non-blocking webhook dispatch via asyncio.create_task.

    Tracks the task in _webhook_tasks to prevent garbage collection and
    cleans up on completion.
    """
    task = asyncio.create_task(
        dispatch_webhook(
            session_factory=session_factory,
            render_id=render_id,
            event=event,
        )
    )
    _webhook_tasks.add(task)
    task.add_done_callback(_webhook_tasks.discard)


async def _log_stage_transition(
    render: Any,
    *,
    status: RenderStatus,
    stage: str,
    progress: int,
) -> None:
    if render is None:
        return

    fields: dict[str, Any] = {
        "render_id": render.id,
        "status": status.value,
        "stage": stage,
        "progress": progress,
    }
    if render.started_at is not None:
        fields["queue_wait_seconds"] = _seconds_between(
            render.created_at,
            render.started_at,
        )
    if render.started_at is not None and render.completed_at is not None:
        fields["render_duration_seconds"] = _seconds_between(
            render.started_at,
            render.completed_at,
        )
    await logger.ainfo("worker_stage_transition", **fields)


class _PipelineCancelledError(Exception):
    """Internal signal: pipeline was cancelled cooperatively."""


def _resolve_error_code(exc: Exception) -> ErrorCode:
    """Map an exception to a normalized error code."""
    if isinstance(exc, TimeoutError):
        return ErrorCode.RENDER_TIMEOUT
    if isinstance(exc, RenderServiceError):
        code_str = exc.error_code
        try:
            return ErrorCode(code_str)
        except ValueError:
            return (
                error_code_for_exception(exc.cause)
                if exc.cause
                else ErrorCode.WORKER_UNEXPECTED_ERROR
            )
    return error_code_for_exception(exc)


def _renderer_name_for_exception(exc: Exception) -> str | None:
    if isinstance(exc, RenderServiceError) and isinstance(
        exc.cause,
        RendererCapabilityError,
    ):
        return exc.cause.renderer
    return None


async def _mark_failed(
    session_factory: Any,
    render_id: str,
    error_code: ErrorCode,
    error_message: str,
    log_collector: RenderLogCollector,
    workspace: Any,
    *,
    renderer: str | None = None,
) -> None:
    """Transition render to FAILED status with error details."""
    log_collector.add_error("failed", f"{error_code.value}: {error_message}")

    async with session_factory() as session:
        render = await render_crud.get_render_by_id(session, render_id)
        updated_render = render
        if render is not None and not RenderStatus(render.status).is_terminal:
            if renderer is not None:
                await render_crud.update_render_renderer(
                    session,
                    render_id,
                    renderer,
                )
            updated_render = await render_crud.update_render_status(
                session,
                render_id,
                RenderStatus.FAILED,
                error_code=error_code.value,
                error_message=error_message[:500],
                stage="failed",
            )

    _fire_webhook(session_factory, render_id, "render.failed")

    await logger.aerror(
        "worker_task_failed",
        render_id=render_id,
        renderer=renderer,
        status=RenderStatus.FAILED.value,
        stage="failed",
        error_code=error_code.value,
        render_duration_seconds=_render_duration_seconds(updated_render),
    )


async def enqueue_render(pool: ArqRedis, render_id: str) -> None:
    """Enqueue a render job to ARQ for async processing."""
    await pool.enqueue_job("run_render", render_id)


def _seconds_between(start: datetime, end: datetime) -> float:
    return round(max(0.0, (end - start).total_seconds()), 3)


def _render_duration_seconds(render: Render | None) -> float | None:
    if render is None:
        return None
    if render.started_at is None or render.completed_at is None:
        return None
    return _seconds_between(render.started_at, render.completed_at)


async def worker_startup(ctx: dict[str, Any]) -> None:
    """ARQ on_startup hook: initialize DB engine and service dependencies."""

    from app.renderers.editly import EditlyRenderer
    from app.services.asset_service import AssetService
    from app.storage.factory import build_storage

    settings = get_settings()

    engine = _get_engine()

    storage = build_storage(settings)
    asset_service = AssetService(settings=settings)
    renderer = EditlyRenderer(settings=settings)
    render_service = RenderService(
        storage=storage,
        asset_service=asset_service,
        renderer=renderer,
    )

    workspace_mgr = WorkspaceManager(workspace_root=settings.render_workspace_root)

    ctx["session_factory"] = _make_session_context_manager(engine)
    ctx["render_service"] = render_service
    ctx["workspace_manager"] = workspace_mgr

    try:
        async with ctx["session_factory"]() as session:
            active_render_ids = await render_crud.list_active_render_ids(session)
        await workspace_mgr.cleanup_orphans(active_render_ids)
    except Exception as exc:
        await logger.awarning("workspace_orphan_cleanup_failed", error=str(exc))

    await logger.ainfo("worker_started")


def _make_session_context_manager(engine: Any) -> Any:
    """Build an async context manager that yields DB sessions."""
    from contextlib import asynccontextmanager

    from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

    @asynccontextmanager
    async def _session_ctx():  # type: ignore[no-untyped-def]
        async with SQLModelAsyncSession(engine) as session:
            yield session

    return _session_ctx


async def worker_shutdown(ctx: dict[str, Any]) -> None:
    """ARQ on_shutdown hook: cleanup resources."""
    await logger.ainfo("worker_shutdown")
