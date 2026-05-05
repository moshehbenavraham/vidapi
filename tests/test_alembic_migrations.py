from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlmodel import SQLModel

import app.db.models
import app.db.template_models
import app.db.webhook_models  # noqa: F401
from alembic import command
from app.core.config import is_postgresql_database_url, reset_settings_cache

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TABLES = {
    "renders",
    "templates",
    "template_versions",
    "webhook_attempts",
}
EXPECTED_RENDER_METADATA_COLUMNS = {
    "caption_mode",
    "caption_format",
    "caption_sidecar_path",
    "caption_sidecar_media_type",
    "caption_sidecar_filename",
    "caption_cue_count",
    "caption_burned_in",
    "poster_mode",
    "poster_timestamp_seconds",
    "poster_media_type",
    "poster_filename",
}
EXPECTED_RENDER_SELECTION_COLUMNS = {
    "renderer",
}
EXPECTED_RENDER_DURATION_COLUMNS = {
    "output_duration_seconds",
}


def _alembic_script() -> ScriptDirectory:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    return ScriptDirectory.from_config(config)


def _alembic_config() -> Config:
    return Config(str(PROJECT_ROOT / "alembic.ini"))


def _sqlite_tables(database_path: Path) -> set[str]:
    with sqlite3.connect(database_path) as conn:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }


def _sqlite_alembic_version(database_path: Path) -> str:
    with sqlite3.connect(database_path) as conn:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    assert row is not None
    return str(row[0])


def _sqlite_columns(database_path: Path, table_name: str) -> set[str]:
    with sqlite3.connect(database_path) as conn:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _has_postgresql_smoke_url() -> bool:
    try:
        return is_postgresql_database_url(os.environ.get("DATABASE_URL", "sqlite://"))
    except ValueError:
        return False


def test_sqlmodel_metadata_includes_current_database_tables() -> None:
    table_names = set(SQLModel.metadata.tables)

    assert EXPECTED_TABLES.issubset(table_names)


def test_sqlmodel_render_metadata_includes_caption_and_poster_columns() -> None:
    render_columns = set(SQLModel.metadata.tables["renders"].columns.keys())

    assert EXPECTED_RENDER_METADATA_COLUMNS.issubset(render_columns)


def test_sqlmodel_render_model_already_persists_renderer_selection() -> None:
    render_columns = set(SQLModel.metadata.tables["renders"].columns.keys())

    assert EXPECTED_RENDER_SELECTION_COLUMNS.issubset(render_columns)


def test_sqlmodel_render_model_persists_output_duration() -> None:
    render_columns = set(SQLModel.metadata.tables["renders"].columns.keys())

    assert EXPECTED_RENDER_DURATION_COLUMNS.issubset(render_columns)


def test_alembic_has_single_current_head() -> None:
    heads = _alembic_script().get_heads()

    assert heads == ["008"]


def test_alembic_revision_chain_includes_caption_and_poster_revision() -> None:
    revisions = {
        revision.revision
        for revision in _alembic_script().walk_revisions(base="base", head="heads")
    }

    assert {"001", "002", "003", "004", "005", "006", "007", "008"}.issubset(revisions)


def test_alembic_upgrades_and_downgrades_sqlite_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "migration-check.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database_path}")
    reset_settings_cache()

    try:
        command.upgrade(_alembic_config(), "head")

        assert EXPECTED_TABLES.issubset(_sqlite_tables(database_path))
        assert _sqlite_alembic_version(database_path) == "008"
        assert EXPECTED_RENDER_METADATA_COLUMNS.issubset(
            _sqlite_columns(database_path, "renders")
        )
        assert EXPECTED_RENDER_SELECTION_COLUMNS.issubset(
            _sqlite_columns(database_path, "renders")
        )
        assert EXPECTED_RENDER_DURATION_COLUMNS.issubset(
            _sqlite_columns(database_path, "renders")
        )

        command.downgrade(_alembic_config(), "base")

        assert EXPECTED_TABLES.isdisjoint(_sqlite_tables(database_path))
    finally:
        reset_settings_cache()


def test_postgresql_smoke_script_skips_without_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    result = subprocess.run(
        ["bash", "scripts/postgres-migration-smoke.sh"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=True,
        text=True,
    )

    assert "skipping because DATABASE_URL is not set" in result.stdout


@pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_MIGRATION_SMOKE") != "true"
    or not _has_postgresql_smoke_url(),
    reason="set RUN_POSTGRES_MIGRATION_SMOKE=true with a PostgreSQL DATABASE_URL",
)
def test_optional_postgresql_migration_smoke_script() -> None:
    subprocess.run(
        ["bash", "scripts/postgres-migration-smoke.sh"],
        cwd=PROJECT_ROOT,
        check=True,
    )
