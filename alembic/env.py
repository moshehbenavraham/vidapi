from __future__ import annotations

import asyncio
from logging.config import fileConfig

from pydantic import ValidationError
from sqlalchemy import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import SQLModel

import app.db.models
import app.db.template_models
import app.db.webhook_models  # noqa: F401
from alembic import context
from app.core.config import get_settings
from app.db.session import DatabaseConfigurationError, create_database_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _get_migration_database_url() -> str:
    try:
        settings = get_settings()
        database_url = settings.normalized_database_url
    except (ValidationError, ValueError) as exc:
        msg = "Alembic could not load a valid DATABASE_URL from app settings"
        raise RuntimeError(msg) from exc
    config.set_main_option("sqlalchemy.url", database_url)
    return database_url


def run_migrations_offline() -> None:
    url = _get_migration_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        try:
            context.run_migrations()
        except SQLAlchemyError as exc:
            msg = "Alembic offline migration generation failed"
            raise RuntimeError(msg) from exc


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    _get_migration_database_url()
    try:
        connectable = create_database_engine(use_null_pool=True)
    except DatabaseConfigurationError as exc:
        msg = "Alembic could not configure the migration database engine"
        raise RuntimeError(msg) from exc

    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    except SQLAlchemyError as exc:
        msg = "Alembic failed while connecting to or migrating the database"
        raise RuntimeError(msg) from exc
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
