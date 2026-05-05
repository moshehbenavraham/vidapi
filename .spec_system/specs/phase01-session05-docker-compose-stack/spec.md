# Session Specification

**Session ID**: `phase01-session05-docker-compose-stack`
**Phase**: 01 - Async Jobs and Multi-track
**Status**: Not Started
**Created**: 2026-05-05

---

## 1. Session Overview

This session delivers the Docker Compose stack that completes Phase 01. The existing codebase has a single combined Dockerfile and a minimal docker-compose.yml that only runs the API service in sync mode. This session splits the build into separate API and worker images, adds Redis as a service, wires async render mode, and verifies the full pipeline works end-to-end from container startup.

The Docker Compose stack is the final deliverable of Phase 01 and the first time the complete async render pipeline (API -> Redis -> Worker -> Storage) runs in a self-contained, one-command environment. This is essential for onboarding developers, running integration tests, and preparing the production deployment shape for Phase 03.

The session also addresses several CONSIDERATIONS.md concerns: workspace cleanup in containers, environment-based configuration for Redis, and container security with non-root users and health checks.

---

## 2. Objectives

1. Split the existing monolithic Dockerfile into a slim API image and a full worker image with Node, Editly, FFmpeg, and fonts
2. Deliver a docker-compose.yml that starts API, worker, and Redis with one command
3. Verify end-to-end async render flow: submit via API, worker picks up from Redis, completes render, status transitions to succeeded
4. Ensure all containers run as non-root with working health checks

---

## 3. Prerequisites

### Required Sessions
- [x] `phase01-session01-redis-arq-queue-integration` - ARQ queue and Redis pool
- [x] `phase01-session02-worker-render-pipeline` - Worker process with stage-by-stage pipeline
- [x] `phase01-session03-progress-tracking-and-cancellation` - Status state machine and cancellation
- [x] `phase01-session04-multi-track-and-audio-mixing` - Multi-track compositing and audio

### Required Tools/Knowledge
- Docker Engine 24+ with BuildKit
- Docker Compose v2
- Understanding of multi-stage Docker builds

### Environment Requirements
- Docker and Docker Compose installed and running
- Ports 8000 (API) and 6379 (Redis) available on host

---

## 4. Scope

### In Scope (MVP)
- Dockerfile.api for the API service (slim Python image with FastAPI + Uvicorn) - split from monolithic Dockerfile
- Dockerfile.worker for the worker service (Python + Node + Editly + FFmpeg + fonts) - derived from existing Dockerfile
- docker-compose.yml with API, worker, and Redis services on shared network
- Shared volume for SQLite database and render artifacts in development
- Environment variable configuration for Redis URL, render mode, and shared settings
- Health checks for API (HTTP), worker (ARQ health key), and Redis (redis-cli ping)
- Non-root user in both API and worker containers
- Worker health check script that verifies ARQ liveness via Redis key
- End-to-end smoke test script for verification
- Docker quick start section in README.md
- .env.docker with default environment values for the compose stack

### Out of Scope (Deferred)
- PostgreSQL container - *Reason: Phase 03 production hardening*
- MinIO/S3 container - *Reason: Phase 03 production hardening*
- Production secrets management - *Reason: Phase 03*
- Multi-stage build size optimization - *Reason: future improvement*
- CI/CD Docker build pipeline - *Reason: Phase transition audit/pipeline steps*

---

## 5. Technical Approach

### Architecture
The stack runs three services on a single Docker bridge network (`vidapi-net`):

```
Host :8000 -> api (FastAPI, sync SQLite, enqueue to Redis)
               |
               v
             redis (ARQ broker, port 6379)
               |
               v
             worker (ARQ consumer, Editly/FFmpeg renderer)
               |
               v
             Shared volume: ./data (SQLite DB + render artifacts)
```

The API and worker share the same SQLite database file and local storage directory via a bind mount. Redis handles job dispatch only. The worker image includes the full rendering toolchain (Node.js, Editly, FFmpeg, fonts) while the API image is a lighter Python-only build.

### Design Patterns
- **Multi-stage Docker build**: Node/Editly installed in a builder stage and copied to the runtime stage (worker only)
- **Shared base**: Both Dockerfiles use python:3.11-slim as the runtime base
- **Health check delegation**: API uses HTTP /health endpoint; worker uses an ARQ Redis health key check script; Redis uses redis-cli ping
- **Environment-driven config**: All service configuration passes through environment variables, matching pydantic-settings pattern in config.py

### Technology Stack
- Docker Engine 24+ with BuildKit
- Docker Compose v2
- python:3.11-slim base image
- node:20-slim for Editly build stage
- redis:7-alpine for the broker

---

## 6. Deliverables

### Files to Create
| File | Purpose | Est. Lines |
|------|---------|------------|
| `Dockerfile.api` | Slim API service image | ~30 |
| `Dockerfile.worker` | Full worker image with Node/Editly/FFmpeg | ~45 |
| `docker-compose.yml` | Multi-service compose stack (replaces existing) | ~65 |
| `.env.docker` | Default environment variables for compose | ~20 |
| `scripts/worker-healthcheck.sh` | Worker health check via ARQ Redis key | ~15 |
| `scripts/smoke-test.sh` | End-to-end render verification script | ~80 |

### Files to Modify
| File | Changes | Est. Lines |
|------|---------|------------|
| `Dockerfile` | Archive or remove (replaced by Dockerfile.api + Dockerfile.worker) | -40 |
| `.dockerignore` | Add entries for new script and env files as needed | ~5 |
| `README.md` | Add Docker Compose quick start section | ~40 |

---

## 7. Success Criteria

### Functional Requirements
- [ ] `docker compose up --build` starts API, worker, and Redis successfully
- [ ] API responds to GET /v1/health from host at localhost:8000
- [ ] Health endpoint shows Redis status as healthy
- [ ] POST /v1/renders returns 202 Accepted and worker picks up the job
- [ ] Worker completes render and status transitions to succeeded
- [ ] GET /v1/renders/{id} reflects completed status with output path
- [ ] Multiple sequential renders complete without workspace corruption

### Testing Requirements
- [ ] Smoke test script passes end-to-end
- [ ] Health checks pass for all three services

### Non-Functional Requirements
- [ ] API health check response under 200ms
- [ ] Worker picks up queued job within 5 seconds of enqueue
- [ ] Containers run as non-root user (vidapi)

### Quality Gates
- [ ] All files ASCII-encoded
- [ ] Unix LF line endings
- [ ] Code follows project conventions

---

## 8. Implementation Notes

### Key Considerations
- The existing monolithic Dockerfile already has the multi-stage pattern for Node/Editly; Dockerfile.worker inherits this approach
- The API service does NOT need Node, Editly, FFmpeg, or fonts -- it only validates and enqueues
- SQLite database must be shared between API and worker via bind mount; both services write to the same file
- ARQ worker health check writes a key to Redis every `health_check_interval` seconds; a script can verify recency

### Potential Challenges
- **SQLite concurrent access from two containers**: SQLite supports multiple readers and one writer with WAL mode. aiosqlite handles this, but under high concurrency this is a known limitation. Acceptable for development; PostgreSQL replaces this in Phase 03.
- **Font availability in worker image**: Must verify Inter, Roboto, and Noto Sans are properly installed and discoverable by Pillow's font search paths
- **Editly binary path**: The symlink from node_modules must be on PATH in the worker container
- **Volume permissions**: The data directory must be writable by the non-root vidapi user in both containers

### Relevant Considerations
- [P00] **Synchronous render in POST handler**: This session sets render_mode=async in the Docker environment, eliminating this tech debt for containerized deployments
- [P00] **No render workspace cleanup**: Workspace cleanup is enabled by default in settings; Docker ephemeral storage provides additional safety net
- [P00] **FFmpeg subprocess resource limits**: Worker container provides basic isolation; explicit limits deferred to Phase 03
- [P00] **Redis for ARQ job queue**: This session makes Redis available as a compose service, resolving the dependency

### Behavioral Quality Focus
Checklist active: Yes
Top behavioral risks for this session:
- Health check scripts must handle Redis connection failures gracefully (timeout, retry/backoff)
- Smoke test must handle slow container startup (explicit loading, retry with backoff on health poll)
- Worker container must clean up render workspaces on exit (cleanup on scope exit)

---

## 9. Testing Strategy

### Unit Tests
- No new Python unit tests expected (Docker infrastructure session)

### Integration Tests
- Smoke test script verifies full pipeline: health -> submit -> poll -> success

### Manual Testing
- `docker compose up --build` and observe service logs
- Submit a test render via curl and poll until succeeded
- Verify health endpoints report all services healthy
- Confirm containers run as non-root via `docker exec`

### Edge Cases
- Worker starts before Redis is ready (depends_on with health check condition)
- API starts before worker is ready (acceptable -- job sits in queue)
- Redis restarts mid-render (worker should reconnect or fail gracefully)
- Missing test assets in container (smoke test uses minimal inline composition)

---

## 10. Dependencies

### External Libraries
- Docker Engine: 24+
- Docker Compose: v2
- redis:7-alpine image
- python:3.11-slim image
- node:20-slim image

### Other Sessions
- **Depends on**: phase01-session01 through phase01-session04
- **Depended by**: Phase 02 sessions (Templates and Polish)

---

## Next Steps

Run the implement workflow step to begin AI-led implementation.
