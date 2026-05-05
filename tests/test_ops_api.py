from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.db import render_crud, webhook_crud
from app.models.render import RenderStatus

INVALID_API_KEY = "invalid-ops-key"


async def _mark_failed(session, render_id: str) -> None:
    await render_crud.update_render_status(session, render_id, RenderStatus.FETCHING)
    await render_crud.update_render_status(
        session,
        render_id,
        RenderStatus.FAILED,
        error_code="RENDER_ERROR",
        error_message="ffmpeg failed " + ("x" * 400),
        stage="failed",
    )


@pytest.mark.asyncio
async def test_ops_routes_require_api_key(
    auth_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    missing_response = await auth_client.get("/v1/ops/renders")
    invalid_response = await auth_client.get(
        "/v1/ops/renders",
        headers={"X-API-Key": INVALID_API_KEY},
    )
    valid_response = await auth_client.get("/v1/ops/renders", headers=auth_headers)

    assert missing_response.status_code == 401
    assert invalid_response.status_code == 403
    assert valid_response.status_code == 200
    assert INVALID_API_KEY not in invalid_response.text


@pytest.mark.asyncio
async def test_ops_renders_pagination_filter_and_status_counts(
    auth_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
) -> None:
    failed = await render_crud.create_render(db_session)
    failed_id = failed.id
    queued = await render_crud.create_render(db_session)
    queued_id = queued.id
    await _mark_failed(db_session, failed_id)

    list_response = await auth_client.get(
        "/v1/ops/renders?status_filter=failed&offset=-10&limit=500",
        headers=auth_headers,
    )
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["offset"] == 0
    assert list_body["limit"] == 100
    assert list_body["total"] == 1
    assert list_body["items"][0]["id"] == failed_id
    assert list_body["items"][0]["status"] == "failed"

    invalid_status = await auth_client.get(
        "/v1/ops/renders?status_filter=bogus",
        headers=auth_headers,
    )
    assert invalid_status.status_code == 422

    counts_response = await auth_client.get(
        "/v1/ops/renders/status-counts",
        headers=auth_headers,
    )
    assert counts_response.status_code == 200
    counts = {
        item["status"]: item["count"] for item in counts_response.json()["counts"]
    }
    assert counts["failed"] == 1
    assert counts["queued"] == 1
    assert queued_id is not None


@pytest.mark.asyncio
async def test_ops_failures_are_redacted_and_bounded(
    auth_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
) -> None:
    render = await render_crud.create_render(
        db_session,
        callback_url="https://example.com/hook?token=secret-token",
    )
    render_id = render.id
    await render_crud.update_render_paths(
        db_session,
        render_id,
        input_path="s3://bucket/render/input.json",
        replay_path="s3://bucket/render/replay.json",
        log_path="s3://bucket/render/logs.txt",
        renderer="editly",
    )
    await _mark_failed(db_session, render_id)

    response = await auth_client.get(
        "/v1/ops/renders/failures",
        headers=auth_headers,
    )
    assert response.status_code == 200
    body_text = response.text
    assert "secret-token" not in body_text
    assert "s3://bucket" not in body_text

    item = response.json()["items"][0]
    assert item["id"] == render_id
    assert item["renderer"] == "editly"
    assert item["replay_available"] is True
    assert item["log_available"] is True
    assert len(item["error_message_excerpt"]) == 300

    renderer_counts = await auth_client.get(
        "/v1/ops/renders/renderer-failures",
        headers=auth_headers,
    )
    assert renderer_counts.status_code == 200
    assert renderer_counts.json()["counts"][0] == {
        "renderer": "editly",
        "error_code": "RENDER_ERROR",
        "count": 1,
    }


@pytest.mark.asyncio
async def test_ops_webhook_attempts_and_outcomes_are_redacted(
    auth_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
) -> None:
    attempt = await webhook_crud.create_attempt(
        db_session,
        render_id="render_webhook",
        event="render.failed",
        url="https://example.com/hook?token=webhook-secret",
        attempt_number=1,
    )
    assert attempt.id is not None
    await webhook_crud.update_attempt_result(
        db_session,
        attempt.id,
        status_code=500,
        response_body_excerpt="receiver failed " + ("y" * 400),
        error="connection secret detail " + ("z" * 400),
    )

    attempts_response = await auth_client.get(
        "/v1/ops/webhooks?render_id=render_webhook&failures_only=true",
        headers=auth_headers,
    )
    assert attempts_response.status_code == 200
    assert "webhook-secret" not in attempts_response.text
    item = attempts_response.json()["items"][0]
    assert item["render_id"] == "render_webhook"
    assert item["webhook_event"] == "render.failed"
    assert item["success"] is False
    assert item["status_code"] == 500
    assert len(item["error_excerpt"]) == 300
    assert len(item["response_body_excerpt"]) == 300

    outcomes_response = await auth_client.get(
        "/v1/ops/webhooks/outcome-counts",
        headers=auth_headers,
    )
    assert outcomes_response.status_code == 200
    assert outcomes_response.json()["counts"] == [
        {"webhook_event": "render.failed", "outcome": "failure", "count": 1}
    ]


@pytest.mark.asyncio
async def test_openapi_documents_ops_security_and_health_remains_public(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    assert {"APIKeyAuth": []} in schema["paths"]["/v1/ops/renders"]["get"]["security"]
    assert {"APIKeyAuth": []} in schema["paths"]["/v1/ops/metrics"]["get"]["security"]
    assert "security" not in schema["paths"]["/v1/health"]["get"]
