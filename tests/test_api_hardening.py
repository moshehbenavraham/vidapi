from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import Settings


@pytest.mark.asyncio
async def test_render_create_rate_limit_returns_retry_after(
    client: AsyncClient,
    sample_composition: dict,
) -> None:
    headers = {"X-Forwarded-For": "203.0.113.10"}

    for _ in range(10):
        response = await client.post(
            "/v1/renders",
            json=sample_composition,
            headers=headers,
        )
        assert response.status_code == 202

    limited = await client.post(
        "/v1/renders",
        json=sample_composition,
        headers=headers,
    )

    assert limited.status_code == 429
    assert limited.headers["Retry-After"].isdigit()
    body = limited.json()
    assert body["detail"] == "Rate limit exceeded"
    assert body["retry_after"] >= 1
    assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert body["error"]["context"]["retry_after"] == body["retry_after"]

    health = await client.get("/v1/health", headers=headers)
    assert health.status_code == 200


def test_production_cors_wildcard_rejected() -> None:
    with pytest.raises(ValueError, match="Wildcard CORS"):
        Settings(cors_origins=["*"], debug=False)


def test_debug_cors_wildcard_allowed() -> None:
    settings = Settings(cors_origins=["*"], debug=True)
    assert settings.cors_origins == ["*"]


@pytest.mark.asyncio
async def test_openapi_documents_phase_02_error_metadata(
    client: AsyncClient,
) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    render_create = schema["paths"]["/v1/renders"]["post"]["responses"]
    assert "422" in render_create
    assert "429" in render_create
    assert "503" in render_create

    render_download = schema["paths"]["/v1/renders/{render_id}/download"]["get"][
        "responses"
    ]
    assert "404" in render_download

    template_render = schema["paths"]["/v1/templates/{template_id}/renders"]["post"][
        "responses"
    ]
    assert "404" in template_render
    assert "409" in template_render
    assert "422" in template_render
    assert "503" in template_render
