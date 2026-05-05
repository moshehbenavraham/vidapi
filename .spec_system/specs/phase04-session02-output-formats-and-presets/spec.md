# Session Specification

**Session ID**: `phase04-session02-output-formats-and-presets`
**Phase**: 04 - Advanced Rendering
**Status**: Completed
**Created**: 2026-05-05

---

## 1. Session Overview

This session expands VidAPI output handling beyond the current MP4-only Editly path. Session 01 made renderer capabilities explicit and currently rejects GIF, WebM, and PNG sequence requests. This session updates that boundary, adds named output presets, and routes requested output formats through the existing renderer, storage, download, and webhook paths.

The implementation keeps Editly as the default renderer and uses it to produce a deterministic MP4 intermediate. Format-specific finishing then converts that intermediate to WebM, GIF, or a PNG sequence with FFmpeg. All produced artifacts must still move through the centralized storage and URL resolver paths established in Phase 03.

The session also records enough output metadata for status responses, downloads, and webhook payloads to describe the artifact without duplicating URL logic. It does not add batch multi-output renders, native FFmpeg renderer parity, HyperFrames output generation, UI changes, or client SDK changes.

---

## 2. Objectives

1. Add stable named output presets for TikTok, Reels, Shorts, YouTube, square ads, and low-resolution previews while preserving explicit width and height precedence.
2. Enable MP4, WebM, GIF, and PNG sequence output requests through capability validation with clear format, duration, fps, and resolution guardrails.
3. Implement deterministic output artifact publishing for single-file and PNG sequence outputs through existing local and S3-compatible storage paths.
4. Include output metadata in render status and webhook payloads while keeping download URLs centralized in `StorageUrlResolver`.

---

## 3. Prerequisites

### Required Sessions
- [x] `phase04-session01-renderer-capability-registry` - Provides renderer selection and unsupported-feature validation.
- [x] `phase03-session01-postgresql-persistence-and-alembic-migrations` - Provides migration-managed schema updates.
- [x] `phase03-session02-s3-compatible-storage-and-download-modes` - Provides centralized artifact URL resolution for local, proxy, signed, and public modes.
- [x] `phase03-session04-limits-resource-controls-and-asset-security-hardening` - Provides duration, fps, resolution, asset, queue, and subprocess guardrails.
- [x] `phase03-session05-operational-visibility-and-production-stack` - Provides redacted logs, metrics, and webhook-safe operational behavior.

### Required Tools/Knowledge
- Pydantic v2 validators and frozen models in `app/models/composition.py`.
- Renderer capability validation in `app/renderers/capabilities.py`.
- Editly compile and render behavior in `app/renderers/editly.py`.
- FFmpeg subprocess conventions from poster, audio, and worker paths.
- SQLModel and Alembic migration conventions.
- Existing storage, download, webhook, worker, and API test fixtures.

### Environment Requirements
- Python 3.11+ dependencies installed with `uv`.
- FFmpeg available for post-processing tests that are not mocked.
- Existing render, storage, webhook, worker, and migration tests runnable before implementation.
- No seed fixtures currently exist; schema changes still need migration and integration coverage.

---

## 4. Scope

### In Scope (MVP)
- Client can set `output.preset` to `tiktok`, `reels`, `shorts`, `youtube`, `square-ad`, or `preview-low` - normalize dimensions, aspect ratio, fps, and quality defaults before rendering.
- Client can specify explicit `output.width` and `output.height` alongside a preset - explicit dimensions win consistently and preset defaults fill only missing fields.
- Client can request `mp4`, `webm`, `gif`, or `png-sequence` outputs - capability validation accepts supported formats after applying format-specific limits.
- System can reject unsupported format, preset, duration, fps, and resolution combinations with stable error envelopes and bounded context.
- Worker can use Editly to render an MP4 intermediate, then convert to WebM, GIF, or PNG sequence with FFmpeg and explicit timeout/failure handling.
- System can publish single-file outputs with deterministic suffix, media type, filename, and storage key behavior.
- System can publish PNG sequence outputs with deterministic frame names, a manifest, and a retrievable download artifact through the existing download endpoint.
- Render records can persist output format, media type, filename, frame count, and manifest path where applicable.
- Status responses and webhook payloads include output metadata while using `StorageUrlResolver` for public, signed, and proxied URLs.
- Tests cover presets, format validation, output artifact metadata, storage URL modes, webhook metadata, and limit failures.

### Out of Scope (Deferred)
- Native FFmpeg renderer parity - Reason: scheduled for Session 05 after shared output handling exists.
- HyperFrames output generation - Reason: scheduled for Session 06 after the adapter contract is ready.
- Multi-output batch rendering in one job - Reason: this session keeps one requested output per render.
- UI or client SDK changes - Reason: explicitly deferred by the session stub.
- Captions, subtitle burn-in, and poster customization - Reason: scheduled for Session 03.
- Broadcast or professional formats such as ProRes, DNxHD, and lossless masters - Reason: excluded from the master PRD MVP.

---

## 5. Technical Approach

### Architecture

Add output preset normalization at the schema boundary so downstream services see concrete width, height, fps, and quality values. The normalized `Output` model should retain the requested preset value for metadata, but explicit dimensions must always override preset dimensions. Preset defaults should be pure data, deterministic, and easy to test.

Extend renderer capabilities so Editly can support the public output formats through a post-processing path rather than by changing route handlers. The capability registry should still reject unavailable renderers and unsupported feature combinations, but it should no longer reject `webm`, `gif`, or `png-sequence` for Editly after this session.

Keep the render pipeline architecture as Editly compile -> Editly MP4 intermediate -> output finishing -> storage publish. Add a small output finishing service that maps requested format to target suffix, media type, deterministic filename, and FFmpeg command. WebM and GIF produce one final file. PNG sequence produces deterministic frame files plus a manifest and a retrievable download artifact, likely a zip, so the existing `/v1/renders/{id}/download` contract remains useful.

Persist output metadata on the render record through SQLModel and Alembic. The metadata should be safe for API responses and webhooks: format, media type, filename, frame count, and manifest URL/path when applicable. Do not store raw command stderr, raw composition JSON, presigned URLs, or secrets in metadata columns.

Update API responses and webhooks through shared metadata builders. `StorageUrlResolver` remains the single source for artifact URLs, so public, signed, and proxied deployments stay aligned. Download responses should use the persisted filename and media type instead of hard-coding MP4.

### Design Patterns
- Pure normalization table: Keep preset definitions as immutable data with direct unit coverage.
- Boundary validation: Apply format and preset constraints before queue admission and again in the worker.
- Centralized artifact metadata: Map format to suffix, media type, filename, and manifest behavior in one helper.
- Subprocess isolation: Run FFmpeg post-processing with timeout, bounded stderr, and explicit failure mapping.
- Migration-managed metadata: Add DB columns and Alembic migration together, with downgrade coverage.
- Redacted URL resolution: Build client-facing URLs through `StorageUrlResolver`, not webhook or route-specific logic.

### Technology Stack
- Python 3.11+
- FastAPI 0.136.1 / Starlette 0.52.1
- Pydantic 2.11.2
- SQLModel / SQLAlchemy async sessions
- Alembic
- FFmpeg subprocesses through `asyncio.create_subprocess_exec`
- Local filesystem and S3-compatible storage adapters
- pytest + pytest-asyncio, ruff, mypy

---

## 6. Deliverables

### Files to Create
| File | Purpose | Est. Lines |
|------|---------|------------|
| `app/models/output_artifacts.py` | Render output metadata models for API and webhook payloads | ~120 |
| `app/services/output_formats.py` | Preset, format, suffix, media type, filename, and manifest planning helpers | ~220 |
| `app/services/output_postprocess.py` | FFmpeg-based WebM, GIF, and PNG sequence finishing service | ~240 |
| `alembic/versions/006_add_render_output_metadata.py` | Migration for render output metadata columns | ~90 |
| `tests/test_output_formats.py` | Unit tests for presets, format planning, filenames, media types, and limits | ~260 |
| `tests/test_output_postprocess.py` | Tests for FFmpeg command construction, timeout handling, and sequence manifest behavior | ~220 |
| `docs/output-formats.md` | Developer/operator documentation for presets, formats, and artifact metadata | ~180 |

### Files to Modify
| File | Changes | Est. Lines |
|------|---------|------------|
| `app/models/composition.py` | Add output preset field and normalize defaults while preserving explicit dimensions | ~100 |
| `app/models/render.py` | Add optional output metadata to render status responses | ~60 |
| `app/db/models.py` | Add output metadata columns to `renders` | ~35 |
| `app/db/render_crud.py` | Add helpers to persist output metadata atomically with artifact paths | ~80 |
| `app/renderers/capabilities.py` | Allow supported output formats and add bounded format-specific validation context | ~90 |
| `app/renderers/editly.py` | Keep MP4 intermediate generation deterministic and record requested output metadata in replay context | ~90 |
| `app/services/render_service.py` | Wire output finishing, artifact publishing, metadata persistence, and failure handling | ~150 |
| `app/storage/base.py` | Add format-aware media type and manifest artifact support | ~90 |
| `app/storage/local.py` | Publish deterministic single-file and sequence-related artifacts locally | ~80 |
| `app/storage/s3.py` | Publish deterministic single-file and sequence-related artifacts to S3-compatible storage | ~90 |
| `app/storage/urls.py` | Resolve output and manifest URLs through proxy, signed, and public modes | ~70 |
| `app/api/routes_renders.py` | Return format-aware download responses and output metadata | ~110 |
| `app/services/webhook_service.py` | Include output metadata using shared URL resolution | ~70 |
| `app/services/limits.py` | Enforce format and preset-specific duration, fps, and resolution guardrails | ~70 |
| `app/core/config.py` | Add bounded output post-processing timeout and sequence guardrail settings if needed | ~45 |
| `tests/test_composition_schema.py` | Cover preset parsing, defaulting, and explicit dimension precedence | ~100 |
| `tests/test_renderer_capabilities.py` | Update expected Editly format support and rejection cases | ~90 |
| `tests/test_api_renders.py` | Cover format-aware downloads, response metadata, and validation errors | ~150 |
| `tests/test_storage.py` | Cover deterministic suffix and manifest artifact behavior | ~100 |
| `tests/test_storage_urls.py` | Cover public, signed, and proxy URLs for new output metadata paths | ~100 |
| `tests/test_webhook_service.py` | Cover output metadata in webhook payloads without URL duplication | ~100 |
| `tests/test_worker_pipeline.py` | Cover worker-side format validation, post-processing, metadata, and failure paths | ~120 |
| `tests/test_alembic_migrations.py` | Verify render output metadata migration is in the revision chain | ~40 |
| `README.md` | Document basic preset and format request examples | ~45 |
| `docs/ARCHITECTURE.md` | Document output finishing and artifact metadata flow | ~90 |
| `docs/renderer-capabilities.md` | Update Editly support matrix and Session 02 output behavior | ~80 |

---

## 7. Success Criteria

### Functional Requirements
- [ ] `output.preset` accepts `tiktok`, `reels`, `shorts`, `youtube`, `square-ad`, and `preview-low`.
- [ ] Explicit `output.width` and `output.height` override preset dimensions consistently.
- [ ] Omitted output fields keep existing MP4 1920x1080 at 30 fps behavior.
- [ ] `mp4`, `webm`, `gif`, and `png-sequence` requests pass capability validation when renderer is omitted, `auto`, or `editly`.
- [ ] Unsupported format, preset, duration, fps, and resolution combinations fail before queue admission with stable error codes and bounded context.
- [ ] WebM and GIF renders publish retrievable single-file artifacts with correct suffix, media type, filename, and download behavior.
- [ ] PNG sequence renders publish deterministic frame artifacts, manifest metadata, and a retrievable download artifact.
- [ ] Public, signed, and proxied URL modes resolve output URLs without route or webhook-specific URL logic.
- [ ] Webhook payloads include output format metadata and remain signed over ASCII JSON bytes.
- [ ] Existing MP4 render behavior, poster behavior, and download endpoints remain backward compatible.

### Testing Requirements
- [ ] Unit tests written and passing for preset normalization and explicit dimension precedence.
- [ ] Unit tests written and passing for output format planning, media types, filenames, sequence manifests, and capability support.
- [ ] API tests written and passing for valid MP4/WebM/GIF/PNG sequence requests and invalid format or limit combinations.
- [ ] Storage and URL resolver tests written and passing for local, proxy, signed, and public modes.
- [ ] Worker/render service tests written and passing for post-processing success and failure paths.
- [ ] Alembic migration test updated and passing.
- [ ] Manual testing completed for one MP4 request, one WebM or GIF request, and one rejected limit case.

### Non-Functional Requirements
- [ ] FFmpeg post-processing uses explicit timeout, bounded stderr capture, and deterministic command arguments.
- [ ] Output metadata avoids raw composition JSON, asset URLs, callback URLs, presigned URLs, local paths, and secrets.
- [ ] PNG sequence guardrails prevent unbounded frame counts and oversized artifacts.
- [ ] Capability registry additions do not require route-handler branches for future renderer sessions.
- [ ] Database migration has a downgrade and runtime model metadata matches the migration.

### Quality Gates
- [ ] All files ASCII-encoded.
- [ ] Unix LF line endings.
- [ ] Code follows project conventions.

---

## 8. Implementation Notes

### Key Considerations
- `OutputFormat` already includes `mp4`, `gif`, `webm`, and `png-sequence`, but Session 01 configured Editly capability support as MP4-only. This session should update capability validation only after the render pipeline can produce and publish those formats.
- `EditlyRenderer.compile()` currently writes an MP4 `outPath` based on `render_id`. Preserve that as the intermediate to avoid relying on renderer-specific format behavior.
- `RenderService.stage_render_and_store()` is the right integration point for output finishing because it already has the rendered artifact, composition, storage, workspace, and DB session.
- `download_render()` currently hard-codes the download filename and MP4 media type. This must become metadata-driven while preserving the `/download` path.
- The `renders` table currently has only `output_path` and `poster_path`. Format-specific metadata needs a migration because response and webhook behavior should not infer everything from file extensions.
- The project appears to have no seed files. The implementation should explicitly note that no seed update is required while still adding migration tests.

### Potential Challenges
- PNG sequence output can produce many files. Keep the first version bounded by duration, fps, and a configured or derived max frame count.
- Existing tests assume unsupported non-MP4 output formats. Those expectations need to move from renderer capability rejection to format-specific validation or successful post-processing.
- Signed and public S3 URLs should never be serialized into durable metadata. Build them per response or webhook dispatch through `StorageUrlResolver`.
- Webhook payload changes should be additive so existing consumers that read `url` and `poster` continue to work.
- Post-processing should not hide the original Editly logs. Preserve render logs and add bounded post-processing diagnostics.

### Relevant Considerations
- [P03] **Migration-managed schema startup**: Output metadata columns must update runtime SQLModel metadata and Alembic migration together.
- [P03] **Centralized artifact URL resolution**: New output and manifest URLs must flow through `StorageUrlResolver`.
- [P03] **S3 and URL mode drift**: Tests must cover local, proxy, signed, and public behavior so deployment settings do not fragment output downloads.
- [P03] **Guardrail tuning is deployment-specific**: Format-specific duration, fps, resolution, and sequence frame limits must respect configured settings.
- [P03] **Redaction discipline**: FFmpeg logs, output metadata, API errors, and webhook payloads must avoid secrets, raw URLs, and raw payloads.
- [P02] **Replay metadata (`replay.json`)**: Replay output should identify requested format and intermediate path without exposing secrets.

### Behavioral Quality Focus
Checklist active: Yes
Top behavioral risks for this session:
- Non-MP4 requests enter the queue but fail late with ambiguous renderer errors.
- PNG sequence output creates unbounded files or inconsistent storage keys.
- Download and webhook URLs drift between proxy, signed, and public modes.
- Output metadata stores presigned URLs, local filesystem paths, or raw payload data.
- Existing MP4 clients see changed response or download behavior.

---

## 9. Testing Strategy

### Unit Tests
- Test every output preset normalizes to expected dimensions, aspect ratio, fps, and quality.
- Test explicit width and height override preset dimensions while preserving other preset defaults.
- Test format planning for MP4, WebM, GIF, and PNG sequence suffixes, media types, filenames, and manifest expectations.
- Test capability validation accepts implemented output formats and rejects unavailable renderers with safe context.
- Test format guardrails reject excessive GIF/PNG sequence duration, fps, resolution, or frame count.

### Integration Tests
- Test `POST /v1/renders` accepts WebM, GIF, and PNG sequence requests in async mode and persists selected renderer plus output metadata.
- Test sync render service publishes a format-specific output and updates the render record atomically.
- Test worker path revalidates format constraints before rendering queued input and persists format-specific failure details.
- Test `/v1/renders/{id}` returns output metadata and URL for succeeded renders only.
- Test `/v1/renders/{id}/download` uses stored filename and media type for MP4, WebM, GIF, and PNG sequence downloads.
- Test webhook payloads include output metadata using the same URL resolver as status responses.
- Test Alembic upgrade and downgrade include the render output metadata columns.

### Manual Testing
- Submit a minimal MP4 composition without `output.preset` and confirm existing behavior still works.
- Submit a vertical preset request for `tiktok` and confirm dimensions and fps are normalized.
- Submit a WebM or GIF request and confirm the status URL, download endpoint, and stored filename match the requested format.
- Submit a PNG sequence request with a short duration and confirm deterministic manifest and download behavior.
- Submit an over-limit GIF or PNG sequence request and confirm a stable validation error.

### Edge Cases
- `output.preset` with explicit dimensions but no aspect ratio.
- `output.preset` with custom fps that exceeds configured or format-specific limits.
- `output.format` omitted, explicitly `mp4`, and non-MP4 with `renderer` omitted or set to `auto`.
- Empty, missing, or failed output artifact metadata should not produce URLs.
- Local storage in signed/public mode should continue to fall back to proxied downloads.
- Webhook dispatch must not fail the render if metadata URL resolution or delivery fails.

---

## 10. Dependencies

### External Libraries
- No new Python package dependencies planned.
- FFmpeg remains a system dependency already required by the worker image.

### Other Sessions
- **Depends on**: `phase04-session01-renderer-capability-registry`.
- **Depended by**: `phase04-session03-captions-and-poster-customization`, `phase04-session04-advanced-transitions-and-feature-validation`, `phase04-session05-native-ffmpeg-renderer-subset`, `phase04-session06-hyperframes-renderer-adapter`.

---

## Next Steps

Run the implement workflow step to begin AI-led implementation.
