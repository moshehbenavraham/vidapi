# Task Checklist

**Session ID**: `phase03-session05-operational-visibility-and-production-stack`
**Total Tasks**: 25
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
| Foundation | 6 | 6 | 0 |
| Implementation | 12 | 12 | 0 |
| Testing | 4 | 4 | 0 |
| **Total** | **25** | **25** | **0** |

---

## Setup (3 tasks)

Initial configuration and environment preparation.

- [x] T001 [S0305] Verify existing render, webhook, logging, health, Docker, and deployment coverage before changing behavior (`app/main.py`)
- [x] T002 [S0305] [P] Create operational router scaffold with authenticated route placeholders and bounded pagination constants (`app/api/routes_ops.py`)
- [x] T003 [S0305] [P] Create redacted operational response model scaffold for render, failure, webhook, and metrics payloads (`app/models/ops.py`)

---

## Foundation (6 tasks)

Core structures and base implementations.

- [x] T004 [S0305] Add read-only render aggregate queries for status counts, recent failures, queue wait, and duration metrics with bounded deterministic ordering (`app/db/render_crud.py`)
- [x] T005 [S0305] Add read-only webhook aggregate queries for recent attempts and outcome counts with bounded deterministic ordering (`app/db/webhook_crud.py`)
- [x] T006 [S0305] [P] Create metrics formatter service for render, queue, renderer failure, and webhook outcomes with explicit missing-Redis handling (`app/services/metrics.py`)
- [x] T007 [S0305] Add safe request logging helpers and redaction conventions for request_id, method, path, status, and duration fields (`app/core/logging.py`)
- [x] T008 [S0305] Add operational error response metadata for protected ops endpoints without changing public health behavior (`app/models/errors.py`)
- [x] T009 [S0305] Update worker Redis health check parsing for password-bearing Redis URLs with timeout and failure-path handling (`scripts/worker-healthcheck.sh`)

---

## Implementation (12 tasks)

Main feature implementation.

- [x] T010 [S0305] Implement operational render list, failure list, status counts, and webhook attempt endpoints with authorization enforced at router mount (`app/api/routes_ops.py`)
- [x] T011 [S0305] Implement operational metrics endpoint using bounded DB aggregates and queue checks with timeout, retry/backoff, and failure-path handling (`app/api/routes_ops.py`)
- [x] T012 [S0305] Mount ops router and log request completion with request_id preserved on success and exception paths (`app/main.py`)
- [x] T013 [S0305] Emit queue wait, render duration, stage, and failure context logs from worker transitions without raw composition data (`app/workers/render_worker.py`)
- [x] T014 [S0305] Emit webhook delivery outcome logs with render_id, webhook_event, attempt, status code, and bounded error excerpts (`app/services/webhook_service.py`)
- [x] T015 [S0305] [P] Create production-like Compose overlay for API, worker, Redis AUTH, PostgreSQL, MinIO, health checks, and durable volumes (`docker-compose.prod.yml`)
- [x] T016 [S0305] [P] Create production environment sample for Postgres, Redis AUTH/TLS expectations, S3/MinIO, API key auth, and resource limits (`.env.production.example`)
- [x] T017 [S0305] [P] Create operations guide for ops endpoints, metrics, logs, health checks, troubleshooting, and safe redaction expectations (`docs/operations.md`)
- [x] T018 [S0305] [P] Update README quickstart and architecture notes to link operational endpoints, metrics, and production-like stack usage (`README.md`)
- [x] T019 [S0305] Update deployment guide with production-like compose commands, Redis AUTH/TLS, Postgres, MinIO, and verification steps (`docs/deployment.md`)
- [x] T020 [S0305] Update environment matrix with production variables for API keys, Postgres, Redis AUTH/TLS, S3/MinIO, metrics, and logs (`docs/environments.md`)
- [x] T021 [S0305] Update incident-response runbook with ops endpoint, metrics, log, queue, Redis, Postgres, and MinIO triage steps (`docs/runbooks/incident-response.md`)

---

## Testing (4 tasks)

Verification and quality assurance.

- [x] T022 [S0305] [P] Write API tests for ops endpoints, auth requirements, pagination bounds, status filters, and redaction (`tests/test_ops_api.py`)
- [x] T023 [S0305] [P] Write metrics tests for aggregate snapshots, Prometheus text output, deterministic ordering, and unavailable Redis behavior (`tests/test_metrics.py`)
- [x] T024 [S0305] Write logging tests for request_id propagation, request completion fields, and sensitive-field exclusion (`tests/test_logging.py`)
- [x] T025 [S0305] Run targeted tests, static compose/config checks, and ASCII validation on all session files (`tests/test_ops_api.py`)

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

Run the implement workflow step to begin AI-led implementation.
