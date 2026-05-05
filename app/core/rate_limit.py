from __future__ import annotations

import asyncio
import ipaddress
import time
from collections import defaultdict
from dataclasses import dataclass, field

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings

_EXEMPT_PATHS = {"/health", "/v1/health"}
_MAX_CLIENT_KEY_LENGTH = 128
_MAX_FORWARDED_FOR_LENGTH = 512


def _parse_rate(rate_str: str) -> tuple[int, int]:
    """Parse rate string like '60/minute' into (count, window_seconds)."""
    count_str, period = rate_str.split("/")
    count = int(count_str)
    period = period.rstrip("s")
    windows = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
    return count, windows[period]


@dataclass
class _Bucket:
    tokens: list[float] = field(default_factory=list)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        settings = get_settings()
        self._default_max, self._default_window = _parse_rate(
            settings.rate_limit_default
        )
        self._render_max, self._render_window = _parse_rate(
            settings.rate_limit_render_create
        )
        self._buckets: dict[str, _Bucket] = defaultdict(_Bucket)
        self._lock = asyncio.Lock()

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            forwarded = forwarded[:_MAX_FORWARDED_FOR_LENGTH]
            candidate = forwarded.split(",", 1)[0].strip()
        else:
            candidate = request.client.host if request.client else "unknown"

        if not candidate or len(candidate) > _MAX_CLIENT_KEY_LENGTH:
            return "unknown"

        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            return "unknown"

    def _is_rate_limited(
        self, key: str, max_requests: int, window: int
    ) -> tuple[bool, int]:
        """Check if key exceeds rate limit. Returns (limited, retry_after)."""
        now = time.time()
        bucket = self._buckets[key]
        bucket.tokens = [t for t in bucket.tokens if now - t < window]

        if len(bucket.tokens) >= max_requests:
            oldest = bucket.tokens[0]
            retry_after = int(window - (now - oldest)) + 1
            return True, retry_after

        bucket.tokens.append(now)
        return False, 0

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        if path.rstrip("/") in _EXEMPT_PATHS:
            return await call_next(request)

        client_ip = self._get_client_ip(request)

        is_render_create = request.method == "POST" and path.rstrip("/") in (
            "/v1/renders",
            "/renders",
        )

        if is_render_create:
            key = f"render:{client_ip}"
            async with self._lock:
                limited, retry_after = self._is_rate_limited(
                    key, self._render_max, self._render_window
                )
        else:
            key = f"default:{client_ip}"
            async with self._lock:
                limited, retry_after = self._is_rate_limited(
                    key, self._default_max, self._default_window
                )

        if limited:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after": retry_after,
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Rate limit exceeded",
                        "context": {"retry_after": retry_after},
                    },
                },
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        return response
