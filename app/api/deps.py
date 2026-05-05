from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.redis import get_arq_pool
from app.db.session import get_session
from app.renderers import (
    DEFAULT_RENDERER,
    FFMPEG_NATIVE_RENDERER,
    NativeFfmpegRenderer,
    RendererProtocol,
    RendererResolver,
    select_renderer,
)
from app.renderers.editly import EditlyRenderer
from app.services.asset_service import AssetService
from app.services.render_service import RenderService
from app.services.template_service import TemplateService
from app.storage.base import ArtifactStorageProtocol
from app.storage.factory import build_storage, build_storage_url_resolver
from app.storage.local import LocalStorage
from app.storage.urls import StorageUrlResolver

SettingsDep = Annotated[Settings, Depends(get_settings)]
DBSessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_arq_pool_dep() -> ArqRedis | None:
    """Dependency that provides the ARQ Redis pool for routes.

    Returns None when RENDER_MODE=sync to avoid requiring Redis.
    """
    settings = get_settings()
    if settings.render_mode != "async":
        return None
    return await get_arq_pool()


ArqPoolDep = Annotated[ArqRedis | None, Depends(get_arq_pool_dep)]


@lru_cache(maxsize=1)
def get_local_storage() -> LocalStorage:
    settings = get_settings()
    return LocalStorage(
        workspace_root=settings.render_workspace_root,
        artifact_root=settings.storage_root / "artifacts",
    )


@lru_cache(maxsize=1)
def get_storage_backend() -> ArtifactStorageProtocol:
    return build_storage(get_settings())


@lru_cache(maxsize=1)
def get_storage_url_resolver() -> StorageUrlResolver:
    settings = get_settings()
    storage = get_storage_backend()
    return build_storage_url_resolver(settings=settings, storage=storage)


@lru_cache(maxsize=1)
def get_asset_service() -> AssetService:
    settings = get_settings()
    return AssetService(settings=settings)


@lru_cache(maxsize=1)
def get_editly_renderer() -> EditlyRenderer:
    settings = get_settings()
    return EditlyRenderer(settings=settings)


@lru_cache(maxsize=1)
def get_native_ffmpeg_renderer() -> NativeFfmpegRenderer:
    settings = get_settings()
    return NativeFfmpegRenderer(settings=settings)


@lru_cache(maxsize=1)
def get_renderer_resolver() -> RendererResolver:
    def _resolve(renderer_name: str | None = None) -> RendererProtocol:
        selection = select_renderer(renderer_name)
        if selection.renderer == DEFAULT_RENDERER:
            return get_editly_renderer()
        if selection.renderer == FFMPEG_NATIVE_RENDERER:
            return get_native_ffmpeg_renderer()
        msg = f"No renderer implementation configured for {selection.renderer}"
        raise ValueError(msg)

    return _resolve


@lru_cache(maxsize=1)
def get_render_service() -> RenderService:
    return RenderService(
        storage=get_storage_backend(),
        asset_service=get_asset_service(),
        renderer=get_editly_renderer(),
        renderer_resolver=get_renderer_resolver(),
    )


@lru_cache(maxsize=1)
def get_template_service() -> TemplateService:
    return TemplateService()


TemplateServiceDep = Annotated[TemplateService, Depends(get_template_service)]
StorageDep = Annotated[ArtifactStorageProtocol, Depends(get_storage_backend)]
StorageUrlResolverDep = Annotated[
    StorageUrlResolver,
    Depends(get_storage_url_resolver),
]
AssetServiceDep = Annotated[AssetService, Depends(get_asset_service)]
EditlyRendererDep = Annotated[EditlyRenderer, Depends(get_editly_renderer)]
RendererResolverDep = Annotated[RendererResolver, Depends(get_renderer_resolver)]
RenderServiceDep = Annotated[RenderService, Depends(get_render_service)]
