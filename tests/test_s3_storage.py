from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from app.api.errors import StorageError
from app.storage.base import ArtifactType, StorageBackend
from app.storage.s3 import S3Storage


class FakeBody:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0
        self.closed = False

    def read(self, size: int | None = None) -> bytes:
        if size is None:
            self._offset = len(self._data)
            return self._data
        chunk = self._data[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def close(self) -> None:
        self.closed = True


def _storage(tmp_path: Path, client: MagicMock | None = None) -> S3Storage:
    return S3Storage(
        workspace_root=tmp_path / "scratch",
        bucket="vidapi-renders",
        region="us-east-1",
        object_prefix="renders",
        client=client or MagicMock(),
    )


def _missing_object_error() -> ClientError:
    return ClientError(
        {
            "Error": {"Code": "NoSuchKey", "Message": "not found"},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        },
        "GetObject",
    )


def test_s3_backend_identifier(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    assert storage.backend == StorageBackend.S3


def test_object_key_is_deterministic_and_render_scoped(tmp_path: Path) -> None:
    storage = _storage(tmp_path)

    key = storage.object_key(
        "render_abc123",
        ArtifactType.OUTPUT,
        suffix=".mp4",
    )

    assert key == "renders/render_abc123/output.mp4"


def test_object_key_rejects_path_like_render_id(tmp_path: Path) -> None:
    storage = _storage(tmp_path)

    with pytest.raises(ValueError, match="Invalid render ID"):
        storage.object_key("../bad", ArtifactType.INPUT)


@pytest.mark.asyncio
async def test_publish_bytes_uploads_object(tmp_path: Path) -> None:
    client = MagicMock()
    storage = _storage(tmp_path, client)

    uri = await storage.publish_bytes(
        "render_abc123",
        ArtifactType.INPUT,
        b"{}",
    )

    assert uri == "s3://vidapi-renders/renders/render_abc123/input.json"
    client.put_object.assert_called_once_with(
        Bucket="vidapi-renders",
        Key="renders/render_abc123/input.json",
        Body=b"{}",
        ContentType="application/json",
    )


@pytest.mark.asyncio
async def test_publish_file_uploads_with_content_type(tmp_path: Path) -> None:
    client = MagicMock()
    storage = _storage(tmp_path, client)
    source = tmp_path / "output.mp4"
    source.write_bytes(b"video")

    uri = await storage.publish_file(
        "render_abc123",
        ArtifactType.OUTPUT,
        source,
    )

    assert uri == "s3://vidapi-renders/renders/render_abc123/output.mp4"
    client.upload_file.assert_called_once_with(
        str(source),
        "vidapi-renders",
        "renders/render_abc123/output.mp4",
        ExtraArgs={"ContentType": "video/mp4"},
    )


@pytest.mark.asyncio
async def test_read_uri_reads_and_closes_body(tmp_path: Path) -> None:
    body = FakeBody(b"artifact")
    client = MagicMock()
    client.get_object.return_value = {"Body": body}
    storage = _storage(tmp_path, client)

    data = await storage.read_uri(
        "s3://vidapi-renders/renders/render_abc123/input.json"
    )

    assert data == b"artifact"
    assert body.closed is True


@pytest.mark.asyncio
async def test_iter_uri_streams_chunks(tmp_path: Path) -> None:
    client = MagicMock()
    client.get_object.return_value = {"Body": FakeBody(b"abcdef")}
    storage = _storage(tmp_path, client)

    chunks = [
        chunk
        async for chunk in storage.iter_uri(
            "s3://vidapi-renders/renders/render_abc123/logs.txt",
            chunk_size=2,
        )
    ]

    assert chunks == [b"ab", b"cd", b"ef"]


@pytest.mark.asyncio
async def test_read_uri_missing_object_raises_file_not_found(tmp_path: Path) -> None:
    client = MagicMock()
    client.get_object.side_effect = _missing_object_error()
    storage = _storage(tmp_path, client)

    with pytest.raises(FileNotFoundError):
        await storage.read_uri("s3://vidapi-renders/renders/render_abc123/input.json")


@pytest.mark.asyncio
async def test_exists_uri_returns_false_for_missing_object(tmp_path: Path) -> None:
    client = MagicMock()
    client.head_object.side_effect = _missing_object_error()
    storage = _storage(tmp_path, client)

    exists = await storage.exists_uri(
        "s3://vidapi-renders/renders/render_abc123/input.json"
    )

    assert exists is False


@pytest.mark.asyncio
async def test_presign_uri_delegates_to_client(tmp_path: Path) -> None:
    client = MagicMock()
    client.generate_presigned_url.return_value = "https://signed.example/object"
    storage = _storage(tmp_path, client)

    url = await storage.presign_uri(
        "s3://vidapi-renders/renders/render_abc123/output.mp4",
        expires_in_seconds=300,
    )

    assert url == "https://signed.example/object"
    client.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={
            "Bucket": "vidapi-renders",
            "Key": "renders/render_abc123/output.mp4",
        },
        ExpiresIn=300,
    )


@pytest.mark.asyncio
async def test_wrong_bucket_uri_raises_storage_error(tmp_path: Path) -> None:
    storage = _storage(tmp_path)

    with pytest.raises(StorageError, match="bucket does not match"):
        await storage.exists_uri("s3://other-bucket/renders/render_abc/input.json")
