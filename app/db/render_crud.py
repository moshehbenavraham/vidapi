from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.db.models import Render
from app.models.render import RenderStatus


async def create_render(
    session: AsyncSession,
    *,
    template_id: str | None = None,
    template_version_id: str | None = None,
) -> Render:
    """Create a new render record in QUEUED status."""
    render = Render(
        template_id=template_id,
        template_version_id=template_version_id,
    )
    session.add(render)
    await session.commit()
    await session.refresh(render)
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
    await session.commit()
    await session.refresh(render)
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
    await session.commit()
    await session.refresh(render)
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
    await session.commit()
    await session.refresh(render)
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
    await session.commit()
    await session.refresh(render)
    return render
