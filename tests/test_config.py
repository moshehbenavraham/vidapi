from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.config import Settings


def test_default_settings_load() -> None:
    settings = Settings()
    assert settings.app_name == "VidAPI"
    assert settings.app_version == "0.1.1"
    assert settings.debug is False
    assert settings.log_level == "INFO"
    assert settings.max_fps == 60


def test_database_url_default() -> None:
    settings = Settings()
    assert "sqlite" in settings.database_url


def test_storage_root_default() -> None:
    settings = Settings()
    assert settings.storage_root == Path("data")
    assert settings.storage_backend == "local"
    assert settings.storage_url_mode == "proxy"


def test_env_var_override() -> None:
    with patch.dict(os.environ, {"APP_NAME": "TestAPI", "DEBUG": "true"}):
        settings = Settings()
        assert settings.app_name == "TestAPI"
        assert settings.debug is True


def test_log_level_override() -> None:
    with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
        settings = Settings()
        assert settings.log_level == "DEBUG"


def test_invalid_log_level_raises() -> None:
    with (
        patch.dict(os.environ, {"LOG_LEVEL": "INVALID"}),
        pytest.raises(ValueError),
    ):
        Settings()


def test_numeric_settings_override() -> None:
    with patch.dict(os.environ, {"MAX_FPS": "120"}):
        settings = Settings()
        assert settings.max_fps == 120


def test_render_timeout_default() -> None:
    settings = Settings()
    assert settings.render_timeout_seconds == 600


def test_s3_backend_requires_bucket() -> None:
    with pytest.raises(ValueError, match="S3_BUCKET"):
        Settings(storage_backend="s3")


def test_s3_backend_accepts_bucket_without_local_credentials() -> None:
    settings = Settings(storage_backend="s3", s3_bucket="vidapi-renders")
    assert settings.storage_backend == "s3"
    assert settings.s3_bucket == "vidapi-renders"


def test_s3_public_mode_requires_public_base_url() -> None:
    with pytest.raises(ValueError, match="S3_PUBLIC_BASE_URL"):
        Settings(
            storage_backend="s3",
            s3_bucket="vidapi-renders",
            storage_url_mode="public",
        )


def test_public_base_url_rejects_embedded_credentials() -> None:
    with pytest.raises(ValueError, match="embedded credentials"):
        Settings(
            storage_backend="s3",
            s3_bucket="vidapi-renders",
            storage_url_mode="public",
            s3_public_base_url="https://user:pass@example.com/renders",
        )


def test_production_s3_backend_requires_credentials() -> None:
    with pytest.raises(ValueError, match="S3_ACCESS_KEY_ID"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://user:pass@localhost/vidapi",
            database_auto_create=False,
            storage_backend="s3",
            s3_bucket="vidapi-renders",
        )
