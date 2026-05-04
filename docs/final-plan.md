# VidAPI Final Architecture Plan

This document supersedes `docs/architecture.md` and `docs/vidapi-architecture-plan.md`.
It is the single implementation plan for building VidAPI: a self-hosted Python FastAPI service that accepts JSON video compositions, queues asynchronous renders, produces video outputs, and exposes status, download, template, and webhook APIs.

## Executive Decision

VidAPI should use a FastAPI orchestration layer with a VidAPI-owned JSON composition schema and a pluggable renderer interface.

The first production path should be an Editly renderer bridge, invoked from Python as a Node subprocess. This gets the product to a usable Creatomate/JSON2Video-style loop quickly because Editly already provides a declarative edit format, clip/layer composition, image/video/text/audio support, transitions, and FFmpeg output.

The system should not expose Editly's schema as the public API. VidAPI owns the public schema and compiles it into renderer-specific artifacts. That keeps the API stable when we add:

- A native FFmpeg renderer for simple, high-throughput timelines.
- A HyperFrames renderer for HTML/CSS/GSAP-rich templates.
- Future renderer-specific escape hatches without breaking normal clients.

The core MVP is:

```text
JSON composition -> POST /v1/renders -> queued job -> worker render -> MP4 URL
```

## Goals

1. Provide a self-hosted alternative to Creatomate and JSON2Video for programmatic video rendering.
2. Accept a JSON document describing a multi-track timeline with clips, assets, text, transitions, output settings, and optional callbacks.
3. Render asynchronously through a queue so API requests never block on long encodes.
4. Support reusable templates with strict variable substitution.
5. Store render inputs, compiled renderer specs, logs, outputs, and posters for replay and debugging.
6. Keep the renderer backend swappable through a stable internal protocol.
7. Ship a one-command Docker Compose development stack.

## Non-Goals

- Browser-based video editor UI.
- Real-time streaming or live compositing.
- Cloning every Creatomate/JSON2Video feature in v1.
- Multi-tenant SaaS billing, subscriptions, or user management.
- AI generation of images, videos, voiceovers, or music.
- Distributed render orchestration beyond multiple workers sharing one queue.
- Broadcast/professional output formats such as ProRes or lossless masters.

## Reference Roles

| Reference | Role In VidAPI |
| --- | --- |
| [Shottower](../references/shottower/README.md) | API shape, render lifecycle, Shotstack-style timeline vocabulary: timeline, tracks, clips, assets, outputs, callbacks. |
| [Editly](../references/editly/README.md) | Default MVP render engine. VidAPI compiles its internal schema to Editly JSON and invokes Editly as a subprocess. |
| [HyperFrames](../references/hyperframes/docs/introduction.mdx) | Future advanced renderer for HTML-first templates, CSS/GSAP animations, and browser-native layout. |
| [Video Artist API](../references/video-artist-api/README.md) | Reference for a simple Python-adjacent JSON video API and preview/render flow, not the main architecture. |

## Design Principles

1. **JSON-first**: every render is fully described by a JSON document.
2. **Async by default**: render work is queued; clients poll or receive webhooks.
3. **Renderer-independent public API**: clients send VidAPI JSON, not Editly, FFmpeg, or HyperFrames internals.
4. **Replayable renders**: each job stores input JSON, expanded JSON, compiled renderer spec, command/replay metadata, stderr logs, output, and poster.
5. **Strict asset security**: remote media rendering is SSRF-prone, so URL and file access are constrained from day one.
6. **Small, explicit state machine**: job status should be easy for clients and operators to understand.
7. **Local-first, production-ready seams**: local filesystem and SQLite for development; storage and database adapters support S3/Postgres in production.
8. **Incremental renderer maturity**: Editly gets us working quickly; FFmpeg-native and HyperFrames broaden performance and creative capability later.

## System Architecture

```text
Client
  |
  | POST /v1/renders
  v
FastAPI API
  | validate request
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

- API key authentication.
- Request validation with Pydantic v2 models.
- Render job creation and status reads.
- Template CRUD and template render submission.
- Download URL generation.
- Health checks.
- Thin route handlers that delegate business logic to services.

### Database

Use SQLite for local development and PostgreSQL for production. Use SQLModel or SQLAlchemy with Alembic migrations.

Core tables:

| Table | Purpose |
| --- | --- |
| `renders` | One row per render job: id, status, progress, renderer, input JSON, expanded JSON, output path, poster path, error, timestamps. |
| `templates` | Reusable VidAPI composition JSON, metadata, active version pointer. |
| `template_versions` | Immutable template versions once a template has been rendered. |
| `assets` | Optional cached asset metadata: source URL, local path, content hash, MIME type, ffprobe metadata. |
| `webhook_attempts` | Delivery audit trail, response status/body, retry schedule. |

### Queue And Worker

Use ARQ with Redis for the MVP. It fits FastAPI's async model and keeps the stack simpler than Celery. Celery remains an escape hatch if future routing, broker, or scheduling needs justify it.

Worker lifecycle:

1. Load render record.
2. Mark status `fetching`.
3. Resolve remote/local assets into an isolated job workspace.
4. Run asset validation and `ffprobe` on media.
5. Apply merge variables if they were not already applied by template submission.
6. Mark status `compiling`.
7. Compile VidAPI composition to the selected renderer spec.
8. Save compiled spec and replay metadata.
9. Mark status `rendering`.
10. Invoke renderer with timeout and resource limits.
11. Parse renderer/FFmpeg output for progress where possible.
12. Mark status `uploading`.
13. Generate poster/thumbnail.
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
- `/v1/renders/{id}/download` remains available for private/local storage mode.

## Suggested Project Structure

```text
app/
  main.py
  api/
    deps.py
    errors.py
    routes_renders.py
    routes_templates.py
    routes_health.py
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
    render_service.py
    template_service.py
    asset_service.py
    storage_service.py
    webhook_service.py
  renderers/
    base.py
    editly.py
    ffmpeg_native.py
    hyperframes.py
  workers/
    render_worker.py
  storage/
    base.py
    local.py
    s3.py
tests/
  fixtures/
  test_api_renders.py
  test_composition_schema.py
  test_editly_compiler.py
  test_asset_security.py
  test_worker_flow.py
docker-compose.yml
Dockerfile.api
Dockerfile.worker
pyproject.toml
README.md
```

## Canonical Public API

Use plural REST resources. Do not build new singular `/v1/render` endpoints unless compatibility aliases are explicitly needed later.

### Render Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/v1/renders` | Create a render job from raw VidAPI JSON. |
| `GET` | `/v1/renders/{id}` | Read status, progress, output URL, poster URL, and errors. |
| `GET` | `/v1/renders` | List recent render jobs with pagination. |
| `DELETE` | `/v1/renders/{id}` | Cancel queued jobs and best-effort cancel running jobs. |
| `GET` | `/v1/renders/{id}/download` | Download output through the API. |

### Template Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/v1/templates` | Create a reusable template. |
| `GET` | `/v1/templates` | List templates. |
| `GET` | `/v1/templates/{id}` | Retrieve template metadata and active version. |
| `PUT` | `/v1/templates/{id}` | Update a template by creating a new version. |
| `DELETE` | `/v1/templates/{id}` | Soft-delete or archive a template. |
| `POST` | `/v1/templates/{id}/renders` | Render a template with merge variables. |

### Health Endpoint

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/v1/health` | API health check. |

## Render Request

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

VidAPI owns this schema. It should be modeled with Pydantic v2 discriminated unions and should never leak renderer-specific details into common fields.

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
| --- | --- | --- |
| `video` | Yes | HTTPS/local file, trim, volume, cover/contain/stretch. |
| `image` | Yes | HTTPS/local file, held for clip duration, cover/contain/stretch. |
| `text` | Yes | Render to image with Pillow for deterministic fonts, then place as renderer layer. |
| `audio` | Yes | Soundtrack and detached audio with trim and volume. |
| `color` | Yes | Solid background or clip/layer fill. |
| `html` | Deferred | Route to HyperFrames in advanced phase. Reject in MVP unless explicitly converted to an image asset. |

### Clip Fields

| Field | Meaning |
| --- | --- |
| `start` | Absolute timeline start in seconds. |
| `length` | Clip duration in seconds. |
| `fit` | How media maps into output bounds: `cover`, `contain`, `stretch`, `none`. |
| `position` | Named position or normalized coordinate. |
| `offset` | Relative x/y adjustment from named position. |
| `scale` | Multiplicative scale, default `1.0`. |
| `opacity` | `0.0` to `1.0`. |
| `transition` | Optional in/out transition with name and duration. |
| `transform` | Future rotation/skew/keyframe support. |

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
| --- | --- | --- | --- | --- |
| `360` | 640x360 | 360x640 | 360x360 | 360x450 |
| `480` | 854x480 | 480x854 | 480x480 | 480x600 |
| `720` | 1280x720 | 720x1280 | 720x720 | 720x900 |
| `1080` | 1920x1080 | 1080x1920 | 1080x1080 | 1080x1350 |
| `4k` | 3840x2160 | 2160x3840 | 2160x2160 | 2160x2700 |

H.264 quality presets:

| Quality | CRF | Preset |
| --- | --- | --- |
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

- `progress`: integer 0-100.
- `stage`: short current phase label.
- `error_code`: stable machine-readable error code.
- `error_message`: short client-facing message.
- `debug_log_path`: internal log artifact path.
- `replay_path`: artifact with the renderer command and environment metadata.

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
| --- | --- | --- |
| `editly` | Default renderer for image, video, text, audio, color timelines. | MVP |
| `hyperframes` | HTML/CSS/GSAP templates and browser-native layout/animation. | Advanced |
| `ffmpeg-native` | Simple high-throughput timelines and constrained operations where direct filter graphs are faster. | Advanced |

Default selection rule:

1. If `renderer` is explicitly provided, validate that the composition uses supported features for that renderer.
2. If `renderer` is absent or `auto`, use `hyperframes` when HTML/advanced animation blocks are present.
3. Otherwise use `editly`.
4. Later, route simple timelines to `ffmpeg-native` only after compatibility tests prove parity.

## MVP Rendering Pipeline

### Phase 1: Validation And Merge

1. Validate JSON with Pydantic.
2. Normalize output dimensions, fps, duration, clip ordering, and defaults.
3. Apply merge variables using the same template engine used for templates.
4. Store original `input.json` and final `expanded.json`.

### Phase 2: Asset Resolution

1. Walk all assets in the expanded composition.
2. Validate URL/file access policy before fetching.
3. Download remote assets with `httpx`.
4. Enforce timeout, max size, and MIME allowlist.
5. Cache assets by SHA-256.
6. Run `ffprobe` on audio/video inputs.
7. Render text assets to transparent PNGs with Pillow and bundled fonts when the selected renderer path needs image-backed text.

### Phase 3: Compile

1. Select renderer.
2. Compile VidAPI composition into renderer-specific spec.
3. Save the compiled spec in the render workspace.
4. Save replay metadata including executable, args, environment, timeout, and input paths.

### Phase 4: Render

1. Invoke renderer with `asyncio.create_subprocess_exec`.
2. Set explicit timeout and resource limits.
3. Capture full stdout/stderr.
4. Parse progress where available.
5. Fail with normalized error codes and keep raw logs for debugging.

### Phase 5: Store And Notify

1. Generate poster with FFmpeg.
2. Move output and artifacts to storage.
3. Mark render `succeeded` or `failed`.
4. Dispatch webhook asynchronously if configured.

## Editly Renderer Plan

Editly is the MVP renderer because it reduces the amount of rendering engine code VidAPI has to write before the API can be useful.

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
9. Translate clip-relative timing into source trim/cut fields.
10. Convert soundtrack and detached audio into Editly audio fields where supported.
11. Emit a deterministic JSON spec for reproducible tests.

This segment compiler is the most important MVP implementation risk. It needs tests before broad feature work.

### Mapping

| VidAPI | Editly |
| --- | --- |
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
| `transition` | Editly transition when supported; otherwise reject or ignore only if explicitly configured. |

### MVP Constraints

The Editly MVP should support:

- Image backgrounds and overlays.
- Video backgrounds and overlays.
- Text overlays rendered with deterministic bundled fonts.
- Soundtrack audio.
- Basic fit modes.
- Basic named positions.
- One output file per render.

The Editly MVP can defer:

- Complex transitions beyond fade/crossfade.
- Keyframed transforms.
- HTML/CSS assets.
- Lottie.
- Batch outputs.
- Advanced audio ducking.

## Native FFmpeg Renderer Plan

The native FFmpeg renderer is not the first implementation path, but the architecture must preserve room for it.

Use it later when:

- Timelines are simple and can be rendered faster without Editly.
- We need tighter control over filter graphs.
- We need fewer Node/browser dependencies in constrained deployments.
- We need deterministic low-level behavior for specific operations.

Core algorithm:

1. Collect input files for video, image, audio, and rendered-text PNGs.
2. Create a base canvas with FFmpeg `color` at target resolution and duration.
3. For each track from bottom to top:
   - Trim/cut media to the clip's time range.
   - Scale according to fit mode.
   - Apply opacity and transitions.
   - Overlay with `enable='between(t,start,end)'`.
4. Mix audio streams and soundtrack with `amix`/`amerge`.
5. Encode with explicit codec, CRF, preset, fps, and format.
6. Parse FFmpeg stderr for progress.

Initial native FFmpeg feature set should be narrower than the public schema. It can reject unsupported features and fall back to Editly while parity grows.

## HyperFrames Renderer Plan

Use HyperFrames for advanced creative templates once the API and Editly path are stable.

Use it when:

- The composition contains `asset.type == "html"`.
- A template needs CSS layout, DOM text wrapping, rich typography, or GSAP-style animation.
- Agent-authored or browser-authored compositions become a priority.

HyperFrames should still sit behind the same `Renderer` protocol. VidAPI should compile its own composition/template format into a HyperFrames-compatible composition rather than exposing HyperFrames internals directly.

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
- Only substitute inside whitelisted string fields.
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
- `localhost`, `127.0.0.0/8`, `::1`.
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
- Run `ffprobe` for media duration, codec, and stream validation.
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
- Retry with exponential backoff, initially 1s, 10s, 60s.
- Store every attempt.
- Do not block render completion on webhook delivery.
- Keep webhook failure separate from render success.

## Authentication And Limits

MVP can start with a single API key environment variable, but the schema should allow multiple keys later.

Initial controls:

- API key required for all non-health endpoints.
- Max render duration.
- Max output width/height.
- Max fps.
- Max clips per render.
- Max tracks per render.
- Max remote asset size.
- Max concurrent jobs per worker.
- Request body size limit.

Recommended first limits:

| Limit | Initial Value |
| --- | --- |
| Max render duration | 120 seconds |
| Max output resolution | 1920x1920 or 1920x1080 equivalent pixels |
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
- Bundled fonts: Inter, Roboto, and Noto Sans as a practical baseline.
- Non-root user in production.
- Health checks.
- Ephemeral render workspaces cleaned after artifacts are persisted.

## Observability

Use structured logging with render ID in every worker/API log line.

Capture:

- Request ID.
- Render ID.
- Template ID/version when applicable.
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

Every failed render test should verify that input JSON, compiled spec, logs, and replay metadata are persisted.

## Implementation Roadmap

This roadmap follows the local spec-system principle: each implementation session should be 2-4 hours and contain roughly 12-25 focused tasks.

### Phase 00: Foundation

Objective: prove the core JSON-to-video loop locally.

Deliverables:

- FastAPI skeleton with `/v1/health`.
- Pydantic composition models.
- Render DB model with SQLite.
- Local filesystem storage adapter.
- `POST /v1/renders`.
- `GET /v1/renders/{id}`.
- `GET /v1/renders/{id}/download`.
- Synchronous local render service behind the same service boundary that the worker will use later.
- Editly renderer wrapper.
- Editly segment compiler for image, video, text, and soundtrack.
- Poster generation.
- Golden-path end-to-end render test.

Exit criteria:

- A sample JSON with one image/video background, one text overlay, optional music, and vertical MP4 output renders successfully.
- Stored artifacts include `input.json`, `expanded.json`, `compiled.editly.json`, `replay.json`, `output.mp4`, `poster.jpg`, and `logs.txt`.

### Phase 01: Async Jobs And Multi-Track

Objective: move rendering out of the API request path and support real timeline layering.

Deliverables:

- Redis + ARQ queue.
- Worker process.
- Status transitions through the full state machine.
- Progress updates where renderer output allows it.
- Render log capture.
- Cancellation for queued jobs and best-effort running cancellation.
- Multi-track segment compiler z-order.
- Docker Compose with API, worker, Redis.

Exit criteria:

- API returns `202 Accepted` immediately.
- Worker completes render independently.
- Polling reflects status changes.
- Multiple queued jobs can complete without corrupting each other's workspaces.

### Phase 02: Templates, Audio, And Polish

Objective: make VidAPI useful for repeatable programmatic video generation.

Deliverables:

- Template CRUD.
- Template versioning.
- Strict Jinja2 merge variables.
- `POST /v1/templates/{id}/renders`.
- Soundtrack and detached audio improvements.
- Named positions and offsets.
- Basic transitions: fade in/out, crossfade where supported.
- Webhook callbacks with signing and retry.

Exit criteria:

- A product-ad style template can render multiple variations.
- Historical renders remain reproducible after template updates.
- Webhook attempts are recorded and signed.

### Phase 03: Production Hardening

Objective: make the service safe and operable outside local development.

Deliverables:

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

Exit criteria:

- Docker Compose can run API, worker, Redis, Postgres, and MinIO.
- Production-like storage URLs work.
- Common asset attack cases are rejected by tests.

### Phase 04: Advanced Rendering

Objective: expand creative ceiling and performance options without changing the public API.

Deliverables:

- HyperFrames renderer for HTML/CSS/GSAP templates.
- Native FFmpeg renderer for simple timelines.
- GIF and WebM output support.
- Captions/subtitles.
- Poster customization.
- Additional transitions.
- Render presets for TikTok, Reels, Shorts, YouTube, square ads.
- Optional low-resolution preview mode.

Exit criteria:

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

## Key Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Absolute timeline to Editly sequential clip conversion becomes complex. | Keep MVP schema constrained and build segment compiler tests first. |
| Remote asset fetching creates SSRF exposure. | Enforce strict URL validation, network blocking, timeouts, size limits, MIME checks, and redirect checks from MVP. |
| Editly subprocess failures are hard to debug. | Save compiled spec, full stderr, normalized error code, and replay metadata for every render. |
| Fonts render differently across machines. | Bundle known fonts and use explicit font paths. |
| Long renders block API resources. | Queue all renders; local synchronous mode only exists behind the same service boundary for early development. |
| Renderer lock-in. | Keep public schema VidAPI-owned and renderer artifacts generated. |
| Native FFmpeg path becomes a second incompatible product. | Add it only behind the same renderer protocol and only for tested subsets of the schema. |

## Resolved Architecture Questions

| Question | Decision |
| --- | --- |
| Singular or plural render endpoints? | Use plural `/v1/renders`. |
| Explicit dimensions or presets? | Support both; explicit `width`/`height` win over presets. |
| Render IDs? | Use sortable public IDs with `render_` prefix, preferably ULID-style. |
| Queue library? | Use ARQ with Redis for MVP. |
| First renderer? | Editly subprocess bridge. |
| Text rendering? | Use deterministic Pillow-rendered PNG overlays for MVP; map to Editly text layers only where parity is acceptable. |
| HTML support? | Defer to HyperFrames renderer. |
| Worker isolation? | Docker container isolation is acceptable for MVP; add stricter cgroup/namespace controls if running untrusted workloads at scale. |
| Unsupported renderer features? | Reject with clear validation errors or require explicit renderer-specific extension fields later. |

## Replacement Checklist

This document fully carries forward the important content from the two older plans:

- API contract and endpoint naming.
- Internal JSON composition schema.
- Render lifecycle and worker pipeline.
- Editly-first MVP renderer plan.
- Native FFmpeg renderer strategy from the original architecture plan.
- HyperFrames future renderer path.
- Template system.
- Asset security requirements.
- Storage, database, and queue choices.
- Deployment shape.
- Testing strategy.
- Implementation phases and first demo target.

After this file is reviewed, `docs/architecture.md` and `docs/vidapi-architecture-plan.md` can be deleted without losing architectural direction.
