from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.db.webhook_models import WebhookAttempt


async def _commit_and_refresh(session: AsyncSession, *instances: object) -> None:
    try:
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        raise

    for instance in instances:
        await session.refresh(instance)


async def create_attempt(
    session: AsyncSession,
    *,
    render_id: str,
    event: str,
    url: str,
    attempt_number: int,
    scheduled_at: datetime | None = None,
) -> WebhookAttempt:
    """Persist a new webhook attempt record before delivery."""
    attempt = WebhookAttempt(
        render_id=render_id,
        event=event,
        url=url,
        attempt_number=attempt_number,
        scheduled_at=scheduled_at or datetime.now(tz=UTC),
    )
    session.add(attempt)
    await _commit_and_refresh(session, attempt)
    return attempt


async def update_attempt_result(
    session: AsyncSession,
    attempt_id: int,
    *,
    status_code: int | None = None,
    response_body_excerpt: str | None = None,
    error: str | None = None,
) -> WebhookAttempt | None:
    """Update a webhook attempt with delivery result."""
    result = await session.execute(
        select(WebhookAttempt).where(WebhookAttempt.id == attempt_id)
    )
    attempt = result.scalar_one_or_none()
    if attempt is None:
        return None

    now = datetime.now(tz=UTC)
    attempt.delivered_at = now
    attempt.updated_at = now

    if status_code is not None:
        attempt.status_code = status_code
    if response_body_excerpt is not None:
        attempt.response_body_excerpt = response_body_excerpt[:500]
    if error is not None:
        attempt.error = error[:500]

    session.add(attempt)
    await _commit_and_refresh(session, attempt)
    return attempt


async def list_attempts_by_render_id(
    session: AsyncSession,
    render_id: str,
) -> list[WebhookAttempt]:
    """Return all webhook attempts for a given render, ordered by created_at."""
    result = await session.execute(
        select(WebhookAttempt)
        .where(WebhookAttempt.render_id == render_id)
        .order_by(col(WebhookAttempt.created_at).asc())
    )
    return list(result.scalars().all())
