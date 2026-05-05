# Session Specification

**Session ID**: `phase03-session04-limits-resource-controls-and-asset-security-hardening`
**Phase**: 03 - Production Hardening
**Status**: Completed
**Created**: 2026-05-05

---

## 1. Session Overview

This session adds production-grade admission control and resource guardrails to VidAPI. Sessions 01-03 established PostgreSQL migrations, S3-compatible storage, and API key authentication; the next production risk is that an authenticated caller can still submit compositions, assets, or render jobs that consume unbounded CPU, disk, memory, queue capacity, or subprocess runtime.

The work centralizes limit settings, validates composition shape and output targets before work is queued, rejects oversized request bodies early, and checks queue capacity with clear 413, 422, and 429 responses. It also tightens media validation after ffprobe, makes subprocess timeout behavior explicit across Editly and FFmpeg paths, and adds periodic orphan workspace cleanup so crashed workers do not accumulate stale scratch data.

The session preserves the existing renderer-independent schema and thin-router pattern. Limit calculation stays in pure services, API routes only perform boundary enforcement, and worker-level cleanup remains isolated in `WorkspaceManager` so sync mode, async mode, local storage, and S3 storage keep the same public API behavior.

---

## 2. Objectives

1. Add centralized request, composition, asset, queue, workspace, Redis, and subprocess limit settings with production validation.
2. Reject oversized requests and over-limit compositions before render input is persisted or queued.
3. Enforce asset media duration, resolution, stream-count, MIME, redirect, and size controls in the worker path.
4. Harden renderer and FFmpeg subprocess timeouts, and clean orphaned workspaces without deleting active jobs.

---

## 3. Prerequisites

### Required Sessions
- [x] `phase03-session01-postgresql-persistence-and-alembic-migrations` - Provides durable render metadata and production settings validation patterns.
- [x] `phase03-session02-s3-compatible-storage-and-download-modes` - Provides artifact storage adapters that limit failures must preserve.
- [x] `phase03-session03-api-key-authentication-and-access-control` - Ensures non-health routes are already protected before adding resource admission.
- [x] `phase01-session02-worker-render-pipeline` - Provides async worker stage boundaries and cancellation checkpoints.
- [x] `phase02-session05-audio-polish-and-hardening` - Provides current audio subprocess and rate-limit behavior to preserve.

### Required Tools/Knowledge
- FastAPI middleware and request body handling.
- Pydantic settings validators and test-time settings cache isolation.
- ARQ/Redis queue access patterns and 429 response semantics.
- Existing composition model, ffprobe media metadata, renderer subprocess handling, and workspace lifecycle tests.

### Environment Requirements
- Python 3.11+ environment with project dependencies installed through `uv`.
- SQLite-backed tests remain sufficient for limit, route, and worker cleanup coverage.
- Redis, S3, Node, Editly, and FFmpeg should be mocked in unit and integration tests except for existing lightweight local subprocess tests.

---

## 4. Scope

### In Scope (MVP)
- Operator can configure request body, render duration, output resolution, fps, track, clip, asset, media stream, queue depth, workspace age, and workspace disk limits - add bounded settings and production guardrails.
- Client can submit render and template requests only within configured limits - validate direct render requests, template creation/update compositions, and expanded template render compositions before enqueue.
- Client receives clear 413, 422, or 429 responses for request size, composition limit, asset limit, and queue admission failures - map errors at API boundaries without leaking internals.
- Worker can reject media assets whose ffprobe metadata exceeds duration, resolution, or stream-count limits - keep SSRF, redirect, MIME, timeout, and size checks active.
- Renderer, audio, poster, and ffprobe subprocesses cannot run beyond configured timeouts - terminate with bounded grace handling and normalized failure details.
- Worker can remove orphaned workspaces older than a configured TTL without deleting active render workspaces - run cleanup at startup and expose a reusable cleanup method.
- Operator has Redis AUTH and TLS expectations documented and production settings validated where possible.
- Tests cover rejected over-limit compositions, blocked asset cases, request body limits, queue admission, subprocess timeout paths, and orphan cleanup.

### Out of Scope (Deferred)
- Full cgroup, namespace, or container-level isolation - Reason: portable app-level guardrails satisfy the Phase 03 MVP.
- Distributed scheduler admission control across many API instances - Reason: single Redis queue depth checks are adequate for the current one-node deployment model.
- WAF, network perimeter controls, or cloud firewall rules - Reason: deployment perimeter belongs to infrastructure outside the VidAPI app.
- Per-user quotas or billing-driven limits - Reason: the PRD excludes SaaS tenancy and user account management.

---

## 5. Technical Approach

### Architecture

Add limit configuration to `Settings` with explicit lower and upper bounds. New settings should include request body caps, template body caps, max assets per render, max media streams per asset, queue depth threshold, workspace orphan TTL, optional workspace byte budget, subprocess kill grace period, and production Redis security expectations. Production validators should fail closed for obviously unsafe Redis settings when async mode is enabled.

Create a small request-size middleware in `app/core/request_limits.py` that rejects requests with oversized `Content-Length` headers before route validation, and guards streamed bodies when the header is absent. Register it in `app/main.py` before CORS route handling so JSON parsing work is avoided for known oversized bodies.

Create `app/services/limits.py` for pure limit calculations. It should walk `Composition` objects, count tracks, clips, assets, total timeline duration, output width/height/fps, and media metadata from `MediaInfo`. It should raise a domain error with stable code, human-readable message, violated field, configured limit, and observed value. API routes convert these errors to documented HTTP responses.

Create `app/services/queue_admission.py` to check async queue depth before enqueueing. The helper should skip checks in sync mode, use bounded Redis calls, and map queue saturation to 429 with `Retry-After` where a retry window is available. The same helper should be used by direct render and template render paths.

Extend `AssetService` so ffprobe metadata is not merely advisory. After a remote or file asset is probed, apply duration, resolution, and stream-count limits using the same limit service. Existing SSRF validation, manual redirect following, MIME allowlist, zero-byte, and max-byte checks remain in place.

Harden subprocess paths by keeping explicit timeouts on Editly, audio mix, poster generation, and ffprobe, ensuring timeout branches terminate and await child processes with a bounded grace period. Error logs should remain bounded and diagnostic enough for replay without buffering unbounded output.

Add orphan workspace cleanup to `WorkspaceManager`. The method should scan only under the configured workspace root, skip active render IDs loaded from the database, skip workspaces newer than the configured TTL, and optionally enforce a coarse disk budget by removing oldest stale workspaces first. Worker startup should invoke this once so crashed-worker residue is handled without a separate scheduler.

### Design Patterns
- Pure validator service: Keeps limit math deterministic and easy to test.
- Boundary enforcement: Reject unsafe requests at middleware, API, asset, and worker boundaries closest to the resource.
- Structured domain errors: Preserve consistent API responses and stable machine-readable error codes.
- Conservative cleanup: Only delete stale directories under the configured root and never delete active render IDs.
- Production settings guardrails: Fail startup for unsafe production combinations instead of relying on operator memory.

### Technology Stack
- Python 3.11+
- FastAPI 0.136.1 / Starlette 0.52.1
- Pydantic Settings
- ARQ 0.28.x / Redis
- pytest + pytest-asyncio + httpx ASGI transport
- ffprobe / FFmpeg / Editly subprocess paths already present in the project

---

## 6. Deliverables

### Files to Create
| File | Purpose | Est. Lines |
|------|---------|------------|
| `app/core/request_limits.py` | Request body size middleware and 413 response helper | ~120 |
| `app/services/limits.py` | Composition, output, asset count, and media metadata limit validators | ~220 |
| `app/services/queue_admission.py` | Redis/ARQ queue depth admission helper | ~100 |
| `tests/test_limits.py` | Unit tests for settings, composition limits, and media metadata limits | ~260 |
| `tests/test_request_limits.py` | ASGI middleware tests for content-length and streamed oversized bodies | ~170 |

### Files to Modify
| File | Changes | Est. Lines |
|------|---------|------------|
| `app/core/config.py` | Add limit settings, subprocess grace settings, and production Redis validation | ~90 |
| `app/main.py` | Register request size middleware in app creation | ~15 |
| `app/api/errors.py` | Add limit and request-size domain errors if needed by handlers | ~35 |
| `app/models/errors.py` | Document 413, 422 limit, and 429 queue saturation responses | ~30 |
| `app/models/error_codes.py` | Add stable codes for limit and request-size failures | ~20 |
| `app/api/routes_renders.py` | Enforce composition and queue limits before persist/enqueue | ~70 |
| `app/api/routes_templates.py` | Enforce template composition, expanded render, and queue limits | ~90 |
| `app/services/asset_service.py` | Apply media metadata limits after ffprobe and keep SSRF regressions covered | ~60 |
| `app/services/ffprobe.py` | Keep ffprobe timeout termination bounded and expose stream-count metadata clearly | ~25 |
| `app/renderers/editly.py` | Harden Editly timeout, cancellation, stderr bounds, and termination handling | ~60 |
| `app/services/audio_mixer.py` | Harden FFmpeg audio timeout and termination behavior | ~40 |
| `app/renderers/poster.py` | Use configured FFmpeg binary and bounded timeout termination | ~35 |
| `app/workers/workspace.py` | Add orphan cleanup with TTL, active-ID skip, and disk guardrails | ~110 |
| `app/workers/render_worker.py` | Run orphan cleanup on startup and preserve failure semantics | ~45 |
| `tests/test_api_hardening.py` | Add API limit and queue admission integration tests | ~220 |
| `tests/test_asset_security.py` | Add media metadata and redirect limit regression tests | ~140 |
| `tests/test_workspace.py` | Add orphan cleanup and active workspace preservation tests | ~180 |
| `tests/test_worker_pipeline.py` | Add startup cleanup invocation and timeout regression tests | ~90 |
| `README.md` | Document local limit settings and expected rejection behavior | ~50 |
| `docs/deployment.md` | Document production limit tuning, Redis AUTH, and Redis TLS expectations | ~90 |

---

## 7. Success Criteria

### Functional Requirements
- [ ] Oversized render and template request bodies are rejected before route handlers persist or enqueue work.
- [ ] Over-limit duration, resolution, fps, track count, clip count, and asset count return clear validation errors.
- [ ] Template creation/update and template render expansion cannot bypass composition limits.
- [ ] Async render and template render submissions are rejected with 429 when configured queue depth is exceeded.
- [ ] Remote asset redirects to blocked networks remain rejected, including redirect targets that resolve to blocked IPs.
- [ ] Media assets with excessive duration, resolution, or stream count are rejected after ffprobe.
- [ ] Editly, audio, poster, and ffprobe subprocess timeout paths terminate child processes and return normalized errors.
- [ ] Orphan workspace cleanup removes stale inactive workspaces without deleting active render workspaces.
- [ ] Production Redis AUTH and TLS expectations are validated or explicitly documented where validation is not portable.

### Testing Requirements
- [ ] Unit tests written and passing for settings validators, composition limit math, and media metadata limit checks.
- [ ] Integration tests written and passing for request body limits, render/template composition limits, and queue admission responses.
- [ ] Regression tests written and passing for SSRF redirects, media metadata limits, subprocess timeout handling, and orphan cleanup.
- [ ] Manual testing completed for one over-limit direct render request and one stale workspace cleanup run.

### Non-Functional Requirements
- [ ] Non-render API endpoints remain within the PRD target of under 200 ms p95 under normal single-node load.
- [ ] Limit validation is deterministic and does not perform network, database, or subprocess work.
- [ ] Queue admission uses bounded Redis operations and fails closed when configured to enforce capacity.
- [ ] Cleanup only deletes directories under the configured workspace root.

### Quality Gates
- [ ] All files ASCII-encoded.
- [ ] Unix LF line endings.
- [ ] Code follows project conventions.

---

## 8. Implementation Notes

### Key Considerations
- Apply composition limits before writing input artifacts so rejected jobs do not leave durable partial state.
- Validate both stored template compositions and expanded template render compositions; expansion can inflate text, callbacks, or nested content.
- Keep the limit service framework-independent. It should accept `Composition`, `Settings`, and `MediaInfo`, then return or raise structured results.
- Prefer one stable error shape for all limit failures. Clients should be able to distinguish request size, composition limit, media limit, and queue limit failures by code.
- Redis production validation can verify URI scheme and credentials in settings, but certificate details may need documentation rather than strict runtime checks.
- Orphan cleanup must never follow symlinks outside the workspace root.

### Potential Challenges
- FastAPI body parsing may happen before route code sees oversized requests: add middleware instead of relying only on route validation.
- Queue depth inspection can vary by ARQ internals: isolate Redis access in one helper and keep tests mock-based.
- Template render expansion can fail before limits run: preserve existing template error mapping and only limit-check after a valid expanded composition exists.
- Subprocess timeout code is duplicated today: use consistent termination behavior without broad refactors that would exceed session scope.
- Workspace cleanup can be destructive if path checks are loose: resolve paths, require subpath containment, and skip active IDs.

### Relevant Considerations
- [P00] **FFmpeg subprocess resource limits**: This session adds practical timeout and output guardrails for Editly, ffprobe, poster, and audio FFmpeg paths.
- [P01] **TTL-based workspace cleanup**: This session adds an orphan workspace scan for crashed workers.
- [P00] **FFmpeg filter graph complexity**: Track, clip, duration, resolution, and fps limits reduce non-linear runtime blowups.
- [P00] **Manual redirect following for SSRF**: Keep per-hop redirect validation and add regression coverage while extending asset limits.
- [P01] **Redis connection TLS not enforced**: Production validation and docs must make `rediss://` expectations explicit.
- [P01] **Redis AUTH not configured**: Production Redis guidance must require credentials.
- [P01] **Settings singleton mutation in tests**: Tests must reset settings and dependency caches around limit-specific overrides.

### Behavioral Quality Focus
Checklist active: Yes
Top behavioral risks for this session:
- Limit enforcement is applied to direct renders but bypassed through templates or async worker replay.
- Queue and request-size failures return inconsistent response shapes or persist partial render records.
- Orphan cleanup deletes an active workspace or follows an unsafe path outside the workspace root.
- Timeout branches kill the immediate subprocess but leave unread output, zombie processes, or misleading error codes.

---

## 9. Testing Strategy

### Unit Tests
- Test `Settings` accepts sane local limits and rejects invalid or unsafe production Redis combinations.
- Test composition validators reject over-limit duration, output width/height, fps, tracks, clips, and asset counts.
- Test media validators reject excessive duration, dimensions, and stream counts from `MediaInfo`.
- Test request-size middleware returns 413 for oversized `Content-Length` and streamed bodies without consuming route logic.

### Integration Tests
- Test `POST /v1/renders` rejects over-limit compositions before creating a render record.
- Test `POST /v1/templates`, `PUT /v1/templates/{id}`, and `POST /v1/templates/{id}/renders` enforce limits.
- Test async render and template render paths return 429 when queue depth is configured as saturated.
- Test OpenAPI documents 413, 422, and 429 responses for affected endpoints.

### Manual Testing
- Start the app in local sync mode with very small limits and verify an oversized composition returns a structured 422.
- Create a stale workspace directory under `data/renders`, run worker startup cleanup, and verify stale inactive data is removed while active IDs are preserved.

### Edge Cases
- Missing `Content-Length` with streamed request bodies.
- Exact-boundary values for duration, resolution, fps, tracks, clips, assets, and queue depth.
- Template composition within limits before expansion but over limits after merge.
- Remote redirect chains that end on private, loopback, link-local, metadata, or credential-bearing URLs.
- Workspace names with path traversal characters, symlinks, files instead of directories, and new workspaces below TTL.
- Subprocess timeout after partial stderr output and cancellation immediately after timeout.

---

## 10. Dependencies

### External Libraries
- No new runtime dependencies required.
- Existing FastAPI, Pydantic, ARQ/Redis, httpx, and pytest tooling are sufficient.

### Other Sessions
- **Depends on**: `phase03-session01-postgresql-persistence-and-alembic-migrations`, `phase03-session02-s3-compatible-storage-and-download-modes`, `phase03-session03-api-key-authentication-and-access-control`
- **Depended by**: `phase03-session05-operational-visibility-and-production-stack`

---

## Next Steps

Run the implement workflow step to begin AI-led implementation.
