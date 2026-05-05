# PRD Phase 03: Production Hardening

**Status**: In Progress
**Sessions**: 5 (initial estimate)
**Estimated Duration**: 10-20 days

**Progress**: 1/5 sessions (20%)

---

## Overview

Make VidAPI safe and operable outside local development by adding production database migrations, S3-compatible storage, API key authentication, deployment-grade limits, structured observability, and a production-like Docker Compose stack with Postgres, Redis, and MinIO.

---

## Progress Tracker

| Session | Name | Status | Est. Tasks | Validated |
|---------|------|--------|------------|-----------|
| 01 | PostgreSQL Persistence and Alembic Migrations | Complete | ~20 | 2026-05-05 |
| 02 | S3-compatible Storage and Download Modes | Not Started | ~20 | - |
| 03 | API Key Authentication and Access Control | Not Started | ~18 | - |
| 04 | Limits, Resource Controls, and Asset Security Hardening | Not Started | ~20 | - |
| 05 | Operational Visibility and Production Stack | Not Started | ~20 | - |

---

## Completed Sessions

- Session 01: PostgreSQL Persistence and Alembic Migrations (2026-05-05)

---

## Upcoming Sessions

- Session 02: S3-compatible Storage and Download Modes

---

## Objectives

1. Replace local-only persistence assumptions with PostgreSQL support and migrations.
2. Add durable object storage and secure download URL modes for production deployments.
3. Protect non-health APIs with API keys, bounded limits, resource controls, and operational observability.

---

## Prerequisites

- Phase 02 completed (Templates and Polish)
- Async API, worker, Redis queue, templates, webhooks, and rate limiting operational
- Docker Compose stack from Phase 01 available as the base for production-like services

---

## Technical Considerations

### Architecture
- Keep public API behavior stable while swapping local development adapters for production-ready adapters.
- Database and storage adapters must remain configurable so SQLite/local filesystem stay available for tests and local development.
- Security controls should fail closed in production mode and remain explicit in debug/local mode.
- Operational endpoints should expose enough state for operators without leaking secrets, filesystem paths, or raw user content.

### Technologies
- PostgreSQL with async SQLAlchemy or SQLModel engine support
- Alembic for schema migrations
- S3-compatible storage via boto3 or an async-compatible wrapper
- API key hashing and dependency-based FastAPI authentication
- Prometheus-style metrics or a lightweight metrics endpoint
- Docker Compose services for API, worker, Redis, Postgres, and MinIO

### Risks
- Migration drift between SQLModel definitions and Alembic revisions: mitigate with focused migration tests and documented revision generation workflow.
- S3 URL mode differences across AWS, R2, and MinIO: mitigate with adapter tests and explicit signed, public, and proxied modes.
- API key rollout can break health checks or internal worker paths: keep `/v1/health` unauthenticated and scope auth dependencies to public routes.
- Resource limits may be platform-specific: implement portable time, size, duration, track, clip, fps, and resolution limits before lower-level cgroup controls.

### Relevant Considerations
- [P00] **Base-36 render IDs**: Migrate render identifiers to python-ulid or provide a compatible production-safe path.
- [P01] **TTL-based workspace cleanup**: Add periodic orphan workspace cleanup for crashed workers.
- [P00] **FFmpeg subprocess resource limits**: Add timeout, duration, size, and practical subprocess guardrails.
- [P00] **No authentication**: Scope non-health API access to authenticated API key callers.
- [P01] **Redis connection TLS not enforced**: Document and enforce production `rediss://` when production mode is enabled.
- [P01] **Redis AUTH not configured**: Production stack must require Redis authentication.
- [P02] **Webhook delivery durability**: Harden webhook retries or document any remaining non-durable edge cases.

---

## Success Criteria

Phase complete when:
- [ ] All 5 sessions completed
- [ ] VidAPI can run against PostgreSQL with Alembic-managed schema
- [ ] Render artifacts can be stored in S3-compatible storage and returned through configured URL modes
- [ ] Non-health API routes require API key authentication when enabled
- [ ] Request, asset, render, queue, and subprocess limits are enforced by tests
- [ ] Operators can inspect render jobs, webhook attempts, logs, metrics, and deployment health
- [ ] Docker Compose can run API, worker, Redis, Postgres, and MinIO together

---

## Dependencies

### Depends On
- Phase 02: Templates and Polish

### Enables
- Phase 04: Advanced Rendering
