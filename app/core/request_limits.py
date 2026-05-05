from __future__ import annotations

from collections.abc import Callable
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings, get_settings

BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})
REQUEST_TOO_LARGE_CODE = "REQUEST_BODY_TOO_LARGE"


class RequestBodyLimitMiddleware:
    """Reject oversized request bodies before FastAPI parses JSON."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings_provider: Callable[[], Settings] = get_settings,
    ) -> None:
        self._app = app
        self._settings_provider = settings_provider

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        method = str(scope.get("method", "")).upper()
        if method not in BODY_METHODS:
            await self._app(scope, receive, send)
            return

        settings = self._settings_provider()
        limit = _limit_for_path(settings, str(scope.get("path", "")))
        content_length = _content_length(scope)
        if content_length is not None and content_length > limit:
            await _send_request_too_large(
                scope,
                send,
                limit=limit,
                observed=content_length,
            )
            return

        buffered_messages: list[Message] = []
        observed = 0

        while True:
            message = await receive()
            buffered_messages.append(message)

            if message["type"] == "http.disconnect":
                break

            if message["type"] != "http.request":
                continue

            body = message.get("body", b"")
            if isinstance(body, bytes):
                observed += len(body)

            if observed > limit:
                await _send_request_too_large(
                    scope,
                    send,
                    limit=limit,
                    observed=observed,
                )
                return

            if not message.get("more_body", False):
                break

        message_index = 0

        async def replay_receive() -> Message:
            nonlocal message_index
            if message_index < len(buffered_messages):
                message = buffered_messages[message_index]
                message_index += 1
                return message
            return {"type": "http.request", "body": b"", "more_body": False}

        await self._app(scope, replay_receive, send)


def _limit_for_path(settings: Settings, path: str) -> int:
    if path == "/v1/renders":
        return settings.max_render_request_body_bytes
    if path == "/v1/templates" or (
        path.startswith("/v1/templates/") and path.endswith("/renders")
    ):
        return settings.max_template_request_body_bytes
    if path.startswith("/v1/templates/"):
        return settings.max_template_request_body_bytes
    return settings.max_request_body_bytes


def _content_length(scope: Scope) -> int | None:
    for raw_name, raw_value in scope.get("headers", []):
        if raw_name.lower() != b"content-length":
            continue
        try:
            return int(raw_value.decode("ascii"))
        except ValueError:
            return None
    return None


async def _send_request_too_large(
    scope: Scope,
    send: Send,
    *,
    limit: int,
    observed: int,
) -> None:
    response = JSONResponse(
        status_code=413,
        content=request_too_large_payload(limit=limit, observed=observed),
    )
    await response(scope, _empty_receive, send)


async def _empty_receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


def request_too_large_payload(*, limit: int, observed: int) -> dict[str, Any]:
    return {
        "error": {
            "code": REQUEST_TOO_LARGE_CODE,
            "message": "Request body exceeds configured size limit.",
            "context": {
                "field": "body",
                "limit": limit,
                "observed": observed,
            },
        }
    }
