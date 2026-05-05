from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.api.deps import (
    get_arq_pool_dep,
    get_asset_service,
    get_editly_renderer,
    get_hyperframes_renderer,
    get_local_storage,
    get_native_ffmpeg_renderer,
    get_render_service,
    get_renderer_resolver,
    get_storage_backend,
    get_storage_url_resolver,
    get_template_service,
)
from app.core.config import Settings, get_settings, reset_settings_cache
from app.core.security import hash_api_key
from app.db.session import get_session, set_engine
from app.main import create_app
from app.renderers.base import CompiledRender, RenderArtifact
from app.renderers.editly import EditlyRenderer
from app.services.asset_service import AssetService, ResolvedAsset
from app.services.render_service import RenderService
from app.services.template_service import TemplateService
from app.storage.base import StorageUrlMode
from app.storage.local import LocalStorage
from app.storage.urls import StorageUrlResolver

FIXTURES_DIR = Path(__file__).parent / "fixtures"
AUTH_TEST_API_KEY = "vidapi-test-key"
AUTH_TEST_API_KEY_HASH = hash_api_key(AUTH_TEST_API_KEY)


@pytest.fixture(autouse=True)
def reset_app_settings_cache() -> Iterator[None]:
    reset_settings_cache()
    get_local_storage.cache_clear()
    get_storage_backend.cache_clear()
    get_storage_url_resolver.cache_clear()
    get_asset_service.cache_clear()
    get_editly_renderer.cache_clear()
    get_hyperframes_renderer.cache_clear()
    get_native_ffmpeg_renderer.cache_clear()
    get_renderer_resolver.cache_clear()
    get_render_service.cache_clear()
    get_template_service.cache_clear()
    yield
    reset_settings_cache()
    get_local_storage.cache_clear()
    get_storage_backend.cache_clear()
    get_storage_url_resolver.cache_clear()
    get_asset_service.cache_clear()
    get_editly_renderer.cache_clear()
    get_hyperframes_renderer.cache_clear()
    get_native_ffmpeg_renderer.cache_clear()
    get_renderer_resolver.cache_clear()
    get_render_service.cache_clear()
    get_template_service.cache_clear()


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        api_key_auth_enabled=True,
        api_key_hashes=[AUTH_TEST_API_KEY_HASH],
    )


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-API-Key": AUTH_TEST_API_KEY}


@pytest.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    set_engine(None)
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    set_engine(engine)
    try:
        yield engine
    finally:
        set_engine(None)
        await engine.dispose()


@pytest.fixture
async def db_session(db_engine) -> AsyncIterator[SQLModelAsyncSession]:
    async with SQLModelAsyncSession(db_engine) as session:
        yield session


@pytest.fixture
def test_storage(tmp_path: Path) -> LocalStorage:
    workspace_root = tmp_path / "renders"
    workspace_root.mkdir()
    return LocalStorage(workspace_root=workspace_root)


@pytest.fixture
def mock_asset_service() -> AssetService:
    service = MagicMock(spec=AssetService)
    service.resolve_asset = AsyncMock(
        return_value=ResolvedAsset(
            local_path=Path("/dev/null"),
            content_hash="abc123",
            media_info=None,
            source_url=None,
            asset_type="file",
        )
    )
    return service


@pytest.fixture
def mock_renderer(tmp_path: Path) -> EditlyRenderer:
    renderer = MagicMock(spec=EditlyRenderer)
    renderer.name = "editly"

    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)

    spec_path = workspace / "compiled.editly.json"
    spec_path.write_text("{}", encoding="utf-8")
    replay_path = workspace / "replay.json"
    replay_path.write_text("{}", encoding="utf-8")

    output_path = workspace / "output.mp4"
    output_path.write_bytes(b"\x00" * 100)

    log_path = workspace / "render.log"
    log_path.write_text("OK", encoding="utf-8")

    renderer.compile = AsyncMock(
        return_value=CompiledRender(
            spec_path=spec_path,
            replay_path=replay_path,
            workspace=workspace,
            renderer_name="editly",
            spec_json="{}",
        )
    )
    renderer.render = AsyncMock(
        return_value=RenderArtifact(
            output_path=output_path,
            poster_path=None,
            log_path=log_path,
            duration_seconds=2.5,
            exit_code=0,
        )
    )
    return renderer


@pytest.fixture
def render_service(
    test_storage: LocalStorage,
    mock_asset_service: AssetService,
    mock_renderer: EditlyRenderer,
) -> RenderService:
    return RenderService(
        storage=test_storage,
        asset_service=mock_asset_service,
        renderer=mock_renderer,
    )


@pytest.fixture
def test_url_resolver(test_storage: LocalStorage) -> StorageUrlResolver:
    return StorageUrlResolver(
        storage=test_storage,
        url_mode=StorageUrlMode.PROXY,
        signed_url_expiry_seconds=900,
    )


@pytest.fixture
def sample_composition() -> dict:
    path = FIXTURES_DIR / "sample_composition.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
async def client(
    db_engine,
    test_storage,
    test_url_resolver,
    mock_asset_service,
    mock_renderer,
    render_service,
) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _override_session():
        async with SQLModelAsyncSession(db_engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_local_storage] = lambda: test_storage
    app.dependency_overrides[get_storage_backend] = lambda: test_storage
    app.dependency_overrides[get_storage_url_resolver] = lambda: test_url_resolver
    app.dependency_overrides[get_asset_service] = lambda: mock_asset_service
    app.dependency_overrides[get_editly_renderer] = lambda: mock_renderer
    app.dependency_overrides[get_render_service] = lambda: render_service
    app.dependency_overrides[get_arq_pool_dep] = lambda: None
    app.dependency_overrides[get_template_service] = lambda: TemplateService()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def auth_client(
    auth_settings,
    db_engine,
    test_storage,
    test_url_resolver,
    mock_asset_service,
    mock_renderer,
    render_service,
) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _override_session():
        async with SQLModelAsyncSession(db_engine) as session:
            yield session

    app.dependency_overrides[get_settings] = lambda: auth_settings
    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_local_storage] = lambda: test_storage
    app.dependency_overrides[get_storage_backend] = lambda: test_storage
    app.dependency_overrides[get_storage_url_resolver] = lambda: test_url_resolver
    app.dependency_overrides[get_asset_service] = lambda: mock_asset_service
    app.dependency_overrides[get_editly_renderer] = lambda: mock_renderer
    app.dependency_overrides[get_render_service] = lambda: render_service
    app.dependency_overrides[get_arq_pool_dep] = lambda: None
    app.dependency_overrides[get_template_service] = lambda: TemplateService()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
