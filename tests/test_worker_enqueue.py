from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.api.deps import (
    get_arq_pool_dep,
    get_asset_service,
    get_editly_renderer,
    get_local_storage,
    get_render_service,
    get_storage_backend,
)
from app.core.config import get_settings
from app.db import render_crud
from app.db.session import get_session, set_engine
from app.main import create_app
from app.models.render import RenderStatus
from app.renderers.base import CompiledRender, RenderArtifact
from app.services.render_service import RenderService
from app.storage.base import ArtifactType
from app.storage.local import LocalStorage
from app.workers.render_worker import enqueue_render, run_render
from app.workers.workspace import WorkspaceManager

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def worker_db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        echo=False,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    set_engine(engine)
    yield engine
    await engine.dispose()
    set_engine(None)  # type: ignore[arg-type]


@pytest.fixture
def worker_session_factory(worker_db_engine):
    @asynccontextmanager
    async def _factory():
        async with SQLModelAsyncSession(worker_db_engine) as session:
            yield session

    return _factory


@pytest.fixture
def worker_storage(tmp_path: Path) -> LocalStorage:
    workspace_root = tmp_path / "renders"
    workspace_root.mkdir()
    return LocalStorage(workspace_root=workspace_root)


@pytest.fixture
def mock_render_service(tmp_path: Path) -> RenderService:
    service = MagicMock(spec=RenderService)

    async def _execute(composition, session):
        render = await render_crud.create_render(session)
        await render_crud.update_render_status(
            session, render.id, RenderStatus.FETCHING, stage="test"
        )
        await render_crud.update_render_status(
            session, render.id, RenderStatus.COMPILING, stage="test"
        )
        await render_crud.update_render_status(
            session, render.id, RenderStatus.RENDERING, stage="test"
        )
        await render_crud.update_render_status(
            session, render.id, RenderStatus.UPLOADING, stage="test"
        )
        await render_crud.update_render_status(
            session,
            render.id,
            RenderStatus.SUCCEEDED,
            stage="complete",
            progress=100,
        )
        return await render_crud.get_render_by_id(session, render.id)

    service.execute_render = AsyncMock(side_effect=_execute)
    return service


@pytest.fixture
def worker_workspace_mgr(tmp_path: Path) -> WorkspaceManager:
    workspace_root = tmp_path / "ws"
    workspace_root.mkdir()
    return WorkspaceManager(workspace_root=workspace_root)


@pytest.fixture
def sample_composition_dict() -> dict:
    path = FIXTURES_DIR / "sample_composition.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _wire_worker_storage_methods(service: MagicMock) -> None:
    async def _read_artifact_uri(uri: str) -> bytes:
        return Path(uri).read_bytes()

    async def _publish_artifact_file(
        render_id: str,
        artifact_type: ArtifactType,
        source_path: Path,
        session,
    ) -> str:
        if artifact_type is ArtifactType.LOG:
            await render_crud.update_render_paths(
                session,
                render_id,
                log_path=str(source_path),
            )
        return str(source_path)

    service.read_artifact_uri = AsyncMock(side_effect=_read_artifact_uri)
    service.publish_artifact_file = AsyncMock(side_effect=_publish_artifact_file)


# ---------------------------------------------------------------------------
# T017: Unit tests for enqueue path (mocked Redis/ARQ pool)
# ---------------------------------------------------------------------------


class TestEnqueuePath:
    @pytest.mark.asyncio
    async def test_enqueue_render_calls_enqueue_job(self):
        """enqueue_render should call pool.enqueue_job with correct args."""
        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock(return_value=MagicMock())

        await enqueue_render(mock_pool, "render_abc123")

        mock_pool.enqueue_job.assert_called_once_with("run_render", "render_abc123")

    @pytest.mark.asyncio
    async def test_post_renders_async_mode_returns_202_queued(
        self, worker_db_engine, tmp_path, sample_composition_dict
    ):
        """POST /v1/renders in async mode returns 202 with status=queued."""
        from app.core.config import Settings

        app = create_app()
        workspace_root = tmp_path / "renders"
        workspace_root.mkdir()
        storage = LocalStorage(workspace_root=workspace_root)

        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock(return_value=MagicMock())

        async def _override_session():
            async with SQLModelAsyncSession(worker_db_engine) as session:
                yield session

        async_settings = Settings(render_mode="async")

        app.dependency_overrides[get_session] = _override_session
        app.dependency_overrides[get_local_storage] = lambda: storage
        app.dependency_overrides[get_storage_backend] = lambda: storage
        app.dependency_overrides[get_arq_pool_dep] = lambda: mock_pool
        app.dependency_overrides[get_settings] = lambda: async_settings

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/v1/renders", json=sample_composition_dict)

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "queued"
        assert data["progress"] == 0
        mock_pool.enqueue_job.assert_called_once()

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_post_renders_async_redis_down_returns_503(
        self, worker_db_engine, tmp_path, sample_composition_dict
    ):
        """POST /v1/renders returns 503 when Redis is unreachable."""
        from redis.exceptions import ConnectionError as RedisConnectionError

        from app.core.config import Settings

        app = create_app()
        workspace_root = tmp_path / "renders"
        workspace_root.mkdir()
        storage = LocalStorage(workspace_root=workspace_root)

        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock(
            side_effect=RedisConnectionError("Connection refused")
        )

        async def _override_session():
            async with SQLModelAsyncSession(worker_db_engine) as session:
                yield session

        async_settings = Settings(render_mode="async")

        app.dependency_overrides[get_session] = _override_session
        app.dependency_overrides[get_local_storage] = lambda: storage
        app.dependency_overrides[get_storage_backend] = lambda: storage
        app.dependency_overrides[get_arq_pool_dep] = lambda: mock_pool
        app.dependency_overrides[get_settings] = lambda: async_settings

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/v1/renders", json=sample_composition_dict)

        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_post_renders_sync_mode_bypasses_enqueue(
        self, worker_db_engine, tmp_path, sample_composition_dict
    ):
        """POST /v1/renders in sync mode does not use ARQ pool."""
        app = create_app()
        workspace_root = tmp_path / "renders"
        workspace_root.mkdir()
        storage = LocalStorage(workspace_root=workspace_root)

        mock_renderer = MagicMock()
        mock_renderer.name = "editly"
        output_path = tmp_path / "output.mp4"
        output_path.write_bytes(b"\x00" * 100)
        log_path = tmp_path / "render.log"
        log_path.write_text("OK", encoding="utf-8")
        spec_path = tmp_path / "compiled.editly.json"
        spec_path.write_text("{}", encoding="utf-8")
        replay_path = tmp_path / "replay.json"
        replay_path.write_text("{}", encoding="utf-8")

        mock_renderer.compile = AsyncMock(
            return_value=CompiledRender(
                spec_path=spec_path,
                replay_path=replay_path,
                workspace=tmp_path,
                renderer_name="editly",
                spec_json="{}",
            )
        )
        mock_renderer.render = AsyncMock(
            return_value=RenderArtifact(
                output_path=output_path,
                poster_path=None,
                log_path=log_path,
                duration_seconds=2.5,
                exit_code=0,
            )
        )

        mock_asset_service = MagicMock()
        mock_asset_service.resolve_asset = AsyncMock(
            return_value=MagicMock(local_path=Path("/dev/null"), content_hash="x")
        )

        render_service = RenderService(
            storage=storage,
            asset_service=mock_asset_service,
            renderer=mock_renderer,
        )

        async def _override_session():
            async with SQLModelAsyncSession(worker_db_engine) as session:
                yield session

        app.dependency_overrides[get_session] = _override_session
        app.dependency_overrides[get_local_storage] = lambda: storage
        app.dependency_overrides[get_storage_backend] = lambda: storage
        app.dependency_overrides[get_asset_service] = lambda: mock_asset_service
        app.dependency_overrides[get_editly_renderer] = lambda: mock_renderer
        app.dependency_overrides[get_render_service] = lambda: render_service
        app.dependency_overrides[get_arq_pool_dep] = lambda: None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/v1/renders", json=sample_composition_dict)

        assert response.status_code == 202
        data = response.json()
        assert data["status"] in ("succeeded", "failed")

        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# T018: Unit tests for worker task function (mocked RenderService)
# ---------------------------------------------------------------------------


class TestWorkerTask:
    @pytest.mark.asyncio
    async def test_worker_task_runs_render_pipeline(
        self,
        worker_db_engine,
        worker_session_factory,
        worker_storage,
        worker_workspace_mgr,
        sample_composition_dict,
    ):
        """Worker task loads composition and calls stage methods."""
        async with worker_session_factory() as session:
            render = await render_crud.create_render(session)
            render_id = render.id
            workspace = await worker_storage.create_workspace(render_id)
            input_path = workspace / "input.json"
            input_path.write_text(json.dumps(sample_composition_dict), encoding="utf-8")
            await render_crud.update_render_paths(
                session, render_id, input_path=str(input_path)
            )

        mock_service = MagicMock(spec=RenderService)

        async def _validate(comp, rid, ws, sess):
            return comp

        async def _compile(comp, rid, ws, sess):
            return MagicMock()

        async def _render(comp, compiled, rid, ws, sess):
            pass

        mock_service.stage_validate_and_expand = AsyncMock(side_effect=_validate)
        mock_service.stage_resolve_and_compile = AsyncMock(side_effect=_compile)
        mock_service.stage_render_and_store = AsyncMock(side_effect=_render)
        _wire_worker_storage_methods(mock_service)

        ctx = {
            "session_factory": worker_session_factory,
            "render_service": mock_service,
            "workspace_manager": worker_workspace_mgr,
        }

        await run_render(ctx, render_id)

        mock_service.stage_validate_and_expand.assert_called_once()
        mock_service.stage_resolve_and_compile.assert_called_once()
        mock_service.stage_render_and_store.assert_called_once()

    @pytest.mark.asyncio
    async def test_worker_task_handles_missing_render(
        self, worker_session_factory, worker_workspace_mgr
    ):
        """Worker task logs and returns early for nonexistent render_id."""
        mock_service = MagicMock(spec=RenderService)
        ctx = {
            "session_factory": worker_session_factory,
            "render_service": mock_service,
            "workspace_manager": worker_workspace_mgr,
        }

        await run_render(ctx, "render_nonexistent")

        mock_service.stage_validate_and_expand.assert_not_called()

    @pytest.mark.asyncio
    async def test_worker_task_handles_terminal_status(
        self,
        worker_db_engine,
        worker_session_factory,
        worker_storage,
        worker_workspace_mgr,
        sample_composition_dict,
    ):
        """Worker task skips renders already in terminal status."""
        async with worker_session_factory() as session:
            render = await render_crud.create_render(session)
            render_id = render.id
            workspace = await worker_storage.create_workspace(render_id)
            input_path = workspace / "input.json"
            input_path.write_text(json.dumps(sample_composition_dict), encoding="utf-8")
            await render_crud.update_render_paths(
                session, render_id, input_path=str(input_path)
            )
            await render_crud.update_render_status(
                session, render_id, RenderStatus.FETCHING
            )
            await render_crud.update_render_status(
                session, render_id, RenderStatus.FAILED, error_code="TEST"
            )

        mock_service = MagicMock(spec=RenderService)
        ctx = {
            "session_factory": worker_session_factory,
            "render_service": mock_service,
            "workspace_manager": worker_workspace_mgr,
        }

        await run_render(ctx, render_id)

        mock_service.stage_validate_and_expand.assert_not_called()

    @pytest.mark.asyncio
    async def test_worker_task_marks_failed_on_exception(
        self,
        worker_db_engine,
        worker_session_factory,
        worker_storage,
        worker_workspace_mgr,
        sample_composition_dict,
    ):
        """Worker task marks render as failed on unexpected exception."""
        async with worker_session_factory() as session:
            render = await render_crud.create_render(session)
            render_id = render.id
            workspace = await worker_storage.create_workspace(render_id)
            input_path = workspace / "input.json"
            input_path.write_text(json.dumps(sample_composition_dict), encoding="utf-8")
            await render_crud.update_render_paths(
                session, render_id, input_path=str(input_path)
            )

        mock_service = MagicMock(spec=RenderService)
        mock_service.stage_validate_and_expand = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        _wire_worker_storage_methods(mock_service)

        ctx = {
            "session_factory": worker_session_factory,
            "render_service": mock_service,
            "workspace_manager": worker_workspace_mgr,
        }

        await run_render(ctx, render_id)

        async with worker_session_factory() as session:
            render = await render_crud.get_render_by_id(session, render_id)
            assert render is not None
            assert render.status == RenderStatus.FAILED.value
            assert render.error_code == "WORKER_UNEXPECTED_ERROR"

    @pytest.mark.asyncio
    async def test_worker_task_handles_missing_input_file(
        self,
        worker_db_engine,
        worker_session_factory,
        worker_storage,
        worker_workspace_mgr,
    ):
        """Worker marks render failed when input file is missing on disk."""
        async with worker_session_factory() as session:
            render = await render_crud.create_render(session)
            render_id = render.id
            await render_crud.update_render_paths(
                session, render_id, input_path="/nonexistent/input.json"
            )

        mock_service = MagicMock(spec=RenderService)
        _wire_worker_storage_methods(mock_service)
        mock_service.read_artifact_uri = AsyncMock(side_effect=FileNotFoundError)
        ctx = {
            "session_factory": worker_session_factory,
            "render_service": mock_service,
            "workspace_manager": worker_workspace_mgr,
        }

        await run_render(ctx, render_id)

        async with worker_session_factory() as session:
            render = await render_crud.get_render_by_id(session, render_id)
            assert render is not None
            assert render.status == RenderStatus.FAILED.value
            assert render.error_code == "INPUT_FILE_MISSING"
