# Architecture

## System Overview

VidAPI is a self-hosted FastAPI service that accepts JSON timeline compositions
and renders video through pluggable renderer backends. The current stack uses
Editly (a Node.js tool backed by FFmpeg) as the default renderer, invoked as a
subprocess from an async Python pipeline. Templates, webhook delivery, and
renderer-independent positioning and transitions all sit on top of the same
public composition schema.

## Dependency Graph

```
Client
  |
  | POST /v1/renders (JSON composition)
  v
FastAPI API (validate, create record, enqueue)
  |-- Renderer Capability Registry (select + validate renderer support)
  |
  v
Redis (ARQ job queue)
  |
  v
Render Worker (ARQ consumer)
  |-- Workspace Manager (isolated per-job directories)
  |-- Log Collector (structured render logs)
  |-- Cancellation Checkpoints (cooperative cancel via DB flag)
  |
  |-- Render Service (stage methods)
  |   |-- Renderer Capability Registry (fail-closed replay validation)
  |   |-- Merge Service (variable substitution)
  |   |-- Template Service (CRUD, version pinning, template renders)
  |   |-- Asset Service (fetch, validate, cache)
  |   |   |-- SSRF Validator
  |   |   |-- ffprobe (media validation)
  |   |   |-- Text Renderer (Pillow PNG)
  |   |
  |   |-- Renderer (compile + render)
  |   |   |-- Editly Renderer (Node subprocess)
  |   |   |   |-- Segment Compiler (timeline -> sequential clips)
  |   |   |   |-- Position Resolver (named positions + offsets)
  |   |   |   |-- Transition Planner (schema values -> validated renderer boundaries)
  |   |   |   |-- FFmpeg (invoked by Editly)
  |   |   |-- Native FFmpeg Renderer (bounded FFmpeg filter graph)
  |   |   |   |-- Native Subset Validator
  |   |   |   |-- Timeline Helper (duration + visual ordering)
  |   |   |   |-- FFmpeg (direct subprocess)
  |   |   |
  |   |   |-- Audio Mixer (FFmpeg post-process for detached audio)
  |   |   |-- Caption Finisher (sidecars + FFmpeg burn-in)
  |   |   |-- Output Postprocessor (FFmpeg WebM, GIF, PNG sequence finishing)
  |   |   |-- Poster Generator (FFmpeg frame extraction)
  |   |   |-- Webhook Service (HMAC-signed callbacks + retries)
  |   |-- Storage Adapter (persist artifacts)
  v
SQLite Database (render metadata)
Local Filesystem (render artifacts)
```

## Components

### FastAPI API
- **Purpose**: HTTP layer -- validates requests, enqueues jobs, returns status
- **Tech**: FastAPI, Pydantic v2, structlog
- **Location**: `app/api/`

### Composition Models
- **Purpose**: Pydantic v2 schemas for the public JSON composition format
- **Tech**: Pydantic v2 discriminated unions for asset types
- **Location**: `app/models/composition.py`

### Redis + ARQ Queue
- **Purpose**: Async job queue decoupling API from render processing
- **Tech**: ARQ (async Redis queue), redis[hiredis]
- **Location**: `app/core/redis.py` (pool), `app/workers/arq_settings.py` (config)

### Render Worker
- **Purpose**: ARQ consumer that drives the render pipeline stage-by-stage
- **Tech**: ARQ worker process, cooperative cancellation, progress callbacks
- **Location**: `app/workers/render_worker.py`

### Workspace Manager
- **Purpose**: Creates isolated per-job directories; handles cleanup on success/failure
- **Tech**: Filesystem operations with configurable cleanup policy
- **Location**: `app/workers/workspace.py`

### Log Collector
- **Purpose**: Buffers structured per-render log entries; flushes atomically to logs.txt
- **Tech**: In-memory buffer with single atomic write
- **Location**: `app/workers/log_collector.py`

### Render Service
- **Purpose**: Stateless stage methods (validate, resolve, compile, render, store)
- **Tech**: Python async, structlog context binding
- **Location**: `app/services/render_service.py`

### Template Service
- **Purpose**: Manages reusable templates, immutable versions, and template-backed render submission
- **Tech**: CRUD layer with version pinning and template expansion
- **Location**: `app/services/template_service.py`

### Asset Service
- **Purpose**: Resolves remote/local/text assets with SSRF protection, MIME validation, and caching
- **Tech**: httpx (async), Pillow (text rendering), ffprobe (media validation)
- **Location**: `app/services/asset_service.py`

### Editly Renderer
- **Purpose**: Compiles VidAPI compositions to Editly JSON and invokes Editly as a Node subprocess
- **Tech**: Segment compiler (pure functions), asyncio subprocess, streaming stderr with progress/cancel callbacks
- **Location**: `app/renderers/editly.py`

### Native FFmpeg Renderer
- **Purpose**: Compiles a constrained simple timeline subset directly to FFmpeg command and filter graph artifacts
- **Tech**: Native subset validator, deterministic plan objects, asyncio subprocess, streaming stderr with progress/cancel callbacks
- **Location**: `app/renderers/native_ffmpeg.py`, `app/renderers/native_ffmpeg_subset.py`
- **Current support**: explicit `ffmpeg-native` requests for color, image, video, text PNG, soundtrack, and detached audio timelines without transitions, captions, poster controls, transforms, or client-supplied filters

### Renderer Capability Registry
- **Purpose**: Selects the effective renderer and validates renderer-feature compatibility before queue admission, worker compile, or sync-service compile
- **Tech**: Immutable support declarations, stable capability exceptions, redacted error context
- **Location**: `app/renderers/capabilities.py`
- **Current support**: omitted, `auto`, and `editly` select Editly; explicit `ffmpeg-native` selects the native FFmpeg subset; `hyperframes` is known but unavailable

### Segment Compiler
- **Purpose**: Converts absolute-time timeline clips into sequential Editly clips with layers
- **Tech**: Pure functions -- collect boundaries, generate segments, map layers
- **Location**: `app/renderers/editly.py` (functions: `collect_boundaries`, `generate_segments`)

### Position Resolver
- **Purpose**: Resolves named and coordinate-based positions into normalized renderer coordinates
- **Tech**: Pure helpers with pixel offsets and clamping
- **Location**: `app/renderers/position.py`

### Transition Compiler
- **Purpose**: Validates public transition semantics and emits Editly-compatible transitions at segment boundaries
- **Tech**: Pure planner, renderer-facing mapping, shared limit validation, bounded errors
- **Location**: `app/renderers/transitions.py`, `app/renderers/editly.py`

### Audio Mixer
- **Purpose**: Post-processes rendered video to mix detached audio clips with correct timing
- **Tech**: FFmpeg complex filter graph (-c:v copy), two-pass architecture
- **Location**: `app/services/audio_mixer.py`

### Output Postprocessor
- **Purpose**: Converts the Editly MP4 intermediate into requested WebM, GIF, or PNG sequence outputs and writes output metadata
- **Tech**: FFmpeg subprocess with explicit timeout, bounded stderr logs, deterministic PNG manifests, and zip archives
- **Location**: `app/services/output_postprocess.py`, `app/services/output_formats.py`

### Caption Finisher
- **Purpose**: Writes caption sidecars or burns generated ASS captions into the MP4 intermediate before output conversion
- **Tech**: Pure SRT/WebVTT/ASS format helpers plus FFmpeg subprocess with timeout and bounded stderr
- **Location**: `app/services/caption_formats.py`, `app/services/caption_finishing.py`

### Poster Generator
- **Purpose**: Extracts a request-selected frame from rendered video as a JPEG poster
- **Tech**: FFmpeg subprocess with default, timestamp, percent, and disabled modes
- **Location**: `app/renderers/poster.py`

### Webhook Service
- **Purpose**: Delivers terminal-state callbacks with HMAC signatures and retry tracking
- **Tech**: httpx client, HMAC-SHA256 payload signing, retry schedule persistence
- **Location**: `app/services/webhook_service.py`

### Storage Adapter
- **Purpose**: Persists render artifacts to a deterministic directory structure
- **Tech**: Protocol-based (local filesystem for dev, S3-compatible for production)
- **Location**: `app/storage/`

### Database
- **Purpose**: Render job metadata persistence
- **Tech**: SQLModel + aiosqlite/asyncpg, Alembic migrations
- **Location**: `app/db/`

## Tech Stack Rationale

| Technology | Purpose | Why Chosen |
|------------|---------|------------|
| FastAPI | Web framework | Async-native, Pydantic integration, auto OpenAPI docs |
| Pydantic v2 | Schema validation | Discriminated unions for asset types, fast validation |
| ARQ + Redis | Job queue | Async-native, lightweight, fits FastAPI model |
| SQLModel + aiosqlite/asyncpg | Database | Async SQLite for dev, PostgreSQL for production |
| Alembic | Migrations | Standard Python migration tool, async-compatible |
| structlog | Logging | Structured JSON logs with context binding |
| httpx | HTTP client | Async, manual redirect control for SSRF validation |
| Pillow | Text rendering | Deterministic text-to-PNG with bundled fonts |
| Editly (Node.js) | Video rendering | Declarative timeline editing, reduces custom FFmpeg work |
| FFmpeg | Video encoding | Poster extraction, audio mixing, media probing |
| hatchling | Build backend | Modern, lightweight, explicit package discovery |

## Data Layer

- **Database**: SQLite (development), PostgreSQL (production)
- **Migration Tool**: Alembic, migrations in `alembic/versions/`, sequential numbering
- **Storage**: Local filesystem under `data/renders/<render_id>/`

## Data Flow

### Async Mode (default with Docker Compose)

1. Client POSTs JSON composition to `/v1/renders`
2. Pydantic validates the composition schema
3. Renderer capability validation selects `editly` for omitted, `auto`, or explicit `editly` requests
4. Shared composition limits validate duration, output, captions, posters, and transition semantics
5. Render record created in SQLite with status `queued` and selected renderer metadata
6. Input JSON persisted to workspace; job enqueued to Redis via ARQ
7. API returns 202 Accepted with render ID immediately
8. Worker picks up job and revalidates stored renderer capabilities before workspace creation
9. Worker creates isolated workspace and drives pipeline: fetching -> compiling -> rendering -> uploading
10. Assets resolved: remote fetched via httpx, text rendered to PNG, all cached by SHA-256
11. Template-backed renders expand merge variables before compile and persist `expanded.json`
12. Render service revalidates renderer capabilities and transition semantics before compilation as a replay defense
13. Selected renderer compiles absolute-time timeline data into renderer-specific artifacts
14. Editly uses the segment compiler, position resolver, and transition planner; native FFmpeg uses native subset validation, timeline ordering, and deterministic FFmpeg filters
15. Compiled renderer JSON + replay metadata written to workspace
16. Renderer subprocess invoked with timeout; progress parsed from FFmpeg stderr
17. Detached audio clips mixed via FFmpeg post-processing when needed
18. Caption finisher writes sidecars or burns captions into the MP4 intermediate when requested
19. Output postprocessor keeps MP4 or converts the selected intermediate to WebM, GIF, or a PNG sequence zip and manifest
20. Poster extraction uses request-level default, timestamp, percent, or disabled behavior
21. Artifacts and caption, output, and poster metadata persist to storage and database
22. Render status updated to `succeeded` or `failed`
23. Webhook delivery is queued for terminal states when configured
24. Client polls GET `/v1/renders/{id}` for status, progress, artifact metadata, and download URLs

### Cancellation Flow

1. Client sends DELETE `/v1/renders/{id}`
2. Queued jobs: immediate transition to `cancelled`
3. Running jobs: `cancel_requested_at` flag set in DB
4. Worker checks flag between stages and during stderr streaming
5. On detection: subprocess terminated (SIGTERM, then SIGKILL), status set to `cancelled`

### Template Render Flow

1. Client creates or updates a template through `/v1/templates`
2. Client submits merge data to `/v1/templates/{id}/renders`
3. Service pins the active template version before render creation
4. Merge variables are expanded against the stored template composition
5. Render job stores both template references and the expanded composition
6. Worker runs the standard render pipeline with the expanded input

### Webhook Flow

1. Render reaches a terminal state and an event payload is built
2. Payload is signed with HMAC-SHA256 when `WEBHOOK_SECRET` is configured
3. Each delivery attempt is stored in `webhook_attempts`
4. Failed deliveries retry on the configured schedule
5. Delivery stops after the retry budget is exhausted

### Sync Mode (local development without Redis)

Same pipeline stages run synchronously within the API request when `RENDER_MODE=sync`.

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Editly over raw FFmpeg | Editly subprocess | Reduces custom filter graph code for MVP |
| Segment compiler as pure functions | No class state | Easier to test, clearer data flow |
| Base-36 render IDs | No ULID dependency | Minimal dependencies while keeping sortable public IDs |
| Non-fatal poster generation | Warning on failure | Missing poster should not fail a successful render |
| Manual redirect following | Per-hop SSRF check | Prevents redirect-to-private-IP attacks |
| Track 0 on bottom | Natural z-order | Matches Editly layer ordering |
| ARQ over Celery | Lightweight async queue | Fits FastAPI async model, simpler than Celery |
| Worker drives status transitions | Stateless service methods | Required for progress tracking and cancellation |
| Cooperative cancellation via DB flag | Not ARQ abort | Renderer-agnostic, easier to test |
| Two-pass audio mixing | FFmpeg post-process | Editly audioTracks lacks per-track timing; -c:v copy avoids re-encoding |
| MP4 intermediate for non-MP4 outputs | FFmpeg finishing step | Keeps Editly as the default renderer while enabling WebM, GIF, and PNG sequence artifacts |
| Caption finishing before output conversion | Shared intermediate step | Burned captions propagate to all requested output formats without renderer-specific public schemas |
| Public transition allowlist | Explicit enum values | Keeps Editly transition names and params behind the compiler boundary |
| Workspace isolation per job | Separate WorkspaceManager | Single responsibility, concurrent safety |
| Xvfb in worker container | Virtual framebuffer | Editly's gl module needs an OpenGL context |
| Template renders pin version at submission | Stored active version pointer | Reproducible template renders and stable audit trail |
| Webhooks are delivered asynchronously | Non-blocking render completion | Render success must not depend on callback success |

See [.spec_system/PRD/PRD.md](.spec_system/PRD/PRD.md) for full architecture decisions.
