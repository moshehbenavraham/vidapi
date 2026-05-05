# Session Specification

**Session ID**: `phase03-session01-postgresql-persistence-and-alembic-migrations`
**Phase**: 03 - Production Hardening
**Status**: Not Started
**Created**: 2026-05-05

---

## 1. Session Overview

This session makes VidAPI's metadata persistence suitable for production by hardening the existing async SQLModel database layer for PostgreSQL while preserving SQLite as the default local and test path. The project already has Alembic revisions through the Phase 02 tables, so the focus is to make that migration chain operational for PostgreSQL, ensure the Alembic environment sees all models, and prevent production startup from silently creating unmanaged schemas.

The work is the first session of Phase 03 because every later production hardening feature depends on durable, migration-managed metadata. S3 storage, API key authentication, resource limits, and operational visibility all rely on render, template, and webhook rows being stable across process restarts and deploys.

The implementation should keep public API behavior stable. Route handlers and services continue using async sessions through the existing dependency boundary, while configuration and startup behavior decide whether local development may auto-create tables or production must require migrations.

---

## 2. Objectives

1. Add PostgreSQL-capable async database configuration without breaking the SQLite default.
2. Make Alembic use application settings and complete SQLModel metadata for render, template, and webhook tables.
3. Ensure production startup does not rely on implicit `create_all` table creation.
4. Add focused tests, smoke checks, and documentation for migration apply and rollback workflows.

---

## 3. Prerequisites

### Required Sessions
- [x] `phase02-session01-template-models-and-crud-api` - Stable template and template version models.
- [x] `phase02-session02-template-variables-and-rendering` - Template render traceability through render rows.
- [x] `phase02-session03-webhook-delivery-system` - Webhook attempt persistence model and CRUD.
- [x] `phase02-session04-transitions-and-positioning` - Existing render pipeline still green before database changes.
- [x] `phase02-session05-audio-polish-and-hardening` - Phase 02 final hardening baseline.

### Required Tools/Knowledge
- Python 3.11+ and async SQLAlchemy/SQLModel sessions.
- Alembic async migration environment.
- SQLite with `aiosqlite` for local tests.
- PostgreSQL with `asyncpg` for production and optional smoke testing.

### Environment Requirements
- Existing SQLite tests must remain runnable without external services.
- Optional PostgreSQL smoke checks should run only when a PostgreSQL `DATABASE_URL` is available.
- Redis, Editly, and FFmpeg are not required for the database migration checks in this session.

---

## 4. Scope

### In Scope (MVP)
- Operator can run VidAPI with PostgreSQL metadata persistence - add driver support, URL validation, and async engine setup.
- Operator can manage schema with Alembic migrations - make the migration environment settings-driven and metadata-complete.
- Developer can keep SQLite for local development and tests - preserve in-memory and file-backed SQLite fixtures.
- Production startup avoids unmanaged schema creation - gate `create_all` behind explicit development/test settings.
- Maintainer can verify migrations - add tests or smoke scripts for Alembic head, metadata imports, upgrade, and downgrade.
- Maintainer can follow documented migration workflow - document apply, rollback, local SQLite, and PostgreSQL examples.

### Out of Scope (Deferred)
- S3-compatible object storage - *Reason: Phase 03 Session 02 owns storage adapters and download modes.*
- API key authentication - *Reason: Phase 03 Session 03 owns access control.*
- Request, queue, and render resource limits - *Reason: Phase 03 Session 04 owns runtime limits.*
- Admin endpoints, metrics, and production Compose stack - *Reason: Phase 03 Session 05 owns operational visibility and stack wiring.*
- Client-facing ID migration to ULID - *Reason: Track as a Phase 03 concern, but do not alter ID semantics during database adapter hardening unless required by PostgreSQL compatibility.*

---

## 5. Technical Approach

### Architecture

Keep the existing database access boundary: API routes and services receive sessions through `get_session`, tests override the engine, and CRUD modules use SQLModel `select()` statements. Add PostgreSQL support by improving settings validation and engine construction rather than scattering database-specific branches across services.

Alembic should become the production schema authority. `alembic/env.py` should load the configured database URL from application settings, import every SQLModel metadata module, and expose deterministic metadata to migrations. Application lifespan should continue to support frictionless local development, but production mode must not silently call `SQLModel.metadata.create_all`.

### Design Patterns
- Lazy engine initialization: Preserves test overrides and avoids import-time database side effects.
- Settings-driven adapters: Keeps SQLite and PostgreSQL selected through `DATABASE_URL`.
- Migration-managed production schema: Uses Alembic for durable environments and `create_all` only for explicit local/test paths.
- ID-based CRUD re-fetching: Continues the Phase 02 pattern that avoids async expired-state failures.

### Technology Stack
- Python 3.11+
- FastAPI 0.136.1
- SQLModel 0.0.24
- SQLAlchemy async engine
- `aiosqlite` 0.21.0
- `asyncpg` for PostgreSQL
- Alembic 1.15+
- pytest and pytest-asyncio

---

## 6. Deliverables

### Files to Create
| File | Purpose | Est. Lines |
|------|---------|------------|
| `tests/test_database_session.py` | Settings and engine behavior tests for SQLite/PostgreSQL database configuration | ~130 |
| `tests/test_alembic_migrations.py` | Alembic metadata, head, upgrade, downgrade, and optional PostgreSQL smoke coverage | ~160 |
| `scripts/postgres-migration-smoke.sh` | Optional manual PostgreSQL migration smoke script gated by `DATABASE_URL` | ~80 |

### Files to Modify
| File | Changes | Est. Lines |
|------|---------|------------|
| `pyproject.toml` | Add PostgreSQL async driver dependency | ~2 |
| `app/core/config.py` | Add production database startup guard settings and validation | ~35 |
| `app/db/session.py` | Refactor engine creation and table creation behavior for SQLite/PostgreSQL | ~70 |
| `alembic/env.py` | Load settings URL, import all metadata modules, improve offline/online configuration | ~60 |
| `alembic.ini` | Keep safe default while allowing env-driven URL resolution | ~5 |
| `app/main.py` | Use explicit database startup behavior in lifespan | ~25 |
| `tests/conftest.py` | Keep tests explicitly creating in-memory SQLite schemas | ~25 |
| `app/db/render_crud.py` | Verify and adjust async transaction/query compatibility if needed | ~20 |
| `app/db/template_crud.py` | Verify and adjust async transaction/query compatibility if needed | ~20 |
| `app/db/webhook_crud.py` | Verify and adjust async transaction/query compatibility if needed | ~20 |
| `docs/development.md` | Document local database URLs and migration commands | ~40 |
| `docs/deployment.md` | Document production migration workflow and startup expectations | ~60 |

---

## 7. Success Criteria

### Functional Requirements
- [ ] SQLite remains the default local and test database path.
- [ ] PostgreSQL `DATABASE_URL` creates async sessions through `asyncpg`.
- [ ] Alembic sees render, template, template version, and webhook attempt metadata.
- [ ] Alembic can upgrade a fresh database to the current schema.
- [ ] Production mode does not rely on implicit table creation.

### Testing Requirements
- [ ] Unit tests written and passing for settings and session behavior.
- [ ] Alembic metadata and migration tests written and passing.
- [ ] Optional PostgreSQL smoke script documented and safe to skip when no database is configured.
- [ ] Existing render, template, and webhook database tests keep passing.
- [ ] Manual migration workflow reviewed from docs.

### Non-Functional Requirements
- [ ] Non-render API endpoints keep the current p95 target by preserving pooled async sessions.
- [ ] Migration errors are explicit and actionable during startup or CLI runs.
- [ ] Local development remains one-command friendly with SQLite defaults.

### Quality Gates
- [ ] All files ASCII-encoded.
- [ ] Unix LF line endings.
- [ ] Code follows project conventions.
- [ ] `ruff check .` passes.
- [ ] `ruff format --check .` passes.
- [ ] `mypy app/` passes.
- [ ] `pytest` passes, or any skipped PostgreSQL smoke check is clearly documented.

---

## 8. Implementation Notes

### Key Considerations
- Existing Alembic revisions `001` through `005` already describe the current schema. Do not create a duplicate baseline unless the migration chain is intentionally reset.
- `alembic/env.py` currently imports render and template models; ensure webhook models are included so autogenerate and metadata checks are complete.
- Keep `set_engine` test override behavior intact because current fixtures rely on it.
- Avoid import-time engine creation. The existing lazy engine pattern is intentional and should remain.
- Use `DATABASE_URL` as the only database connection source, matching CONVENTIONS.md.

### Potential Challenges
- Async Alembic URL handling: Use the existing async migration pattern and make URL resolution explicit.
- PostgreSQL smoke availability: Keep tests deterministic without external services and gate real PostgreSQL checks by environment.
- Production startup behavior: Add a clear config switch or mode check so development remains simple but production fails closed when migrations are required.
- Migration drift: Add tests that assert all table metadata is loaded and that Alembic has a single current head.

### Relevant Considerations
- [P00] **Import-time DB engine creation**: Preserve lazy engine initialization and test overrides.
- [P02] **ID-based CRUD re-fetching**: Keep CRUD patterns compatible with async session boundaries.
- [P02] **SQLAlchemy Relationship declarations with generic list types in async models**: Continue using explicit SELECTs rather than relationship-heavy models.
- [P00] **Base-36 render IDs**: Do not make schema decisions that block a future ULID migration.

### Behavioral Quality Focus
Checklist active: Yes
Top behavioral risks for this session:
- Production boot silently creates or mutates schema outside Alembic.
- Alembic metadata omits a model and autogenerate drifts from runtime tables.
- PostgreSQL configuration fails late or with unclear errors after deployment.

---

## 9. Testing Strategy

### Unit Tests
- Settings defaults keep SQLite and validate PostgreSQL/production combinations.
- Engine/session helpers select the correct async driver behavior for SQLite and PostgreSQL URLs.
- Production startup guard skips implicit table creation when configured.

### Integration Tests
- Alembic metadata imports include `renders`, `templates`, `template_versions`, and `webhook_attempts`.
- Alembic has one head and can upgrade/downgrade the SQLite test database.
- Optional PostgreSQL migration smoke script upgrades a disposable database when `DATABASE_URL` points to PostgreSQL.

### Manual Testing
- Run `alembic upgrade head` against the default SQLite database.
- If PostgreSQL is available, run the smoke script against a disposable database.
- Start the API in local mode and verify health still succeeds.

### Edge Cases
- Missing or invalid `DATABASE_URL`.
- `postgres://` versus `postgresql+asyncpg://` URL variants.
- Existing SQLite tests with in-memory database URLs.
- Alembic offline mode with the configured URL.
- Production mode without migrations applied.

---

## 10. Dependencies

### External Libraries
- `asyncpg`: PostgreSQL async driver.
- `SQLModel`: Existing ORM/model layer.
- `SQLAlchemy`: Async engine and session layer.
- `Alembic`: Migration framework.
- `aiosqlite`: Existing SQLite async driver.

### Other Sessions
- **Depends on**: `phase02-session01-template-models-and-crud-api`, `phase02-session02-template-variables-and-rendering`, `phase02-session03-webhook-delivery-system`, `phase02-session04-transitions-and-positioning`, `phase02-session05-audio-polish-and-hardening`
- **Depended by**: `phase03-session02-s3-compatible-storage-and-download-modes`, `phase03-session03-api-key-authentication-and-access-control`, `phase03-session04-limits-resource-controls-and-asset-security-hardening`, `phase03-session05-operational-visibility-and-production-stack`

---

## Next Steps

Run the implement workflow step to begin AI-led implementation.
