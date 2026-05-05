from __future__ import annotations

from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.db import render_crud
from app.models.composition import Composition
from app.services.output_postprocess import FinishedOutput
from app.services.render_service import RenderService


async def _render_count(db_session) -> int:
    _items, total = await render_crud.list_renders(db_session)
    return total


@pytest.mark.asyncio
async def test_direct_render_without_renderer_persists_editly(
    client: AsyncClient,
    db_session,
    sample_composition: dict,
) -> None:
    response = await client.post("/v1/renders", json=sample_composition)

    assert response.status_code == 202
    render = await render_crud.get_render_by_id(db_session, response.json()["id"])
    assert render is not None
    assert render.renderer == "editly"


@pytest.mark.asyncio
async def test_direct_render_with_explicit_editly_persists_editly(
    client: AsyncClient,
    db_session,
    sample_composition: dict,
) -> None:
    payload = deepcopy(sample_composition)
    payload["renderer"] = "editly"

    response = await client.post("/v1/renders", json=payload)

    assert response.status_code == 202
    render = await render_crud.get_render_by_id(db_session, response.json()["id"])
    assert render is not None
    assert render.renderer == "editly"


@pytest.mark.asyncio
async def test_direct_render_rejects_unknown_renderer_without_record(
    client: AsyncClient,
    db_session,
    sample_composition: dict,
) -> None:
    payload = deepcopy(sample_composition)
    payload["renderer"] = "not-a-renderer"

    response = await client.post("/v1/renders", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "UNSUPPORTED_RENDERER"
    assert body["error"]["context"]["renderer"] == "not-a-renderer"
    assert await _render_count(db_session) == 0


@pytest.mark.asyncio
async def test_direct_render_accepts_supported_webm_output(
    client: AsyncClient,
    db_session,
    mock_renderer,
    sample_composition: dict,
) -> None:
    payload = deepcopy(sample_composition)
    payload["output"]["format"] = "webm"

    response = await client.post("/v1/renders", json=payload)

    assert response.status_code == 202
    body = response.json()
    assert body["id"]

    render = await render_crud.get_render_by_id(db_session, body["id"])
    assert render is not None
    assert render.renderer == "editly"
    mock_renderer.compile.assert_awaited_once()


@pytest.mark.asyncio
async def test_render_service_finishes_supported_gif_output(
    db_session,
    test_storage,
    mock_asset_service,
    mock_renderer,
    sample_composition: dict,
) -> None:
    payload = deepcopy(sample_composition)
    payload["output"]["format"] = "gif"
    composition = Composition.model_validate(payload)

    render = await render_crud.create_render(db_session)
    mock_postprocessor = MagicMock()
    mock_postprocessor.finish = AsyncMock(
        return_value=FinishedOutput(
            output_path=mock_renderer.render.return_value.output_path,
            media_type="image/gif",
            filename="render_test.gif",
            suffix=".gif",
            log_path=mock_renderer.render.return_value.log_path,
        )
    )
    render_service = RenderService(
        storage=test_storage,
        asset_service=mock_asset_service,
        renderer=mock_renderer,
        output_postprocessor=mock_postprocessor,
    )

    workspace = await test_storage.create_workspace(render.id)
    expanded = await render_service.stage_validate_and_expand(
        composition, render.id, workspace, db_session
    )
    compiled = await render_service.stage_resolve_and_compile(
        expanded, render.id, workspace, db_session
    )
    await render_service.stage_render_and_store(
        expanded, compiled, render.id, workspace, db_session
    )

    stored = await render_crud.get_render_by_id(db_session, render.id)
    assert stored is not None
    assert stored.output_format == "gif"
    assert stored.output_media_type == "image/gif"
    assert stored.output_filename == "render_test.gif"
    mock_renderer.compile.assert_awaited_once()
    mock_postprocessor.finish.assert_awaited_once()


@pytest.mark.asyncio
async def test_render_service_resolves_explicit_editly(
    db_session,
    render_service: RenderService,
    mock_renderer,
    sample_composition: dict,
) -> None:
    payload = deepcopy(sample_composition)
    payload["renderer"] = "editly"
    composition = Composition.model_validate(payload)

    render = await render_service.execute_render(composition, db_session)

    assert render.renderer == "editly"
    assert isinstance(mock_renderer.compile, AsyncMock)
    mock_renderer.compile.assert_awaited_once()
