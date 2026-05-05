# Task Checklist

**Session ID**: `phase03-session01-postgresql-persistence-and-alembic-migrations`
**Total Tasks**: 20
**Estimated Duration**: 3-4 hours
**Created**: 2026-05-05

---

## Legend

- `[x]` = Completed
- `[ ]` = Pending
- `[P]` = Parallelizable (can run with other [P] tasks)
- `[SNNMM]` = Session reference (NN=phase number, MM=session number)
- `TNNN` = Task ID

---

## Progress Summary

| Category | Total | Done | Remaining |
|----------|-------|------|-----------|
| Setup | 3 | 3 | 0 |
| Foundation | 5 | 5 | 0 |
| Implementation | 8 | 8 | 0 |
| Testing | 4 | 4 | 0 |
| **Total** | **20** | **20** | **0** |

---

## Setup (3 tasks)

Initial configuration and environment preparation.

- [x] T001 [S0301] Verify current SQLite migration/test baseline and record head revision (`alembic/versions/005_add_webhook_attempts.py`)
- [x] T002 [S0301] [P] Add asyncpg runtime dependency while preserving aiosqlite support (`pyproject.toml`)
- [x] T003 [S0301] [P] Add database setup notes for SQLite and PostgreSQL URLs (`docs/development.md`)

---

## Foundation (5 tasks)

Core structures and base implementations.

- [x] T004 [S0301] Extend database settings for auto-create and production guards with schema-validated input and explicit error mapping (`app/core/config.py`)
- [x] T005 [S0301] Refactor async engine construction for SQLite and PostgreSQL driver options with timeout, retry/backoff, and failure-path handling (`app/db/session.py`)
- [x] T006 [S0301] Load all SQLModel metadata modules and settings-driven URLs in Alembic with explicit error mapping (`alembic/env.py`)
- [x] T007 [S0301] Normalize Alembic defaults so command-line runs defer safely to `DATABASE_URL` (`alembic.ini`)
- [x] T008 [S0301] Update app lifespan startup to skip implicit table creation in production with fail-closed behavior (`app/main.py`)

---

## Implementation (8 tasks)

Main feature implementation.

- [x] T009 [S0301] Update test database fixtures to create in-memory SQLite schemas explicitly with state reset on re-entry (`tests/conftest.py`)
- [x] T010 [S0301] [P] Add database session tests for SQLite default, PostgreSQL URL handling, and invalid production settings (`tests/test_database_session.py`)
- [x] T011 [S0301] Add Alembic metadata/import tests for render, template, and webhook tables (`tests/test_alembic_migrations.py`)
- [x] T012 [S0301] Validate render CRUD async transaction behavior with transaction boundaries and rollback on failure (`app/db/render_crud.py`)
- [x] T013 [S0301] Validate template CRUD async transaction behavior with transaction boundaries and rollback on failure (`app/db/template_crud.py`)
- [x] T014 [S0301] Validate webhook CRUD async transaction behavior with transaction boundaries and rollback on failure (`app/db/webhook_crud.py`)
- [x] T015 [S0301] [P] Add optional PostgreSQL migration smoke script gated by `DATABASE_URL` with timeout, retry/backoff, and failure-path handling (`scripts/postgres-migration-smoke.sh`)
- [x] T016 [S0301] [P] Document migration apply/rollback workflow and production no-auto-create behavior (`docs/deployment.md`)

---

## Testing (4 tasks)

Verification and quality assurance.

- [x] T017 [S0301] Run migration upgrade/downgrade checks against SQLite and optional PostgreSQL (`tests/test_alembic_migrations.py`)
- [x] T018 [S0301] Run focused database and API regression tests for render persistence (`tests/test_api_renders.py`)
- [x] T019 [S0301] Run full quality gates for lint, format, type checks, and tests (`pyproject.toml`)
- [x] T020 [S0301] Validate ASCII encoding and Unix LF line endings for session artifacts (`.spec_system/specs/phase03-session01-postgresql-persistence-and-alembic-migrations/tasks.md`)

---

## Completion Checklist

Before marking session complete:

- [x] All tasks marked `[x]`
- [x] All tests passing
- [x] All files ASCII-encoded
- [x] implementation-notes.md updated
- [x] Ready for the validate workflow step

---

## Next Steps

Run the validate workflow step to verify session completeness.
