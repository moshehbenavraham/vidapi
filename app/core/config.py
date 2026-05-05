from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    database_url: str = "sqlite+aiosqlite:///./data/vidapi.db"

    redis_url: str = "redis://localhost:6379"
    render_mode: Literal["sync", "async"] = "sync"

    storage_root: Path = Path("data")
    render_workspace_root: Path = Path("data/renders")
    asset_cache_root: Path = Path("data/assets")
    allowed_asset_dirs: list[str] = []

    allowed_hosts: list[str] = ["*"]
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

    @model_validator(mode="after")
    def _validate_production_cors(self) -> Settings:
        if "*" in self.cors_origins and not self.debug:
            msg = "Wildcard CORS origins require DEBUG=true"
            raise ValueError(msg)
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Clear cached settings so tests can isolate environment overrides."""
    get_settings.cache_clear()
