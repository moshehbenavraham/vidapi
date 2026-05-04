from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient) -> None:
    response = await client.get("/v1/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_response_shape(client: AsyncClient) -> None:
    response = await client.get("/v1/health")
    data = response.json()
    assert data["status"] == "ok"
    assert "service" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_health_content_type(client: AsyncClient) -> None:
    response = await client.get("/v1/health")
    assert "application/json" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_health_includes_request_id(client: AsyncClient) -> None:
    response = await client.get("/v1/health")
    assert "x-request-id" in response.headers


@pytest.mark.asyncio
async def test_health_echoes_custom_request_id(client: AsyncClient) -> None:
    custom_id = "test-request-123"
    response = await client.get("/v1/health", headers={"X-Request-ID": custom_id})
    assert response.headers["x-request-id"] == custom_id
