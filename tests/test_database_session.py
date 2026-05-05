from __future__ import annotations

import pytest

from app.core.config import Settings, normalize_database_url, reset_settings_cache
from app.db.session import (
    DatabaseConfigurationError,
    create_database_engine,
    create_engine_options,
    create_tables,
    dispose_engine,
    set_engine,
)


def test_default_database_url_uses_sqlite_aiosqlite() -> None:
    settings = Settings()

    assert settings.is_sqlite_database
    assert settings.normalized_database_url == "sqlite+aiosqlite:///./data/vidapi.db"


def test_plain_sqlite_url_normalizes_to_aiosqlite() -> None:
    assert (
        normalize_database_url("sqlite:///./data/local.db")
        == "sqlite+aiosqlite:///./data/local.db"
    )


def test_postgresql_url_normalizes_to_asyncpg() -> None:
    settings = Settings(
        database_url="postgresql://vidapi:secret@localhost:5432/vidapi",
    )

    assert settings.is_postgresql_database
    assert (
        settings.normalized_database_url
        == "postgresql+asyncpg://vidapi:secret@localhost:5432/vidapi"
    )


def test_legacy_postgres_url_normalizes_to_asyncpg() -> None:
    assert (
        normalize_database_url("postgres://vidapi:secret@localhost/vidapi")
        == "postgresql+asyncpg://vidapi:secret@localhost/vidapi"
    )


def test_invalid_database_scheme_raises_clear_error() -> None:
    with pytest.raises(ValueError, match="DATABASE_URL must use"):
        Settings(database_url="mysql://vidapi:secret@localhost/vidapi")


def test_sqlite_engine_options_include_timeout() -> None:
    settings = Settings(database_url="sqlite:///./data/test.db")
    options = create_engine_options(settings)

    assert options["connect_args"]["timeout"] == 10.0


@pytest.mark.asyncio
async def test_postgresql_engine_uses_asyncpg_driver() -> None:
    settings = Settings(
        database_url="postgresql://vidapi:secret@localhost:5432/vidapi",
    )
    engine = create_database_engine(settings)

    try:
        assert engine.url.drivername == "postgresql+asyncpg"
    finally:
        await engine.dispose()


def test_production_requires_postgresql_database_url() -> None:
    with pytest.raises(ValueError, match="requires a PostgreSQL DATABASE_URL"):
        Settings(
            environment="production",
            database_url="sqlite+aiosqlite:///./data/vidapi.db",
            database_auto_create=False,
        )


def test_production_disables_database_auto_create() -> None:
    with pytest.raises(ValueError, match="DATABASE_AUTO_CREATE must be false"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://vidapi:secret@localhost/vidapi",
        )


def test_valid_production_database_settings() -> None:
    settings = Settings(
        environment="production",
        database_url="postgresql+asyncpg://vidapi:secret@localhost/vidapi",
        database_auto_create=False,
    )

    assert settings.environment == "production"
    assert settings.database_auto_create is False
    assert settings.is_postgresql_database


@pytest.mark.asyncio
async def test_create_tables_rejects_disabled_auto_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("DATABASE_AUTO_CREATE", "false")
    reset_settings_cache()
    set_engine(None)

    try:
        with pytest.raises(DatabaseConfigurationError, match="auto-create is disabled"):
            await create_tables()
    finally:
        await dispose_engine()
        reset_settings_cache()
