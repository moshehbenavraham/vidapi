from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core.config import Settings


@dataclass(frozen=True)
class QueueAdmissionResult:
    """Successful queue admission check details."""

    checked: bool
    depth: int | None
    max_depth: int


class QueueAdmissionUnavailableError(Exception):
    """Raised when queue depth cannot be checked with bounded Redis calls."""


class QueueSaturatedError(Exception):
    """Raised when the render queue is at or above configured capacity."""

    def __init__(self, *, depth: int, max_depth: int, retry_after: int) -> None:
        self.depth = depth
        self.max_depth = max_depth
        self.retry_after = retry_after
        super().__init__("Render queue is at capacity.")


async def admit_render_queue(
    *,
    settings: Settings,
    arq_pool: Any,
) -> QueueAdmissionResult:
    """Check async queue capacity before a render job is persisted or enqueued."""
    if settings.render_mode != "async":
        return QueueAdmissionResult(
            checked=False,
            depth=None,
            max_depth=settings.max_async_queue_depth,
        )

    try:
        depth = await asyncio.wait_for(
            _get_queue_depth(arq_pool, settings.redis_queue_name),
            timeout=settings.queue_admission_timeout_seconds,
        )
    except (
        AttributeError,
        OSError,
        RedisConnectionError,
        RedisError,
        RedisTimeoutError,
        TypeError,
        TimeoutError,
    ) as exc:
        raise QueueAdmissionUnavailableError(
            "Render queue capacity check failed."
        ) from exc

    max_depth = settings.max_async_queue_depth
    if depth >= max_depth:
        raise QueueSaturatedError(
            depth=depth,
            max_depth=max_depth,
            retry_after=settings.queue_retry_after_seconds,
        )

    return QueueAdmissionResult(checked=True, depth=depth, max_depth=max_depth)


async def _get_queue_depth(arq_pool: Any, queue_name: str) -> int:
    llen = getattr(arq_pool, "llen", None)
    if callable(llen):
        return int(await llen(queue_name))

    redis = getattr(arq_pool, "redis", None)
    if redis is not None:
        redis_llen = getattr(redis, "llen", None)
        if callable(redis_llen):
            return int(await redis_llen(queue_name))

    raise AttributeError("ARQ pool does not expose Redis LLEN")
