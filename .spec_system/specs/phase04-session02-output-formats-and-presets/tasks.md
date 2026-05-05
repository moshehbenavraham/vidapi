# Task Checklist

**Session ID**: `phase04-session02-output-formats-and-presets`
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
| Implementation | 11 | 11 | 0 |
| Testing | 4 | 4 | 0 |
| **Total** | **24** | **24** | **0** |

---

## Setup (3 tasks)

Initial configuration and environment preparation.

- [x] T001 [S0402] Verify current renderer capability, output schema, storage URL, download, webhook, worker, and migration behavior before changing output handling (`app/renderers/capabilities.py`)
- [x] T002 [S0402] [P] Create output formats documentation scaffold for presets, format support, and artifact metadata (`docs/output-formats.md`)
- [x] T003 [S0402] [P] Confirm current Alembic head and note that no seed fixture update is required for render output metadata (`tests/test_alembic_migrations.py`)

---

## Foundation (6 tasks)

Core structures and base implementations.

- [x] T004 [S0402] Add output preset enum, preset field, and deterministic normalization with explicit width and height precedence (`app/models/composition.py`)
- [x] T005 [S0402] [P] Create render output metadata models for API responses and webhook payloads with types matching declared contracts (`app/models/output_artifacts.py`)
- [x] T006 [S0402] Create render output metadata Alembic migration with upgrade and downgrade paths (`alembic/versions/006_add_render_output_metadata.py`)
- [x] T007 [S0402] Add render output metadata columns to runtime SQLModel metadata in alignment with the migration (`app/db/models.py`)
- [x] T008 [S0402] Add CRUD helpers for output metadata persistence with transaction boundaries and deterministic failure-path behavior (`app/db/render_crud.py`)
- [x] T009 [S0402] [P] Create output format planning helpers for suffixes, media types, filenames, preset defaults, and PNG sequence manifests (`app/services/output_formats.py`)

---

## Implementation (11 tasks)

Main feature implementation.

- [x] T010 [S0402] Update renderer capability validation to allow implemented output formats and return bounded format error context with schema-validated input and explicit error mapping (`app/renderers/capabilities.py`)
- [x] T011 [S0402] Enforce preset and format-specific duration, fps, resolution, and PNG frame-count guardrails before queue admission (`app/services/limits.py`)
- [x] T012 [S0402] Keep Editly MP4 intermediate output deterministic and include requested output metadata in replay data without leaking raw payloads (`app/renderers/editly.py`)
- [x] T013 [S0402] Implement FFmpeg output post-processing for WebM, GIF, and PNG sequence with timeout, bounded stderr, cleanup on scope exit for all acquired resources, and explicit failure mapping (`app/services/output_postprocess.py`)
- [x] T014 [S0402] Wire render service output finishing, artifact publishing, metadata persistence, and compensation on failure into the existing stage flow (`app/services/render_service.py`)
- [x] T015 [S0402] Extend shared storage artifact descriptors for format-aware output media types, safe suffixes, and manifest artifact naming (`app/storage/base.py`)
- [x] T016 [S0402] Update local storage publishing for deterministic output filenames, sequence manifests, content types, and atomic file writes (`app/storage/local.py`)
- [x] T017 [S0402] Update S3-compatible artifact publishing for deterministic output filenames, sequence manifests, content types, and retry/backoff failure handling (`app/storage/s3.py`)
- [x] T018 [S0402] Update centralized storage URL resolution for output metadata and manifest-related URLs across proxy, signed, and public modes (`app/storage/urls.py`)
- [x] T019 [S0402] Update render status and download routes to use persisted output metadata, format-aware media types, and explicit error mapping (`app/api/routes_renders.py`)
- [x] T020 [S0402] Update webhook payload construction to include output metadata through shared URL resolution without duplicating URL logic (`app/services/webhook_service.py`)

---

## Testing (4 tasks)

Verification and quality assurance.

- [x] T021 [S0402] [P] Write unit tests for output preset parsing, explicit dimension precedence, format planning, media types, filenames, and guardrail failures (`tests/test_output_formats.py`)
- [x] T022 [S0402] [P] Write unit tests for FFmpeg post-processing command construction, timeout handling, bounded diagnostics, and PNG sequence manifest behavior (`tests/test_output_postprocess.py`)
- [x] T023 [S0402] Update integration tests for API render submission, worker output finishing, storage URL modes, webhook metadata, migration chain, and MP4 backward compatibility (`tests/test_api_renders.py`)
- [x] T024 [S0402] Run targeted tests, ruff, mypy where feasible, and ASCII validation on all session artifacts (`tests/test_output_formats.py`)

---

## Completion Checklist

Before marking session complete:

- [x] All tasks marked `[x]`
- [x] All tests passing
- [x] All files ASCII-encoded
- [x] implementation-notes.md updated
- [x] Ready for the validate workflow step

---

## Next Steps

Run the validate workflow step to verify session completeness.
