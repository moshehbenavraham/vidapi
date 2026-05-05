from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, case, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.db.webhook_models import WebhookAttempt


@dataclass(frozen=True)
class WebhookOutcomeCount:
    webhook_event: str
    outcome: str
    count: int


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


def _webhook_failure_filter():
    return or_(
        col(WebhookAttempt.error).is_not(None),
        and_(
            col(WebhookAttempt.delivered_at).is_not(None),
            or_(
                col(WebhookAttempt.status_code).is_(None),
                col(WebhookAttempt.status_code) < 200,
                col(WebhookAttempt.status_code) >= 300,
            ),
        ),
    )


async def list_recent_attempts(
    session: AsyncSession,
    *,
    render_id: str | None = None,
    failures_only: bool = False,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[WebhookAttempt], int]:
    """Return bounded webhook attempts ordered newest first."""
    filters = []
    if render_id is not None:
        filters.append(WebhookAttempt.render_id == render_id)
    if failures_only:
        filters.append(_webhook_failure_filter())

    count_stmt = select(func.count()).select_from(WebhookAttempt)
    query = select(WebhookAttempt)
    for where_clause in filters:
        count_stmt = count_stmt.where(where_clause)
        query = query.where(where_clause)

    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()

    result = await session.execute(
        query.order_by(
            col(WebhookAttempt.created_at).desc(),
            col(WebhookAttempt.id).desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all()), total


async def count_webhook_outcomes(
    session: AsyncSession,
    *,
    limit: int = 100,
) -> list[WebhookOutcomeCount]:
    """Return webhook attempt counts grouped by event and outcome."""
    outcome = case(
        (col(WebhookAttempt.delivered_at).is_(None), "pending"),
        (
            and_(
                col(WebhookAttempt.status_code) >= 200,
                col(WebhookAttempt.status_code) < 300,
                col(WebhookAttempt.error).is_(None),
            ),
            "success",
        ),
        else_="failure",
    ).label("outcome")

    result = await session.execute(
        select(WebhookAttempt.event, outcome, func.count())
        .select_from(WebhookAttempt)
        .group_by(WebhookAttempt.event, outcome)
        .order_by(WebhookAttempt.event, outcome)
        .limit(limit)
    )
    return [
        WebhookOutcomeCount(
            webhook_event=str(webhook_event),
            outcome=str(outcome_value),
            count=int(count_value),
        )
        for webhook_event, outcome_value, count_value in result.all()
    ]
