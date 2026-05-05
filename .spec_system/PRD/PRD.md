# VidAPI - Product Requirements Document

## Overview

VidAPI is a self-hosted Python FastAPI service for programmatic video rendering. Clients submit a JSON composition that describes a video timeline with tracks, clips, media assets, text overlays, audio, transitions, output settings, and optional callbacks. VidAPI validates the request, creates an asynchronous render job, renders the output through a worker, stores all render artifacts, and exposes status, download, template, and webhook APIs.

VidAPI is positioned as a self-hosted, open-source alternative to commercial JSON video APIs such as Creatomate and JSON2Video. The product is API-first: developers and automation pipelines integrate with VidAPI to generate repeatable videos from data, templates, and supplied media assets without using a hosted SaaS vendor.

VidAPI owns its public JSON composition schema. Renderers are internal, pluggable backends behind a stable protocol. The first production path is an Editly renderer bridge invoked from Python as a Node subprocess because Editly already supports declarative timeline editing, clips, layers, transitions, audio, and FFmpeg output. Future renderer paths include a native FFmpeg renderer for constrained high-throughput timelines and a HyperFrames renderer for HTML/CSS/GSAP-rich templates.

The core MVP loop is:

```text
JSON composition -> POST /v1/renders -> queued job -> worker render -> MP4 URL
```

## Goals

1. Provide a self-hosted alternative to Creatomate and JSON2Video for programmatic video rendering.
2. Accept a JSON document describing a multi-track timeline with clips, assets, text, transitions, output settings, merge data, and optional callbacks.
3. Render asynchronously through a queue so API requests never block on long encodes.
4. Support reusable templates with strict variable substitution for batch and dynamic video generation.
5. Store render inputs, expanded compositions, compiled renderer specs, logs, outputs, and posters for replay and debugging.
6. Keep the public API independent from Editly, FFmpeg, HyperFrames, or any future renderer internals.
7. Ship a one-command Docker Compose development stack with API, worker, queue, database, and storage services.
8. Make remote asset fetching safe by enforcing SSRF protection, size limits, MIME validation, redirects checks, and timeouts from the MVP.

## Non-Goals

- Browser-based video editor UI.
- Real-time video streaming or live compositing.
- Cloning every Creatomate, JSON2Video, or Shotstack feature in v1.
- Multi-tenant SaaS billing, subscription plans, or user management.
- AI generation of images, videos, voiceovers, music, or captions.
- Native mobile SDKs or official client libraries in the initial phases.
- Distributed render orchestration beyond multiple workers sharing one queue.
- Broadcast or professional output formats such as ProRes, DNxHD, or lossless masters.
- Direct public exposure of Editly, FFmpeg filter graph, or HyperFrames schemas as VidAPI's common API.

## Users and Use Cases

### Primary Users

- **Backend Developer**: Integrates VidAPI into a product to generate videos from user or business data, such as personalized ads, onboarding videos, product videos, or social media clips.
- **Automation Engineer**: Builds scheduled, CI/CD, or data-pipeline jobs that produce videos from templates and variable data, such as reports, listings, or automated marketing assets.
- **Content Creator or Agency**: Uses templates to produce batches of branded videos with different copy, images, prices, music, and calls to action.
- **Self-Hosted Operator**: Runs VidAPI privately for cost control, data control, compliance, or offline/local rendering workflows.

### Key Use Cases

1. Submit a JSON composition with one background image or video, one text overlay, optional music, and vertical MP4 output; receive a render ID immediately and a completed MP4 after worker processing.
2. Poll a render job to show status and progress in a client application.
3. Download rendered output and poster through the API for private/local storage deployments.
4. Create a reusable product-ad template with placeholder variables and render many variations by supplying different merge data.
5. Queue multiple render jobs and receive signed webhook callbacks when each completes, fails, or is cancelled.
6. Cancel a queued render job and best-effort cancel a running render job.
7. Inspect stored input, expanded JSON, compiled renderer spec, replay metadata, poster, output, and logs when diagnosing a failed render.

## Reference Roles

| Reference | Role In VidAPI |
|-----------|----------------|
| `references/shottower` | API shape, render lifecycle, and Shotstack-style timeline vocabulary: timeline, tracks, clips, assets, outputs, callbacks. |
| `references/editly` | Default MVP render engine. VidAPI compiles its internal schema to Editly JSON and invokes Editly as a subprocess. |
| `references/hyperframes` | Future advanced renderer for HTML-first templates, CSS/GSAP animations, and browser-native layout. |
| `references/video-artist-api` | Reference for a simple Python-adjacent JSON video API and preview/render flow, not the main architecture. |

## Design Principles

1. **JSON-first**: every render is fully described by a JSON document.
2. **Async by default**: render work is queued; clients poll or receive webhooks.
3. **Renderer-independent public API**: clients send VidAPI JSON, not Editly, FFmpeg, or HyperFrames internals.
4. **Replayable renders**: each job stores input JSON, expanded JSON, compiled renderer spec, command/replay metadata, logs, output, and poster.
5. **Strict asset security**: remote media rendering is SSRF-prone, so URL and file access are constrained from the MVP.
6. **Small explicit state machine**: job status should be easy for clients and operators to understand.
7. **Local-first, production-ready adapters**: local filesystem and SQLite reduce development friction; storage and database adapters support S3-compatible storage and PostgreSQL in production.
8. **Incremental renderer maturity**: Editly gets the product working quickly; FFmpeg-native and HyperFrames broaden performance and creative capability later.

## Requirements

### MVP Functional Requirements

- Client can call `GET /v1/health` to verify API health without authentication.
- Client can POST a JSON composition to `/v1/renders` and receive `202 Accepted` with a render job ID.
- Client can GET `/v1/renders/{id}` to poll status, stage, progress, output URL, poster URL, timestamps, and error details.
- Client can GET `/v1/renders/{id}/download` to download the rendered output through the API.
- Client can submit compositions with video, image, text, audio, and color assets.
- Client can specify output format, explicit dimensions, fps, and quality for MP4 renders.
- Worker can resolve HTTPS remote assets with timeout, size, MIME, redirect, and SSRF protections.
- Worker can resolve `file://` assets only under explicitly configured local directories.
- Worker can render text assets to transparent PNG images with Pillow and bundled fonts.
- Worker can compile VidAPI's absolute-time composition schema into an Editly JSON spec via a segment compiler.
- Worker can invoke Editly as a Node subprocess with explicit timeout and resource limits.
- Worker can generate a poster or thumbnail from the rendered output using FFmpeg.
- System can store render artifacts in a deterministic local filesystem workspace.
- System can persist render metadata in SQLite for local development.
- System can validate all render requests with Pydantic v2 models before creating a job.
- System can store `input.json`, `expanded.json`, `compiled.editly.json`, `replay.json`, `output.mp4`, `poster.jpg`, and `logs.txt` for successful renders.
- System can store input, compiled spec when available, logs, replay metadata, and normalized errors for failed renders.
- System can expose a synchronous local render service behind the same service boundary used by the async worker path, only for early development and tests.

### Phase 01 Functional Requirements

- Client can GET `/v1/renders` to list recent render jobs with pagination.
- Client can DELETE `/v1/renders/{id}` to cancel queued jobs and best-effort cancel running jobs.
- API can enqueue render jobs into Redis through ARQ and return immediately.
- Worker can process queued jobs independently from the API process.
- Worker can update render status through `queued`, `fetching`, `compiling`, `rendering`, `uploading`, and terminal states.
- Worker can parse FFmpeg/Editly output for progress where available.
- Worker can isolate render workspaces per job so concurrent jobs do not corrupt each other.
- Worker can support multi-track compositing with z-order by track index.
- Worker can mix soundtrack and detached audio clips.
- Docker Compose can run API, worker, and Redis services together.

### Phase 02 Functional Requirements

- Client can create reusable templates through `POST /v1/templates`.
- Client can list templates through `GET /v1/templates`.
- Client can retrieve template metadata and active version through `GET /v1/templates/{id}`.
- Client can update a template through `PUT /v1/templates/{id}`, creating a new immutable version.
- Client can soft-delete or archive a template through `DELETE /v1/templates/{id}`.
- Client can render a template with merge variables through `POST /v1/templates/{id}/renders`.
- System can validate template variable schemas before expansion.
- System can substitute variables using Jinja2 sandbox mode with strict undefined handling.
- System can substitute variables only inside whitelisted string fields.
- System can validate expanded compositions after substitution and store the expanded composition per render.
- System can deliver webhook callbacks for render completion, failure, and cancellation.
- System can sign webhook payloads with HMAC-SHA256.
- System can retry failed webhooks with exponential backoff and store every delivery attempt.
- System can support named positions, offsets, basic fades, and crossfade transitions where supported by the selected renderer.

### Phase 03 Functional Requirements

- Operator can run VidAPI with PostgreSQL metadata persistence and Alembic migrations.
- Operator can run VidAPI with S3-compatible storage such as S3, Cloudflare R2, or MinIO.
- Client can authenticate non-health API requests with API keys.
- System can enforce request size, render duration, resolution, fps, clips, tracks, asset size, queue, and rate limits.
- Operator can configure public, signed, or proxied download URLs depending on deployment mode.
- Operator can inspect render jobs, statuses, errors, and webhook attempts through operational/admin endpoints.
- System can emit structured logs with request IDs and render IDs.
- System can expose basic metrics for queue wait time, render duration, status counts, renderer failures, and webhook delivery outcomes.

### Phase 04 Functional Requirements

- System can route HTML/CSS/GSAP-heavy compositions to a HyperFrames renderer behind the same renderer protocol.
- System can route simple high-throughput timelines to a native FFmpeg renderer after compatibility tests prove parity for supported subsets.
- Client can request GIF and WebM outputs.
- Client can request PNG sequence output where supported.
- Client can add captions or subtitles.
- Client can customize poster generation.
- Client can use render presets for TikTok, Reels, Shorts, YouTube, square ads, and low-resolution previews.
- System can reject unsupported renderer-feature combinations with clear validation errors.

## Non-Functional Requirements

- **Performance**: Render a 30-second, 1080p single-track video with 2-3 clips in under 60 seconds on a 4-core machine through Editly + FFmpeg.
- **API Latency**: Non-render API endpoints respond in under 200 ms at p95 under normal local or single-node deployment load.
- **Async Behavior**: `POST /v1/renders` returns `202 Accepted` without waiting for encode completion.
- **Concurrency**: Support at least 10 queued render jobs per worker instance without workspace collisions.
- **Reliability**: Every render reaches exactly one terminal state: `succeeded`, `failed`, or `cancelled`.
- **Replayability**: Every render stores enough artifacts to replay or diagnose the run: input, expanded composition, compiled spec when available, replay metadata, logs, output when available, and poster when available.
- **Asset Security**: Block localhost, loopback, link-local, private networks, metadata service endpoints, and redirects to blocked networks by default.
- **Asset Limits**: Enforce max remote asset size, per-asset timeout, MIME allowlist, duration limits, resolution limits, and stream-count limits before rendering.
- **Webhook Delivery**: Retry failed webhook callbacks 3 times with initial delays of 1s, 10s, and 60s; store every attempt for audit.
- **Storage**: Cache downloaded assets by SHA-256 to avoid redundant fetches.
- **Container Security**: Production containers run as a non-root user and expose health checks.
- **Determinism**: Same JSON input and same assets should produce functionally identical output and identical compiled renderer spec.
- **API Documentation**: OpenAPI documentation covers 100% of public endpoints, request models, response models, errors, and authentication behavior.

## Constraints and Dependencies

- Python 3.11+ runtime is required.
- Node.js runtime is required in the worker container for Editly.
- FFmpeg 6+ and ffprobe are required with libx264, libx265, and libvpx where relevant.
- Redis is required for ARQ queue processing from Phase 01 onward.
- Editly must be installed or vendored in the worker Docker image.
- Worker image must include deterministic fonts, initially Inter, Roboto, and Noto Sans.
- SQLite is allowed for local development; PostgreSQL is required for production deployments.
- Local filesystem storage is allowed for local development; S3-compatible object storage is required for production deployments that need durable remote artifacts.
- Remote asset fetching defaults to HTTPS only; HTTP may be enabled only for local development.
- `file://` URLs are allowed only under explicitly configured directories.
- Docker container isolation is acceptable for MVP worker isolation; stricter cgroup or namespace controls may be added for untrusted workloads at scale.

## System Architecture

```text
Client
  |
  | POST /v1/renders
  v
FastAPI API
  | validate request
  | authenticate when required
  | apply template variables when needed
  | create render record
  | enqueue job
  v
Redis Queue
  |
  v
Render Worker
  | resolve and validate assets
  | compile VidAPI JSON to renderer spec
  | invoke renderer subprocess
  | parse progress
  | generate poster
  | store artifacts
  | update status
  | enqueue webhook delivery
  v
Storage
  |
  v
GET /v1/renders/{id} -> status + URLs
```

## Runtime Components

### FastAPI API

Responsibilities:

- Health checks.
- API key authentication for non-health endpoints when authentication is enabled.
- Request validation with Pydantic v2 models.
- Render job creation and status reads.
- Template CRUD and template render submission.
- Download URL generation.
- Thin route handlers that delegate business logic to services.

### Database

Use SQLite for local development and PostgreSQL for production. Use SQLModel or SQLAlchemy with Alembic migrations.

Core tables:

| Table | Purpose |
|-------|---------|
| `renders` | One row per render job: id, status, progress, renderer, input JSON, expanded JSON, output path, poster path, error, timestamps. |
| `templates` | Reusable VidAPI composition JSON, metadata, soft-delete status, and active version pointer. |
| `template_versions` | Immutable template versions once a template has been rendered. |
| `assets` | Optional cached asset metadata: source URL, local path, content hash, MIME type, ffprobe metadata. |
| `webhook_attempts` | Delivery audit trail: event, status code, response body excerpt, retry schedule, timestamps. |

### Queue And Worker

Use ARQ with Redis for the MVP async path. ARQ fits FastAPI's async model and keeps the stack simpler than Celery. Celery remains an escape hatch only if future routing, broker, scheduling, or operational needs justify it.

Worker lifecycle:

1. Load render record.
2. Mark status `fetching`.
3. Resolve remote and local assets into an isolated job workspace.
4. Run asset validation and ffprobe on media inputs.
5. Apply merge variables if they were not already applied by template submission.
6. Mark status `compiling`.
7. Compile VidAPI composition to the selected renderer spec.
8. Save compiled spec and replay metadata.
9. Mark status `rendering`.
10. Invoke renderer with timeout and resource limits.
11. Parse renderer/FFmpeg output for progress where possible.
12. Mark status `uploading`.
13. Generate poster or thumbnail.
14. Move artifacts to storage.
15. Mark `succeeded` or `failed`.
16. Queue webhook delivery if configured.

### Storage

Use a storage adapter from day one.

Development storage:

```text
data/
  renders/
    render_01HZABC/
      input.json
      expanded.json
      compiled.editly.json
      replay.json
      output.mp4
      poster.jpg
      logs.txt
  assets/
    sha256/
      ab/cd/<hash>/original.ext
```

Production storage:

- S3, Cloudflare R2, MinIO, or any S3-compatible object store.
- API returns signed or public URLs depending on deployment settings.
- `/v1/renders/{id}/download` remains available for private and local storage modes.

## Suggested Project Structure

```text
app/
  main.py
  api/
    deps.py
    errors.py
    routes_health.py
    routes_renders.py
    routes_templates.py
  core/
    config.py
    logging.py
    security.py
  db/
    models.py
    session.py
    migrations/
  models/
    composition.py
    render.py
    template.py
  services/
    asset_service.py
    render_service.py
    storage_service.py
    template_service.py
    webhook_service.py
  renderers/
    base.py
    editly.py
    ffmpeg_native.py
    hyperframes.py
  storage/
    base.py
    local.py
    s3.py
  workers/
    render_worker.py
tests/
  fixtures/
  test_api_renders.py
  test_asset_security.py
  test_composition_schema.py
  test_editly_compiler.py
  test_worker_flow.py
docker-compose.yml
Dockerfile.api
Dockerfile.worker
pyproject.toml
README.md
```

## Canonical Public API

Use plural REST resources. Do not introduce singular `/v1/render` endpoints unless compatibility aliases are explicitly required later.

### Render Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/renders` | Create a render job from raw VidAPI JSON. |
| `GET` | `/v1/renders/{id}` | Read status, progress, output URL, poster URL, timestamps, and errors. |
| `GET` | `/v1/renders` | List recent render jobs with pagination. |
| `DELETE` | `/v1/renders/{id}` | Cancel queued jobs and best-effort cancel running jobs. |
| `GET` | `/v1/renders/{id}/download` | Download output through the API. |

### Template Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/templates` | Create a reusable template. |
| `GET` | `/v1/templates` | List templates. |
| `GET` | `/v1/templates/{id}` | Retrieve template metadata and active version. |
| `PUT` | `/v1/templates/{id}` | Update a template by creating a new version. |
| `DELETE` | `/v1/templates/{id}` | Soft-delete or archive a template. |
| `POST` | `/v1/templates/{id}/renders` | Render a template with merge variables. |

### Health Endpoint

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/v1/health` | API health check. |

## Render Request And Responses

### Render Request Example

```json
{
  "timeline": {
    "background": "#000000",
    "tracks": [
      {
        "clips": [
          {
            "asset": {
              "type": "image",
              "src": "https://example.com/photo.jpg"
            },
            "start": 0,
            "length": 4,
            "fit": "cover"
          }
        ]
      },
      {
        "clips": [
          {
            "asset": {
              "type": "text",
              "text": "Hello {{name}}",
              "font_family": "Inter",
              "font_size": 64,
              "color": "#ffffff",
              "background": "rgba(0,0,0,0.45)",
              "padding": 16
            },
            "start": 0.5,
            "length": 3,
            "position": "center",
            "opacity": 1
          }
        ]
      }
    ],
    "soundtrack": {
      "type": "audio",
      "src": "https://example.com/music.mp3",
      "volume": 0.35,
      "effect": "fadeOut"
    }
  },
  "output": {
    "format": "mp4",
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "quality": "medium"
  },
  "merge": {
    "name": "World"
  },
  "callback": "https://example.com/webhooks/render"
}
```

### Create Render Response

```json
{
  "id": "render_01HZZZ00000000000000000000",
  "status": "queued",
  "progress": 0,
  "created_at": "2026-05-05T01:30:00Z"
}
```

### Render Status Response

```json
{
  "id": "render_01HZZZ00000000000000000000",
  "status": "succeeded",
  "stage": "complete",
  "progress": 100,
  "url": "https://storage.example.com/renders/render_01HZZZ/output.mp4",
  "poster": "https://storage.example.com/renders/render_01HZZZ/poster.jpg",
  "duration": 4.0,
  "created_at": "2026-05-05T01:30:00Z",
  "completed_at": "2026-05-05T01:30:12Z",
  "error": null
}
```

## Internal Composition Schema

VidAPI owns this schema. It should be modeled with Pydantic v2 discriminated unions and should not leak renderer-specific details into common fields.

```text
Composition
  timeline: Timeline
  output: Output
  merge: dict[str, str | int | float | bool] | null
  callback: AnyUrl | null
  renderer: "auto" | "editly" | "ffmpeg-native" | "hyperframes" | null

Timeline
  background: color | null
  tracks: list[Track]
  soundtrack: AudioAsset | null

Track
  clips: list[Clip]

Clip
  asset: Asset
  start: float
  length: float
  fit: "cover" | "contain" | "stretch" | "none"
  position: Position
  offset: Offset | null
  scale: float
  opacity: float
  transition: Transition | null
  transform: Transform | null

Asset
  type: "video" | "image" | "text" | "audio" | "color" | "html"
```

### Asset Support

| Asset | MVP Support | Notes |
|-------|-------------|-------|
| `video` | Yes | HTTPS/local file, trim, volume, cover/contain/stretch. |
| `image` | Yes | HTTPS/local file, held for clip duration, cover/contain/stretch. |
| `text` | Yes | Render to image with Pillow and deterministic fonts, then place as renderer layer. |
| `audio` | Yes | Soundtrack and detached audio with trim and volume. |
| `color` | Yes | Solid background or clip/layer fill. |
| `html` | Deferred | Route to HyperFrames in an advanced phase; reject in MVP unless explicitly converted to an image asset. |

### Clip Fields

| Field | Meaning |
|-------|---------|
| `start` | Absolute timeline start in seconds. |
| `length` | Clip duration in seconds. |
| `fit` | How media maps into output bounds: `cover`, `contain`, `stretch`, `none`. |
| `position` | Named position or normalized coordinate. |
| `offset` | Relative x/y adjustment from named position. |
| `scale` | Multiplicative scale, default `1.0`. |
| `opacity` | `0.0` to `1.0`. |
| `transition` | Optional in/out transition with name and duration. |
| `transform` | Future rotation, skew, or keyframe support. |

### Output

Support explicit dimensions and presets. Explicit dimensions win if both are provided.

```text
Output
  format: "mp4" | "gif" | "webm" | "png-sequence"
  width: int | null
  height: int | null
  resolution: "360" | "480" | "720" | "1080" | "4k" | null
  aspect_ratio: "16:9" | "9:16" | "1:1" | "4:5" | null
  fps: int
  quality: "low" | "medium" | "high"
```

Resolution presets:

| Name | 16:9 | 9:16 | 1:1 | 4:5 |
|------|------|------|-----|-----|
| `360` | 640x360 | 360x640 | 360x360 | 360x450 |
| `480` | 854x480 | 480x854 | 480x480 | 480x600 |
| `720` | 1280x720 | 720x1280 | 720x720 | 720x900 |
| `1080` | 1920x1080 | 1080x1920 | 1080x1080 | 1080x1350 |
| `4k` | 3840x2160 | 2160x3840 | 2160x2160 | 2160x2700 |

H.264 quality presets:

| Quality | CRF | Preset |
|---------|-----|--------|
| `low` | 28 | `veryfast` |
| `medium` | 23 | `medium` |
| `high` | 18 | `slow` |

## Job Status State Machine

Use these status values exactly:

```text
queued
fetching
compiling
rendering
uploading
succeeded
failed
cancelled
```

Allowed transitions:

```text
queued -> fetching -> compiling -> rendering -> uploading -> succeeded
queued -> cancelled
fetching -> failed
compiling -> failed
rendering -> failed
uploading -> failed
queued -> failed
```

Each render stores:

- `progress`: integer from 0 to 100.
- `stage`: short current phase label.
- `error_code`: stable machine-readable error code.
- `error_message`: short client-facing message.
- `debug_log_path`: internal log artifact path.
- `replay_path`: artifact with renderer command and environment metadata.

## Renderer Abstraction

All rendering happens through a renderer protocol. Route handlers and high-level services must never call Editly, FFmpeg, or HyperFrames directly.

```python
from typing import Protocol


class Renderer(Protocol):
    name: str

    async def compile(
        self,
        composition: Composition,
        workspace: RenderWorkspace,
    ) -> CompiledRender:
        ...

    async def render(
        self,
        compiled: CompiledRender,
        workspace: RenderWorkspace,
    ) -> RenderArtifact:
        ...
```

Renderer selection:

| Renderer | When Used | Phase |
|----------|-----------|-------|
| `editly` | Default renderer for image, video, text, audio, and color timelines. | MVP |
| `hyperframes` | HTML/CSS/GSAP templates and browser-native layout/animation. | Advanced |
| `ffmpeg-native` | Simple high-throughput timelines and constrained operations where direct filter graphs are faster. | Advanced |

Default selection rule:

1. If `renderer` is explicitly provided, validate that the composition uses supported features for that renderer.
2. If `renderer` is absent or `auto`, use `hyperframes` when HTML or advanced animation blocks are present.
3. Otherwise use `editly`.
4. Route simple timelines to `ffmpeg-native` only after compatibility tests prove parity for the supported subset.

## MVP Rendering Pipeline

### Phase 1: Validation And Merge

1. Validate JSON with Pydantic.
2. Normalize output dimensions, fps, duration, clip ordering, and defaults.
3. Apply merge variables using the same template engine used for templates.
4. Store original `input.json` and final `expanded.json`.

### Phase 2: Asset Resolution

1. Walk all assets in the expanded composition.
2. Validate URL and file access policy before fetching.
3. Download remote assets with `httpx`.
4. Enforce timeout, max size, MIME allowlist, and redirect checks.
5. Cache assets by SHA-256.
6. Run ffprobe on audio and video inputs.
7. Render text assets to transparent PNGs with Pillow and bundled fonts when the selected renderer path needs image-backed text.

### Phase 3: Compile

1. Select renderer.
2. Compile VidAPI composition into renderer-specific spec.
3. Save the compiled spec in the render workspace.
4. Save replay metadata including executable, args, environment, timeout, and input paths.

### Phase 4: Render

1. Invoke renderer with `asyncio.create_subprocess_exec`.
2. Set explicit timeout and resource limits.
3. Capture full stdout and stderr.
4. Parse progress where available.
5. Fail with normalized error codes and keep raw logs for debugging.

### Phase 5: Store And Notify

1. Generate poster with FFmpeg.
2. Move output and artifacts to storage.
3. Mark render `succeeded` or `failed`.
4. Dispatch webhook asynchronously if configured.

## Editly Renderer Plan

Editly is the MVP renderer because it reduces the amount of rendering engine code VidAPI has to write before the API is useful.

### Editly Invocation

- Install or vendor Editly in the worker image.
- Generate `compiled.editly.json` in the job workspace.
- Invoke Editly as a Node subprocess through `asyncio.create_subprocess_exec`.
- Pass explicit `outPath`, `width`, `height`, and `fps`.
- Save the full stderr log and a replay command.
- Treat non-zero exit, timeout, missing output, and invalid output as render failures.

### Segment Compiler

VidAPI uses absolute timeline placement. Editly uses sequential `clips[]`. The compiler bridges the models by slicing the VidAPI timeline into non-overlapping segments.

Algorithm:

1. Collect every clip boundary: `start` and `start + length`.
2. Add timeline `0` and total duration.
3. Sort and deduplicate boundaries.
4. Convert adjacent boundaries into non-empty segments.
5. For each segment, find all clips active during that time window.
6. Generate one Editly clip with `duration = segment_end - segment_start`.
7. Convert active VidAPI clips into Editly layers.
8. Preserve track order as z-order.
9. Translate clip-relative timing into source trim and cut fields.
10. Convert soundtrack and detached audio into Editly audio fields where supported.
11. Emit deterministic JSON for reproducible tests.

The segment compiler is the most important MVP implementation risk. Build focused tests before broad feature work.

### Mapping

| VidAPI | Editly |
|--------|--------|
| `output.width` / `height` / `fps` | Top-level `width`, `height`, `fps`. |
| `output.format` | `outPath` extension and encoder settings where supported. |
| `timeline.background` | Background layer or Editly background option. |
| `video` asset | `video` layer with local `path`, `cutFrom`, `resizeMode`. |
| `image` asset | `image` or `image-overlay` layer with local `path`, `resizeMode`. |
| `text` asset | Prefer deterministic Pillow PNG overlay in MVP; map simple cases to `title`/`subtitle` only if parity is acceptable. |
| `audio` asset | `audioTracks` or clip audio where supported. |
| `timeline.soundtrack` | Top-level `audioTracks` or `audioFilePath`. |
| `fit: cover` | `resizeMode: "cover"`. |
| `fit: contain` | `resizeMode: "contain"` or compatible Editly contain mode. |
| `fit: stretch` | Editly stretch/fill equivalent if available; otherwise pre-scale asset. |
| `position` | Editly `position` where compatible, otherwise pre-compute overlay position. |
| `transition` | Editly transition when supported; otherwise reject unless explicitly configured. |

### MVP Constraints

The Editly MVP supports:

- Image backgrounds and overlays.
- Video backgrounds and overlays.
- Text overlays rendered with deterministic bundled fonts.
- Soundtrack audio.
- Basic fit modes.
- Basic named positions.
- One output file per render.

The Editly MVP defers:

- Complex transitions beyond fade and crossfade.
- Keyframed transforms.
- HTML/CSS assets.
- Lottie.
- Batch outputs.
- Advanced audio ducking.

## Native FFmpeg Renderer Plan

The native FFmpeg renderer is not the first implementation path, but the architecture must preserve room for it.

Use it later when:

- Timelines are simple and can render faster without Editly.
- VidAPI needs tighter control over filter graphs.
- Deployments need fewer Node or browser dependencies.
- Specific operations require deterministic low-level FFmpeg behavior.

Core algorithm:

1. Collect input files for video, image, audio, and rendered-text PNGs.
2. Create a base canvas with FFmpeg `color` at target resolution and duration.
3. For each track from bottom to top, trim media to the clip time range.
4. Scale according to fit mode.
5. Apply opacity and transitions.
6. Overlay with `enable='between(t,start,end)'`.
7. Mix audio streams and soundtrack with `amix` or `amerge`.
8. Encode with explicit codec, CRF, preset, fps, and format.
9. Parse FFmpeg stderr for progress.

Initial native FFmpeg support should be narrower than the public schema. It can reject unsupported features and fall back to Editly while parity grows.

## HyperFrames Renderer Plan

Use HyperFrames for advanced creative templates once the API and Editly path are stable.

Use it when:

- The composition contains `asset.type == "html"`.
- A template needs CSS layout, DOM text wrapping, rich typography, or GSAP-style animation.
- Agent-authored or browser-authored compositions become a priority.

HyperFrames still sits behind the same `Renderer` protocol. VidAPI compiles its own composition/template format into a HyperFrames-compatible artifact rather than exposing HyperFrames internals directly.

## Template System

Templates are stored VidAPI compositions with variable placeholders and optional variable schemas.

Template create request:

```json
{
  "name": "Product Ad",
  "variables": {
    "product_name": { "type": "string", "required": true },
    "product_image": { "type": "url", "required": true },
    "price": { "type": "string", "default": "$9.99" }
  },
  "composition": {
    "timeline": {
      "tracks": [
        {
          "clips": [
            {
              "asset": {
                "type": "image",
                "src": "{{ product_image }}"
              },
              "start": 0,
              "length": 5
            },
            {
              "asset": {
                "type": "text",
                "text": "{{ product_name }} - {{ price }}"
              },
              "start": 1,
              "length": 4,
              "position": "bottom"
            }
          ]
        }
      ]
    },
    "output": {
      "format": "mp4",
      "resolution": "1080",
      "aspect_ratio": "9:16"
    }
  }
}
```

Template render request:

```json
{
  "merge": {
    "product_name": "Widget Pro",
    "product_image": "https://cdn.example.com/widget.png",
    "price": "$19.99"
  },
  "callback": "https://example.com/webhooks/render"
}
```

Rules:

- Use Jinja2 sandbox mode with strict undefined handling.
- Substitute only inside whitelisted string fields.
- Validate variable schema before expansion.
- Validate the expanded composition after expansion.
- Store the expanded composition on the render record.
- Make template versions immutable once rendered.
- Updating a template creates a new version rather than mutating historical render inputs.

## Asset Security

Remote asset fetching is one of the highest-risk parts of this product. Implement these rules in the MVP, not as a later hardening pass.

Allowed by default:

- `https://` remote assets.
- `file://` assets only under explicitly configured directories.

Blocked by default:

- `http://` unless enabled for local development.
- `localhost`, `127.0.0.0/8`, and `::1`.
- Private networks.
- Link-local addresses.
- Metadata service endpoints.
- Redirects to blocked networks.

Validation rules:

- Resolve DNS and validate final IP before connecting.
- Re-check redirects.
- Enforce max download size.
- Enforce per-asset timeout.
- Enforce MIME allowlist.
- Save SHA-256 hash.
- Run ffprobe for media duration, codec, and stream validation.
- Reject files exceeding max duration, resolution, or stream count.

## Webhooks

Webhook events:

```text
render.succeeded
render.failed
render.cancelled
```

Payload:

```json
{
  "event": "render.succeeded",
  "render_id": "render_01HZZZ00000000000000000000",
  "status": "succeeded",
  "url": "https://storage.example.com/renders/render_01HZZZ/output.mp4",
  "poster": "https://storage.example.com/renders/render_01HZZZ/poster.jpg",
  "completed_at": "2026-05-05T01:30:12Z"
}
```

Implementation:

- Sign payloads with HMAC-SHA256.
- Include timestamp and signature headers.
- Retry with exponential backoff, initially 1s, 10s, and 60s.
- Store every attempt.
- Do not block render completion on webhook delivery.
- Keep webhook failure separate from render success.

## Authentication And Limits

The MVP can start with a single API key environment variable, but the schema and service boundaries should allow multiple keys later.

Initial controls:

- API key required for all non-health endpoints.
- Max render duration.
- Max output width and height.
- Max fps.
- Max clips per render.
- Max tracks per render.
- Max remote asset size.
- Max concurrent jobs per worker.
- Request body size limit.
- Rate limits on render submission in production.

Recommended first limits:

| Limit | Initial Value |
|-------|---------------|
| Max render duration | 120 seconds |
| Max output resolution | 1920x1920 or equivalent pixels |
| Max fps | 60 |
| Max clips | 50 |
| Max tracks | 10 |
| Max asset size | 500 MB video/audio, 50 MB image |
| Render timeout | 10 minutes |

## Deployment

MVP Docker Compose:

```text
api        FastAPI + Uvicorn
worker     Python + Node + Editly + FFmpeg + fonts
redis      ARQ queue
postgres   production-like metadata store
minio      S3-compatible local object storage
```

Development may allow SQLite and local filesystem storage to reduce setup friction.

Worker image requirements:

- Python 3.11+.
- Node.js runtime.
- Editly installed or vendored.
- FFmpeg and ffprobe.
- Bundled fonts: Inter, Roboto, and Noto Sans.
- Non-root user in production.
- Health checks.
- Ephemeral render workspaces cleaned after artifacts are persisted.

## Observability

Use structured logging with render ID in every worker and API log line.

Capture:

- Request ID.
- Render ID.
- Template ID and version when applicable.
- Renderer name.
- Status transitions.
- Asset fetch timings and sizes.
- Compile duration.
- Render duration.
- Output size.
- Error code and stderr artifact path on failure.

Metrics to add after MVP:

- Render count by status.
- Render duration histogram.
- Queue wait time.
- Asset download failures.
- Renderer failure rate.
- Webhook delivery success/failure.

## Testing Strategy

Test priorities:

1. Composition schema validation.
2. Asset URL security validation.
3. Segment compiler behavior.
4. Worker state transitions.
5. Render artifact persistence.
6. API endpoint contracts.
7. One short end-to-end render.

Segment compiler tests must cover:

- Single clip.
- Two sequential clips.
- Overlapping clips on different tracks.
- Gaps in the timeline.
- Text overlay active for only part of a background clip.
- Asset trim/cut offsets.
- Zero-length or negative-length rejection.
- Track z-order.
- Soundtrack inclusion.

Integration tests should use 1-2 second fixture assets to keep CI fast.

Every failed render test should verify that input JSON, compiled spec when available, logs, and replay metadata are persisted.

## Phases

This system delivers the product via phases. Each phase is implemented via multiple 2-4 hour sessions with 12-25 tasks each.

| Phase | Name | Sessions | Status |
|-------|------|----------|--------|
| 00 | Foundation | 5 | Complete (5/5) |
| 01 | Async Jobs and Multi-track | 5 | Complete (5/5) |
| 02 | Templates and Polish | 5 | Complete (5/5) |
| 03 | Production Hardening | 5 | Complete (5/5) |
| 04 | Advanced Rendering | TBD | Not Started |

## Phase 00: Foundation

### Objective

Prove the core JSON-to-video loop locally.

### Deliverables

- FastAPI skeleton with `/v1/health`.
- Pydantic composition models.
- Render DB model with SQLite.
- Local filesystem storage adapter.
- `POST /v1/renders`.
- `GET /v1/renders/{id}`.
- `GET /v1/renders/{id}/download`.
- Synchronous local render service behind the same service boundary used by the worker later.
- Editly renderer wrapper.
- Editly segment compiler for image, video, text, and soundtrack.
- Poster generation.
- Golden-path end-to-end render test.

### Exit Criteria

- A sample JSON with one image/video background, one text overlay, optional music, and vertical MP4 output renders successfully.
- Stored artifacts include `input.json`, `expanded.json`, `compiled.editly.json`, `replay.json`, `output.mp4`, `poster.jpg`, and `logs.txt`.
- Segment compiler tests cover the core single-track and overlay cases.

### Sessions

| Session | Name | Est. Tasks |
|---------|------|------------|
| 01 | Project Skeleton and Config | ~15-20 |
| 02 | Composition Schema and DB Models | ~15-20 |
| 03 | Storage and Asset Service | ~15-20 |
| 04 | Editly Renderer and Segment Compiler | ~20-25 |
| 05 | Render Service and API Endpoints | ~15-20 |

Session stubs: `.spec_system/PRD/phase_00/`

## Phase 01: Async Jobs And Multi-track

### Objective

Move rendering out of the API request path and support real timeline layering.

### Deliverables

- Redis + ARQ queue.
- Worker process.
- Status transitions through the full state machine.
- Progress updates where renderer output allows it.
- Render log capture.
- Cancellation for queued jobs and best-effort running cancellation.
- Multi-track segment compiler z-order.
- Soundtrack and detached audio mixing.
- Docker Compose with API, worker, and Redis.
- `GET /v1/renders` list endpoint with pagination.

### Exit Criteria

- API returns `202 Accepted` immediately.
- Worker completes render independently.
- Polling reflects status changes.
- Multiple queued jobs can complete without corrupting each other's workspaces.

## Phase 02: Templates And Polish

### Objective

Make VidAPI useful for repeatable programmatic video generation.

### Deliverables

- Template CRUD.
- Template versioning.
- Strict Jinja2 merge variables.
- `POST /v1/templates/{id}/renders`.
- Soundtrack and detached audio improvements.
- Named positions and offsets.
- Basic transitions: fade in/out and crossfade where supported.
- Webhook callbacks with signing and retry.

This phase is complete. Archived session artifacts live in `.spec_system/archive/phases/phase_02/`.

### Exit Criteria

- A product-ad style template can render multiple variations.
- Historical renders remain reproducible after template updates.
- Webhook attempts are recorded and signed.

### Sessions

| Session | Name | Est. Tasks |
|---------|------|------------|
| 01 | Template Models and CRUD API | ~20 |
| 02 | Template Variables and Rendering | ~18 |
| 03 | Webhook Delivery System | ~18 |
| 04 | Transitions and Positioning | ~16 |
| 05 | Audio Polish and Hardening | ~15 |

Archived phase artifacts: `.spec_system/archive/phases/phase_02/`

## Phase 03: Production Hardening

### Objective

Make the service safe and operable outside local development.

### Deliverables

- PostgreSQL support.
- Alembic migrations.
- S3-compatible storage.
- API key authentication.
- Rate limiting.
- Asset SSRF protections.
- Resource limits for render subprocesses.
- Configurable max duration, size, fps, resolution, tracks, and clips.
- Admin/list endpoints for operational visibility.
- Structured logs and basic metrics.

This phase is complete. Archived session artifacts live in `.spec_system/archive/phases/phase_03/`.

### Exit Criteria

- Docker Compose can run API, worker, Redis, Postgres, and MinIO.
- Production-like storage URLs work.
- Common asset attack cases are rejected by tests.

### Sessions

| Session | Name | Est. Tasks |
|---------|------|------------|
| 01 | PostgreSQL Persistence and Alembic Migrations | ~20 |
| 02 | S3-compatible Storage and Download Modes | ~20 |
| 03 | API Key Authentication and Access Control | ~18 |
| 04 | Limits, Resource Controls, and Asset Security Hardening | ~20 |
| 05 | Operational Visibility and Production Stack | ~20 |

Archived phase artifacts: `.spec_system/archive/phases/phase_03/`

## Phase 04: Advanced Rendering

### Objective

Expand creative ceiling and performance options without changing the public API.

### Deliverables

- HyperFrames renderer for HTML/CSS/GSAP templates.
- Native FFmpeg renderer for simple timelines.
- GIF and WebM output support.
- PNG sequence output support.
- Captions/subtitles.
- Poster customization.
- Additional transitions.
- Render presets for TikTok, Reels, Shorts, YouTube, square ads, and low-resolution previews.

### Exit Criteria

- Renderer selection works through the same protocol.
- Existing Editly-backed renders keep passing.
- New renderer paths have focused compatibility tests.

## First Build Target

The first demo should do exactly this:

1. Submit JSON with one background image or video.
2. Add one text overlay.
3. Optionally include music.
4. Request vertical MP4 output with explicit dimensions.
5. Receive `202 Accepted` with a render ID.
6. Poll until `succeeded`.
7. Download `output.mp4`.
8. Inspect stored input, expanded JSON, compiled Editly spec, replay metadata, poster, and logs.

This target proves the product loop without overbuilding templates, HTML rendering, distributed workers, or a native FFmpeg graph builder too early.

## Technical Stack

- **Python 3.11+ / FastAPI** - Async web framework with OpenAPI docs and Pydantic integration.
- **Pydantic v2** - Discriminated unions for asset types, fast validation, and settings management.
- **ARQ + Redis** - Lightweight async-native task queue.
- **Editly** - Default MVP renderer invoked as a Node subprocess.
- **FFmpeg 6+** - Video encoding, filter graphs, poster generation, ffprobe, and audio mixing.
- **Pillow + fonttools** - Text-to-image rendering with precise font control.
- **SQLite / PostgreSQL** - SQLite for development, PostgreSQL for production metadata persistence.
- **SQLModel or SQLAlchemy + Alembic** - Database models and migrations.
- **Local filesystem / S3-compatible storage** - Output files, cached assets, and render artifacts.
- **Docker Compose** - API, worker, Redis, Postgres, and MinIO in one stack.
- **httpx** - Async asset downloads and webhook delivery.
- **Jinja2 sandbox** - Template variable substitution with strict undefined handling.
- **structlog** - Structured application and worker logging.
- **pytest + pytest-asyncio** - Unit, integration, and async workflow tests.
- **ruff + mypy** - Formatting, linting, and type safety.

## Success Criteria

- [ ] POST a JSON composition and receive a rendered MP4 within 60 seconds for a 30-second single-track video.
- [ ] Support video, image, text, audio, and color asset types in compositions.
- [ ] Support multi-track overlay compositing with z-order, positioning, and timing.
- [ ] Editly segment compiler correctly converts absolute-time timelines to sequential Editly clips.
- [ ] Async job queue supports status polling through the full state machine.
- [ ] Render cancellation works for queued jobs and best-effort for running jobs.
- [ ] Template CRUD supports Jinja2 variable substitution and immutable versioning.
- [ ] Webhook callbacks fire on completion, failure, and cancellation with HMAC signing and retry.
- [ ] Docker Compose provides one-command local development with API, worker, Redis, Postgres, and MinIO.
- [ ] Pluggable renderer abstraction uses Editly as the default backend without leaking Editly schemas to clients.
- [ ] Asset downloads enforce SSRF protection, redirect validation, size limits, MIME validation, and timeout.
- [ ] Every render stores input JSON, expanded JSON, compiled spec when available, output, poster, logs, and replay metadata.
- [ ] Tests cover schema validation, asset security, segment compilation, worker status transitions, API contracts, and one end-to-end render.

## Risks

- **Absolute timeline to Editly sequential clip conversion becomes complex**: Keep the MVP schema constrained and build segment compiler tests first.
- **Remote asset fetching creates SSRF exposure**: Enforce strict URL validation, network blocking, redirect checks, timeouts, size limits, and MIME checks from the MVP.
- **Editly subprocess failures are hard to debug**: Save compiled spec, full stderr, normalized error code, and replay metadata for every render.
- **Fonts render differently across machines**: Bundle known fonts and use explicit font paths.
- **Long renders block API resources**: Queue all renders; local synchronous mode exists only behind the same service boundary for early development.
- **Renderer lock-in**: Keep the public schema VidAPI-owned and renderer artifacts generated behind a protocol interface.
- **Native FFmpeg path becomes a second incompatible product**: Add it only behind the same renderer protocol and only for tested subsets of the schema.
- **Docker worker image grows large**: Use multi-stage builds, clear dependency boundaries, and explicit `.dockerignore` exclusions.

## Assumptions

- FFmpeg 6+ with required codecs is available in the worker container.
- Node.js is available in the worker container for Editly.
- Redis is available for the job queue from Phase 01 onward.
- Remote assets are accessible via HTTPS from the worker network.
- Render jobs are independent and share no mutable state beyond the queue, database, and storage backend.
- A 4-core machine can render a 30-second 1080p video in under 60 seconds through Editly + FFmpeg for the MVP target case.
- The service starts as self-hosted single-tenant software; multi-tenant SaaS concerns are out of scope.

## Resolved Architecture Decisions

| Question | Decision |
|----------|----------|
| Singular or plural render endpoints? | Use plural `/v1/renders`. |
| Explicit dimensions or presets? | Support both; explicit `width` and `height` win over presets. |
| Render IDs? | Use sortable public IDs with `render_` prefix, preferably ULID-style. |
| Queue library? | Use ARQ with Redis for MVP. |
| First renderer? | Use Editly subprocess bridge. |
| Text rendering? | Use deterministic Pillow-rendered PNG overlays for MVP; map to Editly text layers only where parity is acceptable. |
| HTML support? | Defer to HyperFrames renderer. |
| Worker isolation? | Docker container isolation is acceptable for MVP; add stricter controls if running untrusted workloads at scale. |
| Unsupported renderer features? | Reject with clear validation errors or require explicit renderer-specific extension fields later. |
| Database path? | Use SQLite for development and PostgreSQL for production. |
| Storage path? | Use local filesystem for development and S3-compatible storage for production. |

## Open Questions

1. Which API key model should follow the MVP single-key environment variable: static key list, hashed keys in PostgreSQL, or an external identity provider?
2. Which storage URL policy should be the production default: signed object URLs, public object URLs, or always-proxied downloads?
3. Which exact local directories should be allowed for `file://` assets in development and production?
4. Which render presets should be available in the first public release beyond the base resolution/aspect-ratio matrix?
5. What retention policy should apply to render artifacts, cached assets, logs, and webhook attempts?

## Source Carryforward

This PRD carries forward the implementation-critical content from `docs/final-plan.md` and the prior draft PRD:

- Product positioning, goals, non-goals, users, and use cases.
- API contract and endpoint naming.
- Internal JSON composition schema.
- Render lifecycle and worker pipeline.
- Editly-first MVP renderer plan.
- Native FFmpeg renderer strategy.
- HyperFrames future renderer path.
- Template system.
- Asset security requirements.
- Webhook behavior.
- Storage, database, and queue choices.
- Deployment shape.
- Observability and testing strategy.
- Implementation phases and first demo target.
- Key risks, mitigations, assumptions, and resolved architecture decisions.

After this PRD is reviewed, `docs/final-plan.md` can be deleted without losing architectural direction.
