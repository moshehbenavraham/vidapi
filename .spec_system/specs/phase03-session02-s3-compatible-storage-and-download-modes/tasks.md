# Task Checklist

**Session ID**: `phase03-session02-s3-compatible-storage-and-download-modes`
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
| Foundation | 5 | 2 | 3 |
| Implementation | 8 | 0 | 8 |
| Testing | 4 | 0 | 4 |
| **Total** | **20** | **5** | **15** |

---

## Setup (3 tasks)

Initial dependency, configuration, and current-flow preparation.

- [x] T001 [S0302] Verify storage and download prerequisites from Phase 03 Session 01 (`.spec_system/specs/phase03-session01-postgresql-persistence-and-alembic-migrations/validation.md`)
- [x] T002 [S0302] Add S3 client dependency for upload, download, and presigned URL support (`pyproject.toml`)
- [x] T003 [S0302] Add storage backend, S3, URL mode, expiry, and public base URL settings with production validation (`app/core/config.py`)

---

## Foundation (5 tasks)

Core storage contracts and backend construction.

- [x] T004 [S0302] Define artifact URI, media type, backend, and URL mode contract types (`app/storage/base.py`)
- [x] T005 [S0302] Extend local storage to satisfy the artifact backend contract while preserving workspace behavior (`app/storage/local.py`)
- [ ] T006 [S0302] [P] Create S3-compatible storage backend with deterministic keys, timeout-aware operations, and explicit error mapping (`app/storage/s3.py`)
- [ ] T007 [S0302] [P] Create storage URL resolver for proxy, signed, and public modes with credential-leak safeguards (`app/storage/urls.py`)
- [ ] T008 [S0302] Create settings-driven storage factory and update FastAPI dependencies (`app/storage/factory.py`, `app/api/deps.py`)

---

## Implementation (8 tasks)

Main S3 artifact persistence and API behavior.

- [ ] T009 [S0302] Update render submission to persist input JSON through configured storage before enqueue with rollback/error mapping (`app/api/routes_renders.py`)
- [ ] T010 [S0302] Update template render submission to persist input and expanded JSON through configured storage before enqueue with rollback/error mapping (`app/api/routes_templates.py`)
- [ ] T011 [S0302] Update worker preflight to read render input through storage backend instead of assuming local path visibility (`app/workers/render_worker.py`)
- [ ] T012 [S0302] Publish expanded composition, compiled spec, replay metadata, output, poster, and logs through storage after each stage with transaction-safe path updates (`app/services/render_service.py`)
- [ ] T013 [S0302] Use storage URL resolver in render status responses for output and poster URLs (`app/api/routes_renders.py`)
- [ ] T014 [S0302] Implement proxied output and poster endpoints with streaming S3/local reads and missing-artifact handling (`app/api/routes_renders.py`)
- [ ] T015 [S0302] Update webhook payload URLs to use the shared storage URL resolver (`app/services/webhook_service.py`)
- [ ] T016 [S0302] Update worker startup and app dependency fixtures to construct configured storage backends consistently (`app/workers/render_worker.py`, `tests/conftest.py`)

---

## Testing (4 tasks)

Verification and quality assurance.

- [ ] T017 [S0302] [P] Add storage settings and local adapter compatibility tests (`tests/test_config.py`, `tests/test_storage.py`)
- [ ] T018 [S0302] [P] Add S3 backend and URL resolver tests using mocked clients without real credentials (`tests/test_s3_storage.py`, `tests/test_storage_urls.py`)
- [ ] T019 [S0302] Add API, worker, template render, and webhook tests for proxy, signed, public, and missing-artifact behavior (`tests/test_api_renders.py`, `tests/test_worker_pipeline.py`, `tests/test_api_template_renders.py`, `tests/test_webhook_service.py`)
- [ ] T020 [S0302] Update storage documentation and run quality gates (`docs/development.md`, `docs/deployment.md`)

---

## Completion Checklist

Before marking session complete:

- [ ] All tasks marked `[x]`
- [ ] All tests passing
- [ ] All files ASCII-encoded
- [ ] implementation-notes.md updated
- [ ] Ready for the validate workflow step

---

## Next Steps

Run the implement workflow step to begin AI-led implementation.
