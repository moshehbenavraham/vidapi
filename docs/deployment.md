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
- **Dockerfile.worker**: Multi-stage build (node:22-slim for Editly and HyperFrames, python:3.11-slim runtime), includes GL libraries and Xvfb for headless rendering, non-root `vidapi` user

Environment defaults live in `.env.docker`.

## Production-Like Compose Stack

Use the production-like overlay to validate the adapters used by a self-hosted
deployment: API, worker, Redis AUTH, PostgreSQL, and MinIO.

```bash
cp .env.production.example .env.production
# Replace every change-me value and API_KEY_HASHES.
docker compose --env-file .env.production -f docker-compose.prod.yml up --build
```

Verify startup:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml ps
curl http://localhost:8000/v1/health
curl -H "X-API-Key: $VIDAPI_API_KEY" http://localhost:8000/v1/ops/metrics
curl -H "X-API-Key: $VIDAPI_API_KEY" http://localhost:8000/v1/ops/renders
```

The overlay uses named volumes for API scratch data, worker scratch data,
PostgreSQL, Redis, and MinIO. To reset a validation environment:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml down -v
```

The overlay is production-like for local validation and one-node self-hosting.
It does not replace external TLS termination, secret management, backups,
monitoring, or high-availability planning.

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

For the production-like compose stack, run Alembic against the compose database
before starting the app when the database is empty or after schema changes:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api \
  alembic upgrade head
```

## API Key Authentication

Health endpoints remain public for load balancers and probes:

- `GET /health`
- `GET /v1/health`

All render and template endpoints require `X-API-Key` when authentication is
enabled:

```bash
export VIDAPI_API_KEY="replace-with-a-production-secret"
export API_KEY_AUTH_ENABLED=true
export API_KEY_HASHES="$(python -c 'import hashlib, os; print(hashlib.sha256(os.environ["VIDAPI_API_KEY"].encode()).hexdigest())')"

curl -H "X-API-Key: $VIDAPI_API_KEY" https://api.example.com/v1/renders
```

Production startup enforces:

```bash
ENVIRONMENT=production
API_KEY_AUTH_ENABLED=true
API_KEY_HASHES=<sha256-hex-digest>[,<sha256-hex-digest>]
```

Do not store raw API keys in `.env`, Docker Compose files, deployment manifests,
or logs. Store only SHA-256 hashes in VidAPI settings and keep the raw keys in a
secret manager for clients that need to call the API.

## Production Resource Limits

Set resource limits explicitly for production. The defaults are conservative for
one-node deployments, but operators should tune them to available CPU, memory,
disk, and queue capacity:

```bash
MAX_RENDER_REQUEST_BODY_BYTES=2097152
MAX_TEMPLATE_REQUEST_BODY_BYTES=2097152
MAX_RENDER_DURATION_SECONDS=120
MAX_OUTPUT_WIDTH=1920
MAX_OUTPUT_HEIGHT=1920
MAX_FPS=60
MAX_TRACKS_PER_RENDER=50
MAX_CLIPS_PER_RENDER=50
MAX_ASSETS_PER_RENDER=100
MAX_ASSET_SIZE_MB=500
MAX_MEDIA_DURATION_SECONDS=600
MAX_MEDIA_WIDTH=3840
MAX_MEDIA_HEIGHT=3840
MAX_MEDIA_STREAMS_PER_ASSET=8
MAX_ASYNC_QUEUE_DEPTH=1000
QUEUE_ADMISSION_TIMEOUT_SECONDS=1
QUEUE_RETRY_AFTER_SECONDS=10
WORKSPACE_ORPHAN_TTL_SECONDS=86400
WORKSPACE_DISK_BUDGET_BYTES=
SUBPROCESS_KILL_GRACE_SECONDS=5
MAX_SUBPROCESS_STDERR_BYTES=1048576
```

Expected rejection behavior:

| Condition | Response |
|-----------|----------|
| Request body exceeds configured size | 413 `REQUEST_BODY_TOO_LARGE` |
| Composition duration, dimensions, fps, tracks, clips, or assets exceed limits | 422 `COMPOSITION_LIMIT_EXCEEDED` |
| Probed media duration, dimensions, or stream count exceed limits | render fails with `MEDIA_LIMIT_EXCEEDED` |
| Async queue depth is at capacity | 429 `QUEUE_SATURATED` with `Retry-After` |
| Queue capacity cannot be checked | 503 queue unavailable |

Limit checks run before render records are created where possible. Worker-side
media checks run after SSRF, redirect, MIME, byte-size, and ffprobe validation.
Worker startup also removes stale inactive workspaces older than
`WORKSPACE_ORPHAN_TTL_SECONDS` while preserving active render IDs.

## Redis Security

Production async deployments must use Redis authentication and TLS by default:

```bash
ENVIRONMENT=production
RENDER_MODE=async
REDIS_URL=rediss://:strong-redis-password@redis.example.com:6379/0
REDIS_REQUIRE_AUTH_IN_PRODUCTION=true
REDIS_REQUIRE_TLS_IN_PRODUCTION=true
```

Startup fails closed if production async mode uses `redis://` or omits Redis
credentials. Only disable `REDIS_REQUIRE_AUTH_IN_PRODUCTION` or
`REDIS_REQUIRE_TLS_IN_PRODUCTION` for a private, explicitly controlled network
where equivalent transport and access controls are enforced outside VidAPI.

The production-like compose overlay uses Redis AUTH with `redis://` on an
internal bridge network and sets `REDIS_REQUIRE_TLS_IN_PRODUCTION=false`.
For any network outside a single controlled host, use `rediss://` and keep TLS
required.

## CI/CD Pipeline

```
Push --> Lint/Format/Type Check --> Test --> Build Docker Image
```

GitHub Actions workflows at `.github/workflows/`.

## Render Artifact Storage

Renderers always write to a local scratch workspace because Editly and FFmpeg
need filesystem paths. After each stage, VidAPI publishes durable artifacts
through the configured storage backend:

```
<backend>/<render_id>/
  input.json              # Original composition
  expanded.json           # After merge variable substitution
  compiled.editly.json    # Compiled Editly spec
  replay.json             # Subprocess command and environment for replay
  output.mp4              # Rendered video
  poster.jpg              # Poster frame
  logs.txt                # Structured render log (stage entries)
```

Local mode is the default and stores durable files under
`STORAGE_ROOT/artifacts/<render_id>/`. This is suitable for one-host
development and tests.

S3-compatible mode stores durable fields as `s3://bucket/key` URIs. API and
worker processes must use the same settings:

```bash
STORAGE_BACKEND=s3
STORAGE_URL_MODE=proxy
S3_BUCKET=vidapi-renders
S3_REGION=us-east-1
S3_ENDPOINT_URL=https://s3.example.com
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
S3_OBJECT_PREFIX=renders
S3_FORCE_PATH_STYLE=true
```

URL modes:

| Mode | Behavior |
|------|----------|
| `proxy` | API streams local or S3 artifacts through `/download`, `/poster`, `/captions`, and `/artifacts/{name}` |
| `signed` | S3 status/webhook URLs and direct endpoints use presigned redirects |
| `public` | S3 status/webhook URLs and direct endpoints use `S3_PUBLIC_BASE_URL` |

Use `proxy` unless clients should bypass the API for artifact bytes. `public`
mode requires a public object base URL with no embedded credentials.

The production-like compose overlay uses MinIO:

```bash
STORAGE_BACKEND=s3
STORAGE_URL_MODE=proxy
S3_BUCKET=vidapi-renders
S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY_ID=vidapi-minio
S3_SECRET_ACCESS_KEY=change-me-minio
S3_FORCE_PATH_STYLE=true
```

Create the bucket before rendering if your MinIO instance does not auto-create
it through external provisioning.

### Logs in This Environment

- Live API and worker logs are Docker stdout/stderr:
  `sg docker -c "docker compose --env-file .env.production -f docker-compose.prod.yml -f docker-compose.vps.yml logs -f --tail=200 api worker"`.
- Durable per-render logs are stored as `logs.txt`. In this VPS stack, MinIO
  stores them at `s3://vidapi-renders/renders/<render_id>/logs.txt`; fetch them
  through `GET /v1/renders/<render_id>/artifacts/logs.txt` or the `logs` alias.
- Failed render scratch diagnostics are preserved in the worker container at
  `/app/data/renders/<render_id>/logs.txt`. Successful render workspaces are
  cleaned after artifacts are published.
- The repo-level `logs/` directory is not used for runtime logs.

## Operational Visibility

Authenticated operators can inspect the stack through `/v1/ops`:

```bash
curl -H "X-API-Key: $VIDAPI_API_KEY" http://localhost:8000/v1/ops/renders
curl -H "X-API-Key: $VIDAPI_API_KEY" http://localhost:8000/v1/ops/renders/failures
curl -H "X-API-Key: $VIDAPI_API_KEY" http://localhost:8000/v1/ops/webhooks
curl -H "X-API-Key: $VIDAPI_API_KEY" http://localhost:8000/v1/ops/metrics
```

Operational payloads are redacted and bounded. They should be safe for internal
operator use but must still be protected by API key auth and transport security.

## Health Check

- **Endpoint**: `GET /v1/health`
- **Response**: `{"status": "healthy", "service": "VidAPI", "redis": {"status": "healthy"}}`
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

## Production Deployment Notes

Before running outside a local validation host, provide:

- HTTPS/TLS termination for clients and `rediss://` for Redis.
- Secret management for API keys, Redis passwords, PostgreSQL passwords, MinIO
  credentials, and webhook secrets.
- PostgreSQL backup and restore procedures.
- MinIO or S3 bucket lifecycle and backup policy.
- Metrics scraping and alert routing for `/v1/ops/metrics`.
