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
