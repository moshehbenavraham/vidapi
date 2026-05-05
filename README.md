# VidAPI

Self-hosted Python FastAPI service for programmatic video rendering.
Accepts JSON timeline compositions and renders video via Editly, native FFmpeg,
or HyperFrames for HTML-backed compositions.
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
- **worker** -- ARQ consumer with Editly, HyperFrames, and FFmpeg for rendering
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
# Prerequisites: Python 3.11+, Node.js 22+, FFmpeg 6+, Redis
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
- Node.js 22+ (for Editly and HyperFrames renderers)
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
|   |-- renderers/         # Renderer protocol, capabilities, Editly, HyperFrames, FFmpeg
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
| `GET` | `/v1/renders/{id}/captions` | Download or redirect to a caption sidecar |
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

Render requests may omit `renderer`, set it to `auto`, explicitly request
`editly`, explicitly request `ffmpeg-native`, or explicitly request
`hyperframes`. Omitted, `null`, and `auto` select HyperFrames when any clip uses
`asset.type: "html"`; otherwise they select Editly. `ffmpeg-native` selects the
constrained native FFmpeg adapter for simple high-throughput timelines.
`hyperframes` compiles VidAPI HTML assets into a workspace-local HyperFrames
project and produces an MP4 intermediate for shared finishing.

VidAPI validates renderer capabilities before direct render jobs are persisted,
queued, or compiled. Unsupported renderers return `UNSUPPORTED_RENDERER`.
Unsupported renderer-feature combinations return `UNSUPPORTED_RENDERER_FEATURE`
with bounded context. See
[Renderer Capabilities](docs/renderer-capabilities.md) for the support matrix
and extension contract. See
[Native FFmpeg Renderer](docs/native-ffmpeg-renderer.md) for the native subset,
replay artifacts, and rejection behavior. See
[HyperFrames Renderer](docs/hyperframes-renderer.md) for HTML asset boundaries,
runtime dependencies, and replay artifacts.

### Transitions

Clip transitions are declared in VidAPI's renderer-neutral composition schema.
Supported values include `fade_in`, `fade_out`, `crossfade`,
`directional_left`, `directional_right`, `directional_up`, `directional_down`,
`wipe_left`, `wipe_right`, `wipe_up`, `wipe_down`, `cross_zoom`,
`simple_zoom`, `circle_open`, and `linear_blur`.

`between` transitions are declared on the outgoing clip and require an exact
same-track successor. Gaps, overlaps, overlong durations, audio-only clips, and
multiple transitions at one rendered boundary are rejected before the job is
queued or compiled.

```json
{
  "timeline": {
    "tracks": [
      {
        "clips": [
          {
            "asset": {"type": "video", "src": "intro.mp4"},
            "start": 0,
            "length": 2,
            "transition": {"name": "wipe_left", "duration": 0.4}
          },
          {
            "asset": {"type": "video", "src": "main.mp4"},
            "start": 2,
            "length": 3
          }
        ]
      }
    ]
  }
}
```

See [Transitions](docs/transitions.md) for aliases, placement rules, timing
constraints, and renderer support notes.

### Output Formats And Presets

`output.format` supports `mp4`, `webm`, `gif`, and `png-sequence`. Editly,
HyperFrames, and the native FFmpeg renderer all produce MP4 intermediates; WebM,
GIF, and PNG sequence outputs are finished with FFmpeg before storage. PNG
sequence downloads are zip archives and expose `manifest.json` through the
render artifact endpoint.

`output.preset` supports `tiktok`, `reels`, `shorts`, `youtube`, `square-ad`,
and `preview-low`. Explicit `output.width` and `output.height` override preset
dimensions, while omitted FPS and quality values use preset defaults.

### Captions And Posters

Render requests may include a top-level `captions` block with timed cues.
Supported modes are `sidecar` for SRT or WebVTT files and `burn-in` for
FFmpeg-backed caption burn-in before output conversion.

Poster generation is configured under `output.poster`. Omitting the block keeps
the service default poster behavior. Supported modes are `default`,
`timestamp`, `percent`, and `disabled`.

```json
{
  "captions": {
    "mode": "sidecar",
    "format": "srt",
    "cues": [{"start": 0, "duration": 1.5, "text": "Hello"}]
  },
  "output": {
    "format": "mp4",
    "poster": {"mode": "timestamp", "timestamp": 0.5}
  }
}
```

Succeeded status responses and webhook payloads can include structured
`captions` and `poster_metadata` fields. See
[Captions and Posters](docs/captions-and-posters.md) for details.

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
- [HyperFrames Renderer](docs/hyperframes-renderer.md)
- [Transitions](docs/transitions.md)
- [Output Formats](docs/output-formats.md)
- [Captions and Posters](docs/captions-and-posters.md)
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
- **HyperFrames** - HTML/CSS/GSAP renderer adapter (Node.js subprocess)
- **FFmpeg** - Video encoding, poster extraction, audio mixing, media probing
- **Pillow** - Text-to-image rendering with bundled fonts
- **Jinja2** - Sandboxed template expansion for reusable compositions
- **httpx** - Async asset downloads with SSRF protection
- **structlog** - Structured JSON logging
- **S3-compatible storage** - Production artifact backend with MinIO validation

## Project Status

Phases 00, 01, 02, and 03 are complete; Phase 04 is in progress. See
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
