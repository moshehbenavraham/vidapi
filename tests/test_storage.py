from __future__ import annotations

from pathlib import Path

import pytest

from app.api.errors import StorageError
from app.storage.base import ArtifactType, StorageBackend
from app.storage.local import LocalStorage


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(workspace_root=tmp_path)


RENDER_ID = "render_test123"


class TestWorkspaceLifecycle:
    """Storage adapter workspace create/read/write/list cycle."""

    @pytest.mark.asyncio
    async def test_create_workspace_returns_path(
        self,
        storage: LocalStorage,
        tmp_path: Path,
    ) -> None:
        ws = await storage.create_workspace(RENDER_ID)
        assert ws.exists()
        assert ws.is_dir()
        assert ws == (tmp_path / RENDER_ID).resolve()
        assert storage.backend == StorageBackend.LOCAL

    @pytest.mark.asyncio
    async def test_create_workspace_idempotent(
        self,
        storage: LocalStorage,
    ) -> None:
        ws1 = await storage.create_workspace(RENDER_ID)
        ws2 = await storage.create_workspace(RENDER_ID)
        assert ws1 == ws2

    @pytest.mark.asyncio
    async def test_workspace_path_without_create(
        self,
        storage: LocalStorage,
        tmp_path: Path,
    ) -> None:
        ws = await storage.workspace_path(RENDER_ID)
        assert ws == (tmp_path / RENDER_ID).resolve()
        assert not ws.exists()


class TestArtifactWriteRead:
    """Write and read back each artifact type."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("artifact_type", list(ArtifactType))
    async def test_write_and_read_artifact(
        self,
        storage: LocalStorage,
        artifact_type: ArtifactType,
    ) -> None:
        await storage.create_workspace(RENDER_ID)
        data = b'{"test": true}'
        suffix = ".mp4" if artifact_type is ArtifactType.OUTPUT else ""

        path = await storage.write_artifact(
            RENDER_ID,
            artifact_type,
            data,
            suffix=suffix,
        )
        assert path.exists()

        read_back = await storage.read_artifact(
            RENDER_ID,
            artifact_type,
            suffix=suffix,
        )
        assert read_back == data

    @pytest.mark.asyncio
    async def test_write_artifact_without_workspace_raises(
        self,
        storage: LocalStorage,
    ) -> None:
        with pytest.raises(StorageError, match="does not exist"):
            await storage.write_artifact(
                "nonexistent_render",
                ArtifactType.INPUT,
                b"data",
            )

    @pytest.mark.asyncio
    async def test_read_missing_artifact_raises_file_not_found(
        self,
        storage: LocalStorage,
    ) -> None:
        await storage.create_workspace(RENDER_ID)
        with pytest.raises(FileNotFoundError):
            await storage.read_artifact(RENDER_ID, ArtifactType.INPUT)

    @pytest.mark.asyncio
    async def test_output_artifact_with_suffix(
        self,
        storage: LocalStorage,
    ) -> None:
        await storage.create_workspace(RENDER_ID)
        data = b"\x00\x00\x00"

        path = await storage.write_artifact(
            RENDER_ID,
            ArtifactType.OUTPUT,
            data,
            suffix=".gif",
        )
        assert path.name == "output.gif"

        read_back = await storage.read_artifact(
            RENDER_ID,
            ArtifactType.OUTPUT,
            suffix=".gif",
        )
        assert read_back == data


class TestArtifactList:
    """List artifacts in a workspace."""

    @pytest.mark.asyncio
    async def test_list_artifacts_empty_workspace(
        self,
        storage: LocalStorage,
    ) -> None:
        await storage.create_workspace(RENDER_ID)
        artifacts = await storage.list_artifacts(RENDER_ID)
        assert artifacts == []

    @pytest.mark.asyncio
    async def test_list_artifacts_with_files(
        self,
        storage: LocalStorage,
    ) -> None:
        await storage.create_workspace(RENDER_ID)
        await storage.write_artifact(
            RENDER_ID,
            ArtifactType.INPUT,
            b'{"timeline": {}}',
        )
        await storage.write_artifact(
            RENDER_ID,
            ArtifactType.LOG,
            b"render log content",
        )

        artifacts = await storage.list_artifacts(RENDER_ID)
        names = {a.name for a in artifacts}
        assert "input.json" in names
        assert "logs.txt" in names

    @pytest.mark.asyncio
    async def test_list_artifacts_nonexistent_workspace(
        self,
        storage: LocalStorage,
    ) -> None:
        artifacts = await storage.list_artifacts("does_not_exist")
        assert artifacts == []


class TestDeterministicPaths:
    """Paths are deterministic from render ID."""

    @pytest.mark.asyncio
    async def test_same_id_same_path(
        self,
        storage: LocalStorage,
    ) -> None:
        p1 = await storage.workspace_path("render_abc")
        p2 = await storage.workspace_path("render_abc")
        assert p1 == p2

    @pytest.mark.asyncio
    async def test_different_ids_different_paths(
        self,
        storage: LocalStorage,
    ) -> None:
        p1 = await storage.workspace_path("render_abc")
        p2 = await storage.workspace_path("render_xyz")
        assert p1 != p2


class TestDurableLocalArtifacts:
    @pytest.mark.asyncio
    async def test_publish_bytes_writes_to_artifact_root(
        self,
        tmp_path: Path,
    ) -> None:
        storage = LocalStorage(
            workspace_root=tmp_path / "scratch",
            artifact_root=tmp_path / "artifacts",
        )

        uri = await storage.publish_bytes(
            RENDER_ID,
            ArtifactType.INPUT,
            b'{"ok": true}',
        )

        assert Path(uri) == (tmp_path / "artifacts" / RENDER_ID / "input.json")
        assert await storage.exists_uri(uri)
        assert await storage.read_uri(uri) == b'{"ok": true}'

    @pytest.mark.asyncio
    async def test_publish_file_copies_to_artifact_root(
        self,
        tmp_path: Path,
    ) -> None:
        storage = LocalStorage(
            workspace_root=tmp_path / "scratch",
            artifact_root=tmp_path / "artifacts",
        )
        workspace = await storage.create_workspace(RENDER_ID)
        source = workspace / "source.mp4"
        source.write_bytes(b"video")

        uri = await storage.publish_file(
            RENDER_ID,
            ArtifactType.OUTPUT,
            source,
        )
        source.unlink()

        assert Path(uri).name == "output.mp4"
        assert await storage.read_uri(uri) == b"video"

    @pytest.mark.asyncio
    async def test_iter_uri_streams_chunks(self, tmp_path: Path) -> None:
        storage = LocalStorage(
            workspace_root=tmp_path / "scratch",
            artifact_root=tmp_path / "artifacts",
        )
        uri = await storage.publish_bytes(
            RENDER_ID,
            ArtifactType.LOG,
            b"abcdef",
        )

        chunks = [chunk async for chunk in storage.iter_uri(uri, chunk_size=2)]

        assert chunks == [b"ab", b"cd", b"ef"]

    @pytest.mark.asyncio
    async def test_read_uri_rejects_paths_outside_storage_roots(
        self,
        storage: LocalStorage,
        tmp_path: Path,
    ) -> None:
        outside = tmp_path.parent / "outside.txt"
        outside.write_text("secret", encoding="utf-8")

        with pytest.raises(StorageError, match="outside configured storage roots"):
            await storage.read_uri(str(outside))
