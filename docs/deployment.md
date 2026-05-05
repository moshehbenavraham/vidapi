# Deployment

## Local Dev (Sync Mode)

```bash
uvicorn app.main:app --reload    # Start server (RENDER_MODE=sync, no Redis needed)
curl localhost:8000/v1/health    # Verify
# Ctrl+C to stop
```

## Docker Compose (Async Mode)

```bash
docker compose up --build        # Build and start API + worker + Redis
curl localhost:8000/v1/health    # Verify (should show redis: ok)
bash scripts/smoke-test.sh       # End-to-end render test
docker compose down              # Stop
```

Three services run on a shared bridge network:

| Service | Image | Purpose |
|---------|-------|---------|
| `api` | `Dockerfile.api` | FastAPI + Uvicorn (Python-only, slim) |
| `worker` | `Dockerfile.worker` | ARQ consumer + Node.js + Editly + FFmpeg + Xvfb |
| `redis` | `redis:7-alpine` | ARQ job queue broker |

### Image Details

- **Dockerfile.api**: Slim Python image with curl for health checks, non-root `vidapi` user
- **Dockerfile.worker**: Multi-stage build (node:20-slim for Editly, python:3.11-slim runtime), includes GL libraries and Xvfb for headless rendering, non-root `vidapi` user

Environment defaults live in `.env.docker`.

## Local Dev (Async Mode, No Docker)

```bash
redis-server &                                   # Start Redis
RENDER_MODE=async uvicorn app.main:app --reload  # Start API in async mode
arq app.workers.arq_settings.WorkerSettings      # Start worker (separate terminal)
```

## Database Migrations

Production metadata uses PostgreSQL and Alembic-managed schemas. Application
startup must not create tables in production.

Required production settings:

```bash
ENVIRONMENT=production
DATABASE_AUTO_CREATE=false
DATABASE_URL=postgresql+asyncpg://vidapi:secret@db.example.com:5432/vidapi
```

Apply migrations before starting new API or worker processes:

```bash
alembic upgrade head
uvicorn app.main:app
```

Rollback on a disposable or explicitly approved database:

```bash
alembic downgrade -1
alembic upgrade head
```

For a disposable PostgreSQL database, run the optional smoke check:

```bash
DATABASE_URL=postgresql+asyncpg://vidapi:secret@localhost:5432/vidapi_test \
POSTGRES_MIGRATION_SMOKE_DISPOSABLE=true \
bash scripts/postgres-migration-smoke.sh
```

If `DATABASE_AUTO_CREATE=false`, startup verifies database connectivity and the
Alembic head revision. If migrations are missing or stale, startup fails with an
actionable error instead of mutating the schema.

## CI/CD Pipeline

```
Push --> Lint/Format/Type Check --> Test --> Build Docker Image
```

GitHub Actions workflows at `.github/workflows/`.

## Render Artifact Storage

Each render produces artifacts in a deterministic directory:

```
data/renders/<render_id>/
  input.json              # Original composition
  expanded.json           # After merge variable substitution
  compiled.editly.json    # Compiled Editly spec
  replay.json             # Subprocess command and environment for replay
  output.mp4              # Rendered video
  poster.jpg              # Poster frame
  logs.txt                # Structured render log (stage entries)
```

## Health Check

- **Endpoint**: `GET /v1/health`
- **Response**: `{"status": "ok", "service": "VidAPI", "redis": {"status": "ok"}}`
- **Redis check**: Skipped in sync mode, PING with 2s timeout in async mode
- **API probe**: Every 30s, 5s timeout, 3 retries
- **Worker probe**: Redis key-based health check via `scripts/worker-healthcheck.sh`

## Rollback

Docker rollback:

```bash
docker compose down
docker compose up -d --no-build   # Restart previous image
```

**When to rollback**: Health check fails post-deploy, error rate spikes, or
renderer subprocess failures increase.

## Production Deployment (Planned)

Phase 03 will add:
- S3-compatible storage for artifacts
- API key authentication
- Operational visibility and production stack wiring
