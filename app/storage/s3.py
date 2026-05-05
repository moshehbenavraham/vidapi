from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from app.api.errors import StorageError
from app.storage.base import (
    ArtifactType,
    StorageBackend,
    artifact_descriptor,
    validate_render_id,
)
from app.storage.local import LocalStorage

MISSING_OBJECT_CODES = frozenset({"404", "NoSuchKey", "NotFound"})


class S3Storage:
    """S3-compatible durable artifact storage with local scratch workspaces."""

    def __init__(
        self,
        *,
        workspace_root: Path,
        bucket: str,
        region: str,
        endpoint_url: str = "",
        access_key_id: str = "",
        secret_access_key: str = "",
        object_prefix: str = "renders",
        force_path_style: bool = True,
        connect_timeout_seconds: float = 5.0,
        read_timeout_seconds: float = 60.0,
        max_attempts: int = 3,
        client: Any | None = None,
    ) -> None:
        if not bucket.strip():
            msg = "S3 bucket must not be empty"
            raise ValueError(msg)

        self._scratch = LocalStorage(workspace_root=workspace_root)
        self._bucket = bucket.strip()
        self._object_prefix = self._normalize_prefix(object_prefix)
        self._max_attempts = max_attempts
        self._client = client or self._build_client(
            region=region,
            endpoint_url=endpoint_url,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            force_path_style=force_path_style,
            connect_timeout_seconds=connect_timeout_seconds,
            read_timeout_seconds=read_timeout_seconds,
            max_attempts=max_attempts,
        )

    @property
    def backend(self) -> StorageBackend:
        return StorageBackend.S3

    @property
    def bucket(self) -> str:
        return self._bucket

    def object_key(
        self,
        render_id: str,
        artifact_type: ArtifactType,
        *,
        suffix: str = "",
    ) -> str:
        validate_render_id(render_id)
        descriptor = artifact_descriptor(artifact_type, suffix=suffix)
        parts = [render_id, descriptor.filename]
        if self._object_prefix:
            parts.insert(0, self._object_prefix)
        return "/".join(parts)

    async def create_workspace(self, render_id: str) -> Path:
        return await self._scratch.create_workspace(render_id)

    async def write_artifact(
        self,
        render_id: str,
        artifact_type: ArtifactType,
        data: bytes,
        *,
        suffix: str = "",
    ) -> Path:
        return await self._scratch.write_artifact(
            render_id,
            artifact_type,
            data,
            suffix=suffix,
        )

    async def publish_bytes(
        self,
        render_id: str,
        artifact_type: ArtifactType,
        data: bytes,
        *,
        suffix: str = "",
        media_type: str | None = None,
    ) -> str:
        descriptor = artifact_descriptor(
            artifact_type,
            suffix=suffix,
            media_type=media_type,
        )
        key = self.object_key(render_id, artifact_type, suffix=suffix)
        try:
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=descriptor.media_type,
            )
        except (BotoCoreError, ClientError, NoCredentialsError) as exc:
            raise self._storage_error(
                "Failed to upload artifact to S3",
                exc,
                key=key,
                artifact=artifact_type.value,
            ) from exc
        return self._uri_for_key(key)

    async def publish_file(
        self,
        render_id: str,
        artifact_type: ArtifactType,
        source_path: Path,
        *,
        suffix: str = "",
        media_type: str | None = None,
    ) -> str:
        if not source_path.is_file():
            raise FileNotFoundError(source_path)

        descriptor = artifact_descriptor(
            artifact_type,
            suffix=suffix or source_path.suffix,
            media_type=media_type,
        )
        key = self.object_key(
            render_id,
            artifact_type,
            suffix=suffix or source_path.suffix,
        )
        try:
            await asyncio.to_thread(
                self._client.upload_file,
                str(source_path),
                self._bucket,
                key,
                ExtraArgs={"ContentType": descriptor.media_type},
            )
        except (BotoCoreError, ClientError, NoCredentialsError) as exc:
            raise self._storage_error(
                "Failed to upload artifact file to S3",
                exc,
                key=key,
                artifact=artifact_type.value,
            ) from exc
        return self._uri_for_key(key)

    async def read_artifact(
        self,
        render_id: str,
        artifact_type: ArtifactType,
        *,
        suffix: str = "",
    ) -> bytes:
        return await self._scratch.read_artifact(
            render_id,
            artifact_type,
            suffix=suffix,
        )

    async def read_uri(self, uri: str) -> bytes:
        bucket, key = self._parse_uri(uri)
        try:
            response = await asyncio.to_thread(
                self._client.get_object,
                Bucket=bucket,
                Key=key,
            )
            body = response["Body"]
            try:
                return await asyncio.to_thread(body.read)
            finally:
                close = getattr(body, "close", None)
                if close is not None:
                    await asyncio.to_thread(close)
        except ClientError as exc:
            if self._is_missing_object(exc):
                raise FileNotFoundError(uri) from exc
            raise self._storage_error(
                "Failed to read S3 artifact",
                exc,
                key=key,
            ) from exc
        except (BotoCoreError, NoCredentialsError) as exc:
            raise self._storage_error(
                "Failed to read S3 artifact",
                exc,
                key=key,
            ) from exc

    async def iter_uri(
        self,
        uri: str,
        *,
        chunk_size: int = 1024 * 1024,
    ) -> AsyncIterator[bytes]:
        bucket, key = self._parse_uri(uri)
        try:
            response = await asyncio.to_thread(
                self._client.get_object,
                Bucket=bucket,
                Key=key,
            )
            body = response["Body"]
            try:
                while True:
                    chunk = await asyncio.to_thread(body.read, chunk_size)
                    if not chunk:
                        break
                    yield chunk
            finally:
                close = getattr(body, "close", None)
                if close is not None:
                    await asyncio.to_thread(close)
        except ClientError as exc:
            if self._is_missing_object(exc):
                raise FileNotFoundError(uri) from exc
            raise self._storage_error(
                "Failed to stream S3 artifact",
                exc,
                key=key,
            ) from exc
        except (BotoCoreError, NoCredentialsError) as exc:
            raise self._storage_error(
                "Failed to stream S3 artifact",
                exc,
                key=key,
            ) from exc

    async def exists_uri(self, uri: str) -> bool:
        bucket, key = self._parse_uri(uri)
        try:
            await asyncio.to_thread(
                self._client.head_object,
                Bucket=bucket,
                Key=key,
            )
            return True
        except ClientError as exc:
            if self._is_missing_object(exc):
                return False
            raise self._storage_error(
                "Failed to check S3 artifact",
                exc,
                key=key,
            ) from exc
        except (BotoCoreError, NoCredentialsError) as exc:
            raise self._storage_error(
                "Failed to check S3 artifact",
                exc,
                key=key,
            ) from exc

    async def presign_uri(self, uri: str, *, expires_in_seconds: int) -> str:
        bucket, key = self._parse_uri(uri)
        try:
            return await asyncio.to_thread(
                self._client.generate_presigned_url,
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires_in_seconds,
            )
        except (BotoCoreError, ClientError, NoCredentialsError) as exc:
            raise self._storage_error(
                "Failed to sign S3 artifact URL",
                exc,
                key=key,
            ) from exc

    async def list_artifacts(self, render_id: str) -> list[Path]:
        return await self._scratch.list_artifacts(render_id)

    async def workspace_path(self, render_id: str) -> Path:
        return await self._scratch.workspace_path(render_id)

    def _build_client(
        self,
        *,
        region: str,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        force_path_style: bool,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        max_attempts: int,
    ) -> Any:
        import boto3

        config = Config(
            connect_timeout=connect_timeout_seconds,
            read_timeout=read_timeout_seconds,
            retries={"max_attempts": max_attempts, "mode": "standard"},
            s3={"addressing_style": "path" if force_path_style else "auto"},
        )
        kwargs: dict[str, Any] = {
            "service_name": "s3",
            "region_name": region,
            "config": config,
        }
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        if access_key_id:
            kwargs["aws_access_key_id"] = access_key_id
        if secret_access_key:
            kwargs["aws_secret_access_key"] = secret_access_key
        return boto3.client(**kwargs)

    def _uri_for_key(self, key: str) -> str:
        return f"s3://{self._bucket}/{key}"

    def _parse_uri(self, uri: str) -> tuple[str, str]:
        parsed = urlsplit(uri)
        if parsed.scheme != "s3" or not parsed.netloc:
            raise StorageError(
                detail="Artifact URI is not an S3 URI",
                context={"uri": uri},
            )
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        if bucket != self._bucket:
            raise StorageError(
                detail="Artifact URI bucket does not match configured bucket",
                context={"bucket": bucket},
            )
        if not key:
            raise StorageError(
                detail="Artifact URI is missing an object key",
                context={"uri": uri},
            )
        return bucket, key

    @staticmethod
    def _normalize_prefix(prefix: str) -> str:
        clean = prefix.strip().strip("/")
        if not clean:
            return ""
        parts = [part for part in clean.split("/") if part]
        if any(part in {".", ".."} for part in parts):
            msg = "S3 object prefix must not contain relative path segments"
            raise ValueError(msg)
        return "/".join(parts)

    @staticmethod
    def _is_missing_object(exc: ClientError) -> bool:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        status_code = str(
            exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", "")
        )
        return code in MISSING_OBJECT_CODES or status_code == "404"

    def _storage_error(
        self,
        detail: str,
        exc: Exception,
        *,
        key: str,
        artifact: str | None = None,
    ) -> StorageError:
        context: dict[str, str] = {
            "bucket": self._bucket,
            "key": key,
            "max_attempts": str(self._max_attempts),
        }
        if artifact is not None:
            context["artifact"] = artifact
        if isinstance(exc, ClientError):
            error = exc.response.get("Error", {})
            code = str(error.get("Code", ""))
            if code:
                context["provider_code"] = code
        return StorageError(detail=detail, context=context)
