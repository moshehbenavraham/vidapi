from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.db.models import Render
from app.models.render import RenderStatus


@dataclass(frozen=True)
class RenderStatusCount:
    status: str
    count: int


@dataclass(frozen=True)
class RendererFailureCount:
    renderer: str
    error_code: str
    count: int


@dataclass(frozen=True)
class RenderTimingSample:
    render_id: str
    seconds: float


async def _commit_and_refresh(session: AsyncSession, *instances: object) -> None:
    try:
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        raise

    for instance in instances:
        await session.refresh(instance)


async def create_render(
    session: AsyncSession,
    *,
    template_id: str | None = None,
    template_version_id: str | None = None,
    callback_url: str | None = None,
) -> Render:
    """Create a new render record in QUEUED status."""
    render = Render(
        template_id=template_id,
        template_version_id=template_version_id,
        callback_url=callback_url,
    )
    session.add(render)
    await _commit_and_refresh(session, render)
    return render


async def get_render_by_id(
    session: AsyncSession,
    render_id: str,
) -> Render | None:
    """Return a render by ID or None if not found."""
    result = await session.execute(select(Render).where(Render.id == render_id))
    return result.scalar_one_or_none()


async def update_render_status(
    session: AsyncSession,
    render_id: str,
    new_status: RenderStatus,
    *,
    error_code: str | None = None,
    error_message: str | None = None,
    stage: str | None = None,
    progress: int | None = None,
) -> Render | None:
    """Transition a render to a new status with state-machine validation.

    Returns the updated render or None if not found.
    Raises ValueError on invalid status transition.
    """
    render = await get_render_by_id(session, render_id)
    if render is None:
        return None

    current = RenderStatus(render.status)
    current.transition_to(new_status)

    render.status = new_status.value
    render.updated_at = datetime.now(tz=UTC)

    if stage is not None:
        render.stage = stage
    if progress is not None:
        render.progress = progress
    if error_code is not None:
        render.error_code = error_code
    if error_message is not None:
        render.error_message = error_message

    if new_status == RenderStatus.FETCHING and render.started_at is None:
        render.started_at = datetime.now(tz=UTC)

    if new_status.is_terminal:
        render.completed_at = datetime.now(tz=UTC)
        if new_status == RenderStatus.SUCCEEDED:
            render.progress = 100

    session.add(render)
    await _commit_and_refresh(session, render)
    return render


async def list_renders(
    session: AsyncSession,
    *,
    offset: int = 0,
    limit: int = 20,
    status_filter: RenderStatus | None = None,
) -> tuple[list[Render], int]:
    """Return paginated render list ordered by created_at DESC.

    Returns (items, total_count).
    """
    base = select(Render)
    count_stmt = select(func.count()).select_from(Render)

    if status_filter is not None:
        base = base.where(Render.status == status_filter.value)
        count_stmt = count_stmt.where(Render.status == status_filter.value)

    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()

    query = base.order_by(col(Render.created_at).desc()).offset(offset).limit(limit)
    result = await session.execute(query)
    items = list(result.scalars().all())

    return items, total


async def count_renders_by_status(session: AsyncSession) -> list[RenderStatusCount]:
    """Return render counts grouped by status with deterministic ordering."""
    result = await session.execute(
        select(Render.status, func.count())
        .select_from(Render)
        .group_by(Render.status)
        .order_by(Render.status)
    )
    return [
        RenderStatusCount(status=str(status_value), count=int(count_value))
        for status_value, count_value in result.all()
    ]


async def list_recent_failed_renders(
    session: AsyncSession,
    *,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[Render], int]:
    """Return bounded failed renders ordered by newest update first."""
    count_stmt = (
        select(func.count())
        .select_from(Render)
        .where(Render.status == RenderStatus.FAILED.value)
    )
    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()

    query = (
        select(Render)
        .where(Render.status == RenderStatus.FAILED.value)
        .order_by(col(Render.updated_at).desc(), col(Render.created_at).desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(query)
    return list(result.scalars().all()), total


async def count_renderer_failures(
    session: AsyncSession,
    *,
    limit: int = 100,
) -> list[RendererFailureCount]:
    """Return failed render counts grouped by renderer and error code."""
    result = await session.execute(
        select(Render.renderer, Render.error_code, func.count())
        .select_from(Render)
        .where(Render.status == RenderStatus.FAILED.value)
        .group_by(Render.renderer, Render.error_code)
        .order_by(func.count().desc(), Render.renderer, Render.error_code)
        .limit(limit)
    )
    return [
        RendererFailureCount(
            renderer=str(renderer or "unknown"),
            error_code=str(error_code or "UNKNOWN"),
            count=int(count_value),
        )
        for renderer, error_code, count_value in result.all()
    ]


async def list_queue_wait_samples(
    session: AsyncSession,
    *,
    limit: int = 100,
) -> list[RenderTimingSample]:
    """Return recent queue wait samples derived from started_at - created_at."""
    result = await session.execute(
        select(Render.id, Render.created_at, Render.started_at)
        .where(col(Render.started_at).is_not(None))
        .order_by(col(Render.started_at).desc())
        .limit(limit)
    )
    samples: list[RenderTimingSample] = []
    for render_id, created_at, started_at in result.all():
        if started_at is None:
            continue
        seconds = max(0.0, (started_at - created_at).total_seconds())
        samples.append(RenderTimingSample(render_id=str(render_id), seconds=seconds))
    return samples


async def list_render_duration_samples(
    session: AsyncSession,
    *,
    limit: int = 100,
) -> list[RenderTimingSample]:
    """Return recent render duration samples derived from completed - started."""
    result = await session.execute(
        select(Render.id, Render.started_at, Render.completed_at)
        .where(col(Render.started_at).is_not(None))
        .where(col(Render.completed_at).is_not(None))
        .order_by(col(Render.completed_at).desc())
        .limit(limit)
    )
    samples: list[RenderTimingSample] = []
    for render_id, started_at, completed_at in result.all():
        if started_at is None or completed_at is None:
            continue
        seconds = max(0.0, (completed_at - started_at).total_seconds())
        samples.append(RenderTimingSample(render_id=str(render_id), seconds=seconds))
    return samples


async def list_active_render_ids(session: AsyncSession) -> set[str]:
    """Return render IDs that may still own active workspaces."""
    active_statuses = [
        RenderStatus.QUEUED.value,
        RenderStatus.FETCHING.value,
        RenderStatus.COMPILING.value,
        RenderStatus.RENDERING.value,
        RenderStatus.UPLOADING.value,
    ]
    result = await session.execute(
        select(Render.id).where(col(Render.status).in_(active_statuses))
    )
    return {str(render_id) for render_id in result.scalars().all()}


async def set_cancel_requested(
    session: AsyncSession,
    render_id: str,
) -> Render | None:
    """Set cancel_requested_at timestamp on a render.

    Idempotent: if already set, preserves the original timestamp.
    Returns None if render not found.
    """
    render = await get_render_by_id(session, render_id)
    if render is None:
        return None

    if render.cancel_requested_at is not None:
        return render

    render.cancel_requested_at = datetime.now(tz=UTC)
    render.updated_at = datetime.now(tz=UTC)

    session.add(render)
    await _commit_and_refresh(session, render)
    return render


async def update_render_progress(
    session: AsyncSession,
    render_id: str,
    progress: int,
) -> Render | None:
    """Update the progress field on a render record.

    Clamps progress to [0, 100]. Returns None if render not found.
    """
    render = await get_render_by_id(session, render_id)
    if render is None:
        return None

    clamped = max(0, min(100, progress))
    render.progress = clamped
    render.updated_at = datetime.now(tz=UTC)

    session.add(render)
    await _commit_and_refresh(session, render)
    return render


async def update_render_paths(
    session: AsyncSession,
    render_id: str,
    *,
    input_path: str | None = None,
    expanded_path: str | None = None,
    compiled_path: str | None = None,
    output_path: str | None = None,
    poster_path: str | None = None,
    replay_path: str | None = None,
    log_path: str | None = None,
    renderer: str | None = None,
) -> Render | None:
    """Update artifact paths on a render record.

    Only non-None values are updated; existing paths are preserved.
    """
    render = await get_render_by_id(session, render_id)
    if render is None:
        return None

    if input_path is not None:
        render.input_path = input_path
    if expanded_path is not None:
        render.expanded_path = expanded_path
    if compiled_path is not None:
        render.compiled_path = compiled_path
    if output_path is not None:
        render.output_path = output_path
    if poster_path is not None:
        render.poster_path = poster_path
    if replay_path is not None:
        render.replay_path = replay_path
    if log_path is not None:
        render.log_path = log_path
    if renderer is not None:
        render.renderer = renderer

    render.updated_at = datetime.now(tz=UTC)

    session.add(render)
    await _commit_and_refresh(session, render)
    return render
