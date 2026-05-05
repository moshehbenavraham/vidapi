# Session Specification

**Session ID**: `phase03-session05-operational-visibility-and-production-stack`
**Phase**: 03 - Production Hardening
**Status**: Complete
**Created**: 2026-05-05

---

## 1. Session Overview

This session completes Phase 03 by making VidAPI observable and operable in a production-like deployment. Sessions 01-04 added PostgreSQL migrations, S3-compatible storage, API key authentication, and bounded resource controls; the remaining gap is that operators still need focused views into render state, webhook delivery, queue health, metrics, logs, and a full compose stack that exercises the production adapters together.

The work adds authenticated operational endpoints for recent jobs, failure inspection, webhook attempts, status counts, health details, and metrics. It also tightens structured logging so request IDs and render IDs consistently appear across API, worker, and webhook paths without logging raw composition bodies, secrets, or full asset URLs.

The deployment work creates a production-like Docker Compose overlay with API, worker, Redis with authentication, PostgreSQL, and MinIO. It updates environment samples, health checks, Redis security guidance, and operations documentation so an operator can start, verify, troubleshoot, and tune the stack from documented commands.

---

## 2. Objectives

1. Add authenticated operational endpoints for render inspection, status counts, failure details, and webhook attempts.
2. Expose basic metrics for queue wait time, render duration, status counts, renderer failures, and webhook outcomes.
3. Standardize structured request, render, and webhook logging with request_id and render_id correlation.
4. Provide a production-like Docker Compose stack with API, worker, Redis AUTH, PostgreSQL, MinIO, health checks, and operator documentation.

---

## 3. Prerequisites

### Required Sessions
- [x] `phase03-session01-postgresql-persistence-and-alembic-migrations` - Provides PostgreSQL metadata persistence and migration verification.
- [x] `phase03-session02-s3-compatible-storage-and-download-modes` - Provides S3-compatible storage and download URL modes needed by production stack checks.
- [x] `phase03-session03-api-key-authentication-and-access-control` - Provides API key protection for non-health operational routes.
- [x] `phase03-session04-limits-resource-controls-and-asset-security-hardening` - Provides request, queue, asset, subprocess, Redis, and workspace guardrails.
- [x] `phase02-session03-webhook-delivery-system` - Provides webhook attempt records that operational endpoints must expose.

### Required Tools/Knowledge
- FastAPI routers, dependency injection, OpenAPI response metadata, and protected route registration.
- SQLModel and SQLAlchemy aggregate queries for counts, recent failures, and bounded lists.
- structlog context variables, request middleware, and log field hygiene.
- Docker Compose services, health checks, Redis AUTH, PostgreSQL, and MinIO environment wiring.

### Environment Requirements
- Python 3.11+ environment with project dependencies installed through `uv`.
- Existing SQLite-backed tests remain available for route, CRUD, metrics, and logging coverage.
- Docker and Docker Compose are required only for manual verification of the production-like stack.

---

## 4. Scope

### In Scope (MVP)
- Operator can list recent jobs, filter by status, and inspect failed render details through authenticated operational endpoints - keep bounded pagination and avoid exposing raw composition JSON.
- Operator can view render status counts, recent renderer failures, and webhook attempts - add read-only aggregate queries and redacted response models.
- Operator can scrape or inspect basic metrics for queue wait time, render duration, status counts, renderer failures, and webhook delivery outcomes - derive metrics from durable metadata and bounded Redis checks.
- System logs include request_id for API requests and render_id for render, worker, and webhook flows - preserve existing contextvars and add route-level duration/status logging.
- Docker Compose can run API, worker, Redis, PostgreSQL, and MinIO together - add a production-like compose file and environment sample that exercise PostgreSQL and S3 settings.
- Production Redis authentication and TLS expectations are documented and Redis AUTH is used by the compose overlay - update Redis URLs, health checks, and deployment docs.
- Operators have operations and troubleshooting documentation - document metrics, logs, health checks, common failures, and verification commands.
- Tests cover operational routes, aggregate queries, metrics output, request logging, OpenAPI auth behavior, and config file expectations.

### Out of Scope (Deferred)
- Full dashboard UI - Reason: authenticated JSON and metrics endpoints satisfy the Phase 03 operator MVP.
- Alerting integrations such as PagerDuty, Slack, or email - Reason: alert routing belongs after stable metrics exist.
- Kubernetes, Terraform, Helm, or cloud-specific deployment assets - Reason: this phase targets a Docker Compose production-like stack.
- Distributed tracing or OpenTelemetry exporters - Reason: structured logs and request/render IDs are sufficient for single-node operations.
- Durable metrics time-series storage - Reason: the MVP exposes current aggregate metrics without adding a metrics database.

---

## 5. Technical Approach

### Architecture

Create an `app/api/routes_ops.py` router mounted under `/v1/ops` with the same API key dependency used by render and template routes. Keep route handlers thin: parse filters, call CRUD/service helpers, and return Pydantic response models from `app/models/ops.py`. All list endpoints must enforce bounded pagination and deterministic ordering.

Extend `app/db/render_crud.py` with read-only operational queries: status counts, recent renders, recent failures, queue wait and render duration samples, and renderer failure counts. Extend `app/db/webhook_crud.py` with recent attempt listing and outcome aggregates. Query helpers should return simple records or typed dataclasses so route code stays small and tests can cover database behavior directly.

Add `app/services/metrics.py` to convert render, webhook, and queue observations into a Prometheus-style text response without adding a new dependency. Metrics should include render status counts, renderer failure counts, webhook success/failure counts, queue depth, queue wait seconds, and render duration seconds where timestamps are available. The service should tolerate missing Redis in sync mode and never expose secret configuration values.

Enhance structured logging through `app/core/logging.py` and `app/main.py`. Keep `X-Request-ID` support, bind request_id into structlog contextvars, add method/path/status/duration logging at request completion, and avoid raw body, API key, callback URL, or storage credential fields. Worker and webhook paths already bind render IDs in key places; add any missing render_id and webhook outcome fields while preserving `webhook_event` naming.

Create `docker-compose.prod.yml` for the production-like stack. It should define API, worker, Redis with a password, PostgreSQL, MinIO, named volumes, health checks, service dependencies, and non-root application containers. Create `.env.production.example` with PostgreSQL, S3/MinIO, API key hash, Redis AUTH, and production safety settings. Update worker health check parsing so Redis password-bearing URLs work.

Update docs to explain how to run the stack, verify health, inspect metrics, review operational endpoints, troubleshoot failures, and apply Redis TLS guidance. Keep docs clear that the compose overlay is production-like for validation and self-hosted operation, not a cloud HA deployment.

### Design Patterns
- Thin operational routes: Keep FastAPI handlers as authorization, validation, and response mapping boundaries.
- Read-only query helpers: Keep aggregate SQL in `app/db/*_crud.py` rather than route handlers.
- Redacted response models: Expose IDs, statuses, timings, and excerpts, not secrets or raw user content.
- Metrics formatter service: Keep Prometheus text formatting pure and independently testable.
- Context-bound logging: Use structlog contextvars so request_id and render_id attach consistently without manual plumbing everywhere.
- Production-like overlay: Keep dev compose behavior stable while adding a separate production-like compose file.

### Technology Stack
- Python 3.11+
- FastAPI 0.136.1 / Starlette 0.52.1
- SQLModel / SQLAlchemy async sessions
- structlog
- ARQ 0.28.x / Redis
- PostgreSQL / asyncpg
- MinIO as S3-compatible storage
- Docker Compose
- pytest + pytest-asyncio + httpx ASGI transport

---

## 6. Deliverables

### Files to Create
| File | Purpose | Est. Lines |
|------|---------|------------|
| `app/api/routes_ops.py` | Authenticated operational endpoints for renders, failures, webhooks, health details, and metrics | ~220 |
| `app/models/ops.py` | Pydantic response models for redacted operational views and metric summaries | ~180 |
| `app/services/metrics.py` | Prometheus-style metrics collection and text formatting helpers | ~180 |
| `tests/test_ops_api.py` | Route tests for operational endpoints, auth, pagination, and redaction | ~320 |
| `tests/test_metrics.py` | Unit tests for metrics aggregation and text output | ~220 |
| `tests/test_logging.py` | Tests for request ID propagation and structured access log fields | ~180 |
| `docker-compose.prod.yml` | Production-like Compose overlay with API, worker, Redis AUTH, Postgres, and MinIO | ~190 |
| `.env.production.example` | Production-like environment sample using Postgres, Redis AUTH, and S3/MinIO settings | ~100 |
| `docs/operations.md` | Operator guide for endpoints, metrics, logs, health checks, and troubleshooting | ~220 |

### Files to Modify
| File | Changes | Est. Lines |
|------|---------|------------|
| `app/main.py` | Mount ops router and add structured request completion logging | ~45 |
| `app/core/logging.py` | Add request logging helpers and safe field conventions | ~80 |
| `app/db/render_crud.py` | Add status, failure, queue wait, and render duration aggregate queries | ~130 |
| `app/db/webhook_crud.py` | Add recent attempt and webhook outcome aggregate queries | ~90 |
| `app/workers/render_worker.py` | Emit queue wait, render duration, stage, and failure context logs | ~70 |
| `app/services/webhook_service.py` | Emit structured webhook outcome fields for metrics and troubleshooting | ~45 |
| `app/models/errors.py` | Document operational endpoint error responses where needed | ~20 |
| `scripts/worker-healthcheck.sh` | Support Redis URLs with AUTH and keep health checks bounded | ~60 |
| `README.md` | Link production-like stack, ops endpoints, metrics, and operations guide | ~60 |
| `docs/deployment.md` | Add production-like compose usage, Redis AUTH/TLS, Postgres, and MinIO verification | ~140 |
| `docs/environments.md` | Update production configuration matrix and required environment variables | ~80 |
| `docs/runbooks/incident-response.md` | Add operational endpoint and metrics-driven triage steps | ~80 |

---

## 7. Success Criteria

### Functional Requirements
- [ ] Authenticated operators can list recent renders with bounded pagination and optional status filtering.
- [ ] Authenticated operators can inspect recent failures without raw composition JSON, storage credentials, or full callback secrets.
- [ ] Authenticated operators can list webhook attempts by render ID and inspect recent webhook failures.
- [ ] Authenticated operators can retrieve render status counts, renderer failure counts, queue wait metrics, render duration metrics, queue depth, and webhook outcome metrics.
- [ ] Logs include request_id for API requests and render_id where render, worker, and webhook code has render context.
- [ ] Operational endpoints are absent from public health route dependencies and protected by API key auth like other non-health routes.
- [ ] Docker Compose production-like stack starts API, worker, Redis, PostgreSQL, and MinIO with health checks and durable volumes.
- [ ] Redis AUTH is configured in the production-like stack and production Redis TLS expectations remain documented.

### Testing Requirements
- [ ] Unit tests written and passing for render and webhook aggregate queries.
- [ ] Unit tests written and passing for metrics text output and missing-data behavior.
- [ ] API tests written and passing for operational endpoints, auth requirements, pagination bounds, status filters, and redaction.
- [ ] Logging tests written and passing for request_id propagation and request completion log fields.
- [ ] Compose/config tests or static checks verify production-like compose references Postgres, MinIO, Redis AUTH, and required environment variables.
- [ ] Manual testing completed for health, metrics, one ops render list, and one Docker Compose production-like startup path.

### Non-Functional Requirements
- [ ] Operational list endpoints are bounded to a maximum limit of 100 and use deterministic ordering.
- [ ] Metrics collection avoids unbounded queries and degrades gracefully when Redis is unavailable.
- [ ] Logs do not include API key values, raw composition bodies, Redis credentials, S3 credentials, or full presigned URLs.
- [ ] The production-like compose overlay does not break existing `docker compose up --build` development behavior.

### Quality Gates
- [ ] All files ASCII-encoded.
- [ ] Unix LF line endings.
- [ ] Code follows project conventions.

---

## 8. Implementation Notes

### Key Considerations
- The existing `/v1/renders` endpoint already lists client-facing render rows. Operational routes should add failure details, counts, webhook attempts, metrics, and troubleshooting context rather than duplicating the client API shape.
- API key auth already protects non-health routers when mounted with `protected_dependencies` in `app/main.py`. The ops router should be registered in that same protected group.
- Keep operational payloads redacted. IDs, status, timestamps, error codes, short error messages, attempt numbers, and status codes are useful. Raw input JSON, compiled specs, callback URLs with secrets, and storage credentials are not.
- The metrics service can start with current aggregate snapshots. Avoid adding a long-running in-memory metrics registry that would miss events across API and worker processes.
- Queue wait can be computed from `started_at - created_at` for renders that started; render duration can be computed from `completed_at - started_at` for terminal renders with both timestamps.
- In sync mode or when Redis is not configured, queue metrics should report unavailable or zero in a documented way rather than failing the whole metrics endpoint.
- Do not log `event` as a structlog key in async webhook logs because existing guidance notes `event` is reserved; keep using `webhook_event`.

### Potential Challenges
- Aggregate queries may differ between SQLite and PostgreSQL: prefer portable SQLAlchemy expressions and cover them with SQLite tests.
- Metrics endpoints can become expensive if they scan every row: bound time windows or aggregate directly in SQL where possible.
- Health checks with Redis AUTH are easy to break with shell URL parsing: keep the health script simple and test password-bearing `REDIS_URL` parsing where practical.
- Compose production-like files may tempt real production use without TLS termination or secrets management: docs should state what the overlay verifies and what operators must provide externally.

### Relevant Considerations
- [P01] **Redis connection TLS not enforced**: This session documents production `rediss://` expectations while using Redis AUTH in the compose overlay.
- [P01] **Redis AUTH not configured**: This session adds password-bearing Redis URLs and health checks to the production-like stack.
- [P02] **Webhook delivery durability**: Operational webhook attempt views and outcome metrics make remaining delivery behavior inspectable.
- [P02] **structlog event naming**: Use `webhook_event` instead of `event` in webhook logs and metrics context.
- [P00] **Replay metadata (`replay.json`)**: Failure inspection should point operators to replay artifacts without exposing raw artifact contents through ops endpoints.
- [P01] **Worker drives status transitions externally**: Metrics and ops endpoints should derive status and timing from worker-owned transitions.

### Behavioral Quality Focus
Checklist active: Yes
Top behavioral risks for this session:
- Operational endpoints leak secrets, raw render input, callback URLs, filesystem paths, or presigned URLs.
- Metrics queries scan too much data or fail completely when Redis is unavailable.
- Request logging loses request_id on exceptions or duplicates context between concurrent requests.
- Production-like compose changes break the existing development compose path.

---

## 9. Testing Strategy

### Unit Tests
- Test render aggregate query helpers for status counts, recent failures, queue wait samples, and render duration samples.
- Test webhook aggregate query helpers for recent attempts, failure filtering, and outcome counts.
- Test metrics text formatting for valid Prometheus names, deterministic output ordering, and missing Redis behavior.
- Test logging helpers avoid sensitive fields and preserve request_id.

### Integration Tests
- Test `/v1/ops/renders`, `/v1/ops/renders/failures`, `/v1/ops/renders/status-counts`, `/v1/ops/webhooks`, and `/v1/ops/metrics`.
- Test operational endpoints require API keys when auth is enabled.
- Test operational endpoint pagination clamps limit and offset and returns deterministic ordering.
- Test OpenAPI documents protected operational endpoints without making health routes protected.

### Manual Testing
- Start the API locally and verify `X-Request-ID` appears in responses and structured logs.
- Seed a few render rows and webhook attempts, then call the operational endpoints.
- Run the production-like compose stack with Postgres, Redis AUTH, and MinIO, then verify `/v1/health` and one metrics request.

### Edge Cases
- No render rows exist.
- All renders are queued and have no `started_at`.
- Failed renders have no `error_code` or no `error_message`.
- Webhook attempts exist for deleted or missing render IDs.
- Redis is unavailable while metrics are requested.
- Requests fail before route handling and still need request completion logging.
- `REDIS_URL` contains a password, database number, or special characters.

---

## 10. Dependencies

### External Libraries
- No new Python runtime dependency is required for the MVP metrics endpoint.
- Docker Compose uses official `postgres`, `redis`, and `minio/minio` images.

### Other Sessions
- **Depends on**: Phase 03 Sessions 01-04, Phase 02 Session 03.
- **Depended by**: Phase transition audit, pipeline, infra, documents, and Phase 04 advanced rendering.

---

## Next Steps

Run the implement workflow step to begin AI-led implementation.
