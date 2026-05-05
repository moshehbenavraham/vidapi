from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

from app.core.security import normalize_configured_api_key_hashes

SQLITE_DRIVER_NAMES = frozenset({"sqlite", "sqlite+aiosqlite"})
POSTGRESQL_DRIVER_NAMES = frozenset(
    {
        "postgres",
        "postgres+asyncpg",
        "postgresql",
        "postgresql+asyncpg",
    }
)
SUPPORTED_DATABASE_DRIVER_NAMES = SQLITE_DRIVER_NAMES | POSTGRESQL_DRIVER_NAMES
StorageBackendName = Literal["local", "s3"]
StorageUrlModeName = Literal["proxy", "signed", "public"]


def _parse_database_url(database_url: str) -> URL:
    if not database_url.strip():
        msg = "DATABASE_URL must not be empty"
        raise ValueError(msg)
    try:
        return make_url(database_url)
    except ArgumentError as exc:
        msg = "DATABASE_URL must be a valid SQLAlchemy database URL"
        raise ValueError(msg) from exc


def is_sqlite_database_url(database_url: str) -> bool:
    """Return whether a DATABASE_URL targets SQLite."""
    return _parse_database_url(database_url).drivername in SQLITE_DRIVER_NAMES


def is_postgresql_database_url(database_url: str) -> bool:
    """Return whether a DATABASE_URL targets PostgreSQL."""
    return _parse_database_url(database_url).drivername in POSTGRESQL_DRIVER_NAMES


def normalize_database_url(database_url: str) -> str:
    """Return a database URL with the async driver expected by the app."""
    url = _parse_database_url(database_url)
    drivername = url.drivername

    if drivername not in SUPPORTED_DATABASE_DRIVER_NAMES:
        msg = (
            "DATABASE_URL must use sqlite, sqlite+aiosqlite, postgres, "
            "postgresql, or postgresql+asyncpg"
        )
        raise ValueError(msg)

    if drivername == "sqlite":
        url = url.set(drivername="sqlite+aiosqlite")
    elif drivername in {"postgres", "postgres+asyncpg", "postgresql"}:
        url = url.set(drivername="postgresql+asyncpg")

    return url.render_as_string(hide_password=False)


def _validate_url_has_no_credentials(setting_name: str, value: str) -> None:
    if not value:
        return
    parsed = urlsplit(value)
    if parsed.username or parsed.password:
        msg = f"{setting_name} must not include embedded credentials"
        raise ValueError(msg)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "VidAPI"
    app_version: str = "0.1.3"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    environment: Literal["development", "test", "production"] = "development"

    database_url: str = "sqlite+aiosqlite:///./data/vidapi.db"
    database_auto_create: bool = True
    database_connect_timeout_seconds: float = Field(default=10.0, gt=0.0)
    database_connect_retries: int = Field(default=3, ge=1)
    database_connect_retry_backoff_seconds: float = Field(default=0.5, gt=0.0)

    redis_url: str = "redis://localhost:6379"
    redis_queue_name: str = "arq:queue"
    redis_require_auth_in_production: bool = True
    redis_require_tls_in_production: bool = True
    render_mode: Literal["sync", "async"] = "sync"

    api_key_auth_enabled: bool = False
    api_key_hashes: Annotated[list[str], NoDecode] = Field(default_factory=list)

    storage_root: Path = Path("data")
    render_workspace_root: Path = Path("data/renders")
    asset_cache_root: Path = Path("data/assets")
    allowed_asset_dirs: list[str] = []

    storage_backend: StorageBackendName = "local"
    storage_url_mode: StorageUrlModeName = "proxy"
    storage_signed_url_expiry_seconds: int = Field(
        default=900,
        ge=60,
        le=604800,
    )

    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    s3_region: str = "us-east-1"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_object_prefix: str = "renders"
    s3_force_path_style: bool = True
    s3_public_base_url: str = ""
    s3_connect_timeout_seconds: float = Field(default=5.0, gt=0.0)
    s3_read_timeout_seconds: float = Field(default=60.0, gt=0.0)
    s3_max_attempts: int = Field(default=3, ge=1)

    allowed_hosts: list[str] = [
        "localhost",
        "127.0.0.1",
        "test",
        "testserver",
    ]
    cors_origins: list[str] = [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    max_request_body_bytes: int = Field(
        default=2_097_152,
        ge=1,
        le=104_857_600,
    )
    max_render_request_body_bytes: int = Field(
        default=2_097_152,
        ge=1,
        le=104_857_600,
    )
    max_template_request_body_bytes: int = Field(
        default=2_097_152,
        ge=1,
        le=104_857_600,
    )
    max_render_duration_seconds: int = Field(default=120, ge=1, le=86_400)
    max_output_width: int = Field(default=1920, ge=1, le=16_384)
    max_output_height: int = Field(default=1920, ge=1, le=16_384)
    max_fps: int = Field(default=60, ge=1, le=240)
    max_gif_duration_seconds: int = Field(default=15, ge=1, le=86_400)
    max_gif_fps: int = Field(default=30, ge=1, le=240)
    max_gif_pixels: int = Field(default=2_073_600, ge=1, le=268_435_456)
    max_png_sequence_duration_seconds: int = Field(default=10, ge=1, le=86_400)
    max_png_sequence_fps: int = Field(default=30, ge=1, le=240)
    max_png_sequence_frames: int = Field(default=300, ge=1, le=1_000_000)
    max_png_sequence_pixels: int = Field(default=2_073_600, ge=1, le=268_435_456)
    max_clips_per_render: int = Field(default=50, ge=1, le=10_000)
    max_tracks_per_render: int = Field(default=50, ge=1, le=1_000)
    max_assets_per_render: int = Field(default=100, ge=1, le=10_000)
    max_caption_cues: int = Field(default=500, ge=1, le=10_000)
    max_caption_text_chars: int = Field(default=1000, ge=1, le=100_000)
    max_caption_total_text_chars: int = Field(default=50_000, ge=1, le=1_000_000)
    max_asset_size_mb: int = Field(default=500, ge=1, le=10_240)
    max_media_duration_seconds: int = Field(default=600, ge=1, le=86_400)
    max_media_width: int = Field(default=3840, ge=1, le=16_384)
    max_media_height: int = Field(default=3840, ge=1, le=16_384)
    max_media_streams_per_asset: int = Field(default=8, ge=1, le=128)
    max_async_queue_depth: int = Field(default=1000, ge=0, le=1_000_000)
    queue_admission_timeout_seconds: float = Field(default=1.0, gt=0.0, le=30.0)
    queue_retry_after_seconds: int = Field(default=10, ge=1, le=3600)
    render_timeout_seconds: int = Field(default=600, ge=1, le=86_400)

    asset_download_timeout_seconds: int = 60
    asset_max_redirects: int = Field(default=5, ge=0, le=10)
    asset_allow_http: bool = False
    asset_mime_allowlist: list[str] = [
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/svg+xml",
        "video/mp4",
        "video/webm",
        "video/quicktime",
        "audio/mpeg",
        "audio/wav",
        "audio/ogg",
        "audio/aac",
        "audio/flac",
    ]
    font_search_paths: list[str] = [
        "/usr/share/fonts/opentype/inter",
        "/usr/share/fonts/truetype/noto",
        "/usr/share/fonts/truetype/dejavu",
        "/usr/share/fonts",
    ]
    ffprobe_bin: str = "ffprobe"
    ffprobe_timeout_seconds: int = Field(default=30, ge=1, le=3600)

    workspace_cleanup_enabled: bool = True
    workspace_cleanup_keep_on_failure: bool = True
    workspace_orphan_ttl_seconds: int = Field(default=86_400, ge=0, le=31_536_000)
    workspace_disk_budget_bytes: int | None = Field(
        default=None,
        ge=0,
    )

    editly_bin: str = "editly"
    editly_timeout_seconds: int = Field(default=600, ge=1, le=86_400)
    editly_fast_mode: bool = False

    hyperframes_bin: str = "hyperframes"
    hyperframes_timeout_seconds: int = Field(default=600, ge=1, le=86_400)
    hyperframes_workers: int = Field(default=1, ge=1, le=8)
    max_html_asset_bytes: int = Field(default=262_144, ge=1_024, le=2_097_152)
    max_html_css_bytes: int = Field(default=65_536, ge=0, le=1_048_576)
    max_html_script_bytes: int = Field(default=65_536, ge=0, le=1_048_576)
    max_html_media_refs: int = Field(default=32, ge=0, le=1_000)

    ffmpeg_bin: str = "ffmpeg"
    audio_mix_timeout_seconds: int = Field(default=120, ge=1, le=3600)
    output_postprocess_timeout_seconds: int = Field(default=120, ge=1, le=3600)
    caption_burn_in_timeout_seconds: int = Field(default=120, ge=1, le=3600)
    audio_normalization_enabled: bool = False
    audio_fade_duration_seconds: float = Field(default=1.0, gt=0.0)
    subprocess_kill_grace_seconds: float = Field(default=5.0, gt=0.0, le=60.0)
    max_subprocess_stderr_bytes: int = Field(
        default=1_048_576,
        ge=4096,
        le=16_777_216,
    )

    progress_update_interval_seconds: float = 2.0

    rate_limit_default: str = "60/minute"
    rate_limit_render_create: str = "10/minute"
    rate_limit_storage_uri: str = "memory://"

    poster_enabled: bool = True
    poster_timestamp_percent: float = 0.25
    poster_format: str = "jpg"
    poster_quality: int = 85
    poster_timeout_seconds: int = Field(default=30, ge=1, le=3600)

    webhook_secret: str = ""
    webhook_timeout_seconds: int = 10
    webhook_max_retries: int = 3
    webhook_retry_delays: list[int] = [1, 10, 60]

    @field_validator("api_key_hashes", mode="before")
    @classmethod
    def _parse_api_key_hashes(cls, value: Any) -> Any:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    return value
            return [part.strip() for part in stripped.split(",")]
        return value

    @property
    def normalized_database_url(self) -> str:
        return normalize_database_url(self.database_url)

    @property
    def is_sqlite_database(self) -> bool:
        return is_sqlite_database_url(self.database_url)

    @property
    def is_postgresql_database(self) -> bool:
        return is_postgresql_database_url(self.database_url)

    @model_validator(mode="after")
    def _validate_production_cors(self) -> Self:
        if "*" in self.cors_origins and not self.debug:
            msg = "Wildcard CORS origins require DEBUG=true"
            raise ValueError(msg)
        if "*" in self.allowed_hosts and not self.debug:
            msg = "Wildcard allowed_hosts require DEBUG=true"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _validate_database_settings(self) -> Self:
        normalize_database_url(self.database_url)
        if self.environment == "production":
            if not self.is_postgresql_database:
                msg = "ENVIRONMENT=production requires a PostgreSQL DATABASE_URL"
                raise ValueError(msg)
            if self.database_auto_create:
                msg = "DATABASE_AUTO_CREATE must be false when ENVIRONMENT=production"
                raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _validate_api_key_auth_settings(self) -> Self:
        normalized_hashes = normalize_configured_api_key_hashes(self.api_key_hashes)
        self.api_key_hashes = list(normalized_hashes)

        if self.api_key_auth_enabled and not self.api_key_hashes:
            msg = "API_KEY_AUTH_ENABLED=true requires API_KEY_HASHES"
            raise ValueError(msg)

        if self.environment == "production":
            if not self.api_key_auth_enabled:
                msg = "ENVIRONMENT=production requires API_KEY_AUTH_ENABLED=true"
                raise ValueError(msg)
            if not self.api_key_hashes:
                msg = "ENVIRONMENT=production requires API_KEY_HASHES"
                raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _validate_storage_settings(self) -> Self:
        if self.storage_backend == "s3":
            if not self.s3_bucket.strip():
                msg = "STORAGE_BACKEND=s3 requires S3_BUCKET"
                raise ValueError(msg)
            if self.environment == "production":
                if not self.s3_access_key_id.strip():
                    msg = "STORAGE_BACKEND=s3 requires S3_ACCESS_KEY_ID in production"
                    raise ValueError(msg)
                if not self.s3_secret_access_key.strip():
                    msg = (
                        "STORAGE_BACKEND=s3 requires S3_SECRET_ACCESS_KEY in production"
                    )
                    raise ValueError(msg)

        if self.storage_url_mode == "public":
            if self.storage_backend == "s3" and not self.s3_public_base_url.strip():
                msg = (
                    "STORAGE_URL_MODE=public with STORAGE_BACKEND=s3 requires "
                    "S3_PUBLIC_BASE_URL"
                )
                raise ValueError(msg)
            _validate_url_has_no_credentials(
                "S3_PUBLIC_BASE_URL",
                self.s3_public_base_url,
            )

        _validate_url_has_no_credentials("S3_ENDPOINT_URL", self.s3_endpoint_url)
        return self

    @model_validator(mode="after")
    def _validate_redis_settings(self) -> Self:
        parsed = urlsplit(self.redis_url)
        if parsed.scheme not in {"redis", "rediss", "unix"}:
            msg = "REDIS_URL must use redis://, rediss://, or unix://"
            raise ValueError(msg)

        if self.environment == "production" and self.render_mode == "async":
            if self.redis_require_tls_in_production and parsed.scheme != "rediss":
                msg = (
                    "ENVIRONMENT=production with RENDER_MODE=async requires "
                    "a rediss:// REDIS_URL unless "
                    "REDIS_REQUIRE_TLS_IN_PRODUCTION=false"
                )
                raise ValueError(msg)
            if self.redis_require_auth_in_production and not parsed.password:
                msg = (
                    "ENVIRONMENT=production with RENDER_MODE=async requires "
                    "REDIS_URL credentials unless "
                    "REDIS_REQUIRE_AUTH_IN_PRODUCTION=false"
                )
                raise ValueError(msg)
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Clear cached settings so tests can isolate environment overrides."""
    get_settings.cache_clear()
