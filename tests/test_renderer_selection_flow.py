from __future__ import annotations

from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.db import render_crud
from app.models.composition import Composition
from app.renderers.base import CompiledRender, RenderArtifact
from app.services.output_postprocess import FinishedOutput
from app.services.render_service import RenderService


def _mock_protocol_renderer(name: str, tmp_path) -> MagicMock:
    workspace = tmp_path / f"{name}-workspace"
    workspace.mkdir(exist_ok=True)
    spec_path = workspace / f"compiled.{name}.json"
    spec_path.write_text("{}", encoding="ascii")
    replay_path = workspace / "replay.json"
    replay_path.write_text("{}", encoding="ascii")
    output_path = workspace / f"{name}.mp4"
    output_path.write_bytes(b"video")
    log_path = workspace / "render.log"
    log_path.write_text("OK", encoding="utf-8")

    renderer = MagicMock()
    renderer.name = name
    renderer.compile = AsyncMock(
        return_value=CompiledRender(
            spec_path=spec_path,
            replay_path=replay_path,
            workspace=workspace,
            renderer_name=name,
            spec_json="{}",
        )
    )
    renderer.render = AsyncMock(
        return_value=RenderArtifact(
            output_path=output_path,
            poster_path=None,
            log_path=log_path,
            duration_seconds=1.0,
            exit_code=0,
        )
    )
    return renderer


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
    assert render.status == "succeeded"
    assert render.stage == "complete"
    assert render.progress == 100
    assert isinstance(mock_renderer.compile, AsyncMock)
    mock_renderer.compile.assert_awaited_once()


@pytest.mark.asyncio
async def test_direct_render_with_explicit_native_persists_native(
    client: AsyncClient,
    db_session,
    render_service: RenderService,
    tmp_path,
) -> None:
    workspace = tmp_path / "native"
    workspace.mkdir()
    spec_path = workspace / "compiled.ffmpeg.json"
    spec_path.write_text("{}", encoding="ascii")
    replay_path = workspace / "replay.json"
    replay_path.write_text("{}", encoding="ascii")
    output_path = workspace / "native.mp4"
    output_path.write_bytes(b"video")
    log_path = workspace / "render.log"
    log_path.write_text("OK", encoding="utf-8")

    native_renderer = MagicMock()
    native_renderer.name = "ffmpeg-native"
    native_renderer.compile = AsyncMock(
        return_value=CompiledRender(
            spec_path=spec_path,
            replay_path=replay_path,
            workspace=workspace,
            renderer_name="ffmpeg-native",
            spec_json="{}",
        )
    )
    native_renderer.render = AsyncMock(
        return_value=RenderArtifact(
            output_path=output_path,
            poster_path=None,
            log_path=log_path,
            duration_seconds=1.0,
            exit_code=0,
        )
    )
    render_service._renderer_resolver = lambda name=None: native_renderer

    payload = {
        "renderer": "ffmpeg-native",
        "timeline": {
            "background": "#000000",
            "tracks": [
                {
                    "clips": [
                        {
                            "asset": {"type": "color", "color": "#000000"},
                            "length": 1.0,
                        }
                    ]
                }
            ],
        },
        "output": {"format": "mp4", "width": 320, "height": 180, "fps": 24},
    }

    response = await client.post("/v1/renders", json=payload)

    assert response.status_code == 202
    render = await render_crud.get_render_by_id(db_session, response.json()["id"])
    assert render is not None
    assert render.renderer == "ffmpeg-native"
    assert render.status == "succeeded"
    assert render.stage == "complete"
    assert render.progress == 100
    native_renderer.compile.assert_awaited_once()
    native_renderer.render.assert_awaited_once()


@pytest.mark.asyncio
async def test_direct_render_with_auto_html_persists_hyperframes(
    client: AsyncClient,
    db_session,
    render_service: RenderService,
    mock_renderer,
    tmp_path,
) -> None:
    hyperframes_renderer = _mock_protocol_renderer("hyperframes", tmp_path)

    def _resolve(name=None):
        return hyperframes_renderer if name == "hyperframes" else mock_renderer

    render_service._renderer_resolver = _resolve

    payload = {
        "renderer": "auto",
        "timeline": {
            "background": "#000000",
            "tracks": [
                {
                    "clips": [
                        {
                            "asset": {
                                "type": "html",
                                "html": '<div class="title">Hello</div>',
                            },
                            "length": 1.0,
                        }
                    ]
                }
            ],
        },
        "output": {"format": "mp4", "width": 320, "height": 180, "fps": 24},
    }

    response = await client.post("/v1/renders", json=payload)

    assert response.status_code == 202
    render = await render_crud.get_render_by_id(db_session, response.json()["id"])
    assert render is not None
    assert render.renderer == "hyperframes"
    hyperframes_renderer.compile.assert_awaited_once()
    hyperframes_renderer.render.assert_awaited_once()


@pytest.mark.asyncio
async def test_render_service_resolves_explicit_native_for_compile(
    db_session,
    test_storage,
    mock_asset_service,
    tmp_path,
) -> None:
    workspace = tmp_path / "native-compile"
    workspace.mkdir()
    spec_path = workspace / "compiled.ffmpeg.json"
    spec_path.write_text("{}", encoding="ascii")
    replay_path = workspace / "replay.json"
    replay_path.write_text("{}", encoding="ascii")
    native_renderer = MagicMock()
    native_renderer.name = "ffmpeg-native"
    native_renderer.compile = AsyncMock(
        return_value=CompiledRender(
            spec_path=spec_path,
            replay_path=replay_path,
            workspace=workspace,
            renderer_name="ffmpeg-native",
            spec_json="{}",
        )
    )
    editly_renderer = MagicMock()
    editly_renderer.name = "editly"
    service = RenderService(
        storage=test_storage,
        asset_service=mock_asset_service,
        renderer=editly_renderer,
        renderer_resolver=lambda name=None: native_renderer,
    )
    composition = Composition.model_validate(
        {
            "renderer": "ffmpeg-native",
            "timeline": {
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {"type": "color", "color": "#000000"},
                                "length": 1.0,
                            }
                        ]
                    }
                ]
            },
            "output": {"format": "mp4", "width": 320, "height": 180},
        }
    )
    render = await render_crud.create_render(db_session)
    job_workspace = await test_storage.create_workspace(render.id)

    compiled = await service.stage_resolve_and_compile(
        composition,
        render.id,
        job_workspace,
        db_session,
    )

    assert compiled.renderer_name == "ffmpeg-native"
    native_renderer.compile.assert_awaited_once()
    stored = await render_crud.get_render_by_id(db_session, render.id)
    assert stored is not None
    assert stored.renderer == "ffmpeg-native"


@pytest.mark.asyncio
async def test_render_service_resolves_explicit_hyperframes_for_compile(
    db_session,
    test_storage,
    mock_asset_service,
    mock_renderer,
    tmp_path,
) -> None:
    hyperframes_renderer = _mock_protocol_renderer("hyperframes", tmp_path)
    service = RenderService(
        storage=test_storage,
        asset_service=mock_asset_service,
        renderer=mock_renderer,
        renderer_resolver=lambda name=None: hyperframes_renderer,
    )
    composition = Composition.model_validate(
        {
            "renderer": "hyperframes",
            "timeline": {
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "html",
                                    "html": "<div>Hello</div>",
                                },
                                "length": 1.0,
                            }
                        ]
                    }
                ]
            },
            "output": {"format": "mp4", "width": 320, "height": 180},
        }
    )
    render = await render_crud.create_render(db_session)
    job_workspace = await test_storage.create_workspace(render.id)

    compiled = await service.stage_resolve_and_compile(
        composition,
        render.id,
        job_workspace,
        db_session,
    )

    assert compiled.renderer_name == "hyperframes"
    hyperframes_renderer.compile.assert_awaited_once()
    stored = await render_crud.get_render_by_id(db_session, render.id)
    assert stored is not None
    assert stored.renderer == "hyperframes"
