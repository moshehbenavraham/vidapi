from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.services.ffprobe import FFProbeError, MediaInfo, probe
from app.services.ssrf import SSRFValidationError, validate_url


class TestSSRFValidateURL:
    """SSRF validator must block dangerous URLs and allow safe ones."""

    def test_valid_https_url(self) -> None:
        result = validate_url("https://example.com/video.mp4")
        assert result == "https://example.com/video.mp4"

    def test_http_blocked_by_default(self) -> None:
        with pytest.raises(SSRFValidationError, match="not allowed"):
            validate_url("http://example.com/video.mp4")

    def test_http_allowed_when_enabled(self) -> None:
        result = validate_url(
            "http://example.com/video.mp4",
            allow_http=True,
        )
        assert result == "http://example.com/video.mp4"

    def test_no_scheme_rejected(self) -> None:
        with pytest.raises(SSRFValidationError, match="no scheme"):
            validate_url("example.com/video.mp4")

    def test_ftp_scheme_rejected(self) -> None:
        with pytest.raises(SSRFValidationError, match="not allowed"):
            validate_url("ftp://example.com/video.mp4")

    def test_no_hostname_rejected(self) -> None:
        with pytest.raises(SSRFValidationError):
            validate_url("https:///path")

    def test_credentials_in_url_rejected(self) -> None:
        with pytest.raises(SSRFValidationError, match="credentials"):
            validate_url("https://user:pass@example.com/video.mp4")

    @pytest.mark.parametrize(
        "ip",
        [
            "127.0.0.1",
            "127.0.0.2",
            "0.0.0.0",
        ],
    )
    def test_loopback_ips_blocked(self, ip: str) -> None:
        with pytest.raises(SSRFValidationError, match="blocked"):
            validate_url(f"https://{ip}/path")

    @pytest.mark.parametrize(
        "ip",
        [
            "10.0.0.1",
            "172.16.0.1",
            "172.31.255.255",
            "192.168.1.1",
            "192.168.0.100",
        ],
    )
    def test_private_ips_blocked(self, ip: str) -> None:
        with pytest.raises(SSRFValidationError, match="blocked"):
            validate_url(f"https://{ip}/path")

    @pytest.mark.parametrize(
        "ip",
        [
            "169.254.1.1",
            "169.254.169.254",
        ],
    )
    def test_link_local_ips_blocked(self, ip: str) -> None:
        with pytest.raises(SSRFValidationError, match="blocked"):
            validate_url(f"https://{ip}/path")

    def test_metadata_hostname_blocked(self) -> None:
        with pytest.raises(SSRFValidationError, match="blocked"):
            validate_url("https://metadata.google.internal/computeMetadata/")

    def test_aws_metadata_ip_blocked(self) -> None:
        with pytest.raises(SSRFValidationError, match="blocked"):
            validate_url("https://169.254.169.254/latest/meta-data/")

    def test_cloud_metadata_path_blocked(self) -> None:
        with pytest.raises(SSRFValidationError, match="metadata"):
            validate_url("https://example.com/computeMetadata/v1/instance")

    def test_ipv4_mapped_ipv6_loopback_blocked(self) -> None:
        with pytest.raises(SSRFValidationError, match="blocked"):
            validate_url("https://[::ffff:127.0.0.1]/path")

    def test_ipv4_mapped_ipv6_private_blocked(self) -> None:
        with pytest.raises(SSRFValidationError, match="blocked"):
            validate_url("https://[::ffff:10.0.0.1]/path")

    def test_ipv6_loopback_blocked(self) -> None:
        with pytest.raises(SSRFValidationError, match="blocked"):
            validate_url("https://[::1]/path")

    def test_public_ip_allowed(self) -> None:
        result = validate_url("https://8.8.8.8/path")
        assert result == "https://8.8.8.8/path"


class TestSSRFDNSResolution:
    """DNS resolution checks for hostnames resolving to private IPs."""

    def test_localhost_hostname_blocked(self) -> None:
        with pytest.raises(SSRFValidationError, match="blocked"):
            validate_url("https://localhost/path")


class TestAssetMIMEAllowlist:
    """MIME validation in asset service."""

    def test_mime_check_accepts_allowed_type(self) -> None:
        from unittest.mock import MagicMock

        import httpx

        from app.core.config import Settings
        from app.services.asset_service import AssetService

        settings = Settings()
        svc = AssetService(settings=settings)

        response = MagicMock(spec=httpx.Response)
        response.headers = {"content-type": "image/png"}
        response.content = b"\x89PNG" + b"\x00" * 100

        data = svc._validate_response(response, "https://example.com/img.png")
        assert data == response.content

    def test_mime_check_rejects_disallowed_type(self) -> None:
        from unittest.mock import MagicMock

        import httpx

        from app.core.config import Settings
        from app.services.asset_service import AssetMIMEError, AssetService

        settings = Settings()
        svc = AssetService(settings=settings)

        response = MagicMock(spec=httpx.Response)
        response.headers = {"content-type": "application/x-executable"}
        response.content = b"\x00" * 100

        with pytest.raises(AssetMIMEError, match="not allowed"):
            svc._validate_response(response, "https://example.com/bad")


class TestAssetSizeLimit:
    """Asset size limit enforcement."""

    def test_oversized_asset_rejected(self) -> None:
        from unittest.mock import MagicMock

        import httpx

        from app.core.config import Settings
        from app.services.asset_service import AssetService, AssetSizeError

        settings = Settings(max_asset_size_mb=1)
        svc = AssetService(settings=settings)

        response = MagicMock(spec=httpx.Response)
        response.headers = {"content-type": "video/mp4"}
        response.content = b"\x00" * (2 * 1024 * 1024)

        with pytest.raises(AssetSizeError, match="exceeds limit"):
            svc._validate_response(response, "https://example.com/big.mp4")

    def test_zero_byte_response_rejected(self) -> None:
        from unittest.mock import MagicMock

        import httpx

        from app.core.config import Settings
        from app.services.asset_service import AssetFetchError, AssetService

        settings = Settings()
        svc = AssetService(settings=settings)

        response = MagicMock(spec=httpx.Response)
        response.headers = {"content-type": "video/mp4"}
        response.content = b""

        with pytest.raises(AssetFetchError, match="zero bytes"):
            svc._validate_response(response, "https://example.com/empty.mp4")


class TestFileAssetAllowlist:
    """file:// URL resolution with directory allowlist."""

    @pytest.mark.asyncio
    async def test_file_outside_allowlist_rejected(
        self,
        tmp_path: pytest.TempPathFactory,  # type: ignore[type-arg]
    ) -> None:
        import tempfile

        from app.core.config import Settings
        from app.services.asset_service import AssetFileError, AssetService

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00" * 100)
            fpath = f.name

        settings = Settings(allowed_asset_dirs=["/nonexistent/allowed"])
        svc = AssetService(settings=settings)

        with pytest.raises(AssetFileError, match="outside allowed"):
            await svc._resolve_file(f"file://{fpath}")

        import os

        os.unlink(fpath)

    @pytest.mark.asyncio
    async def test_file_inside_allowlist_accepted(
        self,
        tmp_path: pytest.TempPathFactory,  # type: ignore[type-arg]
    ) -> None:
        import tempfile
        from pathlib import Path

        from app.core.config import Settings
        from app.services.asset_service import AssetService

        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = Path(tmpdir) / "test.txt"
            fpath.write_bytes(b"hello world")

            settings = Settings(allowed_asset_dirs=[tmpdir])
            svc = AssetService(settings=settings)

            result = await svc._resolve_file(f"file://{fpath}")
            assert result.local_path == fpath.resolve()
            assert result.asset_type == "file"

    @pytest.mark.asyncio
    async def test_file_nonexistent_rejected(self) -> None:
        from app.core.config import Settings
        from app.services.asset_service import AssetFileError, AssetService

        settings = Settings(allowed_asset_dirs=[])
        svc = AssetService(settings=settings)

        with pytest.raises(AssetFileError, match="not found"):
            await svc._resolve_file("file:///nonexistent/file.mp4")


class TestAssetRedirectRegression:
    @pytest.mark.asyncio
    async def test_redirect_to_blocked_network_is_rejected(self) -> None:
        from app.core.config import Settings
        from app.services.asset_service import AssetService

        class _RedirectResponse:
            is_redirect = True

            def __init__(self) -> None:
                self.headers = {"location": "http://127.0.0.1/private.mp4"}

        class _Client:
            async def get(self, url: str) -> _RedirectResponse:
                return _RedirectResponse()

        settings = Settings(asset_allow_http=True)
        svc = AssetService(settings=settings)

        with pytest.raises(SSRFValidationError):
            await svc._download_with_redirects(
                _Client(),
                "https://example.com/start.mp4",
            )


class TestMediaMetadataLimits:
    @pytest.mark.asyncio
    async def test_file_media_duration_limit_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.api.errors import MediaLimitError
        from app.core.config import Settings
        from app.services.asset_service import AssetService

        asset_path = tmp_path / "clip.mp4"
        asset_path.write_bytes(b"media")
        monkeypatch.setattr(
            "app.services.asset_service.probe",
            AsyncMock(
                return_value=MediaInfo(
                    duration=20.0,
                    width=1920,
                    height=1080,
                    video_codec="h264",
                    audio_codec="aac",
                    stream_count=2,
                    format_name="mov,mp4",
                )
            ),
        )

        settings = Settings(
            allowed_asset_dirs=[str(tmp_path)],
            max_media_duration_seconds=10,
        )
        svc = AssetService(settings=settings)

        with pytest.raises(MediaLimitError) as exc_info:
            await svc._resolve_file(f"file://{asset_path}")

        assert exc_info.value.error_code == "MEDIA_LIMIT_EXCEEDED"
        assert exc_info.value.context["field"] == "media.duration"


class TestSubprocessTimeouts:
    @pytest.mark.asyncio
    async def test_ffprobe_timeout_terminates_process(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class _FakeProcess:
            def __init__(self) -> None:
                self.returncode: int | None = None
                self.terminated = False
                self.killed = False

            async def communicate(self) -> tuple[bytes, bytes]:
                await asyncio.sleep(10)
                return b"{}", b""

            def terminate(self) -> None:
                self.terminated = True
                self.returncode = -15

            def kill(self) -> None:
                self.killed = True
                self.returncode = -9

            async def wait(self) -> int:
                if self.returncode is None:
                    self.returncode = 0
                return self.returncode

        fake_proc = _FakeProcess()

        async def _fake_create_subprocess_exec(
            *args: object, **kwargs: object
        ) -> object:
            return fake_proc

        monkeypatch.setattr(
            "app.services.ffprobe.asyncio.create_subprocess_exec",
            _fake_create_subprocess_exec,
        )

        with pytest.raises(FFProbeError, match="timed out"):
            await probe(
                tmp_path / "clip.mp4",
                timeout_seconds=0.01,
                kill_grace_seconds=0.01,
            )

        assert fake_proc.terminated is True
