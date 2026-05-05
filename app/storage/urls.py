from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlsplit

from app.api.errors import StorageError
from app.models.output_artifacts import (
    RenderCaptionMetadata,
    RenderOutputMetadata,
    RenderPosterMetadata,
    caption_metadata_from_render,
    output_metadata_from_render,
    poster_metadata_from_render,
)
from app.models.render import RenderStatus
from app.storage.base import (
    ArtifactStorageProtocol,
    ArtifactType,
    StorageBackend,
    StorageUrlMode,
)


class StorageUrlResolver:
    """Resolve stored artifact URIs to client-facing render artifact URLs."""

    def __init__(
        self,
        *,
        storage: ArtifactStorageProtocol,
        url_mode: StorageUrlMode,
        signed_url_expiry_seconds: int,
        public_base_url: str = "",
        api_prefix: str = "/v1",
        forbidden_public_fragments: tuple[str, ...] = (),
        forbidden_signed_fragments: tuple[str, ...] = (),
    ) -> None:
        self._storage = storage
        self._url_mode = url_mode
        self._signed_url_expiry_seconds = signed_url_expiry_seconds
        self._public_base_url = public_base_url.rstrip("/")
        self._api_prefix = api_prefix.rstrip("/")
        self._forbidden_public_fragments = tuple(
            fragment for fragment in forbidden_public_fragments if fragment
        )
        self._forbidden_signed_fragments = tuple(
            fragment for fragment in forbidden_signed_fragments if fragment
        )

    @property
    def url_mode(self) -> StorageUrlMode:
        return self._url_mode

    def proxy_url(self, render_id: str, artifact_type: ArtifactType) -> str:
        encoded_render_id = quote(render_id, safe="")
        if artifact_type is ArtifactType.POSTER:
            return f"{self._api_prefix}/renders/{encoded_render_id}/poster"
        if artifact_type is ArtifactType.CAPTION_SIDECAR:
            return f"{self._api_prefix}/renders/{encoded_render_id}/captions"
        if artifact_type is ArtifactType.OUTPUT:
            return f"{self._api_prefix}/renders/{encoded_render_id}/download"
        encoded_artifact = quote(artifact_type.value, safe="")
        return (
            f"{self._api_prefix}/renders/{encoded_render_id}/artifacts/"
            f"{encoded_artifact}"
        )

    async def output_url(self, render: Any) -> str | None:
        if RenderStatus(render.status) != RenderStatus.SUCCEEDED:
            return None
        if not render.output_path:
            return None
        return await self.artifact_url(
            render.id,
            render.output_path,
            ArtifactType.OUTPUT,
        )

    async def poster_url(self, render: Any) -> str | None:
        if not render.poster_path:
            return None
        return await self.artifact_url(
            render.id,
            render.poster_path,
            ArtifactType.POSTER,
        )

    async def caption_sidecar_url(self, render: Any) -> str | None:
        sidecar_path = getattr(render, "caption_sidecar_path", None)
        if not sidecar_path:
            return None
        return await self.artifact_url(
            render.id,
            sidecar_path,
            ArtifactType.CAPTION_SIDECAR,
        )

    async def manifest_url(self, render: Any) -> str | None:
        manifest_path = getattr(render, "output_manifest_path", None)
        if not manifest_path:
            return None
        return await self.artifact_url(
            render.id,
            manifest_path,
            ArtifactType.MANIFEST,
        )

    async def output_metadata(self, render: Any) -> RenderOutputMetadata | None:
        return output_metadata_from_render(
            render,
            manifest_url=await self.manifest_url(render),
        )

    async def caption_metadata(self, render: Any) -> RenderCaptionMetadata | None:
        return caption_metadata_from_render(
            render,
            sidecar_url=await self.caption_sidecar_url(render),
        )

    async def poster_metadata(self, render: Any) -> RenderPosterMetadata | None:
        poster_url = await self.poster_url(render)
        return poster_metadata_from_render(render, poster_url=poster_url)

    async def artifact_url(
        self,
        render_id: str,
        artifact_uri: str,
        artifact_type: ArtifactType,
    ) -> str:
        if self._url_mode is StorageUrlMode.PROXY:
            return self.proxy_url(render_id, artifact_type)

        if self._url_mode is StorageUrlMode.SIGNED:
            if self._storage.backend is StorageBackend.S3:
                url = await self._storage.presign_uri(
                    artifact_uri,
                    expires_in_seconds=self._signed_url_expiry_seconds,
                )
                self._assert_no_forbidden_fragments(
                    url,
                    self._forbidden_signed_fragments,
                )
                return url
            return self.proxy_url(render_id, artifact_type)

        if self._url_mode is StorageUrlMode.PUBLIC:
            if self._storage.backend is StorageBackend.S3:
                url = self._public_s3_url(artifact_uri)
                self._assert_no_forbidden_fragments(
                    url,
                    self._forbidden_public_fragments,
                )
                return url
            return self.proxy_url(render_id, artifact_type)

        return self.proxy_url(render_id, artifact_type)

    async def endpoint_redirect_url(
        self,
        render_id: str,
        artifact_uri: str,
        artifact_type: ArtifactType,
    ) -> str | None:
        if self._url_mode is StorageUrlMode.PROXY:
            return None
        url = await self.artifact_url(render_id, artifact_uri, artifact_type)
        if url.startswith(f"{self._api_prefix}/"):
            return None
        return url

    def _public_s3_url(self, artifact_uri: str) -> str:
        if not self._public_base_url:
            raise StorageError(detail="S3 public base URL is not configured")

        parsed = urlsplit(artifact_uri)
        if parsed.scheme != "s3" or not parsed.netloc:
            raise StorageError(
                detail="Artifact URI is not an S3 URI",
                context={"uri": artifact_uri},
            )

        key = parsed.path.lstrip("/")
        if not key:
            raise StorageError(
                detail="Artifact URI is missing an object key",
                context={"uri": artifact_uri},
            )

        encoded_key = "/".join(quote(part, safe="") for part in key.split("/"))
        return f"{self._public_base_url}/{encoded_key}"

    @staticmethod
    def _assert_no_forbidden_fragments(
        url: str,
        fragments: tuple[str, ...],
    ) -> None:
        for fragment in fragments:
            if fragment and fragment in url:
                raise StorageError(detail="Artifact URL would expose credentials")
