from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.api.deps import (
    get_arq_pool_dep,
    get_asset_service,
    get_editly_renderer,
    get_render_service,
    get_session,
    get_storage_backend,
    get_storage_url_resolver,
    get_template_service,
)
from app.core.config import Settings, get_settings
from app.db import render_crud
from app.main import create_app
from app.services.template_service import TemplateService


@asynccontextmanager
async def _client_with_settings(
    *,
    settings_holder: dict[str, Settings],
    db_engine,
    test_storage,
    test_url_resolver,
    mock_asset_service,
    mock_renderer,
    render_service,
    arq_pool=None,
) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _override_session():
        async with SQLModelAsyncSession(db_engine) as session:
            yield session

    app.dependency_overrides[get_settings] = lambda: settings_holder["settings"]
    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_storage_backend] = lambda: test_storage
    app.dependency_overrides[get_storage_url_resolver] = lambda: test_url_resolver
    app.dependency_overrides[get_asset_service] = lambda: mock_asset_service
    app.dependency_overrides[get_editly_renderer] = lambda: mock_renderer
    app.dependency_overrides[get_render_service] = lambda: render_service
    app.dependency_overrides[get_arq_pool_dep] = lambda: arq_pool
    app.dependency_overrides[get_template_service] = lambda: TemplateService()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


async def _render_count(db_session) -> int:
    _items, total = await render_crud.list_renders(db_session)
    return total


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


@pytest.mark.asyncio
async def test_untrusted_host_is_rejected(client: AsyncClient) -> None:
    response = await client.get(
        "/v1/health",
        headers={"host": "evil.example.com"},
    )

    assert response.status_code == 400
    assert response.text == "Invalid host header"


def test_production_cors_wildcard_rejected() -> None:
    with pytest.raises(ValueError, match="Wildcard CORS"):
        Settings(cors_origins=["*"], debug=False)


def test_production_allowed_hosts_wildcard_rejected() -> None:
    with pytest.raises(ValueError, match="Wildcard allowed_hosts"):
        Settings(allowed_hosts=["*"], debug=False)


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


@pytest.mark.asyncio
async def test_over_limit_direct_render_returns_422_without_record(
    db_engine,
    db_session,
    test_storage,
    test_url_resolver,
    mock_asset_service,
    mock_renderer,
    render_service,
    sample_composition: dict,
) -> None:
    settings_holder = {"settings": Settings(max_render_duration_seconds=1)}

    async with _client_with_settings(
        settings_holder=settings_holder,
        db_engine=db_engine,
        test_storage=test_storage,
        test_url_resolver=test_url_resolver,
        mock_asset_service=mock_asset_service,
        mock_renderer=mock_renderer,
        render_service=render_service,
    ) as ac:
        response = await ac.post("/v1/renders", json=sample_composition)

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "COMPOSITION_LIMIT_EXCEEDED"
    assert body["error"]["context"]["field"] == "timeline.duration"
    assert await _render_count(db_session) == 0


@pytest.mark.asyncio
async def test_direct_render_queue_saturation_returns_429_without_record(
    db_engine,
    db_session,
    test_storage,
    test_url_resolver,
    mock_asset_service,
    mock_renderer,
    render_service,
    sample_composition: dict,
) -> None:
    arq_pool = AsyncMock()
    arq_pool.llen = AsyncMock(return_value=0)
    arq_pool.enqueue_job = AsyncMock()
    settings_holder = {
        "settings": Settings(
            render_mode="async",
            max_async_queue_depth=0,
            queue_retry_after_seconds=7,
        )
    }

    async with _client_with_settings(
        settings_holder=settings_holder,
        db_engine=db_engine,
        test_storage=test_storage,
        test_url_resolver=test_url_resolver,
        mock_asset_service=mock_asset_service,
        mock_renderer=mock_renderer,
        render_service=render_service,
        arq_pool=arq_pool,
    ) as ac:
        response = await ac.post("/v1/renders", json=sample_composition)

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "7"
    assert response.json()["error"]["code"] == "QUEUE_SATURATED"
    arq_pool.enqueue_job.assert_not_called()
    assert await _render_count(db_session) == 0


@pytest.mark.asyncio
async def test_template_create_limit_returns_422(
    db_engine,
    test_storage,
    test_url_resolver,
    mock_asset_service,
    mock_renderer,
    render_service,
    sample_composition: dict,
) -> None:
    settings_holder = {"settings": Settings(max_tracks_per_render=1)}

    async with _client_with_settings(
        settings_holder=settings_holder,
        db_engine=db_engine,
        test_storage=test_storage,
        test_url_resolver=test_url_resolver,
        mock_asset_service=mock_asset_service,
        mock_renderer=mock_renderer,
        render_service=render_service,
    ) as ac:
        response = await ac.post(
            "/v1/templates",
            json={"name": "Too many tracks", "composition": sample_composition},
        )

    assert response.status_code == 422
    assert response.json()["error"]["context"]["field"] == "timeline.tracks"


@pytest.mark.asyncio
async def test_template_render_limit_runs_after_expansion_without_record(
    db_engine,
    db_session,
    test_storage,
    test_url_resolver,
    mock_asset_service,
    mock_renderer,
    render_service,
    sample_composition: dict,
) -> None:
    settings_holder = {"settings": Settings(max_render_duration_seconds=10)}

    async with _client_with_settings(
        settings_holder=settings_holder,
        db_engine=db_engine,
        test_storage=test_storage,
        test_url_resolver=test_url_resolver,
        mock_asset_service=mock_asset_service,
        mock_renderer=mock_renderer,
        render_service=render_service,
    ) as ac:
        create_response = await ac.post(
            "/v1/templates",
            json={"name": "Render limited", "composition": sample_composition},
        )
        assert create_response.status_code == 201
        template_id = create_response.json()["id"]

        settings_holder["settings"] = Settings(max_render_duration_seconds=1)
        render_response = await ac.post(
            f"/v1/templates/{template_id}/renders",
            json={"merge": {}},
        )

    assert render_response.status_code == 422
    assert render_response.json()["error"]["context"]["field"] == "timeline.duration"
    assert await _render_count(db_session) == 0
