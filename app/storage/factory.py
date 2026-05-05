from __future__ import annotations

from app.core.config import Settings
from app.storage.base import ArtifactStorageProtocol, StorageUrlMode
from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage
from app.storage.urls import StorageUrlResolver


def build_storage(settings: Settings) -> ArtifactStorageProtocol:
    if settings.storage_backend == "s3":
        return S3Storage(
            workspace_root=settings.render_workspace_root,
            bucket=settings.s3_bucket,
            region=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            object_prefix=settings.s3_object_prefix,
            force_path_style=settings.s3_force_path_style,
            connect_timeout_seconds=settings.s3_connect_timeout_seconds,
            read_timeout_seconds=settings.s3_read_timeout_seconds,
            max_attempts=settings.s3_max_attempts,
        )

    return LocalStorage(
        workspace_root=settings.render_workspace_root,
        artifact_root=settings.storage_root / "artifacts",
    )


def build_storage_url_resolver(
    *,
    settings: Settings,
    storage: ArtifactStorageProtocol,
) -> StorageUrlResolver:
    return StorageUrlResolver(
        storage=storage,
        url_mode=StorageUrlMode(settings.storage_url_mode),
        signed_url_expiry_seconds=settings.storage_signed_url_expiry_seconds,
        public_base_url=settings.s3_public_base_url,
        forbidden_public_fragments=(
            settings.s3_access_key_id,
            settings.s3_secret_access_key,
        ),
        forbidden_signed_fragments=(settings.s3_secret_access_key,),
    )
