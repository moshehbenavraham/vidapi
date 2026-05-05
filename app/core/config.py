from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "VidAPI"
    app_version: str = "0.1.1"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    environment: Literal["development", "test", "production"] = "development"

    database_url: str = "sqlite+aiosqlite:///./data/vidapi.db"
    database_auto_create: bool = True
    database_connect_timeout_seconds: float = Field(default=10.0, gt=0.0)
    database_connect_retries: int = Field(default=3, ge=1)
    database_connect_retry_backoff_seconds: float = Field(default=0.5, gt=0.0)

    redis_url: str = "redis://localhost:6379"
    render_mode: Literal["sync", "async"] = "sync"

    storage_root: Path = Path("data")
    render_workspace_root: Path = Path("data/renders")
    asset_cache_root: Path = Path("data/assets")
    allowed_asset_dirs: list[str] = []

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

    max_render_duration_seconds: int = 120
    max_output_width: int = 1920
    max_output_height: int = 1920
    max_fps: int = 60
    max_clips_per_render: int = 50
    max_tracks_per_render: int = 10
    max_asset_size_mb: int = 500
    render_timeout_seconds: int = 600

    asset_download_timeout_seconds: int = 60
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
    ffprobe_timeout_seconds: int = 30

    workspace_cleanup_enabled: bool = True
    workspace_cleanup_keep_on_failure: bool = True

    editly_bin: str = "editly"
    editly_timeout_seconds: int = 600
    editly_fast_mode: bool = False

    ffmpeg_bin: str = "ffmpeg"
    audio_mix_timeout_seconds: int = 120
    audio_normalization_enabled: bool = False
    audio_fade_duration_seconds: float = Field(default=1.0, gt=0.0)

    progress_update_interval_seconds: float = 2.0

    rate_limit_default: str = "60/minute"
    rate_limit_render_create: str = "10/minute"
    rate_limit_storage_uri: str = "memory://"

    poster_enabled: bool = True
    poster_timestamp_percent: float = 0.25
    poster_format: str = "jpg"
    poster_quality: int = 85
    poster_timeout_seconds: int = 30

    webhook_secret: str = ""
    webhook_timeout_seconds: int = 10
    webhook_max_retries: int = 3
    webhook_retry_delays: list[int] = [1, 10, 60]

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Clear cached settings so tests can isolate environment overrides."""
    get_settings.cache_clear()
