from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable


class StorageBackend(StrEnum):
    LOCAL = "local"
    S3 = "s3"


class StorageUrlMode(StrEnum):
    PROXY = "proxy"
    SIGNED = "signed"
    PUBLIC = "public"


class ArtifactType(StrEnum):
    INPUT = "input.json"
    EXPANDED = "expanded.json"
    COMPILED = "compiled.editly.json"
    OUTPUT = "output"
    MANIFEST = "manifest.json"
    POSTER = "poster.jpg"
    CAPTION_SIDECAR = "captions"
    REPLAY = "replay.json"
    LOG = "logs.txt"


@dataclass(frozen=True)
class ArtifactDescriptor:
    artifact_type: ArtifactType
    filename: str
    media_type: str


DEFAULT_OUTPUT_SUFFIX = ".mp4"
DEFAULT_CAPTION_SIDECAR_SUFFIX = ".srt"
RENDER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
ARTIFACT_SUFFIX_PATTERN = re.compile(r"^\.[A-Za-z0-9]+$")

ARTIFACT_MEDIA_TYPES: dict[ArtifactType, str] = {
    ArtifactType.INPUT: "application/json",
    ArtifactType.EXPANDED: "application/json",
    ArtifactType.COMPILED: "application/json",
    ArtifactType.OUTPUT: "video/mp4",
    ArtifactType.MANIFEST: "application/json",
    ArtifactType.POSTER: "image/jpeg",
    ArtifactType.CAPTION_SIDECAR: "application/x-subrip",
    ArtifactType.REPLAY: "application/json",
    ArtifactType.LOG: "text/plain; charset=utf-8",
}


def validate_render_id(render_id: str) -> str:
    """Return a render ID after rejecting path-like or empty values."""
    if not RENDER_ID_PATTERN.fullmatch(render_id):
        msg = f"Invalid render ID for artifact storage: {render_id!r}"
        raise ValueError(msg)
    return render_id


def normalize_artifact_suffix(suffix: str) -> str:
    """Return a safe extension suffix for artifact filenames."""
    if not suffix:
        return ""
    if not ARTIFACT_SUFFIX_PATTERN.fullmatch(suffix):
        msg = f"Invalid artifact suffix: {suffix!r}"
        raise ValueError(msg)
    return suffix.lower()


def artifact_filename(artifact_type: ArtifactType, suffix: str = "") -> str:
    """Return the deterministic filename for an artifact type."""
    normalized_suffix = normalize_artifact_suffix(suffix)
    if artifact_type is ArtifactType.OUTPUT:
        return f"{artifact_type.value}{normalized_suffix or DEFAULT_OUTPUT_SUFFIX}"
    if artifact_type is ArtifactType.CAPTION_SIDECAR:
        return (
            f"{artifact_type.value}"
            f"{normalized_suffix or DEFAULT_CAPTION_SIDECAR_SUFFIX}"
        )
    return artifact_type.value


def artifact_media_type(artifact_type: ArtifactType) -> str:
    return ARTIFACT_MEDIA_TYPES[artifact_type]


def artifact_descriptor(
    artifact_type: ArtifactType,
    *,
    suffix: str = "",
    media_type: str | None = None,
) -> ArtifactDescriptor:
    return ArtifactDescriptor(
        artifact_type=artifact_type,
        filename=artifact_filename(artifact_type, suffix),
        media_type=media_type or artifact_media_type(artifact_type),
    )


@runtime_checkable
class ArtifactStorageProtocol(Protocol):
    """Contract for local scratch workspaces and durable render artifacts."""

    @property
    def backend(self) -> StorageBackend:
        """Return the durable artifact backend identifier."""
        ...

    async def create_workspace(self, render_id: str) -> Path:
        """Create a workspace directory for a render job.

        Returns the absolute path to the workspace root.
        Must be idempotent -- calling twice with the same ID returns the
        same path without error.
        """
        ...

    async def write_artifact(
        self,
        render_id: str,
        artifact_type: ArtifactType,
        data: bytes,
        *,
        suffix: str = "",
    ) -> Path:
        """Write an artifact to the render workspace.

        ``suffix`` overrides the file extension for ArtifactType.OUTPUT
        (e.g. ".mp4", ".gif").  Ignored for other artifact types.

        Returns the absolute path to the written file.
        """
        ...

    async def publish_bytes(
        self,
        render_id: str,
        artifact_type: ArtifactType,
        data: bytes,
        *,
        suffix: str = "",
        media_type: str | None = None,
    ) -> str:
        """Persist artifact bytes in durable storage and return its URI."""
        ...

    async def publish_file(
        self,
        render_id: str,
        artifact_type: ArtifactType,
        source_path: Path,
        *,
        suffix: str = "",
        media_type: str | None = None,
    ) -> str:
        """Persist an existing local file in durable storage and return its URI."""
        ...

    async def read_artifact(
        self,
        render_id: str,
        artifact_type: ArtifactType,
        *,
        suffix: str = "",
    ) -> bytes:
        """Read an artifact from the render workspace.

        Raises ``FileNotFoundError`` if the artifact does not exist.
        """
        ...

    async def read_uri(self, uri: str) -> bytes:
        """Read a durable artifact by URI."""
        ...

    def iter_uri(
        self,
        uri: str,
        *,
        chunk_size: int = 1024 * 1024,
    ) -> AsyncIterator[bytes]:
        """Stream a durable artifact by URI without buffering it all."""
        ...

    async def exists_uri(self, uri: str) -> bool:
        """Return whether a durable artifact exists."""
        ...

    async def presign_uri(self, uri: str, *, expires_in_seconds: int) -> str:
        """Return a temporary URL for a durable artifact if supported."""
        ...

    async def list_artifacts(self, render_id: str) -> list[Path]:
        """Return absolute paths of all files in the render workspace."""
        ...

    async def workspace_path(self, render_id: str) -> Path:
        """Return the absolute workspace directory path for a render ID.

        Does NOT create the directory -- use ``create_workspace`` for that.
        """
        ...


StorageProtocol = ArtifactStorageProtocol
