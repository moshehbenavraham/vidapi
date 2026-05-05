from __future__ import annotations

from contextlib import asynccontextmanager
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.api.deps import get_session, get_storage_backend, get_storage_url_resolver
from app.db import render_crud
from app.main import create_app
from app.models.composition import CaptionFormat, CaptionMode, OutputFormat, PosterMode
from app.models.output_artifacts import (
    StoredCaptionMetadata,
    StoredOutputMetadata,
    StoredPosterMetadata,
)
from app.models.render import RenderStatus
from app.services.merge import MergeError, expand_merge_variables
from app.storage.base import ArtifactType, StorageBackend, StorageUrlMode
from app.storage.urls import StorageUrlResolver

# ---------------------------------------------------------------------------
# Merge variable expansion unit tests
# ---------------------------------------------------------------------------


class TestMergeVariables:
    def test_no_merge_returns_unchanged(self):
        original = '{"text": "hello"}'
        assert expand_merge_variables(original, None) == original

    def test_empty_merge_returns_unchanged(self):
        original = '{"text": "hello"}'
        assert expand_merge_variables(original, {}) == original

    def test_substitutes_string_variable(self):
        template = '{"text": "Hello {{name}}"}'
        result = expand_merge_variables(template, {"name": "World"})
        assert result == '{"text": "Hello World"}'

    def test_substitutes_numeric_variable(self):
        template = '{"count": "{{total}}"}'
        result = expand_merge_variables(template, {"total": 42})
        assert result == '{"count": "42"}'

    def test_substitutes_boolean_variable(self):
        template = '{"active": "{{flag}}"}'
        result = expand_merge_variables(template, {"flag": True})
        assert result == '{"active": "true"}'

    def test_substitutes_multiple_variables(self):
        template = '{"a": "{{x}}", "b": "{{y}}"}'
        result = expand_merge_variables(template, {"x": "1", "y": "2"})
        assert result == '{"a": "1", "b": "2"}'

    def test_raises_on_missing_variable(self):
        template = '{"text": "Hello {{missing}}"}'
        with pytest.raises(MergeError, match="missing"):
            expand_merge_variables(template, {"other": "val"})


# ---------------------------------------------------------------------------
# POST /v1/renders contract tests
# ---------------------------------------------------------------------------


class FakeS3StorageForRoutes:
    backend = StorageBackend.S3

    def __init__(self, signed_url: str = "https://signed.example/output.mp4") -> None:
        self.presign_uri = AsyncMock(return_value=signed_url)


async def _mark_render_succeeded(session, render_id: str) -> None:
    await render_crud.update_render_status(session, render_id, RenderStatus.FETCHING)
    await render_crud.update_render_status(session, render_id, RenderStatus.COMPILING)
    await render_crud.update_render_status(session, render_id, RenderStatus.RENDERING)
    await render_crud.update_render_status(session, render_id, RenderStatus.UPLOADING)
    await render_crud.update_render_status(session, render_id, RenderStatus.SUCCEEDED)


@asynccontextmanager
async def _client_with_storage(db_engine, storage, resolver):
    app = create_app()

    async def _override_session():
        async with SQLModelAsyncSession(db_engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_storage_backend] = lambda: storage
    app.dependency_overrides[get_storage_url_resolver] = lambda: resolver

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        follow_redirects=False,
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


class TestPostRenders:
    @pytest.mark.asyncio
    async def test_valid_composition_returns_202(
        self, client: AsyncClient, sample_composition: dict
    ):
        response = await client.post("/v1/renders", json=sample_composition)
        assert response.status_code == 202
        data = response.json()
        assert "id" in data
        assert data["id"].startswith("render_")
        assert "status" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_invalid_composition_returns_422(self, client: AsyncClient):
        response = await client.post("/v1/renders", json={"bad": "data"})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_tracks_returns_422(self, client: AsyncClient):
        payload = {"timeline": {"tracks": []}}
        response = await client.post("/v1/renders", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_clip_length_returns_422(self, client: AsyncClient):
        payload = {
            "timeline": {
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "image",
                                    "src": "http://example.com/img.jpg",
                                },
                                "start": 0.0,
                            }
                        ]
                    }
                ]
            }
        }
        response = await client.post("/v1/renders", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_unknown_renderer_returns_stable_error(
        self,
        client: AsyncClient,
        sample_composition: dict,
    ):
        payload = deepcopy(sample_composition)
        payload["renderer"] = "unknown-renderer"

        response = await client.post("/v1/renders", json=payload)

        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] == "UNSUPPORTED_RENDERER"
        assert body["error"]["context"]["renderer"] == "unknown-renderer"

    @pytest.mark.asyncio
    async def test_png_sequence_fps_limit_returns_stable_error(
        self,
        client: AsyncClient,
        sample_composition: dict,
    ):
        payload = deepcopy(sample_composition)
        payload["output"]["format"] = "png-sequence"
        payload["output"]["width"] = 320
        payload["output"]["height"] = 180
        payload["output"]["fps"] = 31

        response = await client.post("/v1/renders", json=payload)

        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] == "COMPOSITION_LIMIT_EXCEEDED"
        assert body["error"]["context"]["field"] == "output.png_sequence.fps"

    @pytest.mark.asyncio
    async def test_valid_advanced_transition_returns_202(
        self,
        client: AsyncClient,
        sample_composition: dict,
    ):
        payload = deepcopy(sample_composition)
        payload["timeline"]["tracks"] = [
            {
                "clips": [
                    {
                        "asset": {"type": "image", "src": "https://example.com/a.png"},
                        "start": 0.0,
                        "length": 1.0,
                        "transition": {"name": "wipe_left", "duration": 0.25},
                    },
                    {
                        "asset": {"type": "image", "src": "https://example.com/b.png"},
                        "start": 1.0,
                        "length": 1.0,
                    },
                ]
            }
        ]

        response = await client.post("/v1/renders", json=payload)

        assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_invalid_advanced_transition_timing_returns_422(
        self,
        client: AsyncClient,
        sample_composition: dict,
    ):
        payload = deepcopy(sample_composition)
        payload["timeline"]["tracks"] = [
            {
                "clips": [
                    {
                        "asset": {"type": "image", "src": "https://example.com/a.png"},
                        "start": 0.0,
                        "length": 2.0,
                        "transition": {"name": "cross_zoom", "duration": 1.5},
                    },
                    {
                        "asset": {"type": "image", "src": "https://example.com/b.png"},
                        "start": 2.0,
                        "length": 1.0,
                    },
                ]
            }
        ]

        response = await client.post("/v1/renders", json=payload)

        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] == "COMPOSITION_LIMIT_EXCEEDED"
        assert body["error"]["context"]["field"] == (
            "timeline.tracks[0].clips[0].transition.duration"
        )


# ---------------------------------------------------------------------------
# GET /v1/renders/{id} contract tests
# ---------------------------------------------------------------------------


class TestGetRender:
    @pytest.mark.asyncio
    async def test_unknown_id_returns_404(self, client: AsyncClient):
        response = await client.get("/v1/renders/nonexistent_id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_valid_render_returns_status(
        self, client: AsyncClient, sample_composition: dict
    ):
        post_resp = await client.post("/v1/renders", json=sample_composition)
        assert post_resp.status_code == 202
        render_id = post_resp.json()["id"]

        get_resp = await client.get(f"/v1/renders/{render_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["id"] == render_id
        assert "status" in data
        assert "progress" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_succeeded_render_has_url(
        self, client: AsyncClient, sample_composition: dict
    ):
        post_resp = await client.post("/v1/renders", json=sample_composition)
        render_id = post_resp.json()["id"]

        get_resp = await client.get(f"/v1/renders/{render_id}")
        data = get_resp.json()
        if data["status"] == "succeeded":
            assert data["url"] is not None
            assert "/download" in data["url"]

    @pytest.mark.asyncio
    async def test_succeeded_render_has_output_metadata(
        self,
        client: AsyncClient,
        db_session,
        test_storage,
    ):
        render = await render_crud.create_render(db_session)
        render_id = render.id
        output_uri = await test_storage.publish_bytes(
            render_id,
            ArtifactType.OUTPUT,
            b"webm-bytes",
            suffix=".webm",
            media_type="video/webm",
        )
        await render_crud.update_render_output_metadata(
            db_session,
            render_id,
            metadata=StoredOutputMetadata(
                format=OutputFormat.WEBM,
                media_type="video/webm",
                filename=f"{render_id}.webm",
                duration_seconds=1.25,
            ),
            output_path=output_uri,
        )
        await _mark_render_succeeded(db_session, render_id)

        response = await client.get(f"/v1/renders/{render_id}")

        assert response.status_code == 200
        output = response.json()["output"]
        assert output["format"] == "webm"
        assert output["media_type"] == "video/webm"
        assert output["filename"] == f"{render_id}.webm"
        assert response.json()["duration"] == 1.25

    @pytest.mark.asyncio
    async def test_succeeded_render_has_caption_and_poster_metadata(
        self,
        client: AsyncClient,
        db_session,
        test_storage,
    ):
        render = await render_crud.create_render(db_session)
        render_id = render.id
        output_uri = await test_storage.publish_bytes(
            render_id,
            ArtifactType.OUTPUT,
            b"video-bytes",
        )
        sidecar_uri = await test_storage.publish_bytes(
            render_id,
            ArtifactType.CAPTION_SIDECAR,
            b"caption-bytes",
            suffix=".srt",
            media_type="application/x-subrip",
        )
        poster_uri = await test_storage.publish_bytes(
            render_id,
            ArtifactType.POSTER,
            b"poster-bytes",
        )
        await render_crud.update_render_output_metadata(
            db_session,
            render_id,
            metadata=StoredOutputMetadata(
                format=OutputFormat.MP4,
                media_type="video/mp4",
                filename=f"{render_id}.mp4",
            ),
            output_path=output_uri,
        )
        await render_crud.update_render_caption_metadata(
            db_session,
            render_id,
            metadata=StoredCaptionMetadata(
                mode=CaptionMode.SIDECAR,
                format=CaptionFormat.SRT,
                sidecar_media_type="application/x-subrip",
                sidecar_filename=f"{render_id}-captions.srt",
                cue_count=2,
                burned_in=False,
            ),
            sidecar_path=sidecar_uri,
        )
        await render_crud.update_render_poster_metadata(
            db_session,
            render_id,
            metadata=StoredPosterMetadata(
                mode=PosterMode.TIMESTAMP,
                timestamp_seconds=1.25,
                media_type="image/jpeg",
                filename=f"{render_id}.jpg",
            ),
            poster_path=poster_uri,
        )
        await _mark_render_succeeded(db_session, render_id)

        response = await client.get(f"/v1/renders/{render_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["captions"] == {
            "mode": "sidecar",
            "format": "srt",
            "cue_count": 2,
            "burned_in": False,
            "sidecar_url": f"/v1/renders/{render_id}/captions",
            "media_type": "application/x-subrip",
            "filename": f"{render_id}-captions.srt",
        }
        assert body["poster_metadata"] == {
            "mode": "timestamp",
            "timestamp_seconds": 1.25,
            "url": f"/v1/renders/{render_id}/poster",
            "media_type": "image/jpeg",
            "filename": f"{render_id}.jpg",
        }


# ---------------------------------------------------------------------------
# GET /v1/renders/{id}/download contract tests
# ---------------------------------------------------------------------------


class TestDownloadRender:
    @pytest.mark.asyncio
    async def test_unknown_id_returns_404(self, client: AsyncClient):
        response = await client.get("/v1/renders/nonexistent_id/download")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_download_succeeded_render(
        self, client: AsyncClient, sample_composition: dict
    ):
        post_resp = await client.post("/v1/renders", json=sample_composition)
        assert post_resp.status_code == 202
        render_id = post_resp.json()["id"]

        get_resp = await client.get(f"/v1/renders/{render_id}")
        status = get_resp.json()["status"]

        if status == "succeeded":
            dl_resp = await client.get(f"/v1/renders/{render_id}/download")
            assert dl_resp.status_code == 200
            assert dl_resp.headers.get("content-type", "").startswith("video/")

    @pytest.mark.asyncio
    async def test_proxy_download_streams_storage_artifact(
        self,
        client: AsyncClient,
        db_session,
        test_storage,
    ):
        render = await render_crud.create_render(db_session)
        render_id = render.id
        output_uri = await test_storage.publish_bytes(
            render_id,
            ArtifactType.OUTPUT,
            b"video-bytes",
        )
        await render_crud.update_render_paths(
            db_session,
            render_id,
            output_path=output_uri,
        )
        await _mark_render_succeeded(db_session, render_id)

        response = await client.get(f"/v1/renders/{render_id}/download")

        assert response.status_code == 200
        assert response.content == b"video-bytes"
        assert response.headers["content-disposition"].startswith("attachment")

    @pytest.mark.asyncio
    async def test_proxy_download_uses_output_metadata_headers(
        self,
        client: AsyncClient,
        db_session,
        test_storage,
    ):
        render = await render_crud.create_render(db_session)
        render_id = render.id
        output_uri = await test_storage.publish_bytes(
            render_id,
            ArtifactType.OUTPUT,
            b"webm-bytes",
            suffix=".webm",
            media_type="video/webm",
        )
        await render_crud.update_render_output_metadata(
            db_session,
            render_id,
            metadata=StoredOutputMetadata(
                format=OutputFormat.WEBM,
                media_type="video/webm",
                filename=f"{render_id}.webm",
            ),
            output_path=output_uri,
        )
        await _mark_render_succeeded(db_session, render_id)

        response = await client.get(f"/v1/renders/{render_id}/download")

        assert response.status_code == 200
        assert response.content == b"webm-bytes"
        assert response.headers["content-type"].startswith("video/webm")
        assert f'filename="{render_id}.webm"' in response.headers["content-disposition"]

    @pytest.mark.asyncio
    async def test_head_download_returns_output_headers_without_body(
        self,
        client: AsyncClient,
        db_session,
        test_storage,
    ):
        render = await render_crud.create_render(db_session)
        render_id = render.id
        output_uri = await test_storage.publish_bytes(
            render_id,
            ArtifactType.OUTPUT,
            b"video-bytes",
        )
        await render_crud.update_render_output_metadata(
            db_session,
            render_id,
            metadata=StoredOutputMetadata(
                format=OutputFormat.MP4,
                media_type="video/mp4",
                filename=f"{render_id}.mp4",
            ),
            output_path=output_uri,
        )
        await _mark_render_succeeded(db_session, render_id)

        response = await client.head(f"/v1/renders/{render_id}/download")

        assert response.status_code == 200
        assert response.content == b""
        assert response.headers["content-type"].startswith("video/mp4")
        assert f'filename="{render_id}.mp4"' in response.headers["content-disposition"]

    @pytest.mark.asyncio
    async def test_manifest_artifact_endpoint_streams_metadata(
        self,
        client: AsyncClient,
        db_session,
        test_storage,
    ):
        render = await render_crud.create_render(db_session)
        render_id = render.id
        output_uri = await test_storage.publish_bytes(
            render_id,
            ArtifactType.OUTPUT,
            b"zip-bytes",
            suffix=".zip",
            media_type="application/zip",
        )
        manifest_uri = await test_storage.publish_bytes(
            render_id,
            ArtifactType.MANIFEST,
            b'{"frame_count": 2}',
        )
        await render_crud.update_render_output_metadata(
            db_session,
            render_id,
            metadata=StoredOutputMetadata(
                format=OutputFormat.PNG_SEQUENCE,
                media_type="application/zip",
                filename=f"{render_id}.zip",
                frame_count=2,
                manifest_path=manifest_uri,
            ),
            output_path=output_uri,
        )

        response = await client.get(f"/v1/renders/{render_id}/artifacts/manifest.json")

        assert response.status_code == 200
        assert response.content == b'{"frame_count": 2}'
        assert response.headers["content-type"].startswith("application/json")

    @pytest.mark.asyncio
    async def test_generic_artifact_endpoint_streams_persisted_artifacts(
        self,
        client: AsyncClient,
        db_session,
        test_storage,
    ):
        render = await render_crud.create_render(db_session)
        render_id = render.id
        input_uri = await test_storage.publish_bytes(
            render_id,
            ArtifactType.INPUT,
            b'{"input": true}',
        )
        output_uri = await test_storage.publish_bytes(
            render_id,
            ArtifactType.OUTPUT,
            b"video-bytes",
        )
        poster_uri = await test_storage.publish_bytes(
            render_id,
            ArtifactType.POSTER,
            b"poster-bytes",
        )
        replay_uri = await test_storage.publish_bytes(
            render_id,
            ArtifactType.REPLAY,
            b'{"replay": true}',
        )
        log_uri = await test_storage.publish_bytes(
            render_id,
            ArtifactType.LOG,
            b"log-bytes",
        )
        await render_crud.update_render_paths(
            db_session,
            render_id,
            input_path=input_uri,
            replay_path=replay_uri,
            log_path=log_uri,
        )
        await render_crud.update_render_output_metadata(
            db_session,
            render_id,
            metadata=StoredOutputMetadata(
                format=OutputFormat.MP4,
                media_type="video/mp4",
                filename=f"{render_id}.mp4",
            ),
            output_path=output_uri,
        )
        await render_crud.update_render_poster_metadata(
            db_session,
            render_id,
            metadata=StoredPosterMetadata(
                mode=PosterMode.DEFAULT,
                media_type="image/jpeg",
                filename=f"{render_id}.jpg",
            ),
            poster_path=poster_uri,
        )

        expected = {
            "input": b'{"input": true}',
            "input.json": b'{"input": true}',
            "output": b"video-bytes",
            "output.mp4": b"video-bytes",
            f"{render_id}.mp4": b"video-bytes",
            "poster": b"poster-bytes",
            "poster.jpg": b"poster-bytes",
            f"{render_id}.jpg": b"poster-bytes",
            "replay": b'{"replay": true}',
            "replay.json": b'{"replay": true}',
            "logs": b"log-bytes",
            "logs.txt": b"log-bytes",
        }

        for artifact_name, content in expected.items():
            response = await client.get(
                f"/v1/renders/{render_id}/artifacts/{artifact_name}"
            )
            assert response.status_code == 200, artifact_name
            assert response.content == content

    @pytest.mark.asyncio
    async def test_generic_artifact_endpoint_returns_404_for_unknown_name(
        self,
        client: AsyncClient,
        db_session,
    ):
        render = await render_crud.create_render(db_session)

        response = await client.get(f"/v1/renders/{render.id}/artifacts/unknown.txt")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_poster_endpoint_streams_storage_artifact(
        self,
        client: AsyncClient,
        db_session,
        test_storage,
    ):
        render = await render_crud.create_render(db_session)
        render_id = render.id
        poster_uri = await test_storage.publish_bytes(
            render_id,
            ArtifactType.POSTER,
            b"poster-bytes",
        )
        await render_crud.update_render_paths(
            db_session,
            render_id,
            poster_path=poster_uri,
        )

        response = await client.get(f"/v1/renders/{render_id}/poster")

        assert response.status_code == 200
        assert response.content == b"poster-bytes"
        assert response.headers["content-type"].startswith("image/jpeg")

    @pytest.mark.asyncio
    async def test_proxy_download_missing_artifact_returns_404(
        self,
        client: AsyncClient,
        db_session,
        test_storage,
    ):
        render = await render_crud.create_render(db_session)
        render_id = render.id
        missing_path = (await test_storage.workspace_path(render_id)) / "output.mp4"
        missing_uri = str(missing_path)
        await render_crud.update_render_paths(
            db_session,
            render_id,
            output_path=missing_uri,
        )
        await _mark_render_succeeded(db_session, render_id)

        response = await client.get(f"/v1/renders/{render_id}/download")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_caption_sidecar_endpoint_streams_storage_artifact(
        self,
        client: AsyncClient,
        db_session,
        test_storage,
    ):
        render = await render_crud.create_render(db_session)
        render_id = render.id
        sidecar_uri = await test_storage.publish_bytes(
            render_id,
            ArtifactType.CAPTION_SIDECAR,
            b"1\n00:00:00,000 --> 00:00:01,000\nHello\n",
            suffix=".srt",
            media_type="application/x-subrip",
        )
        await render_crud.update_render_caption_metadata(
            db_session,
            render_id,
            metadata=StoredCaptionMetadata(
                mode=CaptionMode.SIDECAR,
                format=CaptionFormat.SRT,
                sidecar_media_type="application/x-subrip",
                sidecar_filename=f"{render_id}-captions.srt",
                cue_count=1,
                burned_in=False,
            ),
            sidecar_path=sidecar_uri,
        )
        await _mark_render_succeeded(db_session, render_id)

        response = await client.get(f"/v1/renders/{render_id}/captions")

        assert response.status_code == 200
        assert response.content.startswith(b"1\n00:00:00,000")
        assert response.headers["content-type"].startswith("application/x-subrip")
        assert (
            f'filename="{render_id}-captions.srt"'
            in response.headers["content-disposition"]
        )

    @pytest.mark.asyncio
    async def test_signed_download_endpoint_redirects(
        self,
        db_engine,
        db_session,
    ):
        render = await render_crud.create_render(db_session)
        render_id = render.id
        output_uri = "s3://vidapi-renders/renders/render_abc/output.mp4"
        await render_crud.update_render_paths(
            db_session,
            render_id,
            output_path=output_uri,
        )
        await _mark_render_succeeded(db_session, render_id)

        storage = FakeS3StorageForRoutes("https://signed.example/output.mp4?sig=abc")
        resolver = StorageUrlResolver(
            storage=storage,  # type: ignore[arg-type]
            url_mode=StorageUrlMode.SIGNED,
            signed_url_expiry_seconds=900,
        )

        async with _client_with_storage(db_engine, storage, resolver) as ac:
            response = await ac.get(f"/v1/renders/{render_id}/download")

        assert response.status_code == 307
        assert response.headers["location"] == (
            "https://signed.example/output.mp4?sig=abc"
        )

    @pytest.mark.asyncio
    async def test_public_poster_endpoint_redirects(
        self,
        db_engine,
        db_session,
    ):
        render = await render_crud.create_render(db_session)
        render_id = render.id
        poster_uri = "s3://vidapi-renders/renders/render_abc/poster.jpg"
        await render_crud.update_render_paths(
            db_session,
            render_id,
            poster_path=poster_uri,
        )

        storage = FakeS3StorageForRoutes()
        resolver = StorageUrlResolver(
            storage=storage,  # type: ignore[arg-type]
            url_mode=StorageUrlMode.PUBLIC,
            signed_url_expiry_seconds=900,
            public_base_url="https://cdn.example.com",
        )

        async with _client_with_storage(db_engine, storage, resolver) as ac:
            response = await ac.get(f"/v1/renders/{render_id}/poster")

        assert response.status_code == 307
        assert response.headers["location"] == (
            "https://cdn.example.com/renders/render_abc/poster.jpg"
        )


# ---------------------------------------------------------------------------
# Golden-path end-to-end integration test
# ---------------------------------------------------------------------------


class TestGoldenPath:
    @pytest.mark.asyncio
    async def test_full_render_lifecycle(
        self,
        client: AsyncClient,
        sample_composition: dict,
        test_storage,
    ):
        """Submit composition -> render succeeds -> poll status -> download."""
        post_resp = await client.post("/v1/renders", json=sample_composition)
        assert post_resp.status_code == 202
        post_data = post_resp.json()
        render_id = post_data["id"]
        assert render_id.startswith("render_")

        get_resp = await client.get(f"/v1/renders/{render_id}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["id"] == render_id
        assert get_data["status"] in ("succeeded", "failed")

        if get_data["status"] == "succeeded":
            assert get_data["url"] is not None
            assert get_data["progress"] == 100

            dl_resp = await client.get(f"/v1/renders/{render_id}/download")
            assert dl_resp.status_code == 200

            workspace = test_storage._workspace_dir(render_id)
            expected_files = ["input.json", "expanded.json"]
            for fname in expected_files:
                fpath = workspace / fname
                assert fpath.exists(), f"Missing artifact: {fname}"
