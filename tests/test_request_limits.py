from __future__ import annotations

import json

import pytest
from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.request_limits import RequestBodyLimitMiddleware


async def _inner_app(scope: Scope, receive: Receive, send: Send) -> None:
    body = b""
    while True:
        message = await receive()
        body += message.get("body", b"")
        if not message.get("more_body", False):
            break
    response = JSONResponse({"size": len(body)})
    await response(scope, receive, send)


async def _run_request(
    *,
    settings: Settings,
    headers: list[tuple[bytes, bytes]],
    messages: list[Message],
) -> list[Message]:
    middleware = RequestBodyLimitMiddleware(
        _inner_app,
        settings_provider=lambda: settings,
    )
    scope: Scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": "/v1/renders",
        "headers": headers,
    }
    sent: list[Message] = []
    receive_index = 0

    async def receive() -> Message:
        nonlocal receive_index
        if receive_index < len(messages):
            message = messages[receive_index]
            receive_index += 1
            return message
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    await middleware(scope, receive, send)
    return sent


def _status(sent: list[Message]) -> int:
    start = next(
        message for message in sent if message["type"] == "http.response.start"
    )
    return int(start["status"])


def _body(sent: list[Message]) -> dict:
    body = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    return json.loads(body)


@pytest.mark.asyncio
async def test_content_length_over_limit_returns_413() -> None:
    sent = await _run_request(
        settings=Settings(max_render_request_body_bytes=8),
        headers=[(b"content-length", b"9")],
        messages=[{"type": "http.request", "body": b"", "more_body": False}],
    )

    assert _status(sent) == 413
    assert _body(sent)["error"]["code"] == "REQUEST_BODY_TOO_LARGE"


@pytest.mark.asyncio
async def test_streamed_body_over_limit_returns_413() -> None:
    sent = await _run_request(
        settings=Settings(max_render_request_body_bytes=5),
        headers=[],
        messages=[
            {"type": "http.request", "body": b"abc", "more_body": True},
            {"type": "http.request", "body": b"def", "more_body": False},
        ],
    )

    assert _status(sent) == 413
    payload = _body(sent)
    assert payload["error"]["context"]["limit"] == 5
    assert payload["error"]["context"]["observed"] == 6


@pytest.mark.asyncio
async def test_body_within_limit_is_replayed_to_route() -> None:
    sent = await _run_request(
        settings=Settings(max_render_request_body_bytes=20),
        headers=[],
        messages=[
            {"type": "http.request", "body": b"abc", "more_body": True},
            {"type": "http.request", "body": b"def", "more_body": False},
        ],
    )

    assert _status(sent) == 200
    assert _body(sent) == {"size": 6}
