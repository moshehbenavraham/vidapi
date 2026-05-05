# Task Checklist

**Session ID**: `phase01-session05-docker-compose-stack`
**Total Tasks**: 20
**Estimated Duration**: 2-3 hours
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

- [x] T001 [S0105] Verify prerequisites met: Docker Engine 24+, Docker Compose v2, ports 8000/6379 available
- [x] T002 [S0105] Review existing Dockerfile and docker-compose.yml to identify reusable patterns and required changes
- [x] T003 [S0105] Create `scripts/` directory at project root for Docker helper scripts

---

## Foundation (5 tasks)

Core Dockerfiles and compose configuration.

- [x] T004 [S0105] [P] Create `Dockerfile.api` for the API service -- slim python:3.11-slim image with FastAPI, Uvicorn, curl for health checks, non-root vidapi user, HEALTHCHECK on /health (`Dockerfile.api`)
- [x] T005 [S0105] [P] Create `Dockerfile.worker` for the worker service -- multi-stage build with node:20-slim for Editly, python:3.11-slim runtime with FFmpeg, fonts (Inter, Noto, DejaVu), curl, non-root vidapi user (`Dockerfile.worker`)
- [x] T006 [S0105] [P] Create `.env.docker` with default environment variables for the compose stack: DATABASE_URL, REDIS_URL, RENDER_MODE=async, LOG_LEVEL, storage paths (`.env.docker`)
- [x] T007 [S0105] Update `.dockerignore` to cover multi-service build context -- ensure scripts/ is NOT excluded, verify references/, tests/, .spec_system/ are excluded (`.dockerignore`)
- [x] T008 [S0105] Create `scripts/worker-healthcheck.sh` -- check ARQ worker liveness by querying the health key in Redis with timeout, retry/backoff, and explicit error mapping (`scripts/worker-healthcheck.sh`)

---

## Implementation (8 tasks)

Docker Compose configuration and supporting scripts.

- [x] T009 [S0105] Write `docker-compose.yml` with three services (api, worker, redis) on a shared bridge network `vidapi-net` with explicit loading, empty, error states for service startup (`docker-compose.yml`)
- [x] T010 [S0105] Configure API service in compose: build from Dockerfile.api, port 8000:8000, env_file .env.docker, volume ./data:/app/data, depends_on redis healthy (`docker-compose.yml`)
- [x] T011 [S0105] Configure worker service in compose: build from Dockerfile.worker, env_file .env.docker, volume ./data:/app/data, depends_on redis healthy, CMD arq (`docker-compose.yml`)
- [x] T012 [S0105] Configure Redis service in compose: redis:7-alpine, port 6379:6379, health check via redis-cli ping, named volume for persistence (`docker-compose.yml`)
- [x] T013 [S0105] Remove or archive the original monolithic `Dockerfile` -- rename to `Dockerfile.legacy` to preserve history without confusion (`Dockerfile`)
- [x] T014 [S0105] Create `scripts/smoke-test.sh` -- end-to-end verification script: wait for API health, submit a minimal render (color asset), poll until terminal state, report pass/fail with explicit loading, error, and timeout states (`scripts/smoke-test.sh`)
- [x] T015 [S0105] Update `README.md` with Docker Compose quick start section: prerequisites, `docker compose up --build`, health check URL, smoke test instructions, environment customization (`README.md`)
- [x] T016 [S0105] Verify data directory permissions: ensure ./data is created with correct ownership for non-root vidapi user in both containers, add init script or compose volume config as needed

---

## Testing (4 tasks)

Verification and quality assurance.

- [x] T017 [S0105] Build Docker images and verify both `Dockerfile.api` and `Dockerfile.worker` build successfully without errors
- [x] T018 [S0105] Run `docker compose up` and verify all three services start with health checks passing -- API returns healthy JSON at /v1/health with Redis status healthy
- [x] T019 [S0105] Execute smoke test: submit render via curl POST /v1/renders, poll GET /v1/renders/{id} until succeeded, verify status transitions and output path populated
- [x] T020 [S0105] Validate ASCII encoding and Unix LF line endings on all new and modified files

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
