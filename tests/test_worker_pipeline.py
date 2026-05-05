from __future__ import annotations

import json
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.core.config import Settings
from app.db import render_crud
from app.db.session import set_engine
from app.models.composition import CaptionFormat, CaptionMode, Composition, PosterMode
from app.models.error_codes import ErrorCode
from app.models.output_artifacts import StoredCaptionMetadata, StoredPosterMetadata
from app.models.render import RenderStatus
from app.renderers.base import CompiledRender
from app.services.caption_finishing import CaptionFinishingError
from app.services.render_service import RenderService, RenderServiceError
from app.storage.base import ArtifactType
from app.workers.render_worker import run_render
from app.workers.workspace import WorkspaceManager

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def pipeline_db_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    set_engine(engine)
    yield engine
    await engine.dispose()
    set_engine(None)  # type: ignore[arg-type]


@pytest.fixture
def pipeline_session_factory(pipeline_db_engine):
    @asynccontextmanager
    async def _factory():
        async with SQLModelAsyncSession(pipeline_db_engine) as session:
            yield session

    return _factory


@pytest.fixture
def pipeline_workspace(tmp_path: Path) -> WorkspaceManager:
    workspace_root = tmp_path / "renders"
    workspace_root.mkdir()
    return WorkspaceManager(workspace_root=workspace_root)


@pytest.fixture
def sample_composition_dict() -> dict:
    path = FIXTURES_DIR / "sample_composition.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def mock_service(tmp_path: Path) -> RenderService:
    """RenderService mock that succeeds through all stages."""
    service = MagicMock(spec=RenderService)

    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    spec_path = workspace / "compiled.editly.json"
    spec_path.write_text("{}", encoding="utf-8")
    replay_path = workspace / "replay.json"
    replay_path.write_text("{}", encoding="utf-8")
    output_path = workspace / "output.mp4"
    output_path.write_bytes(b"\x00" * 100)
    log_path = workspace / "render.log"
    log_path.write_text("OK", encoding="utf-8")

    async def _stage_validate(composition, render_id, ws, session):
        return composition

    async def _stage_compile(composition, render_id, ws, session):
        return CompiledRender(
            spec_path=spec_path,
            replay_path=replay_path,
            workspace=ws,
            renderer_name="editly",
            spec_json="{}",
        )

    async def _stage_render(composition, compiled, render_id, ws, session, **kwargs):
        pass

    async def _read_artifact_uri(uri):
        return Path(uri).read_bytes()

    async def _publish_artifact_file(render_id, artifact_type, source_path, session):
        if artifact_type is ArtifactType.LOG:
            await render_crud.update_render_paths(
                session,
                render_id,
                log_path=str(source_path),
            )
        return str(source_path)

    service.read_artifact_uri = AsyncMock(side_effect=_read_artifact_uri)
    service.stage_validate_and_expand = AsyncMock(side_effect=_stage_validate)
    service.stage_resolve_and_compile = AsyncMock(side_effect=_stage_compile)
    service.stage_render_and_store = AsyncMock(side_effect=_stage_render)
    service.publish_artifact_file = AsyncMock(side_effect=_publish_artifact_file)
    return service


async def _create_render_with_input(session_factory, workspace_mgr, sample_dict) -> str:
    """Helper: create render record with input.json written to workspace."""
    async with session_factory() as session:
        render = await render_crud.create_render(session)
        render_id = render.id

    ws = await workspace_mgr.create(render_id)
    input_path = ws / "input.json"
    input_path.write_text(json.dumps(sample_dict), encoding="utf-8")

    async with session_factory() as session:
        await render_crud.update_render_paths(
            session, render_id, input_path=str(input_path)
        )
    return render_id


# ---------------------------------------------------------------------------
# Tests: Status transition through all stages
# ---------------------------------------------------------------------------


class TestPipelineTransitions:
    @pytest.mark.asyncio
    async def test_full_pipeline_success(
        self,
        pipeline_db_engine,
        pipeline_session_factory,
        pipeline_workspace,
        mock_service,
        sample_composition_dict,
    ):
        """Full pipeline through all status stages to SUCCEEDED."""
        render_id = await _create_render_with_input(
            pipeline_session_factory, pipeline_workspace, sample_composition_dict
        )

        ctx = {
            "session_factory": pipeline_session_factory,
            "render_service": mock_service,
            "workspace_manager": pipeline_workspace,
        }

        await run_render(ctx, render_id)

        async with pipeline_session_factory() as session:
            render = await render_crud.get_render_by_id(session, render_id)
            assert render is not None
            assert render.status == RenderStatus.SUCCEEDED.value
            assert render.progress == 100
            assert render.started_at is not None
            assert render.completed_at is not None

        mock_service.stage_validate_and_expand.assert_called_once()
        mock_service.stage_resolve_and_compile.assert_called_once()
        mock_service.stage_render_and_store.assert_called_once()

    @pytest.mark.asyncio
    async def test_pipeline_sets_started_at_on_fetching(
        self,
        pipeline_db_engine,
        pipeline_session_factory,
        pipeline_workspace,
        mock_service,
        sample_composition_dict,
    ):
        """started_at is set when transitioning to FETCHING."""
        render_id = await _create_render_with_input(
            pipeline_session_factory, pipeline_workspace, sample_composition_dict
        )

        ctx = {
            "session_factory": pipeline_session_factory,
            "render_service": mock_service,
            "workspace_manager": pipeline_workspace,
        }

        await run_render(ctx, render_id)

        async with pipeline_session_factory() as session:
            render = await render_crud.get_render_by_id(session, render_id)
            assert render is not None
            assert render.started_at is not None

    @pytest.mark.asyncio
    async def test_preflight_reads_input_through_storage_uri(
        self,
        pipeline_db_engine,
        pipeline_session_factory,
        pipeline_workspace,
        mock_service,
        sample_composition_dict,
    ):
        """Worker reads stored composition through render service storage."""
        async with pipeline_session_factory() as session:
            render = await render_crud.create_render(session)
            render_id = render.id
            await render_crud.update_render_paths(
                session,
                render_id,
                input_path="s3://vidapi-renders/renders/render_abc/input.json",
            )

        mock_service.read_artifact_uri = AsyncMock(
            return_value=json.dumps(sample_composition_dict).encode("utf-8")
        )

        ctx = {
            "session_factory": pipeline_session_factory,
            "render_service": mock_service,
            "workspace_manager": pipeline_workspace,
        }

        await run_render(ctx, render_id)

        mock_service.read_artifact_uri.assert_awaited_once_with(
            "s3://vidapi-renders/renders/render_abc/input.json"
        )
        async with pipeline_session_factory() as session:
            render = await render_crud.get_render_by_id(session, render_id)
            assert render is not None
            assert render.status == RenderStatus.SUCCEEDED.value

    @pytest.mark.asyncio
    async def test_explicit_native_renderer_persists_selection_and_progress_plumbing(
        self,
        pipeline_db_engine,
        pipeline_session_factory,
        pipeline_workspace,
        mock_service,
    ):
        """Worker keeps explicit native renderer selection and progress callbacks."""
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
        render_id = await _create_render_with_input(
            pipeline_session_factory,
            pipeline_workspace,
            payload,
        )

        ctx = {
            "session_factory": pipeline_session_factory,
            "render_service": mock_service,
            "workspace_manager": pipeline_workspace,
        }

        await run_render(ctx, render_id)

        async with pipeline_session_factory() as session:
            render = await render_crud.get_render_by_id(session, render_id)
            assert render is not None
            assert render.status == RenderStatus.SUCCEEDED.value
            assert render.renderer == "ffmpeg-native"

        kwargs = mock_service.stage_render_and_store.await_args.kwargs
        assert kwargs["progress_callback"] is not None
        assert kwargs["cancel_check"] is not None


# ---------------------------------------------------------------------------
# Tests: Failure paths with error codes
# ---------------------------------------------------------------------------


class TestPipelineFailures:
    @pytest.mark.asyncio
    async def test_compile_error_marks_failed(
        self,
        pipeline_db_engine,
        pipeline_session_factory,
        pipeline_workspace,
        mock_service,
        sample_composition_dict,
    ):
        """COMPILE_ERROR in stage 2 transitions to FAILED."""
        mock_service.stage_resolve_and_compile = AsyncMock(
            side_effect=RenderServiceError("bad spec", error_code="COMPILE_ERROR")
        )

        render_id = await _create_render_with_input(
            pipeline_session_factory, pipeline_workspace, sample_composition_dict
        )

        ctx = {
            "session_factory": pipeline_session_factory,
            "render_service": mock_service,
            "workspace_manager": pipeline_workspace,
        }

        await run_render(ctx, render_id)

        async with pipeline_session_factory() as session:
            render = await render_crud.get_render_by_id(session, render_id)
            assert render is not None
            assert render.status == RenderStatus.FAILED.value
            assert render.error_code == "COMPILE_ERROR"

    @pytest.mark.asyncio
    async def test_render_error_marks_failed(
        self,
        pipeline_db_engine,
        pipeline_session_factory,
        pipeline_workspace,
        mock_service,
        sample_composition_dict,
    ):
        """RENDER_ERROR in stage 3 transitions to FAILED."""
        mock_service.stage_render_and_store = AsyncMock(
            side_effect=RenderServiceError("ffmpeg died", error_code="RENDER_ERROR")
        )

        render_id = await _create_render_with_input(
            pipeline_session_factory, pipeline_workspace, sample_composition_dict
        )

        ctx = {
            "session_factory": pipeline_session_factory,
            "render_service": mock_service,
            "workspace_manager": pipeline_workspace,
        }

        await run_render(ctx, render_id)

        async with pipeline_session_factory() as session:
            render = await render_crud.get_render_by_id(session, render_id)
            assert render is not None
            assert render.status == RenderStatus.FAILED.value
            assert render.error_code == "RENDER_ERROR"

    @pytest.mark.asyncio
    async def test_timeout_marks_failed(
        self,
        pipeline_db_engine,
        pipeline_session_factory,
        pipeline_workspace,
        mock_service,
        sample_composition_dict,
    ):
        """Timeout during pipeline transitions to FAILED with RENDER_TIMEOUT."""
        import asyncio

        async def _slow(*args, **kwargs):
            await asyncio.sleep(30)

        mock_service.stage_validate_and_expand = AsyncMock(side_effect=_slow)

        render_id = await _create_render_with_input(
            pipeline_session_factory, pipeline_workspace, sample_composition_dict
        )

        ctx = {
            "session_factory": pipeline_session_factory,
            "render_service": mock_service,
            "workspace_manager": pipeline_workspace,
        }

        with patch("app.workers.render_worker.get_settings") as mock_settings:
            settings = Settings(render_timeout_seconds=1)
            mock_settings.return_value = settings
            await run_render(ctx, render_id)

        async with pipeline_session_factory() as session:
            render = await render_crud.get_render_by_id(session, render_id)
            assert render is not None
            assert render.status == RenderStatus.FAILED.value
            assert render.error_code == ErrorCode.RENDER_TIMEOUT.value

    @pytest.mark.asyncio
    async def test_unexpected_error_marks_failed(
        self,
        pipeline_db_engine,
        pipeline_session_factory,
        pipeline_workspace,
        mock_service,
        sample_composition_dict,
    ):
        """Unexpected exception transitions to FAILED with WORKER_UNEXPECTED_ERROR."""
        mock_service.stage_validate_and_expand = AsyncMock(
            side_effect=RuntimeError("something broke")
        )

        render_id = await _create_render_with_input(
            pipeline_session_factory, pipeline_workspace, sample_composition_dict
        )

        ctx = {
            "session_factory": pipeline_session_factory,
            "render_service": mock_service,
            "workspace_manager": pipeline_workspace,
        }

        await run_render(ctx, render_id)

        async with pipeline_session_factory() as session:
            render = await render_crud.get_render_by_id(session, render_id)
            assert render is not None
            assert render.status == RenderStatus.FAILED.value
            assert render.error_code == ErrorCode.WORKER_UNEXPECTED_ERROR.value


class TestRenderStageCaptionPosterMetadata:
    @pytest.mark.asyncio
    async def test_render_stage_persists_caption_sidecar_and_disabled_poster_metadata(
        self,
        db_session,
        test_storage,
        render_service,
    ) -> None:
        render = await render_crud.create_render(db_session)
        render_id = render.id
        workspace = await test_storage.create_workspace(render_id)
        compiled = CompiledRender(
            spec_path=workspace / "compiled.editly.json",
            replay_path=workspace / "replay.json",
            workspace=workspace,
            renderer_name="editly",
            spec_json="{}",
        )
        composition = Composition.model_validate(
            {
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
                "output": {"format": "mp4", "poster": {"mode": "disabled"}},
                "captions": {
                    "mode": "sidecar",
                    "format": "srt",
                    "cues": [
                        {"start": 0.0, "end": 1.0, "text": "Hello"},
                    ],
                },
            }
        )

        await render_service.stage_render_and_store(
            composition,
            compiled,
            render_id,
            workspace,
            db_session,
        )

        stored = await render_crud.get_render_by_id(db_session, render_id)
        assert stored is not None
        assert stored.output_path is not None
        assert stored.caption_mode == CaptionMode.SIDECAR.value
        assert stored.caption_format == CaptionFormat.SRT.value
        assert stored.caption_sidecar_path is not None
        assert stored.caption_sidecar_filename == f"{render_id}-captions.srt"
        assert stored.caption_cue_count == 1
        assert stored.caption_burned_in is False
        assert stored.poster_path is None
        assert stored.poster_mode == PosterMode.DISABLED.value

        sidecar_bytes = await test_storage.read_uri(stored.caption_sidecar_path)
        assert sidecar_bytes.startswith(b"1\n00:00:00,000")

    @pytest.mark.asyncio
    async def test_caption_failure_clears_stale_caption_and_poster_metadata(
        self,
        monkeypatch: pytest.MonkeyPatch,
        db_session,
        test_storage,
        render_service,
    ) -> None:
        render = await render_crud.create_render(db_session)
        render_id = render.id
        workspace = await test_storage.create_workspace(render_id)
        await render_crud.update_render_caption_metadata(
            db_session,
            render_id,
            metadata=StoredCaptionMetadata(
                mode=CaptionMode.SIDECAR,
                format=CaptionFormat.SRT,
                sidecar_media_type="application/x-subrip",
                sidecar_filename="stale.srt",
                cue_count=1,
                burned_in=False,
            ),
            sidecar_path="/tmp/stale.srt",
        )
        await render_crud.update_render_poster_metadata(
            db_session,
            render_id,
            metadata=StoredPosterMetadata(
                mode=PosterMode.DEFAULT,
                timestamp_seconds=0.25,
                media_type="image/jpeg",
                filename="stale.jpg",
            ),
            poster_path="/tmp/stale.jpg",
        )
        compiled = CompiledRender(
            spec_path=workspace / "compiled.editly.json",
            replay_path=workspace / "replay.json",
            workspace=workspace,
            renderer_name="editly",
            spec_json="{}",
        )
        composition = Composition.model_validate(
            {
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
                "captions": {
                    "mode": "sidecar",
                    "format": "srt",
                    "cues": [
                        {"start": 0.0, "end": 1.0, "text": "Hello"},
                    ],
                },
            }
        )

        async def _fail_caption_finish(**kwargs: object) -> None:
            raise CaptionFinishingError("caption failed")

        monkeypatch.setattr(
            render_service._caption_finisher,
            "finish",
            _fail_caption_finish,
        )

        with pytest.raises(RenderServiceError):
            await render_service.stage_render_and_store(
                composition,
                compiled,
                render_id,
                workspace,
                db_session,
            )

        stored = await render_crud.get_render_by_id(db_session, render_id)
        assert stored is not None
        assert stored.caption_mode is None
        assert stored.caption_sidecar_path is None
        assert stored.poster_mode is None
        assert stored.poster_path is None

    @pytest.mark.asyncio
    async def test_missing_render_returns_early(
        self,
        pipeline_db_engine,
        pipeline_session_factory,
        pipeline_workspace,
        mock_service,
    ):
        """Worker returns early for nonexistent render_id."""
        ctx = {
            "session_factory": pipeline_session_factory,
            "render_service": mock_service,
            "workspace_manager": pipeline_workspace,
        }

        await run_render(ctx, "nonexistent_id")
        mock_service.stage_validate_and_expand.assert_not_called()

    @pytest.mark.asyncio
    async def test_terminal_render_skipped(
        self,
        pipeline_db_engine,
        pipeline_session_factory,
        pipeline_workspace,
        mock_service,
        sample_composition_dict,
    ):
        """Worker skips render that is already in terminal status."""
        async with pipeline_session_factory() as session:
            render = await render_crud.create_render(session)
            render_id = render.id
            await render_crud.update_render_status(
                session, render_id, RenderStatus.FETCHING
            )
            await render_crud.update_render_status(
                session, render_id, RenderStatus.FAILED, error_code="TEST"
            )

        ctx = {
            "session_factory": pipeline_session_factory,
            "render_service": mock_service,
            "workspace_manager": pipeline_workspace,
        }

        await run_render(ctx, render_id)
        mock_service.stage_validate_and_expand.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_input_data_marks_failed(
        self,
        pipeline_db_engine,
        pipeline_session_factory,
        pipeline_workspace,
        mock_service,
    ):
        """Worker marks FAILED with NO_INPUT_DATA when input_path is None."""
        async with pipeline_session_factory() as session:
            render = await render_crud.create_render(session)
            render_id = render.id

        ctx = {
            "session_factory": pipeline_session_factory,
            "render_service": mock_service,
            "workspace_manager": pipeline_workspace,
        }

        await run_render(ctx, render_id)

        async with pipeline_session_factory() as session:
            render = await render_crud.get_render_by_id(session, render_id)
            assert render is not None
            assert render.status == RenderStatus.FAILED.value
            assert render.error_code == ErrorCode.NO_INPUT_DATA.value

    @pytest.mark.asyncio
    async def test_missing_input_file_marks_failed(
        self,
        pipeline_db_engine,
        pipeline_session_factory,
        pipeline_workspace,
        mock_service,
    ):
        """Worker marks FAILED with INPUT_FILE_MISSING when file doesn't exist."""
        async with pipeline_session_factory() as session:
            render = await render_crud.create_render(session)
            render_id = render.id
            await render_crud.update_render_paths(
                session, render_id, input_path="/nonexistent/input.json"
            )

        ctx = {
            "session_factory": pipeline_session_factory,
            "render_service": mock_service,
            "workspace_manager": pipeline_workspace,
        }

        await run_render(ctx, render_id)

        async with pipeline_session_factory() as session:
            render = await render_crud.get_render_by_id(session, render_id)
            assert render is not None
            assert render.status == RenderStatus.FAILED.value
            assert render.error_code == ErrorCode.INPUT_FILE_MISSING.value

    @pytest.mark.asyncio
    async def test_capability_validation_failure_marks_failed_before_pipeline_stages(
        self,
        pipeline_db_engine,
        pipeline_session_factory,
        pipeline_workspace,
        mock_service,
        sample_composition_dict,
    ):
        """Worker rejects unsupported renderer features before stage execution."""
        payload = deepcopy(sample_composition_dict)
        payload["renderer"] = "hyperframes"
        render_id = await _create_render_with_input(
            pipeline_session_factory,
            pipeline_workspace,
            payload,
        )

        ctx = {
            "session_factory": pipeline_session_factory,
            "render_service": mock_service,
            "workspace_manager": pipeline_workspace,
        }

        await run_render(ctx, render_id)

        async with pipeline_session_factory() as session:
            render = await render_crud.get_render_by_id(session, render_id)
            assert render is not None
            assert render.status == RenderStatus.FAILED.value
            assert render.error_code == ErrorCode.UNSUPPORTED_RENDERER.value
            assert render.renderer == "hyperframes"

        mock_service.stage_validate_and_expand.assert_not_called()
        mock_service.stage_resolve_and_compile.assert_not_called()

    @pytest.mark.asyncio
    async def test_limit_validation_failure_marks_failed_before_pipeline_stages(
        self,
        pipeline_db_engine,
        pipeline_session_factory,
        pipeline_workspace,
        mock_service,
        sample_composition_dict,
    ):
        """Worker rejects output limit failures before stage execution."""
        payload = deepcopy(sample_composition_dict)
        payload["output"]["format"] = "png-sequence"
        payload["output"]["width"] = 320
        payload["output"]["height"] = 180
        payload["output"]["fps"] = 31
        render_id = await _create_render_with_input(
            pipeline_session_factory,
            pipeline_workspace,
            payload,
        )

        ctx = {
            "session_factory": pipeline_session_factory,
            "render_service": mock_service,
            "workspace_manager": pipeline_workspace,
        }

        await run_render(ctx, render_id)

        async with pipeline_session_factory() as session:
            render = await render_crud.get_render_by_id(session, render_id)
            assert render is not None
            assert render.status == RenderStatus.FAILED.value
            assert render.error_code == ErrorCode.COMPOSITION_LIMIT_EXCEEDED.value
            assert render.renderer == "editly"

        mock_service.stage_validate_and_expand.assert_not_called()
        mock_service.stage_resolve_and_compile.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: Log collector integration
# ---------------------------------------------------------------------------


class TestLogCollectorIntegration:
    @pytest.mark.asyncio
    async def test_logs_written_on_success(
        self,
        pipeline_db_engine,
        pipeline_session_factory,
        pipeline_workspace,
        mock_service,
        sample_composition_dict,
    ):
        """logs.txt is written and path stored on successful render."""
        render_id = await _create_render_with_input(
            pipeline_session_factory, pipeline_workspace, sample_composition_dict
        )

        ctx = {
            "session_factory": pipeline_session_factory,
            "render_service": mock_service,
            "workspace_manager": pipeline_workspace,
        }

        with patch("app.workers.workspace.get_settings") as mock_ws_settings:
            settings = MagicMock()
            settings.workspace_cleanup_enabled = False
            mock_ws_settings.return_value = settings
            await run_render(ctx, render_id)

        async with pipeline_session_factory() as session:
            render = await render_crud.get_render_by_id(session, render_id)
            assert render is not None
            assert render.log_path is not None
            log_path = Path(render.log_path)
            assert log_path.exists()
            content = log_path.read_text(encoding="utf-8")
            assert "SUCCEEDED" in content

    @pytest.mark.asyncio
    async def test_logs_written_on_failure(
        self,
        pipeline_db_engine,
        pipeline_session_factory,
        pipeline_workspace,
        mock_service,
        sample_composition_dict,
    ):
        """logs.txt captures error information on failed render."""
        mock_service.stage_validate_and_expand = AsyncMock(
            side_effect=RenderServiceError("test error", error_code="COMPILE_ERROR")
        )

        render_id = await _create_render_with_input(
            pipeline_session_factory, pipeline_workspace, sample_composition_dict
        )

        ctx = {
            "session_factory": pipeline_session_factory,
            "render_service": mock_service,
            "workspace_manager": pipeline_workspace,
        }

        with patch("app.workers.workspace.get_settings") as mock_ws_settings:
            settings = MagicMock()
            settings.workspace_cleanup_enabled = True
            settings.workspace_cleanup_keep_on_failure = True
            mock_ws_settings.return_value = settings
            await run_render(ctx, render_id)

        async with pipeline_session_factory() as session:
            render = await render_crud.get_render_by_id(session, render_id)
            assert render is not None
            assert render.status == RenderStatus.FAILED.value
