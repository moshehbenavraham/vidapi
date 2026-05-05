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
  |   |   |   |-- Transition Compiler (fade and crossfade boundaries)
  |   |   |   |-- FFmpeg (invoked by Editly)
  |   |   |
  |   |   |-- Audio Mixer (FFmpeg post-process for detached audio)
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

### Segment Compiler
- **Purpose**: Converts absolute-time timeline clips into sequential Editly clips with layers
- **Tech**: Pure functions -- collect boundaries, generate segments, map layers
- **Location**: `app/renderers/editly.py` (functions: `collect_boundaries`, `generate_segments`)

### Position Resolver
- **Purpose**: Resolves named and coordinate-based positions into normalized renderer coordinates
- **Tech**: Pure helpers with pixel offsets and clamping
- **Location**: `app/renderers/position.py`

### Transition Compiler
- **Purpose**: Emits Editly-compatible fade and crossfade transitions at segment boundaries
- **Tech**: Renderer-facing transition mapping with composition validation
- **Location**: `app/renderers/editly.py`

### Audio Mixer
- **Purpose**: Post-processes rendered video to mix detached audio clips with correct timing
- **Tech**: FFmpeg complex filter graph (-c:v copy), two-pass architecture
- **Location**: `app/services/audio_mixer.py`

### Poster Generator
- **Purpose**: Extracts a frame from rendered video as a JPEG poster
- **Tech**: FFmpeg subprocess
- **Location**: `app/renderers/poster.py`

### Webhook Service
- **Purpose**: Delivers terminal-state callbacks with HMAC signatures and retry tracking
- **Tech**: httpx client, HMAC-SHA256 payload signing, retry schedule persistence
- **Location**: `app/services/webhook_service.py`

### Storage Adapter
- **Purpose**: Persists render artifacts to a deterministic directory structure
- **Tech**: Protocol-based (local filesystem for dev, S3-compatible planned for production)
- **Location**: `app/storage/`

### Database
- **Purpose**: Render job metadata persistence
- **Tech**: SQLModel + aiosqlite (dev), Alembic migrations
- **Location**: `app/db/`

## Tech Stack Rationale

| Technology | Purpose | Why Chosen |
|------------|---------|------------|
| FastAPI | Web framework | Async-native, Pydantic integration, auto OpenAPI docs |
| Pydantic v2 | Schema validation | Discriminated unions for asset types, fast validation |
| ARQ + Redis | Job queue | Async-native, lightweight, fits FastAPI model |
| SQLModel + aiosqlite | Database | Async SQLite for dev, same API for future PostgreSQL |
| Alembic | Migrations | Standard Python migration tool, async-compatible |
| structlog | Logging | Structured JSON logs with context binding |
| httpx | HTTP client | Async, manual redirect control for SSRF validation |
| Pillow | Text rendering | Deterministic text-to-PNG with bundled fonts |
| Editly (Node.js) | Video rendering | Declarative timeline editing, reduces custom FFmpeg work |
| FFmpeg | Video encoding | Poster extraction, audio mixing, media probing |
| hatchling | Build backend | Modern, lightweight, explicit package discovery |

## Data Layer

- **Database**: SQLite (development), PostgreSQL planned for production
- **Migration Tool**: Alembic, migrations in `alembic/versions/`, sequential numbering
- **Storage**: Local filesystem under `data/renders/<render_id>/`

## Data Flow

### Async Mode (default with Docker Compose)

1. Client POSTs JSON composition to `/v1/renders`
2. Pydantic validates the composition schema
3. Render record created in SQLite with status `queued`
4. Input JSON persisted to workspace; job enqueued to Redis via ARQ
5. API returns 202 Accepted with render ID immediately
6. Worker picks up job, creates isolated workspace
7. Worker drives pipeline: fetching -> compiling -> rendering -> uploading
8. Assets resolved: remote fetched via httpx, text rendered to PNG, all cached by SHA-256
9. Template-backed renders expand merge variables before compile and persist `expanded.json`
10. Segment compiler converts absolute-time timeline to sequential Editly clips
11. Position resolver and transition compiler normalize renderer-facing layout details
12. Compiled Editly JSON + replay metadata written to workspace
13. Editly invoked as Node subprocess with timeout; progress parsed from FFmpeg stderr
14. Detached audio clips mixed via FFmpeg post-processing when needed
15. Poster extracted from output via FFmpeg
16. Artifacts persisted to storage
17. Render status updated to `succeeded` or `failed`
18. Webhook delivery is queued for terminal states when configured
19. Client polls GET `/v1/renders/{id}` for status, progress, and download URL

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
| Base-36 render IDs | No ULID dependency | Minimal dependencies for MVP; proper ULID in Phase 03 |
| Non-fatal poster generation | Warning on failure | Missing poster should not fail a successful render |
| Manual redirect following | Per-hop SSRF check | Prevents redirect-to-private-IP attacks |
| Track 0 on bottom | Natural z-order | Matches Editly layer ordering |
| ARQ over Celery | Lightweight async queue | Fits FastAPI async model, simpler than Celery |
| Worker drives status transitions | Stateless service methods | Required for progress tracking and cancellation |
| Cooperative cancellation via DB flag | Not ARQ abort | Renderer-agnostic, easier to test |
| Two-pass audio mixing | FFmpeg post-process | Editly audioTracks lacks per-track timing; -c:v copy avoids re-encoding |
| Workspace isolation per job | Separate WorkspaceManager | Single responsibility, concurrent safety |
| Xvfb in worker container | Virtual framebuffer | Editly's gl module needs an OpenGL context |
| Template renders pin version at submission | Stored active version pointer | Reproducible template renders and stable audit trail |
| Webhooks are delivered asynchronously | Non-blocking render completion | Render success must not depend on callback success |

See [.spec_system/PRD/PRD.md](.spec_system/PRD/PRD.md) for full architecture decisions.
