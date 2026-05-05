# VidAPI

Self-hosted Python FastAPI service for programmatic video rendering.
Accepts JSON timeline compositions and renders video via Editly + FFmpeg.
Also supports reusable templates, webhook callbacks, and deterministic render artifacts.
A self-hosted, open-source alternative to Creatomate and JSON2Video.

## Quick Start (Docker Compose)

The fastest way to run VidAPI with the full async render pipeline:

```bash
# Prerequisites: Docker Engine 24+ and Docker Compose v2

# Start API, worker, and Redis
docker compose up --build

# Verify health (in another terminal)
curl http://localhost:8000/v1/health

# Run the end-to-end smoke test
bash scripts/smoke-test.sh
```

This starts three services:
- **api** (port 8000) -- FastAPI server accepting render requests
- **worker** -- ARQ consumer with Editly/FFmpeg for rendering
- **redis** (port 6379) -- Job queue broker

For a production-like local stack with API, worker, Redis AUTH, PostgreSQL, and
MinIO:

```bash
cp .env.production.example .env.production
# Replace change-me values and API_KEY_HASHES before use.
docker compose --env-file .env.production -f docker-compose.prod.yml up --build
```

### Environment Customization

Default environment values live in `.env.docker`. Override any variable:

```bash
# Example: enable debug logging
echo "LOG_LEVEL=DEBUG" >> .env.docker
docker compose up --build
```

### Stopping and Cleaning Up

```bash
docker compose down           # Stop services
docker compose down -v        # Stop and remove volumes
```

## Quick Start (Local Development)

```bash
# Prerequisites: Python 3.11+, Node.js 20+, FFmpeg 6+, Redis
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
uvicorn app.main:app --reload

# Verify
curl http://localhost:8000/v1/health
```

Local development starts with API key auth disabled. To exercise protected API
behavior locally, generate a SHA-256 hash for a raw key and enable auth:

```bash
export VIDAPI_API_KEY="replace-with-a-local-secret"
export API_KEY_AUTH_ENABLED=true
export API_KEY_HASHES="$(python -c 'import hashlib, os; print(hashlib.sha256(os.environ["VIDAPI_API_KEY"].encode()).hexdigest())')"
uvicorn app.main:app --reload

curl -H "X-API-Key: $VIDAPI_API_KEY" http://localhost:8000/v1/renders
```

## Prerequisites

- Python 3.11+
- Node.js 20+ (for Editly renderer)
- FFmpeg 6+ and ffprobe
- Bundled fonts: Inter, Noto Sans, DejaVu
- Docker Engine 24+ and Docker Compose v2 (for containerized stack)

## Repository Structure

```
.
|-- app/
|   |-- api/               # Route handlers, dependencies, error handling
|   |-- core/              # Config (pydantic-settings), logging, security
|   |-- db/                # SQLModel tables, CRUD, async sessions
|   |-- models/            # Pydantic composition, template, and render schemas
|   |-- renderers/         # Renderer protocol, capability registry, Editly bridge, poster gen
|   |-- services/          # Render pipeline, asset, template, and webhook services
|   |-- storage/           # Storage protocol and local filesystem adapter
|   \-- workers/           # Background job workers (Phase 01)
|-- alembic/               # Database migrations
|-- tests/                 # Full schema, security, compiler, API, worker, and integration coverage
|-- docs/                  # Architecture, development, deployment guides
|-- Dockerfile.api          # Slim API image (Python + FastAPI)
|-- Dockerfile.worker       # Full worker image (Python + Node + FFmpeg)
|-- docker-compose.yml      # Multi-service compose stack (API + Worker + Redis)
|-- scripts/                # Docker helper scripts (health check, smoke test)
\-- pyproject.toml         # Dependencies and tool config
```

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/v1/health` | Health check (includes Redis status in async mode) |
| `POST` | `/v1/renders` | Create a render job (returns 202 in async mode) |
| `GET` | `/v1/renders` | List recent renders with pagination |
| `GET` | `/v1/renders/{id}` | Get render status, progress, and output URLs |
| `DELETE` | `/v1/renders/{id}` | Cancel a queued or running render |
| `GET` | `/v1/renders/{id}/download` | Download rendered output |
| `GET` | `/v1/renders/{id}/poster` | Download or redirect to a render poster |
| `GET` | `/v1/renders/{id}/artifacts/manifest.json` | Download PNG sequence manifest metadata |

### Operational Endpoints

Operational endpoints are mounted under `/v1/ops` and require `X-API-Key` when
API key auth is enabled.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/v1/ops/renders` | Recent renders with pagination and optional status filter |
| `GET` | `/v1/ops/renders/failures` | Recent failed renders with redacted error excerpts |
| `GET` | `/v1/ops/renders/status-counts` | Current render counts by status |
| `GET` | `/v1/ops/renders/renderer-failures` | Failed render counts by renderer and error code |
| `GET` | `/v1/ops/webhooks` | Recent webhook attempts with optional render filter |
| `GET` | `/v1/ops/webhooks/outcome-counts` | Webhook outcomes by event |
| `GET` | `/v1/ops/metrics` | Prometheus-style metrics text |

### Template Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/templates` | Create a reusable template |
| `GET` | `/v1/templates` | List templates |
| `GET` | `/v1/templates/{id}` | Retrieve template metadata and active version |
| `PUT` | `/v1/templates/{id}` | Update a template by creating a new version |
| `DELETE` | `/v1/templates/{id}` | Soft-delete or archive a template |
| `POST` | `/v1/templates/{id}/renders` | Render a template with merge variables |

Interactive API docs at `http://localhost:8000/docs` (Swagger) or `/redoc`.

### Renderer Selection

Render requests may omit `renderer`, set it to `auto`, or explicitly request
`editly`; all three currently select the Editly renderer. Future renderer names
such as `ffmpeg-native` and `hyperframes` are reserved but unavailable until
their adapters are implemented.

VidAPI validates renderer capabilities before direct render jobs are persisted,
queued, or compiled. Unsupported renderers return `UNSUPPORTED_RENDERER`.
Unsupported renderer-feature combinations return `UNSUPPORTED_RENDERER_FEATURE`
with bounded context. See
[Renderer Capabilities](docs/renderer-capabilities.md) for the support matrix
and extension contract.

### Output Formats And Presets

`output.format` supports `mp4`, `webm`, `gif`, and `png-sequence`. Editly
produces a deterministic MP4 intermediate; WebM, GIF, and PNG sequence outputs
are finished with FFmpeg before storage. PNG sequence downloads are zip archives
and expose `manifest.json` through the render artifact endpoint.

`output.preset` supports `tiktok`, `reels`, `shorts`, `youtube`, `square-ad`,
and `preview-low`. Explicit `output.width` and `output.height` override preset
dimensions, while omitted FPS and quality values use preset defaults.

### API Authentication

`GET /health` and `GET /v1/health` are always public. When
`API_KEY_AUTH_ENABLED=true`, all render and template endpoints require an
`X-API-Key` header. Configure accepted keys as SHA-256 hex digests through
`API_KEY_HASHES`; multiple hashes can be comma-separated.

Production startup requires API key auth to be enabled and at least one hash to
be configured. Raw API keys are never configured in VidAPI settings.

### Resource Limits

VidAPI rejects over-limit work before it is persisted or queued. The main local
settings are:

```bash
MAX_RENDER_REQUEST_BODY_BYTES=2097152
MAX_TEMPLATE_REQUEST_BODY_BYTES=2097152
MAX_RENDER_DURATION_SECONDS=120
MAX_OUTPUT_WIDTH=1920
MAX_OUTPUT_HEIGHT=1920
MAX_FPS=60
MAX_GIF_DURATION_SECONDS=15
MAX_GIF_FPS=30
MAX_PNG_SEQUENCE_DURATION_SECONDS=10
MAX_PNG_SEQUENCE_FPS=30
MAX_PNG_SEQUENCE_FRAMES=300
MAX_TRACKS_PER_RENDER=50
MAX_CLIPS_PER_RENDER=50
MAX_ASSETS_PER_RENDER=100
MAX_ASYNC_QUEUE_DEPTH=1000
```

Oversized HTTP bodies return 413 with `REQUEST_BODY_TOO_LARGE`. Over-limit
compositions or media metadata return 422 with `COMPOSITION_LIMIT_EXCEEDED` or
`MEDIA_LIMIT_EXCEEDED`. Saturated async queues return 429 with `QUEUE_SATURATED`
and a `Retry-After` header.

## Documentation

- [Getting Started](docs/onboarding.md)
- [Development Guide](docs/development.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Renderer Capabilities](docs/renderer-capabilities.md)
- [Output Formats](docs/output-formats.md)
- [Deployment](docs/deployment.md)
- [Environments](docs/environments.md)
- [Operations](docs/operations.md)
- [Contributing](CONTRIBUTING.md)

## Tech Stack

- **FastAPI** - Async web framework with auto OpenAPI docs
- **Pydantic v2** - Discriminated unions for composition schema validation
- **ARQ + Redis** - Async job queue for render workers
- **SQLModel + aiosqlite/asyncpg** - Async database (SQLite dev, PostgreSQL prod)
- **Alembic** - Database migrations
- **Editly** - Default video renderer (Node.js subprocess)
- **FFmpeg** - Video encoding, poster extraction, audio mixing, media probing
- **Pillow** - Text-to-image rendering with bundled fonts
- **Jinja2** - Sandboxed template expansion for reusable compositions
- **httpx** - Async asset downloads with SSRF protection
- **structlog** - Structured JSON logging
- **S3-compatible storage** - Production artifact backend with MinIO validation

## Project Status

Phases 00, 01, 02, and 03 are complete; Phase 04 is not started. See
[PRD](.spec_system/PRD/PRD.md) for current progress and roadmap.

| Phase | Name | Status |
|-------|------|--------|
| 00 | Foundation | Complete (5/5 sessions) |
| 01 | Async Jobs and Multi-track | Complete (5/5 sessions) |
| 02 | Templates and Polish | Complete (5/5 sessions) |
| 03 | Production Hardening | Complete (5/5 sessions) |
| 04 | Advanced Rendering | Not Started |

## License

[MIT](LICENSE)
