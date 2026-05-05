from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

import app.db.models
import app.db.template_models
import app.db.webhook_models  # noqa: F401
from app.core.config import Settings, get_settings

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_T = TypeVar("_T")


class DatabaseConfigurationError(RuntimeError):
    """Raised when database settings or migration state are invalid."""


class DatabaseConnectionError(RuntimeError):
    """Raised when the database cannot be reached after retries."""


_engine: AsyncEngine | None = None


def create_engine_options(
    settings: Settings,
    *,
    use_null_pool: bool = False,
) -> dict[str, Any]:
    """Build async SQLAlchemy engine options for the configured database."""
    connect_args: dict[str, Any] = {
        "timeout": settings.database_connect_timeout_seconds,
    }

    if settings.is_postgresql_database:
        connect_args["server_settings"] = {"application_name": settings.app_name}

    options: dict[str, Any] = {
        "echo": settings.debug,
        "future": True,
        "pool_pre_ping": True,
        "connect_args": connect_args,
    }
    if use_null_pool:
        options["poolclass"] = NullPool
    return options


def create_database_engine(
    settings: Settings | None = None,
    *,
    use_null_pool: bool = False,
) -> AsyncEngine:
    """Create an async engine from application settings without connecting."""
    resolved_settings = settings or get_settings()
    try:
        return create_async_engine(
            resolved_settings.normalized_database_url,
            **create_engine_options(resolved_settings, use_null_pool=use_null_pool),
        )
    except (SQLAlchemyError, ValueError) as exc:
        msg = "Unable to configure database engine from DATABASE_URL"
        raise DatabaseConfigurationError(msg) from exc


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_database_engine()
    return _engine


def set_engine(engine: AsyncEngine | None) -> None:
    """Replace the module-level engine (used by tests)."""
    global _engine
    _engine = engine


async def _run_with_database_retry(
    operation_name: str,
    operation: Callable[[], Awaitable[_T]],
) -> _T:
    settings = get_settings()
    last_error: Exception | None = None
    delay_seconds = settings.database_connect_retry_backoff_seconds

    for attempt in range(1, settings.database_connect_retries + 1):
        try:
            async with asyncio.timeout(settings.database_connect_timeout_seconds):
                return await operation()
        except (OSError, SQLAlchemyError, TimeoutError) as exc:
            last_error = exc
            if attempt == settings.database_connect_retries:
                break
            await asyncio.sleep(delay_seconds)
            delay_seconds *= 2

    msg = (
        f"{operation_name} failed after {settings.database_connect_retries} attempt(s)"
    )
    if last_error is not None:
        raise DatabaseConnectionError(msg) from last_error
    raise DatabaseConnectionError(msg)


async def create_tables() -> None:
    """Create all SQLModel tables. Used for development and tests."""
    settings = get_settings()
    if not settings.database_auto_create:
        msg = (
            "Database table auto-create is disabled; run `alembic upgrade head` "
            "before starting the application."
        )
        raise DatabaseConfigurationError(msg)

    async def _create_tables() -> None:
        engine = _get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    await _run_with_database_retry("create database tables", _create_tables)


async def verify_database_connection() -> None:
    """Verify that the configured database can answer a lightweight query."""

    async def _verify_connection() -> None:
        engine = _get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    await _run_with_database_retry("verify database connection", _verify_connection)


def _get_alembic_heads() -> set[str]:
    alembic_config = Config(str(_PROJECT_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(alembic_config)
    return set(script.get_heads())


async def verify_database_migrations() -> None:
    """Verify the database has been migrated to the current Alembic head."""
    expected_heads = _get_alembic_heads()
    engine = _get_engine()
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            current_heads = {str(row[0]) for row in result}
    except SQLAlchemyError as exc:
        msg = (
            "Database migration state is unavailable; run "
            "`alembic upgrade head` before starting the application."
        )
        raise DatabaseConfigurationError(msg) from exc

    if current_heads != expected_heads:
        msg = (
            "Database migrations are not at Alembic head; expected "
            f"{sorted(expected_heads)}, found {sorted(current_heads)}. "
            "Run `alembic upgrade head` before starting the application."
        )
        raise DatabaseConfigurationError(msg)


async def dispose_engine() -> None:
    """Dispose the engine on shutdown to release connections."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an async database session for dependency injection."""
    engine = _get_engine()
    async with SQLModelAsyncSession(engine) as session:
        yield session
