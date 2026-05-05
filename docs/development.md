# Development Guide

## Required Tools

- Python 3.11+ (tested with 3.12.3)
- Node.js 22+ (tested with v24.14.0)
- FFmpeg 6+ and ffprobe (tested with 6.1.1)
- uv (recommended package manager)

## Port Mappings

| Service | Port | URL |
|---------|------|-----|
| FastAPI API | 8000 | http://localhost:8000 |
| OpenAPI docs | 8000 | http://localhost:8000/docs |
| ReDoc | 8000 | http://localhost:8000/redoc |
| Redis | 6379 | redis://localhost:6379 |

## Dev Scripts

| Command | Purpose |
|---------|---------|
| `uvicorn app.main:app --reload` | Start dev server with auto-reload |
| `arq app.workers.arq_settings.WorkerSettings` | Start ARQ render worker |
| `ruff check .` | Run linter |
| `ruff format .` | Format code |
| `ruff check --fix .` | Auto-fix lint issues |
| `mypy app/` | Type check application code |
| `pytest` | Run full test suite |
| `pytest -x` | Stop on first failure |
| `pytest -k test_name` | Run specific test |
| `alembic upgrade head` | Apply database migrations |
| `alembic downgrade base` | Reset database |
| `docker compose up --build` | Start full async stack (API + worker + Redis) |
| `bash scripts/smoke-test.sh` | Run end-to-end Docker smoke test |

## Database

VidAPI reads database configuration from `DATABASE_URL`.

SQLite remains the default for local development and tests:

```bash
DATABASE_URL=sqlite+aiosqlite:///./data/vidapi.db
alembic upgrade head
uvicorn app.main:app --reload
```

PostgreSQL is supported through the asyncpg driver:

```bash
DATABASE_URL=postgresql+asyncpg://vidapi:vidapi@localhost:5432/vidapi
alembic upgrade head
DATABASE_AUTO_CREATE=false ENVIRONMENT=production uvicorn app.main:app
```

Legacy `postgres://` and plain `postgresql://` URLs are normalized to
`postgresql+asyncpg://` by application settings.

Reset a disposable local database with:

```bash
alembic downgrade base && alembic upgrade head
```

## Render Artifact Storage

Local artifact storage is the default and needs no external service:

```bash
STORAGE_BACKEND=local
STORAGE_URL_MODE=proxy
uvicorn app.main:app --reload
```

Renderers still use `RENDER_WORKSPACE_ROOT` as local scratch space. Durable
local artifacts are published under `STORAGE_ROOT/artifacts`, so async worker
cleanup does not remove completed downloads.

Optional MinIO smoke setup:

```bash
docker run --rm \
  -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=vidapi \
  -e MINIO_ROOT_PASSWORD=vidapi-secret \
  quay.io/minio/minio server /data --console-address ":9001"
```

Create a `vidapi-renders` bucket in the MinIO console, then run API and worker
processes with matching settings:

```bash
STORAGE_BACKEND=s3
STORAGE_URL_MODE=proxy
S3_BUCKET=vidapi-renders
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY_ID=vidapi
S3_SECRET_ACCESS_KEY=vidapi-secret
S3_FORCE_PATH_STYLE=true
```

Tests use mocks for S3 behavior by default; MinIO is only for manual smoke
checks.

## Testing

```bash
pytest                    # Run the full test suite
pytest -v                 # Verbose output
pytest --tb=short         # Short tracebacks
pytest tests/test_segment_compiler.py  # Run specific test file
```

Tests use in-memory SQLite and mock renderers. No external services (Redis, etc.) needed.

## Quality Gates

Run all quality gates before committing:

```bash
ruff check . && ruff format --check . && mypy app/ && pytest
```

## Pre-commit Hooks

Pre-commit is configured in `.pre-commit-config.yaml`. Install hooks:

```bash
pre-commit install
```

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/vidapi.db` | Database connection string |
| `DATABASE_AUTO_CREATE` | `true` | Allow local/test startup to create missing tables |
| `DATABASE_CONNECT_TIMEOUT_SECONDS` | `10` | Per-attempt database connection timeout |
| `DATABASE_CONNECT_RETRIES` | `3` | Startup database retry attempts |
| `DATABASE_CONNECT_RETRY_BACKOFF_SECONDS` | `0.5` | Initial startup database retry backoff |
| `ENVIRONMENT` | `development` | `development`, `test`, or `production` startup guard |
| `STORAGE_ROOT` | `./data` | Root directory for render artifacts |
| `RENDER_WORKSPACE_ROOT` | `data/renders` | Local scratch workspace root for render jobs |
| `STORAGE_BACKEND` | `local` | Artifact backend: `local` or `s3` |
| `STORAGE_URL_MODE` | `proxy` | Artifact URL mode: `proxy`, `signed`, or `public` |
| `STORAGE_SIGNED_URL_EXPIRY_SECONDS` | `900` | Signed S3 URL lifetime |
| `S3_BUCKET` | `unset` | S3-compatible artifact bucket |
| `S3_ENDPOINT_URL` | `unset` | Optional S3-compatible endpoint, such as MinIO or R2 |
| `S3_REGION` | `us-east-1` | S3 region |
| `S3_ACCESS_KEY_ID` | `unset` | S3 access key |
| `S3_SECRET_ACCESS_KEY` | `unset` | S3 secret key |
| `S3_OBJECT_PREFIX` | `renders` | Prefix for render-scoped object keys |
| `S3_FORCE_PATH_STYLE` | `true` | Use path-style S3 addressing for compatible endpoints |
| `S3_PUBLIC_BASE_URL` | `unset` | Public object base URL required for S3 public mode |
| `S3_CONNECT_TIMEOUT_SECONDS` | `5` | S3 connection timeout |
| `S3_READ_TIMEOUT_SECONDS` | `60` | S3 read timeout |
| `S3_MAX_ATTEMPTS` | `3` | S3 retry attempts |
| `DEBUG` | `false` | Enable debug logging |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `RENDER_MODE` | `sync` | `sync` (no Redis) or `async` (Redis + ARQ worker) |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection for ARQ queue |
| `EDITLY_BIN` | `editly` | Path to Editly binary |
| `EDITLY_TIMEOUT_SECONDS` | `600` | Editly subprocess timeout |
| `EDITLY_FAST_MODE` | `false` | Disable some Editly safety checks for faster local runs |
| `FFMPEG_BIN` | `ffmpeg` | Path to FFmpeg binary |
| `AUDIO_MIX_TIMEOUT_SECONDS` | `120` | FFmpeg audio mixing timeout |
| `AUDIO_NORMALIZATION_ENABLED` | `false` | Enable optional final audio normalization |
| `AUDIO_FADE_DURATION_SECONDS` | `1.0` | Default fade window for soundtrack effects |
| `PROGRESS_UPDATE_INTERVAL_SECONDS` | `2.0` | Minimum interval between progress DB writes |
| `ASSET_DOWNLOAD_TIMEOUT_SECONDS` | `60` | Remote asset download timeout |
| `ASSET_ALLOW_HTTP` | `false` | Allow HTTP (non-HTTPS) asset URLs |
| `WORKSPACE_CLEANUP_ENABLED` | `true` | Clean up job workspaces after render |
| `WORKSPACE_CLEANUP_KEEP_ON_FAILURE` | `true` | Preserve workspace on failed renders for debugging |
| `WEBHOOK_SECRET` | `unset` | HMAC secret for signed webhook payloads |
| `WEBHOOK_TIMEOUT_SECONDS` | `10` | Webhook delivery timeout |
| `WEBHOOK_MAX_RETRIES` | `3` | Maximum webhook delivery attempts |
| `WEBHOOK_RETRY_DELAYS` | `[1, 10, 60]` | Retry schedule in seconds |
| `RATE_LIMIT_DEFAULT` | `60/minute` | Default request rate limit |
| `RATE_LIMIT_RENDER_CREATE` | `10/minute` | Render-create rate limit |
| `RATE_LIMIT_STORAGE_URI` | `memory://` | Backing store for rate-limit buckets |
| `CORS_ORIGINS` | localhost list | Allowed browser origins |
| `ALLOWED_HOSTS` | localhost list | Trusted host allowlist |
