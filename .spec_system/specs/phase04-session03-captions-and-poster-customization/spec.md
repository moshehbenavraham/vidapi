# Session Specification

**Session ID**: `phase04-session03-captions-and-poster-customization`
**Phase**: 04 - Advanced Rendering
**Status**: Not Started
**Created**: 2026-05-05

---

## 1. Session Overview

This session adds timed captions/subtitles and request-level poster controls as finishing features in the existing render pipeline. Phase 04 Session 01 made renderer capabilities explicit, and Session 02 added output format post-processing and artifact metadata. Session 03 builds on that foundation by validating caption and poster feature combinations before queue admission, then applying the finishing work in the worker path.

Captions are client-supplied timed text cues, not speech-to-text generation. The implementation should support deterministic sidecar output and FFmpeg-backed burn-in for the supported output path while keeping Editly as the default renderer. Caption artifacts, sidecars, logs, and metadata must flow through the same storage, URL resolver, response, and webhook patterns used for outputs and posters.

Poster customization replaces the settings-only timestamp behavior with explicit request options while preserving the current default when options are omitted. Clients can request the default frame, a bounded timestamp, or disabled poster generation where the selected output mode allows it. The work stays API-first and does not introduce a browser editor, localization workflow, or renderer-native schema exposure.

---

## 2. Objectives

1. Add public caption/subtitle and poster option schemas with deterministic defaults, timing validation, and bounded style fields.
2. Enforce renderer capability, output format, caption mode, cue timing, and poster option validation before render work starts.
3. Implement FFmpeg-backed caption sidecar or burn-in finishing plus request-level poster extraction without breaking current MP4/default poster behavior.
4. Persist and expose caption, sidecar, and poster metadata through existing storage, status response, download, and webhook paths.

---

## 3. Prerequisites

### Required Sessions
- [x] `phase04-session01-renderer-capability-registry` - Provides renderer selection and unsupported-feature validation.
- [x] `phase04-session02-output-formats-and-presets` - Provides output finishing, output metadata, and format-aware artifact handling.
- [x] `phase03-session02-s3-compatible-storage-and-download-modes` - Provides centralized artifact URL resolution for local, proxy, signed, and public modes.
- [x] `phase03-session04-limits-resource-controls-and-asset-security-hardening` - Provides composition, duration, fps, queue, and subprocess guardrails.
- [x] `phase03-session05-operational-visibility-and-production-stack` - Provides redacted logs, metrics, and webhook-safe operational behavior.

### Required Tools/Knowledge
- Pydantic v2 validators and frozen models in `app/models/composition.py`.
- Renderer capability validation in `app/renderers/capabilities.py`.
- Output finishing and artifact metadata behavior in `app/services/output_postprocess.py` and `app/models/output_artifacts.py`.
- Current poster extraction in `app/renderers/poster.py`.
- Render orchestration in `app/services/render_service.py` and worker cancellation conventions.
- SQLModel and Alembic migration conventions.
- Existing local and S3-compatible storage URL resolver behavior.

### Environment Requirements
- Python 3.11+ dependencies installed with `uv`.
- FFmpeg available with subtitle filter support for manual burn-in checks.
- Existing render, storage, output format, webhook, worker, and migration tests runnable before implementation.
- No seed fixtures currently exist; schema changes still need migration and integration coverage.

---

## 4. Scope

### In Scope (MVP)
- Client can submit `captions` as a composition-level finishing block with timed cues, mode, format, and bounded style options - validate cue timing, text length, style bounds, and deterministic ordering.
- Client can request caption burn-in or sidecar generation where supported - create deterministic caption files, reject unsupported output or renderer combinations, and keep sidecars behind storage URLs.
- System can burn captions into the rendered intermediate before output format conversion - preserve GIF, WebM, PNG sequence, and MP4 output handling from Session 02.
- Client can configure poster generation through output-level options - omitted options preserve the existing default, bounded timestamps select a requested frame, and disabled poster mode is allowed only for compatible outputs.
- System can persist caption sidecar path, caption metadata, poster mode, poster timestamp, and poster artifact metadata without storing raw composition JSON, local paths, presigned URLs, or secrets.
- Render status and webhook payloads can include caption and poster metadata while resolving client-facing URLs through `StorageUrlResolver`.
- Tests cover invalid caption timing, unsupported feature combinations, sidecar output, burn-in command construction, poster timestamp bounds, disabled poster mode, metadata persistence, URL modes, and backward compatibility.

### Out of Scope (Deferred)
- Speech-to-text caption generation - Reason: explicitly excluded by the session stub and master PRD non-goals.
- Rich karaoke or word-level caption animation - Reason: requires a more complex timing and animation model.
- Multi-language localization workflow - Reason: this session focuses on one caption track and deterministic artifacts.
- Browser editor or caption authoring UI - Reason: VidAPI remains API-first.
- Arbitrary FFmpeg subtitle filter injection or user-supplied script files - Reason: unsafe and outside MVP capability validation.
- Exposing Editly, FFmpeg, or HyperFrames native caption schemas directly - Reason: public API must remain renderer-independent.

---

## 5. Technical Approach

### Architecture

Add captions as a top-level composition finishing block and poster options under `output` so schema validation happens before queue admission. Captions should contain cue records with `start`, `end` or `duration`, text, and optional style options. Poster options should express mode and timestamp intent without requiring clients to know FFmpeg internals.

Extend the capability registry to use the existing `supports_captions` and `supports_poster_options` fields. Editly can support these features through the shared post-render finishing path, while unavailable renderer paths must reject requests with bounded safe context. Capability validation should remain route-independent and run both in API admission and worker revalidation.

Insert caption finishing between renderer output and output post-processing. The renderer still produces the deterministic MP4 intermediate. Caption burn-in creates a captioned intermediate that `OutputPostprocessor` converts to the requested final format. Sidecar mode creates a deterministic SRT or WebVTT artifact without mutating the video. Poster extraction then uses request-level options and should use the appropriate video source for a stable frame.

Persist new metadata with a migration because render status responses and webhook payloads should not infer caption or poster state from file extensions. Store durable artifact URIs and safe metadata only. Public, signed, and proxied URLs must be generated per response or webhook dispatch through `StorageUrlResolver`.

### Design Patterns
- Boundary validation: Reject invalid caption timing, unsupported modes, and invalid poster timestamps before queue admission.
- Pure formatting helpers: Serialize SRT/WebVTT/ASS output deterministically with escaping covered by unit tests.
- Subprocess isolation: Run FFmpeg caption burn-in and poster extraction with timeout, bounded stderr, cleanup, and explicit failure mapping.
- Centralized artifact metadata: Persist paths and safe metadata once, then build response and webhook payloads through shared builders.
- Migration-managed metadata: Update runtime SQLModel metadata and Alembic migration together, with downgrade coverage.
- Additive API responses: Preserve existing `url` and `poster` fields while adding structured metadata for clients that need it.

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
| `app/services/caption_formats.py` | Caption cue planning plus deterministic SRT/WebVTT/ASS serialization helpers | ~240 |
| `app/services/caption_finishing.py` | FFmpeg-backed burn-in and sidecar preparation service | ~260 |
| `alembic/versions/007_add_caption_and_poster_metadata.py` | Migration for caption and poster metadata columns | ~110 |
| `tests/test_caption_formats.py` | Unit tests for cue ordering, escaping, timing, and sidecar serialization | ~260 |
| `tests/test_caption_finishing.py` | Unit tests for FFmpeg command construction, timeout handling, sidecar output, and poster options | ~240 |
| `docs/captions-and-posters.md` | Developer/operator documentation for captions, sidecars, burn-in, and poster controls | ~180 |

### Files to Modify
| File | Changes | Est. Lines |
|------|---------|------------|
| `app/models/composition.py` | Add caption cue/style models, caption mode/format enums, and output poster options | ~180 |
| `app/models/output_artifacts.py` | Add caption and poster artifact metadata models for responses and webhooks | ~100 |
| `app/models/render.py` | Include structured caption and poster metadata in render status responses | ~50 |
| `app/db/models.py` | Add caption sidecar and poster metadata columns to `renders` | ~45 |
| `app/db/render_crud.py` | Add helpers to persist caption and poster metadata atomically | ~90 |
| `app/renderers/capabilities.py` | Validate captions and poster options against renderer capabilities and output modes | ~90 |
| `app/renderers/poster.py` | Support request-level poster modes, timestamps, disabled handling, and bounded errors | ~120 |
| `app/services/limits.py` | Enforce cue count, text length, duration, timestamp, and sidecar/burn-in guardrails | ~100 |
| `app/services/render_service.py` | Wire caption finishing, output finishing, poster options, artifact publishing, metadata persistence, and cleanup | ~170 |
| `app/storage/base.py` | Add caption sidecar artifact descriptors and media types | ~45 |
| `app/storage/urls.py` | Resolve caption sidecar and structured poster URLs through existing URL modes | ~70 |
| `app/api/routes_renders.py` | Return caption/poster metadata and expose sidecar download behavior with auth checks | ~120 |
| `app/services/webhook_service.py` | Include caption and poster metadata through shared URL resolution | ~80 |
| `tests/test_composition_schema.py` | Cover caption schema validation, style bounds, and poster options | ~140 |
| `tests/test_renderer_capabilities.py` | Cover caption and poster capability rejection/acceptance context | ~90 |
| `tests/test_api_renders.py` | Cover status responses, sidecar download, poster modes, and auth-before-artifact lookup | ~150 |
| `tests/test_storage_urls.py` | Cover proxy, signed, and public caption/poster URL resolution | ~100 |
| `tests/test_webhook_service.py` | Cover caption and poster metadata in signed webhook payloads | ~100 |
| `tests/test_worker_pipeline.py` | Cover worker-side caption finishing, poster metadata, persistence, and failure cleanup | ~150 |
| `tests/test_alembic_migrations.py` | Verify metadata migration is in the revision chain | ~40 |
| `README.md` | Add compact caption and poster request examples | ~50 |
| `docs/ARCHITECTURE.md` | Document caption/poster finishing order and artifact metadata flow | ~90 |
| `docs/renderer-capabilities.md` | Update Editly support matrix for captions and poster options | ~70 |

---

## 7. Success Criteria

### Functional Requirements
- [ ] Caption cues with negative times, zero duration, overlapping invalid ordering, empty text, or excessive style values fail before rendering.
- [ ] Supported sidecar caption requests produce deterministic SRT or WebVTT artifacts and client-facing URLs.
- [ ] Supported burn-in caption requests create a captioned intermediate before output format conversion.
- [ ] Unsupported caption mode, format, output format, or renderer combinations return clear renderer capability or validation errors.
- [ ] Omitted poster options keep existing default poster behavior.
- [ ] Bounded poster timestamp requests extract the requested frame within duration bounds.
- [ ] Disabled poster mode suppresses poster generation only when allowed and does not leave stale poster metadata.
- [ ] Caption and poster metadata are persisted and returned in render status responses without raw payloads, local paths, presigned URLs, or secrets.
- [ ] Webhook payloads include caption and poster metadata through the centralized URL resolver.
- [ ] Existing MP4/WebM/GIF/PNG sequence output behavior from Session 02 remains backward compatible.

### Testing Requirements
- [ ] Unit tests written and passing for caption schema validation, cue timing, style bounds, and poster options.
- [ ] Unit tests written and passing for caption sidecar serialization, escaping, deterministic ordering, and FFmpeg burn-in command construction.
- [ ] API tests written and passing for status metadata, sidecar download, poster endpoint behavior, validation errors, and auth checks.
- [ ] Worker/render service tests written and passing for caption finishing success/failure, poster modes, metadata persistence, and cleanup.
- [ ] Storage URL and webhook tests written and passing for local, proxy, signed, and public URL modes.
- [ ] Alembic migration test updated and passing.
- [ ] Manual testing completed for one sidecar caption render, one burn-in caption render, one custom poster timestamp, and one invalid caption timing request.

### Non-Functional Requirements
- [ ] Caption and poster FFmpeg subprocesses use explicit timeout, bounded stderr capture, cancellation-aware cleanup, and deterministic command arguments.
- [ ] Caption metadata avoids raw composition JSON, raw asset URLs, callback URLs, presigned URLs, local paths, and secrets.
- [ ] Sidecar and burn-in guardrails prevent unbounded cue counts, oversized text payloads, and unsupported output combinations.
- [ ] URL generation remains centralized in `StorageUrlResolver` for status responses, downloads, and webhooks.
- [ ] Database migration has a downgrade and runtime model metadata matches the migration.

### Quality Gates
- [ ] All files ASCII-encoded.
- [ ] Unix LF line endings.
- [ ] Code follows project conventions.

---

## 8. Implementation Notes

### Key Considerations
- `RendererCapability` already has `supports_captions` and `supports_poster_options` fields, but current capabilities leave them disabled. Enable them only after schema validation and finishing services exist.
- `RenderService.stage_render_and_store()` is the right integration point because it has the rendered intermediate, output postprocessor, storage, workspace, and DB session.
- Caption burn-in should happen before `OutputPostprocessor.finish()` so WebM, GIF, and PNG sequence outputs can inherit burned captions from the intermediate.
- Sidecar caption artifacts should be published with deterministic names and media types, then exposed through URL resolver methods rather than hard-coded route URLs.
- Current poster generation uses `settings.poster_timestamp_percent`. Request-level options should override settings only for that render.
- The project appears to have no seed files. The implementation should explicitly note that no seed update is required while still adding migration tests.

### Potential Challenges
- Burned captions need careful escaping so user text cannot break the FFmpeg subtitle filter or generated ASS file.
- Poster timestamp validation needs a reliable duration source; when duration is unavailable, reject explicit out-of-bounds values rather than guessing.
- Disabled poster mode must clear or avoid writing stale `poster_path` and metadata on retries or rerenders.
- Sidecar URL behavior must stay consistent across local proxy mode, S3 signed URLs, and S3 public URLs.
- Webhook payload additions should be additive so existing consumers that read `url` and `poster` continue to work.

### Relevant Considerations
- [P03] **Migration-managed schema startup**: Caption sidecar and poster metadata columns must update runtime SQLModel metadata and Alembic migration together.
- [P03] **Centralized artifact URL resolution**: Caption sidecar and poster metadata URLs must flow through `StorageUrlResolver`.
- [P03] **S3 and URL mode drift**: Tests must cover local, proxy, signed, and public behavior so deployment settings do not fragment artifact links.
- [P03] **Guardrail tuning is deployment-specific**: Caption cue counts, text size, duration, and poster timestamp behavior must respect configured limits.
- [P03] **Redaction discipline**: Caption text, asset URLs, FFmpeg stderr, API errors, and webhook payloads must avoid secrets and raw payload leakage.
- [P02] **Replay metadata (`replay.json`)**: Replay output should identify caption/poster mode and generated artifact names without exposing raw URLs or secrets.

### Behavioral Quality Focus
Checklist active: Yes
Top behavioral risks for this session:
- Caption requests pass API validation but fail late with ambiguous FFmpeg errors.
- Subtitle text escaping allows malformed ASS/SRT/WebVTT output or filter injection.
- Burn-in happens after output conversion and silently misses GIF, WebM, or PNG sequence outputs.
- Disabled poster mode leaves stale poster URLs in status responses or webhooks.
- Caption/poster URLs drift between status responses, downloads, and webhook payloads.

---

## 9. Testing Strategy

### Unit Tests
- Test caption cue timing, ordering, empty text, max text length, style bounds, mode parsing, and sidecar format parsing.
- Test SRT, WebVTT, and ASS serialization for deterministic ordering, newline handling, escaping, and ASCII-safe output where possible.
- Test poster option parsing, default behavior, disabled mode, timestamp seconds, timestamp percent, and out-of-bounds errors.
- Test capability validation accepts implemented Editly finishing features and rejects unavailable renderers with bounded context.
- Test limit validation rejects excessive cue counts, oversized caption payloads, unsupported sidecar/burn-in combinations, and invalid poster timestamps.

### Integration Tests
- Test `POST /v1/renders` accepts valid sidecar and burn-in caption requests and rejects invalid caption timing before queue admission.
- Test worker revalidation rejects unsupported caption/poster combinations before renderer invocation.
- Test render service publishes caption sidecar artifacts, burned-caption output artifacts, customized poster artifacts, and metadata atomically.
- Test failure in caption finishing clears output/caption metadata and marks the render failed with safe error details.
- Test `/v1/renders/{id}` returns caption and poster metadata for succeeded renders only.
- Test sidecar download and poster endpoints authenticate before artifact lookup.
- Test webhook payloads include caption and poster metadata resolved through the same URL resolver as status responses.
- Test Alembic upgrade and downgrade include the caption and poster metadata columns.

### Manual Testing
- Submit a minimal MP4 composition without caption or poster options and confirm existing output and poster behavior still works.
- Submit a sidecar caption request and confirm the status response, sidecar download, and webhook metadata are consistent.
- Submit a burn-in caption request and confirm the final output visually includes the supplied cues.
- Submit a custom poster timestamp request and confirm the generated poster is from the requested point in the video.
- Submit invalid caption timing and confirm a stable validation error before queue admission.

### Edge Cases
- Cue ending exactly at composition duration.
- Cue start equal to prior cue end.
- Multiline caption text with punctuation and characters that need subtitle escaping.
- Explicit poster timestamp at 0 seconds and at the final frame boundary.
- Disabled poster mode on output formats where a poster is required or unsupported.
- Sidecar URL missing, stale, or not available in signed/public storage modes.

---

## 10. Dependencies

### External Libraries
- FFmpeg: Existing system dependency for subtitle burn-in, sidecar validation, and poster extraction.
- Pydantic v2: Existing schema and validation layer.
- SQLModel / Alembic: Existing runtime metadata and migration stack.

### Other Sessions
- **Depends on**: `phase04-session01-renderer-capability-registry`, `phase04-session02-output-formats-and-presets`
- **Depended by**: `phase04-session05-native-ffmpeg-renderer-subset`, `phase04-session06-hyperframes-renderer-adapter`

---

## Next Steps

Run the implement workflow step to begin AI-led implementation.
