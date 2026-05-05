from __future__ import annotations

import asyncio
import contextlib
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlparse

import httpx
import structlog

from app.api.errors import AssetFetchError, MediaLimitError
from app.core.config import Settings
from app.models.composition import TextAsset
from app.services.ffprobe import FFProbeError, MediaInfo, probe
from app.services.limits import LimitExceededError, validate_media_limits
from app.services.ssrf import SSRFValidationError, validate_redirect_url, validate_url
from app.services.text_renderer import TextRenderOptions, render_text_to_png

logger = structlog.get_logger(__name__)


class AssetSizeError(AssetFetchError):
    error_code = "ASSET_TOO_LARGE"
    status_code = 413
    detail = "Asset exceeds maximum allowed size."


class AssetMIMEError(AssetFetchError):
    error_code = "ASSET_MIME_REJECTED"
    status_code = 415
    detail = "Asset MIME type is not allowed."


class AssetFileError(AssetFetchError):
    error_code = "ASSET_FILE_ERROR"
    status_code = 403
    detail = "Local file access denied."


@dataclass(frozen=True)
class ResolvedAsset:
    """Result of resolving an asset to a local file path."""

    local_path: Path
    content_hash: str | None
    media_info: MediaInfo | None
    source_url: str | None
    asset_type: Literal["remote", "text", "file", "color"]


class AssetService:
    """Fetches, validates, caches, and resolves assets for render jobs."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache_root = settings.asset_cache_root.resolve()
        self._max_bytes = settings.max_asset_size_mb * 1024 * 1024
        self._timeout = settings.asset_download_timeout_seconds
        self._max_redirects = settings.asset_max_redirects
        self._allow_http = settings.asset_allow_http
        self._mime_allowlist = frozenset(settings.asset_mime_allowlist)
        self._allowed_asset_dirs = [
            Path(d).resolve() for d in settings.allowed_asset_dirs
        ]
        self._font_paths = settings.font_search_paths
        self._ffprobe_timeout = settings.ffprobe_timeout_seconds

    # ------------------------------------------------------------------
    # Top-level dispatcher (T014)
    # ------------------------------------------------------------------

    async def resolve_asset(
        self,
        src: str,
        *,
        text_asset: TextAsset | None = None,
        workspace: Path | None = None,
    ) -> ResolvedAsset:
        """Resolve an asset reference to a validated local file.

        Dispatches based on source type:
        - ``TextAsset`` -> render to PNG
        - ``file://`` -> local file with allowlist check
        - ``http(s)://`` -> download with full validation
        """
        if text_asset is not None:
            return await self._resolve_text(text_asset, workspace)

        parsed = urlparse(src)

        if parsed.scheme == "file":
            return await self._resolve_file(src)

        if parsed.scheme in ("http", "https"):
            return await self._resolve_remote(src)

        raise AssetFetchError(
            detail=f"Unsupported asset scheme: {parsed.scheme or 'none'}",
            context={"src": src},
        )

    # ------------------------------------------------------------------
    # Remote asset download (T009)
    # ------------------------------------------------------------------

    async def _resolve_remote(self, url: str) -> ResolvedAsset:
        validate_url(url, allow_http=self._allow_http)

        cached = self._check_cache_by_url(url)
        if cached is not None:
            logger.info("asset_cache_hit_url", url=url, path=str(cached))
            media_info = await self._safe_probe(cached)
            self._validate_media_info(media_info)
            return ResolvedAsset(
                local_path=cached,
                content_hash=None,
                media_info=media_info,
                source_url=url,
                asset_type="remote",
            )

        data = await self._download(url)
        content_hash = hashlib.sha256(data).hexdigest()

        cached_path = self._cache_path_for_hash(content_hash)
        if cached_path.exists():
            logger.info(
                "asset_cache_hit_hash",
                url=url,
                hash=content_hash,
            )
            media_info = await self._safe_probe(cached_path)
            self._validate_media_info(media_info)
            return ResolvedAsset(
                local_path=cached_path,
                content_hash=content_hash,
                media_info=media_info,
                source_url=url,
                asset_type="remote",
            )

        dest = self._store_in_cache(content_hash, data)

        media_info = await self._safe_probe(dest)
        self._validate_media_info(media_info)
        return ResolvedAsset(
            local_path=dest,
            content_hash=content_hash,
            media_info=media_info,
            source_url=url,
            asset_type="remote",
        )

    async def _download(self, url: str) -> bytes:
        """Download a remote asset with size limit and MIME enforcement."""
        try:
            async with httpx.AsyncClient(
                follow_redirects=False,
                timeout=httpx.Timeout(self._timeout),
            ) as client:
                return await self._download_with_redirects(client, url)
        except SSRFValidationError:
            raise
        except AssetFetchError:
            raise
        except httpx.TimeoutException as exc:
            raise AssetFetchError(
                detail=f"Asset download timed out: {url}",
                context={"url": url},
            ) from exc
        except httpx.HTTPError as exc:
            raise AssetFetchError(
                detail=f"Asset download failed: {exc}",
                context={"url": url},
            ) from exc

    async def _download_with_redirects(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> bytes:
        """Follow redirects manually to validate each hop against SSRF."""
        current_url = url
        redirect_count = 0

        while True:
            response = await client.get(current_url)

            if response.is_redirect:
                if redirect_count >= self._max_redirects:
                    raise AssetFetchError(
                        detail="Too many redirects",
                        context={
                            "url": url,
                            "max_redirects": self._max_redirects,
                        },
                    )
                location = response.headers.get("location")
                if not location:
                    raise AssetFetchError(
                        detail="Redirect with no Location header",
                        context={"url": current_url},
                    )
                current_url = urljoin(current_url, location)
                validate_redirect_url(
                    current_url,
                    allow_http=self._allow_http,
                )
                redirect_count += 1
                continue

            response.raise_for_status()
            return self._validate_response(response, url)

    # ------------------------------------------------------------------
    # Response validation (T010)
    # ------------------------------------------------------------------

    def _validate_response(
        self,
        response: httpx.Response,
        url: str,
    ) -> bytes:
        """Validate size and MIME type of a completed download."""
        content_type = response.headers.get("content-type", "")
        mime = content_type.split(";")[0].strip().lower()

        if self._mime_allowlist and mime not in self._mime_allowlist:
            raise AssetMIMEError(
                detail=f"MIME type '{mime}' is not allowed",
                context={"url": url, "mime": mime},
            )

        data = response.content
        if len(data) > self._max_bytes:
            raise AssetSizeError(
                detail=(
                    f"Asset is {len(data)} bytes, "
                    f"exceeds limit of {self._max_bytes} bytes"
                ),
                context={
                    "url": url,
                    "size": len(data),
                    "limit": self._max_bytes,
                },
            )

        if len(data) == 0:
            raise AssetFetchError(
                detail="Asset download returned zero bytes",
                context={"url": url},
            )

        return data

    # ------------------------------------------------------------------
    # SHA-256 content-addressed cache (T011)
    # ------------------------------------------------------------------

    def _cache_path_for_hash(self, content_hash: str) -> Path:
        prefix_a = content_hash[:2]
        prefix_b = content_hash[2:4]
        return self._cache_root / "sha256" / prefix_a / prefix_b / content_hash

    def _check_cache_by_url(self, url: str) -> Path | None:
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        path = self._cache_path_for_hash(url_hash)
        if path.exists():
            return path
        return None

    def _store_in_cache(self, content_hash: str, data: bytes) -> Path:
        dest = self._cache_path_for_hash(content_hash)
        tmp = dest.with_suffix(".tmp")
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(data)
            tmp.replace(dest)
        except OSError:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            raise
        logger.info(
            "asset_cached",
            hash=content_hash,
            size=len(data),
            path=str(dest),
        )
        return dest

    # ------------------------------------------------------------------
    # ffprobe media validation (T012)
    # ------------------------------------------------------------------

    async def _safe_probe(self, path: Path) -> MediaInfo | None:
        """Run ffprobe, returning None if it fails (non-media files)."""
        try:
            return await probe(
                path,
                ffprobe_bin=self._settings.ffprobe_bin,
                timeout_seconds=self._ffprobe_timeout,
                kill_grace_seconds=self._settings.subprocess_kill_grace_seconds,
            )
        except FFProbeError:
            return None

    def _validate_media_info(self, media_info: MediaInfo | None) -> None:
        if media_info is None:
            return
        try:
            validate_media_limits(media_info, self._settings)
        except LimitExceededError as exc:
            raise MediaLimitError.from_violation(exc.violation) from exc

    # ------------------------------------------------------------------
    # Text asset resolution (T013)
    # ------------------------------------------------------------------

    async def _resolve_text(
        self,
        text_asset: TextAsset,
        workspace: Path | None,
    ) -> ResolvedAsset:
        options = TextRenderOptions(
            text=text_asset.text,
            font_family=text_asset.font_family,
            font_size=text_asset.font_size,
            color=text_asset.color,
            background=text_asset.background,
            padding=text_asset.padding,
            line_height=text_asset.line_height,
            align=text_asset.align,
        )
        png_data = await asyncio.to_thread(
            render_text_to_png,
            options,
            self._font_paths,
        )
        content_hash = hashlib.sha256(png_data).hexdigest()

        if workspace is not None:
            dest = workspace / f"text_{content_hash[:12]}.png"
        else:
            dest = self._cache_path_for_hash(content_hash)

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(png_data)

        return ResolvedAsset(
            local_path=dest,
            content_hash=content_hash,
            media_info=None,
            source_url=None,
            asset_type="text",
        )

    # ------------------------------------------------------------------
    # file:// resolution with allowlist (T015)
    # ------------------------------------------------------------------

    async def _resolve_file(self, url: str) -> ResolvedAsset:
        parsed = urlparse(url)
        file_path = Path(parsed.path).resolve()

        if not file_path.exists():
            raise AssetFileError(
                detail=f"Local file not found: {file_path}",
                context={"url": url, "path": str(file_path)},
            )

        if not file_path.is_file():
            raise AssetFileError(
                detail=f"Path is not a file: {file_path}",
                context={"url": url, "path": str(file_path)},
            )

        if self._allowed_asset_dirs:
            allowed = any(
                self._is_subpath(file_path, allowed_dir)
                for allowed_dir in self._allowed_asset_dirs
            )
            if not allowed:
                raise AssetFileError(
                    detail="File is outside allowed asset directories",
                    context={
                        "url": url,
                        "path": str(file_path),
                        "allowed_dirs": [str(d) for d in self._allowed_asset_dirs],
                    },
                )

        media_info = await self._safe_probe(file_path)
        self._validate_media_info(media_info)
        return ResolvedAsset(
            local_path=file_path,
            content_hash=None,
            media_info=media_info,
            source_url=url,
            asset_type="file",
        )

    @staticmethod
    def _is_subpath(path: Path, parent: Path) -> bool:
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False
