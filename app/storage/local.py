from __future__ import annotations

import asyncio
import contextlib
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import structlog

from app.api.errors import StorageError
from app.storage.base import (
    ArtifactType,
    StorageBackend,
    artifact_descriptor,
    artifact_filename,
    validate_render_id,
)

logger = structlog.get_logger(__name__)


class LocalStorage:
    """Local filesystem storage adapter for render workspaces.

    Workspace paths are deterministic: ``<root>/<render_id>/``.
    """

    def __init__(self, workspace_root: Path, artifact_root: Path | None = None) -> None:
        self._root = workspace_root.resolve()
        self._artifact_root = (
            artifact_root.resolve() if artifact_root is not None else self._root
        )

    @property
    def backend(self) -> StorageBackend:
        return StorageBackend.LOCAL

    async def create_workspace(self, render_id: str) -> Path:
        validate_render_id(render_id)
        ws = self._workspace_dir(render_id)
        try:
            await asyncio.to_thread(ws.mkdir, parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError(
                detail=f"Failed to create workspace for {render_id}",
                context={"render_id": render_id, "path": str(ws)},
            ) from exc
        logger.info(
            "workspace_created",
            render_id=render_id,
            path=str(ws),
        )
        return ws

    async def write_artifact(
        self,
        render_id: str,
        artifact_type: ArtifactType,
        data: bytes,
        *,
        suffix: str = "",
    ) -> Path:
        validate_render_id(render_id)
        ws = self._workspace_dir(render_id)
        if not ws.exists():
            raise StorageError(
                detail=f"Workspace does not exist for {render_id}",
                context={"render_id": render_id},
            )
        dest = self._artifact_path(ws, artifact_type, suffix)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        try:
            await asyncio.to_thread(tmp.write_bytes, data)
            await asyncio.to_thread(tmp.replace, dest)
        except OSError as exc:
            with contextlib.suppress(OSError):
                await asyncio.to_thread(tmp.unlink, missing_ok=True)
            raise StorageError(
                detail=f"Failed to write artifact {artifact_type.value}",
                context={
                    "render_id": render_id,
                    "artifact": artifact_type.value,
                },
            ) from exc
        logger.debug(
            "artifact_written",
            render_id=render_id,
            artifact=artifact_type.value,
            size=len(data),
        )
        return dest

    async def publish_bytes(
        self,
        render_id: str,
        artifact_type: ArtifactType,
        data: bytes,
        *,
        suffix: str = "",
        media_type: str | None = None,
    ) -> str:
        validate_render_id(render_id)
        descriptor = artifact_descriptor(
            artifact_type,
            suffix=suffix,
            media_type=media_type,
        )
        dest = self._artifact_dir(render_id) / descriptor.filename
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        try:
            await asyncio.to_thread(dest.parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(tmp.write_bytes, data)
            await asyncio.to_thread(tmp.replace, dest)
        except OSError as exc:
            with contextlib.suppress(OSError):
                await asyncio.to_thread(tmp.unlink, missing_ok=True)
            raise StorageError(
                detail=f"Failed to publish artifact {artifact_type.value}",
                context={
                    "render_id": render_id,
                    "artifact": artifact_type.value,
                },
            ) from exc
        return str(dest)

    async def publish_file(
        self,
        render_id: str,
        artifact_type: ArtifactType,
        source_path: Path,
        *,
        suffix: str = "",
        media_type: str | None = None,
    ) -> str:
        validate_render_id(render_id)
        if not source_path.is_file():
            raise FileNotFoundError(source_path)

        descriptor = artifact_descriptor(
            artifact_type,
            suffix=suffix or source_path.suffix,
            media_type=media_type,
        )
        dest = self._artifact_dir(render_id) / descriptor.filename
        if source_path.resolve() == dest.resolve():
            return str(dest)

        tmp = dest.with_suffix(dest.suffix + ".tmp")
        try:
            await asyncio.to_thread(dest.parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(shutil.copyfile, source_path, tmp)
            await asyncio.to_thread(tmp.replace, dest)
        except OSError as exc:
            with contextlib.suppress(OSError):
                await asyncio.to_thread(tmp.unlink, missing_ok=True)
            raise StorageError(
                detail=f"Failed to publish artifact {artifact_type.value}",
                context={
                    "render_id": render_id,
                    "artifact": artifact_type.value,
                    "path": str(source_path),
                },
            ) from exc
        return str(dest)

    async def read_artifact(
        self,
        render_id: str,
        artifact_type: ArtifactType,
        *,
        suffix: str = "",
    ) -> bytes:
        validate_render_id(render_id)
        ws = self._workspace_dir(render_id)
        dest = self._artifact_path(ws, artifact_type, suffix)
        try:
            return await asyncio.to_thread(dest.read_bytes)
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise StorageError(
                detail=f"Failed to read artifact {artifact_type.value}",
                context={
                    "render_id": render_id,
                    "artifact": artifact_type.value,
                },
            ) from exc

    async def read_uri(self, uri: str) -> bytes:
        path = self._path_from_uri(uri)
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise StorageError(
                detail="Failed to read local artifact",
                context={"path": str(path)},
            ) from exc

    async def iter_uri(
        self,
        uri: str,
        *,
        chunk_size: int = 1024 * 1024,
    ) -> AsyncIterator[bytes]:
        path = self._path_from_uri(uri)
        try:
            with path.open("rb") as fh:
                while True:
                    chunk = await asyncio.to_thread(fh.read, chunk_size)
                    if not chunk:
                        break
                    yield chunk
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise StorageError(
                detail="Failed to stream local artifact",
                context={"path": str(path)},
            ) from exc

    async def exists_uri(self, uri: str) -> bool:
        path = self._path_from_uri(uri)
        return await asyncio.to_thread(path.is_file)

    async def presign_uri(self, uri: str, *, expires_in_seconds: int) -> str:
        raise StorageError(
            detail="Signed URLs are not supported for local storage",
            context={"uri": uri, "expires_in_seconds": expires_in_seconds},
        )

    async def list_artifacts(self, render_id: str) -> list[Path]:
        validate_render_id(render_id)
        ws = self._workspace_dir(render_id)
        if not ws.exists():
            return []
        try:
            return await asyncio.to_thread(
                lambda: sorted(p for p in ws.iterdir() if p.is_file()),
            )
        except OSError as exc:
            raise StorageError(
                detail=f"Failed to list artifacts for {render_id}",
                context={"render_id": render_id},
            ) from exc

    async def workspace_path(self, render_id: str) -> Path:
        validate_render_id(render_id)
        return self._workspace_dir(render_id)

    def _workspace_dir(self, render_id: str) -> Path:
        return self._root / render_id

    def _artifact_dir(self, render_id: str) -> Path:
        return self._artifact_root / render_id

    @staticmethod
    def _artifact_path(
        ws: Path,
        artifact_type: ArtifactType,
        suffix: str,
    ) -> Path:
        return ws / artifact_filename(artifact_type, suffix)

    def _path_from_uri(self, uri: str) -> Path:
        raw_path = uri.removeprefix("file://")
        path = Path(raw_path).expanduser().resolve()
        allowed_roots = (self._root, self._artifact_root)
        if not any(path.is_relative_to(root) for root in allowed_roots):
            raise StorageError(
                detail="Local artifact path is outside configured storage roots",
                context={"path": str(path)},
            )
        return path
