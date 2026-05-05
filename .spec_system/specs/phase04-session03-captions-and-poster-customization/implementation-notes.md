# Implementation Notes

**Session ID**: `phase04-session03-captions-and-poster-customization`
**Started**: 2026-05-05 14:31
**Last Updated**: 2026-05-05 14:48

---

## Session Progress

| Metric | Value |
|--------|-------|
| Tasks Completed | 20 / 24 |
| Estimated Remaining | 3-4 hours |
| Blockers | 0 |

---

## Task Log

### 2026-05-05 - Session Start

**Environment verified**:
- [x] Prerequisites confirmed
- [x] Tools available through `uv`
- [x] Directory structure ready
- [x] Database conventions reviewed

---

### Task T001 - Verify current finishing behavior

**Started**: 2026-05-05 14:29
**Completed**: 2026-05-05 14:31
**Duration**: 2 minutes

**Notes**:
- Read current poster generation, output finishing, storage URL resolution,
  webhook payload, worker pipeline, renderer capability, and migration behavior.
- Ran baseline targeted tests before changing finishing controls.
- Baseline result: 62 passed, 1 skipped.

**Files Changed**:
- `.spec_system/specs/phase04-session03-captions-and-poster-customization/implementation-notes.md` - initialized progress log.

**BQC Fixes**:
- N/A - verification-only task.

---

### Task T002 - Create captions and posters documentation scaffold

**Started**: 2026-05-05 14:31
**Completed**: 2026-05-05 14:31
**Duration**: 1 minutes

**Notes**:
- Added a focused scaffold for caption request modes, sidecar formats, poster
  modes, artifact fields, and storage URL expectations.
- Left broader architecture and README updates for the dedicated docs task.

**Files Changed**:
- `docs/captions-and-posters.md` - added initial public schema and artifact
  behavior documentation.

**BQC Fixes**:
- N/A - documentation-only task.

---

### Task T003 - Confirm Alembic head and seed fixture scope

**Started**: 2026-05-05 14:31
**Completed**: 2026-05-05 14:31
**Duration**: 1 minutes

**Notes**:
- Confirmed the current Alembic head before this session is `006`.
- Searched project fixtures and seed references; there is no seed fixture update
  required for caption and poster metadata.
- Existing Alembic tests were part of the baseline pass.

**Files Changed**:
- `.spec_system/specs/phase04-session03-captions-and-poster-customization/implementation-notes.md` - recorded current head and seed fixture finding.

**BQC Fixes**:
- N/A - verification-only task.

---

### Task T004 - Add caption and poster composition schemas

**Started**: 2026-05-05 14:31
**Completed**: 2026-05-05 14:34
**Duration**: 3 minutes

**Notes**:
- Added caption mode, format, style, cue, and top-level captions models.
- Added output-level poster options for default, timestamp, percent, and
  disabled modes.
- Cue validation resolves duration to end time, rejects blank text and overlap,
  and keeps cue ordering deterministic.
- Verified a valid caption and timestamp-poster composition through Pydantic.

**Files Changed**:
- `app/models/composition.py` - added caption and poster public schema models.

**BQC Fixes**:
- Trust boundary enforcement: request fields now validate mode-specific poster
  timestamp fields and caption cue timing before queue admission.
- Contract alignment: added frozen request models using renderer-independent
  enums instead of backend-specific FFmpeg or Editly fields.

---

### Task T005 - Add caption and poster artifact metadata models

**Started**: 2026-05-05 14:34
**Completed**: 2026-05-05 14:34
**Duration**: 1 minutes

**Notes**:
- Added durable and client-facing metadata models for caption sidecars,
  burned-in captions, and poster artifacts.
- Added builders that convert persisted render columns into response-safe
  metadata without exposing durable paths.

**Files Changed**:
- `app/models/output_artifacts.py` - added caption and poster metadata models
  and render-column conversion helpers.

**BQC Fixes**:
- Error information boundaries: response helpers accept resolved URLs and do
  not include raw storage paths in structured metadata.
- Contract alignment: API and webhook metadata now share the same models.

---

### Task T006 - Create caption and poster metadata migration

**Started**: 2026-05-05 14:34
**Completed**: 2026-05-05 14:35
**Duration**: 1 minutes

**Notes**:
- Added revision `007` after `006` for caption and poster metadata columns.
- Included explicit downgrade coverage for every added column.
- Confirmed Alembic reports the new single head as `007`.

**Files Changed**:
- `alembic/versions/007_add_caption_and_poster_metadata.py` - added caption
  and poster metadata migration.

**BQC Fixes**:
- Contract alignment: migration stores only durable artifact URIs and safe
  metadata fields needed by status and webhook contracts.

---

### Task T007 - Add runtime metadata columns

**Started**: 2026-05-05 14:35
**Completed**: 2026-05-05 14:35
**Duration**: 1 minutes

**Notes**:
- Added runtime SQLModel columns matching migration `007`.
- Verified metadata registration exposes caption and poster columns with the
  expected string lengths.

**Files Changed**:
- `app/db/models.py` - added caption sidecar, burn-in, poster mode, timestamp,
  and poster artifact metadata columns.

**BQC Fixes**:
- Contract alignment: runtime model fields now match the migration-managed
  database shape.

---

### Task T008 - Add caption and poster metadata CRUD helpers

**Started**: 2026-05-05 14:35
**Completed**: 2026-05-05 14:36
**Duration**: 1 minutes

**Notes**:
- Added atomic caption metadata update and clear helpers.
- Added atomic poster metadata update and clear helpers.
- Clear helpers reset stored URIs and metadata to prevent stale status and
  webhook fields on retries, failures, or disabled poster mode.

**Files Changed**:
- `app/db/render_crud.py` - added transaction-aware caption and poster metadata
  persistence helpers.

**BQC Fixes**:
- State freshness on re-entry: clear helpers reset stale caption and poster
  metadata before or after render-stage retries.
- Failure path completeness: write helpers share commit/rollback behavior with
  existing render metadata updates.

---

### Task T009 - Create deterministic caption formatting helpers

**Started**: 2026-05-05 14:36
**Completed**: 2026-05-05 14:37
**Duration**: 1 minutes

**Notes**:
- Added pure helpers for cue planning, deterministic sidecar names, media
  types, SRT serialization, WebVTT serialization, and ASS burn-in text.
- Escaping covers HTML-like caption text, WebVTT arrow tokens, ASS braces,
  backslashes, and multiline cue text.
- Smoke-tested SRT sidecar bytes and ASS serialization from a validated
  captions model.

**Files Changed**:
- `app/services/caption_formats.py` - added caption planning and serialization
  helpers.

**BQC Fixes**:
- Trust boundary enforcement: user caption text is escaped before sidecar or
  ASS serialization.
- Contract alignment: sidecar suffixes and media types are centralized for
  storage and response metadata.

---

### Task T010 - Update renderer capability validation

**Started**: 2026-05-05 14:37
**Completed**: 2026-05-05 14:38
**Duration**: 1 minutes

**Notes**:
- Enabled shared finishing support flags for the Editly renderer.
- Added boundary validation for caption modes, sidecar formats, and poster
  modes using the existing bounded capability error context.
- Smoke-tested a burn-in caption request with disabled poster mode through
  renderer selection.

**Files Changed**:
- `app/renderers/capabilities.py` - added caption and poster feature
  validation.

**BQC Fixes**:
- Trust boundary enforcement: unsupported caption and poster feature
  combinations now fail before queue admission and worker execution.
- Error information boundaries: existing bounded capability context is reused
  and does not include raw composition details.

---

### Task T011 - Enforce caption and poster guardrails

**Started**: 2026-05-05 14:38
**Completed**: 2026-05-05 14:39
**Duration**: 1 minutes

**Notes**:
- Added settings for maximum caption cue count, per-cue text length, and total
  caption text payload size.
- Added composition limit checks for cue count, text size, cue end time, and
  explicit poster timestamp bounds.
- Smoke-tested caption end time beyond render duration and confirmed the
  stable field path `captions.cues[0].end`.

**Files Changed**:
- `app/core/config.py` - added caption guardrail settings.
- `app/services/limits.py` - added caption and poster validation.

**BQC Fixes**:
- Trust boundary enforcement: caption and poster resource limits now run before
  queue admission and worker execution.
- Failure path completeness: violations use existing stable limit error
  mapping with field, limit, and observed context.

---

### Task T012 - Implement caption finishing service

**Started**: 2026-05-05 14:39
**Completed**: 2026-05-05 14:40
**Duration**: 1 minutes

**Notes**:
- Added a `CaptionFinisher` service for deterministic sidecar generation and
  FFmpeg-backed ASS burn-in.
- Added timeout, bounded stderr capture, process termination, missing-output
  checks, and output cleanup on failure.
- Smoke-tested command construction and module imports.

**Files Changed**:
- `app/core/config.py` - added caption burn-in timeout setting.
- `app/services/caption_finishing.py` - added caption sidecar and burn-in
  finishing service.

**BQC Fixes**:
- Resource cleanup: failed burn-in removes partial captioned output and
  terminates timed-out FFmpeg processes.
- External dependency resilience: FFmpeg execution has explicit timeout,
  bounded stderr, and stable failure mapping.
- Error information boundaries: only bounded stderr is stored and surfaced.

---

### Task T013 - Update request-level poster generation

**Started**: 2026-05-05 14:40
**Completed**: 2026-05-05 14:41
**Duration**: 1 minutes

**Notes**:
- Added poster planning for default, timestamp, percent, and disabled modes.
- Preserved the historical default timestamp behavior when poster options are
  omitted.
- Added duration-required validation for explicit timestamp and percent modes.

**Files Changed**:
- `app/renderers/poster.py` - added request-level poster option planning.

**BQC Fixes**:
- State freshness on re-entry: disabled mode resolves to a no-op plan so the
  render flow can clear stale poster metadata before completing.
- Failure path completeness: explicit poster modes raise bounded `PosterError`
  messages when duration data is unavailable or out of bounds.

---

### Task T014 - Wire caption, output, poster, and metadata flow

**Started**: 2026-05-05 14:41
**Completed**: 2026-05-05 14:43
**Duration**: 2 minutes

**Notes**:
- Wired caption finishing before output post-processing so burn-in affects MP4,
  WebM, GIF, and PNG sequence output finishing.
- Published sidecar artifacts and persisted caption metadata after successful
  output publication.
- Applied request-level poster planning to the captioned intermediate when
  burn-in is used, and persisted structured poster metadata.
- Added stale caption and poster metadata clearing at render-stage re-entry and
  on output/caption/poster failure paths.

**Files Changed**:
- `app/services/render_service.py` - integrated caption finishing, output
  finishing, poster planning, artifact publishing, metadata persistence, and
  failure compensation.
- `app/storage/base.py` - introduced the caption sidecar artifact type needed
  by render-stage publishing.

**BQC Fixes**:
- State freshness on re-entry: caption and poster metadata are cleared before
  render-stage work starts.
- Failure path completeness: caption and explicit poster failures map to
  render-stage errors with stale metadata cleared.
- Contract alignment: render-stage persistence uses shared durable metadata
  models instead of ad hoc dicts.

---

### Task T015 - Extend storage artifact descriptors

**Started**: 2026-05-05 14:43
**Completed**: 2026-05-05 14:43
**Duration**: 1 minutes

**Notes**:
- Added a caption sidecar artifact type with deterministic `captions.srt` and
  `captions.vtt` names.
- Added default sidecar media type support while preserving explicit media type
  overrides from caption format planning.
- Smoke-tested artifact descriptors for SRT and WebVTT sidecars.

**Files Changed**:
- `app/storage/base.py` - added caption sidecar artifact descriptor support.

**BQC Fixes**:
- Contract alignment: storage filenames, suffixes, and media types now match
  the caption metadata produced by render-stage publishing.

---

### Task T016 - Update storage URL resolution

**Started**: 2026-05-05 14:43
**Completed**: 2026-05-05 14:43
**Duration**: 1 minutes

**Notes**:
- Added proxy URL support for `/v1/renders/{id}/captions`.
- Added caption sidecar URL and structured caption metadata resolution.
- Added structured poster metadata resolution through the existing poster URL
  resolver.
- Smoke-tested caption sidecar proxy URL construction.

**Files Changed**:
- `app/storage/urls.py` - added caption and poster metadata URL resolution.

**BQC Fixes**:
- Contract alignment: status and webhook paths can now use the same resolver
  methods for caption and poster metadata.
- Error information boundaries: resolved metadata contains client-facing URLs,
  not durable local or S3 URIs.

---

### Task T017 - Update render status and caption route

**Started**: 2026-05-05 14:43
**Completed**: 2026-05-05 14:44
**Duration**: 1 minutes

**Notes**:
- Added structured `captions` and `poster_metadata` fields to render status
  responses.
- Added an authenticated `/v1/renders/{id}/captions` sidecar route.
- The sidecar route reads the render record and status before artifact storage
  lookup, matching existing auth-before-artifact behavior.

**Files Changed**:
- `app/models/render.py` - added caption and poster metadata response fields.
- `app/api/routes_renders.py` - added status metadata resolution and caption
  sidecar download route.

**BQC Fixes**:
- Trust boundary enforcement: sidecar download performs DB authorization scope
  checks before artifact existence checks.
- Contract alignment: status responses expose the same metadata models used by
  storage URL resolution.

---

### Task T018 - Update webhook payload metadata

**Started**: 2026-05-05 14:44
**Completed**: 2026-05-05 14:45
**Duration**: 1 minutes

**Notes**:
- Added `captions` and `poster_metadata` fields to webhook payloads.
- Storage-aware webhook payloads resolve caption and poster metadata through
  the shared URL resolver.
- Smoke-tested pure payload construction with sidecar and disabled poster
  metadata.

**Files Changed**:
- `app/services/webhook_service.py` - added caption and poster metadata to
  webhook payload builders.

**BQC Fixes**:
- Contract alignment: webhook payloads reuse the same metadata models and URL
  resolver methods as status responses.
- Error information boundaries: webhook metadata remains additive and avoids
  raw storage paths or internal request payloads.

---

### Task T019 - Update caption and poster documentation

**Started**: 2026-05-05 14:45
**Completed**: 2026-05-05 14:47
**Duration**: 2 minutes

**Notes**:
- Added README endpoint and request examples for caption sidecars, burn-in, and
  poster options.
- Updated architecture flow to show caption finishing before output conversion
  and request-level poster extraction.
- Updated output-format and renderer-capability docs for caption and poster
  support.

**Files Changed**:
- `README.md` - added captions/posters overview, example, endpoint, and docs
  link.
- `docs/ARCHITECTURE.md` - documented caption finishing and updated data flow.
- `docs/output-formats.md` - documented caption/poster finishing and metadata.
- `docs/renderer-capabilities.md` - updated the Editly support matrix.

**BQC Fixes**:
- N/A - documentation-only task.

---

### Task T020 - Write composition schema tests

**Started**: 2026-05-05 14:47
**Completed**: 2026-05-05 14:48
**Duration**: 1 minutes

**Notes**:
- Added tests for caption mode and format parsing, duration-to-end resolution,
  deterministic cue ordering, overlap rejection, blank text rejection, style
  bounds, and poster option mode validation.
- Ran targeted schema tests: 8 passed.

**Files Changed**:
- `tests/test_composition_schema.py` - added caption and poster schema tests.

**BQC Fixes**:
- Trust boundary enforcement: tests cover invalid user-provided caption and
  poster fields before render work begins.

---
