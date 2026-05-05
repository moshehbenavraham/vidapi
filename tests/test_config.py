from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.core.security import (
    REDACTED_SECRET,
    hash_api_key,
    normalize_configured_api_key_hashes,
    redact_secret_values,
    validate_api_key,
)

VALID_API_KEY = "vidapi-config-test-key"
VALID_API_KEY_HASH = hash_api_key(VALID_API_KEY)


def test_default_settings_load() -> None:
    settings = Settings()
    assert settings.app_name == "VidAPI"
    assert settings.app_version == "0.1.1"
    assert settings.debug is False
    assert settings.log_level == "INFO"
    assert settings.max_fps == 60
    assert settings.api_key_auth_enabled is False
    assert settings.api_key_hashes == []


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


def test_settings_ignore_service_level_env_vars() -> None:
    with patch.dict(os.environ, {"POSTGRES_USER": "vidapi"}, clear=False):
        settings = Settings()
        assert settings.app_name == "VidAPI"


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
            api_key_auth_enabled=True,
            api_key_hashes=[VALID_API_KEY_HASH],
            storage_backend="s3",
            s3_bucket="vidapi-renders",
        )


def test_api_key_hashes_parse_comma_separated_env() -> None:
    with patch.dict(
        os.environ,
        {
            "API_KEY_AUTH_ENABLED": "true",
            "API_KEY_HASHES": f" {VALID_API_KEY_HASH.upper()} , {VALID_API_KEY_HASH} ",
        },
    ):
        settings = Settings()

    assert settings.api_key_auth_enabled is True
    assert settings.api_key_hashes == [VALID_API_KEY_HASH]


def test_api_key_hashes_parse_json_list_env() -> None:
    with patch.dict(
        os.environ,
        {
            "API_KEY_AUTH_ENABLED": "true",
            "API_KEY_HASHES": f'["{VALID_API_KEY_HASH}"]',
        },
    ):
        settings = Settings()

    assert settings.api_key_hashes == [VALID_API_KEY_HASH]


def test_auth_enabled_requires_hashes() -> None:
    with pytest.raises(ValueError, match="API_KEY_HASHES"):
        Settings(api_key_auth_enabled=True)


def test_invalid_api_key_hash_rejected() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        Settings(api_key_auth_enabled=True, api_key_hashes=["not-a-sha"])


def test_production_requires_api_key_auth_enabled() -> None:
    with pytest.raises(ValueError, match="API_KEY_AUTH_ENABLED"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://user:pass@localhost/vidapi",
            database_auto_create=False,
        )


def test_production_requires_api_key_hashes() -> None:
    with pytest.raises(ValueError, match="API_KEY_HASHES"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://user:pass@localhost/vidapi",
            database_auto_create=False,
            api_key_auth_enabled=True,
        )


def test_valid_production_api_key_settings() -> None:
    settings = Settings(
        environment="production",
        database_url="postgresql+asyncpg://user:pass@localhost/vidapi",
        database_auto_create=False,
        api_key_auth_enabled=True,
        api_key_hashes=[VALID_API_KEY_HASH],
    )

    assert settings.environment == "production"
    assert settings.api_key_auth_enabled is True
    assert settings.api_key_hashes == [VALID_API_KEY_HASH]


def test_api_key_hash_normalization_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        normalize_configured_api_key_hashes(["bad"])


def test_validate_api_key_accepts_matching_hash() -> None:
    assert validate_api_key(VALID_API_KEY, [VALID_API_KEY_HASH]) is True


def test_validate_api_key_rejects_invalid_and_empty_values() -> None:
    assert validate_api_key("wrong", [VALID_API_KEY_HASH]) is False
    assert validate_api_key(" ", [VALID_API_KEY_HASH]) is False
    assert validate_api_key(VALID_API_KEY, []) is False


def test_redact_secret_values_does_not_mutate_input() -> None:
    original = {
        "X-API-Key": "secret-value",
        "nested": {"authorization": "Bearer abc", "safe": "visible"},
        "items": [{"api_key": "inside-list"}],
    }

    redacted = redact_secret_values(original)

    assert original["X-API-Key"] == "secret-value"
    assert redacted["X-API-Key"] == REDACTED_SECRET
    assert redacted["nested"]["authorization"] == REDACTED_SECRET
    assert redacted["nested"]["safe"] == "visible"
    assert redacted["items"][0]["api_key"] == REDACTED_SECRET
