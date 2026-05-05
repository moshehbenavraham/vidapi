# Session 01: PostgreSQL Persistence and Alembic Migrations

**Session ID**: `phase03-session01-postgresql-persistence-and-alembic-migrations`
**Status**: Complete
**Completed**: 2026-05-05
**Estimated Tasks**: ~20
**Estimated Duration**: 3-4 hours

---

## Objective

Add production PostgreSQL support and Alembic migrations while preserving SQLite as the local development and test database.

---

## Scope

### In Scope (MVP)
- Database URL configuration for SQLite and PostgreSQL
- Async PostgreSQL driver dependency and engine/session setup
- Alembic environment configured for project models
- Initial migration covering existing render, template, template_version, and webhook_attempt tables
- Migration test or smoke check against a disposable database when available
- Repository documentation for creating and applying migrations
- Compatibility checks for existing async SQLModel query patterns
- Production startup behavior that does not auto-create unmanaged schemas

### Out of Scope
- S3 storage adapter (Session 02)
- API key authentication (Session 03)
- Admin endpoints and metrics (Session 05)

---

## Prerequisites

- [x] Phase 02 complete with stable database models
- [x] Current SQLite test path remains green before migration changes

---

## Deliverables

1. PostgreSQL-capable database configuration
2. Alembic environment and initial migration revision
3. Database startup path appropriate for local and production modes
4. Migration documentation
5. Tests or smoke checks covering SQLite compatibility and migration metadata

---

## Success Criteria

- [x] SQLite remains the default local/test database path
- [x] PostgreSQL database URL creates async sessions successfully
- [x] Alembic can upgrade a fresh database to the current schema
- [x] Existing render/template/webhook tests keep passing
- [x] Production mode does not rely on implicit table creation
