from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

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

    storage_root: Path = Path("data")
    render_workspace_root: Path = Path("data/renders")
    asset_cache_root: Path = Path("data/assets")
    allowed_asset_dirs: list[str] = []

    allowed_hosts: list[str] = ["*"]
    cors_origins: list[str] = ["*"]

    max_render_duration_seconds: int = 120
    max_output_width: int = 1920
    max_output_height: int = 1920
    max_fps: int = 60
    max_clips_per_render: int = 50
    max_tracks_per_render: int = 10
    max_asset_size_mb: int = 500
    render_timeout_seconds: int = 600


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
