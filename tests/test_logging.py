from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

import app.main as main_module
from app.core.logging import (
    REDACTED_LOG_VALUE,
    redact_log_fields,
    safe_log_excerpt,
)


class FakeLogger:
    def __init__(self) -> None:
        self.info_records: list[tuple[str, dict]] = []
        self.exception_records: list[tuple[str, dict]] = []

    async def ainfo(self, event: str, **fields) -> None:
        self.info_records.append((event, fields))

    async def aexception(self, event: str, **fields) -> None:
        self.exception_records.append((event, fields))


@pytest.mark.asyncio
async def test_request_id_header_and_completion_log_fields(monkeypatch) -> None:
    fake_logger = FakeLogger()
    monkeypatch.setattr(main_module, "logger", fake_logger)
    app = main_module.create_app()

    @app.get("/ok")
    async def ok() -> dict[str, bool]:
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/ok",
            headers={
                "X-Request-ID": "req-ops-123",
                "X-API-Key": "secret-value",
            },
        )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-ops-123"
    assert fake_logger.info_records[-1][0] == "request_completed"
    fields = fake_logger.info_records[-1][1]
    assert fields["request_id"] == "req-ops-123"
    assert fields["method"] == "GET"
    assert fields["path"] == "/ok"
    assert fields["status_code"] == 200
    assert fields["duration_ms"] >= 0
    assert "secret-value" not in str(fields)


@pytest.mark.asyncio
async def test_request_exception_path_logs_request_id(monkeypatch) -> None:
    fake_logger = FakeLogger()
    monkeypatch.setattr(main_module, "logger", fake_logger)
    app = main_module.create_app()

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with pytest.raises(RuntimeError):
            await client.get("/boom", headers={"X-Request-ID": "req-boom"})

    assert fake_logger.exception_records[-1][0] == "request_failed"
    fields = fake_logger.exception_records[-1][1]
    assert fields["request_id"] == "req-boom"
    assert fields["method"] == "GET"
    assert fields["path"] == "/boom"
    assert fields["status_code"] == 500
    assert fields["duration_ms"] >= 0


def test_redaction_helpers_exclude_sensitive_fields() -> None:
    redacted = redact_log_fields(
        {
            "api_key": "secret",
            "callback_url": "https://example.com/hook?token=secret",
            "composition": {"raw": "body"},
            "safe": "visible",
        }
    )

    assert redacted["api_key"] == REDACTED_LOG_VALUE
    assert redacted["callback_url"] == REDACTED_LOG_VALUE
    assert redacted["composition"] == REDACTED_LOG_VALUE
    assert redacted["safe"] == "visible"
    assert safe_log_excerpt("x" * 600) == "x" * 500
