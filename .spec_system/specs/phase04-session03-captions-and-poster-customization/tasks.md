# Task Checklist

**Session ID**: `phase04-session03-captions-and-poster-customization`
**Total Tasks**: 24
**Estimated Duration**: 3-4 hours
**Created**: 2026-05-05

---

## Legend

- `[x]` = Completed
- `[ ]` = Pending
- `[P]` = Parallelizable (can run with other [P] tasks)
- `[SNNMM]` = Session reference (NN=phase number, MM=session number)
- `TNNN` = Task ID

---

## Progress Summary

| Category | Total | Done | Remaining |
|----------|-------|------|-----------|
| Setup | 3 | 3 | 0 |
| Foundation | 6 | 6 | 0 |
| Implementation | 10 | 10 | 0 |
| Testing | 5 | 1 | 4 |
| **Total** | **24** | **20** | **4** |

---

## Setup (3 tasks)

Initial configuration and environment preparation.

- [x] T001 [S0403] Verify current poster generation, output finishing, storage URL, webhook, worker, capability, and migration behavior before changing finishing controls (`app/services/render_service.py`)
- [x] T002 [S0403] [P] Create captions and posters documentation scaffold for public schema, supported modes, artifacts, and examples (`docs/captions-and-posters.md`)
- [x] T003 [S0403] [P] Confirm current Alembic head and note that no seed fixture update is required for caption and poster metadata (`tests/test_alembic_migrations.py`)

---

## Foundation (6 tasks)

Core structures and base implementations.

- [x] T004 [S0403] Add caption cue/style models, caption mode/format enums, and output poster options with schema-validated input and explicit error mapping (`app/models/composition.py`)
- [x] T005 [S0403] [P] Add caption and poster artifact metadata models for API responses and webhook payloads with types matching declared contracts (`app/models/output_artifacts.py`)
- [x] T006 [S0403] Create caption and poster metadata Alembic migration with upgrade and downgrade paths (`alembic/versions/007_add_caption_and_poster_metadata.py`)
- [x] T007 [S0403] Add caption sidecar and poster metadata columns to runtime SQLModel metadata in alignment with the migration (`app/db/models.py`)
- [x] T008 [S0403] Add CRUD helpers for caption and poster metadata persistence with transaction boundaries and stale-metadata clearing on failure (`app/db/render_crud.py`)
- [x] T009 [S0403] [P] Create deterministic caption formatting helpers for SRT, WebVTT, and ASS sidecars with escaping and bounded cue handling (`app/services/caption_formats.py`)

---

## Implementation (10 tasks)

Main feature implementation.

- [x] T010 [S0403] Update renderer capability validation for captions and poster options with authorization-style boundary rejection closest to queue admission (`app/renderers/capabilities.py`)
- [x] T011 [S0403] Enforce caption cue count, text length, duration, sidecar/burn-in, and poster timestamp guardrails with deterministic validation errors (`app/services/limits.py`)
- [x] T012 [S0403] Implement FFmpeg caption burn-in and sidecar preparation with timeout, bounded stderr, cleanup on scope exit for all acquired resources, and explicit failure mapping (`app/services/caption_finishing.py`)
- [x] T013 [S0403] Update poster generation for request-level default, timestamp, percent, and disabled modes with state reset on re-entry (`app/renderers/poster.py`)
- [x] T014 [S0403] Wire caption finishing, output finishing, poster options, artifact publishing, metadata persistence, and compensation on failure into the render stage flow (`app/services/render_service.py`)
- [x] T015 [S0403] Extend shared storage artifact descriptors for caption sidecars, safe suffixes, media types, and deterministic artifact names (`app/storage/base.py`)
- [x] T016 [S0403] Update centralized storage URL resolution for caption sidecar and structured poster metadata across proxy, signed, and public modes (`app/storage/urls.py`)
- [x] T017 [S0403] Update render status, poster, and caption sidecar routes to use persisted metadata with auth enforced before artifact lookup (`app/api/routes_renders.py`)
- [x] T018 [S0403] Update webhook payload construction to include caption and poster metadata through shared URL resolution without duplicating URL logic (`app/services/webhook_service.py`)
- [x] T019 [S0403] Update README, architecture, output-format, and renderer-capability documentation for caption and poster behavior (`docs/renderer-capabilities.md`)

---

## Testing (5 tasks)

Verification and quality assurance.

- [x] T020 [S0403] [P] Write composition schema tests for caption timing, style bounds, mode parsing, poster options, and explicit validation failures (`tests/test_composition_schema.py`)
- [ ] T021 [S0403] [P] Write caption formatting tests for cue ordering, newline handling, SRT/WebVTT/ASS escaping, and deterministic sidecar bytes (`tests/test_caption_formats.py`)
- [ ] T022 [S0403] [P] Write caption finishing and poster option tests for FFmpeg command construction, timeout handling, bounded diagnostics, and disabled poster mode (`tests/test_caption_finishing.py`)
- [ ] T023 [S0403] Update API, worker, storage URL, webhook, and migration integration tests for caption/poster metadata, sidecar downloads, and failure cleanup (`tests/test_worker_pipeline.py`)
- [ ] T024 [S0403] Run targeted tests, ruff, mypy where feasible, and ASCII validation on all session artifacts (`tests/test_caption_finishing.py`)

---

## Completion Checklist

Before marking session complete:

- [ ] All tasks marked `[x]`
- [ ] All tests passing
- [ ] All files ASCII-encoded
- [ ] implementation-notes.md updated
- [ ] Ready for the validate workflow step

---

## Next Steps

Run the implement workflow step to begin AI-led implementation.
