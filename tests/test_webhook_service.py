from __future__ import annotations

import hashlib
import hmac
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.core.config import Settings
from app.db.models import Render
from app.db.webhook_models import WebhookAttempt  # noqa: F401 - registers table
from app.services.webhook_service import (
    build_headers,
    build_storage_aware_webhook_payload,
    build_webhook_payload,
    deliver_with_retries,
    dispatch_webhook,
    sign_payload,
)


class FakeWebhookUrlResolver:
    async def output_url(self, render: Render) -> str | None:
        if render.output_path:
            return "https://cdn.example.com/output.mp4"
        return None

    async def poster_url(self, render: Render) -> str | None:
        if render.poster_path:
            return "https://cdn.example.com/poster.jpg"
        return None


def _make_render(**overrides) -> Render:
    defaults = {
        "id": "render_test123",
        "status": "succeeded",
        "output_path": "/data/renders/render_test123/output.mp4",
        "poster_path": "/data/renders/render_test123/poster.jpg",
        "completed_at": datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return Render(**defaults)


# ---- T015: Payload construction tests ----


class TestBuildWebhookPayload:
    def test_succeeded_payload_structure(self) -> None:
        render = _make_render()
        payload = build_webhook_payload(event="render.succeeded", render=render)

        assert payload["event"] == "render.succeeded"
        assert payload["render_id"] == "render_test123"
        assert payload["status"] == "succeeded"
        assert payload["url"] == "/v1/renders/render_test123/download"
        assert payload["poster"] == "/v1/renders/render_test123/poster"
        assert payload["completed_at"] is not None

    def test_failed_payload_no_output(self) -> None:
        render = _make_render(
            status="failed",
            output_path=None,
            poster_path=None,
        )
        payload = build_webhook_payload(event="render.failed", render=render)

        assert payload["event"] == "render.failed"
        assert payload["url"] is None
        assert payload["poster"] is None

    def test_cancelled_payload(self) -> None:
        render = _make_render(status="cancelled", output_path=None, poster_path=None)
        payload = build_webhook_payload(event="render.cancelled", render=render)

        assert payload["event"] == "render.cancelled"
        assert payload["status"] == "cancelled"

    def test_no_completed_at(self) -> None:
        render = _make_render(completed_at=None)
        payload = build_webhook_payload(event="render.succeeded", render=render)

        assert payload["completed_at"] is None

    @pytest.mark.asyncio
    async def test_storage_aware_payload_uses_resolved_urls(self) -> None:
        render = _make_render()

        payload = await build_storage_aware_webhook_payload(
            event="render.succeeded",
            render=render,
            url_resolver=FakeWebhookUrlResolver(),  # type: ignore[arg-type]
        )

        assert payload["url"] == "https://cdn.example.com/output.mp4"
        assert payload["poster"] == "https://cdn.example.com/poster.jpg"


# ---- T015: HMAC signing tests ----


class TestSignPayload:
    def test_known_signature(self) -> None:
        secret = "test-secret-key"
        payload_bytes = b'{"event":"render.succeeded"}'

        sig, ts = sign_payload(payload_bytes, secret)

        message = f"{ts}.".encode("ascii") + payload_bytes
        expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
        assert sig == expected

    def test_timestamp_is_numeric(self) -> None:
        _, ts = sign_payload(b"test", "secret")
        assert ts.isdigit()

    def test_different_secrets_produce_different_signatures(self) -> None:
        payload = b"same-payload"
        sig1, _ = sign_payload(payload, "secret-a")
        sig2, _ = sign_payload(payload, "secret-b")
        assert sig1 != sig2


class TestBuildHeaders:
    def test_headers_with_secret(self) -> None:
        headers = build_headers(b"payload", "my-secret")

        assert headers["Content-Type"] == "application/json"
        assert "X-VidAPI-Signature" in headers
        assert "X-VidAPI-Timestamp" in headers

    def test_headers_without_secret(self) -> None:
        headers = build_headers(b"payload", None)

        assert headers["Content-Type"] == "application/json"
        assert "X-VidAPI-Signature" not in headers
        assert "X-VidAPI-Timestamp" not in headers

    def test_headers_with_empty_secret(self) -> None:
        headers = build_headers(b"payload", "")

        assert "X-VidAPI-Signature" not in headers


# ---- T016: Delivery and retry tests ----


@pytest.fixture
async def webhook_db():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    @asynccontextmanager
    async def _factory():
        async with SQLModelAsyncSession(engine) as session:
            yield session

    yield _factory
    await engine.dispose()


def _test_settings(**overrides) -> Settings:
    defaults = {
        "webhook_secret": "test-secret",
        "webhook_timeout_seconds": 2,
        "webhook_max_retries": 3,
        "webhook_retry_delays": [0, 0, 0],
    }
    defaults.update(overrides)
    return Settings(**defaults)


class TestDeliverWithRetries:
    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self, webhook_db) -> None:
        transport = httpx.MockTransport(lambda req: httpx.Response(200, text="OK"))
        settings = _test_settings()

        with patch(
            "app.services.webhook_service.httpx.AsyncClient",
            return_value=httpx.AsyncClient(transport=transport),
        ):
            result = await deliver_with_retries(
                url="https://example.com/hook",
                payload_bytes=b'{"event":"render.succeeded"}',
                headers={"Content-Type": "application/json"},
                session_factory=webhook_db,
                render_id="render_abc",
                event="render.succeeded",
                settings=settings,
            )

        assert result is True

    @pytest.mark.asyncio
    async def test_retries_on_500_then_succeeds(self, webhook_db) -> None:
        call_count = 0

        def _handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return httpx.Response(500, text="Internal Server Error")
            return httpx.Response(200, text="OK")

        transport = httpx.MockTransport(_handler)
        settings = _test_settings()

        with patch(
            "app.services.webhook_service.httpx.AsyncClient",
            return_value=httpx.AsyncClient(transport=transport),
        ):
            result = await deliver_with_retries(
                url="https://example.com/hook",
                payload_bytes=b'{"test": true}',
                headers={"Content-Type": "application/json"},
                session_factory=webhook_db,
                render_id="render_retry",
                event="render.failed",
                settings=settings,
            )

        assert result is True
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exhausts_all_retries(self, webhook_db) -> None:
        transport = httpx.MockTransport(lambda req: httpx.Response(500, text="fail"))
        settings = _test_settings()

        with patch(
            "app.services.webhook_service.httpx.AsyncClient",
            return_value=httpx.AsyncClient(transport=transport),
        ):
            result = await deliver_with_retries(
                url="https://example.com/hook",
                payload_bytes=b'{"test": true}',
                headers={"Content-Type": "application/json"},
                session_factory=webhook_db,
                render_id="render_exhaust",
                event="render.failed",
                settings=settings,
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_handles_timeout_exception(self, webhook_db) -> None:
        def _handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out")

        transport = httpx.MockTransport(_handler)
        settings = _test_settings(webhook_max_retries=1)

        with patch(
            "app.services.webhook_service.httpx.AsyncClient",
            return_value=httpx.AsyncClient(transport=transport),
        ):
            result = await deliver_with_retries(
                url="https://example.com/hook",
                payload_bytes=b"{}",
                headers={"Content-Type": "application/json"},
                session_factory=webhook_db,
                render_id="render_timeout",
                event="render.succeeded",
                settings=settings,
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_handles_connect_error(self, webhook_db) -> None:
        def _handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        transport = httpx.MockTransport(_handler)
        settings = _test_settings(webhook_max_retries=1)

        with patch(
            "app.services.webhook_service.httpx.AsyncClient",
            return_value=httpx.AsyncClient(transport=transport),
        ):
            result = await deliver_with_retries(
                url="https://example.com/hook",
                payload_bytes=b"{}",
                headers={"Content-Type": "application/json"},
                session_factory=webhook_db,
                render_id="render_connect",
                event="render.failed",
                settings=settings,
            )

        assert result is False


class TestDispatchWebhook:
    @pytest.mark.asyncio
    async def test_skips_when_no_callback_url(self, webhook_db) -> None:
        render = _make_render(callback_url=None)

        with patch("app.services.webhook_service.render_crud") as mock_crud:
            mock_crud.get_render_by_id = AsyncMock(return_value=render)

            await dispatch_webhook(
                session_factory=webhook_db,
                render_id="render_test123",
                event="render.succeeded",
            )

    @pytest.mark.asyncio
    async def test_skips_when_render_not_found(self, webhook_db) -> None:
        with patch("app.services.webhook_service.render_crud") as mock_crud:
            mock_crud.get_render_by_id = AsyncMock(return_value=None)

            await dispatch_webhook(
                session_factory=webhook_db,
                render_id="nonexistent",
                event="render.succeeded",
            )

    @pytest.mark.asyncio
    async def test_never_raises_on_error(self, webhook_db) -> None:
        with patch("app.services.webhook_service.render_crud") as mock_crud:
            mock_crud.get_render_by_id = AsyncMock(
                side_effect=RuntimeError("DB exploded")
            )

            await dispatch_webhook(
                session_factory=webhook_db,
                render_id="render_err",
                event="render.succeeded",
            )

    @pytest.mark.asyncio
    async def test_delivers_when_callback_url_set(self, webhook_db) -> None:
        render = _make_render(callback_url="https://example.com/hook")

        transport = httpx.MockTransport(lambda req: httpx.Response(200, text="OK"))

        with (
            patch("app.services.webhook_service.render_crud") as mock_crud,
            patch(
                "app.services.webhook_service.httpx.AsyncClient",
                return_value=httpx.AsyncClient(transport=transport),
            ),
            patch(
                "app.services.webhook_service.get_settings",
                return_value=_test_settings(),
            ),
        ):
            mock_crud.get_render_by_id = AsyncMock(return_value=render)

            await dispatch_webhook(
                session_factory=webhook_db,
                render_id="render_test123",
                event="render.succeeded",
            )
