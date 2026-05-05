# Task Checklist

**Session ID**: `phase04-session05-native-ffmpeg-renderer-subset`
**Total Tasks**: 22
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
| Implementation | 9 | 9 | 0 |
| Testing | 4 | 4 | 0 |
| **Total** | **22** | **22** | **0** |

---

## Setup (3 tasks)

Initial configuration and environment preparation.

- [x] T001 [S0405] Verify current renderer protocol, registry, capability validation, worker progress, and FFmpeg helper behavior before adding native support (`app/renderers/base.py`)
- [x] T002 [S0405] [P] Create native FFmpeg renderer documentation scaffold covering support matrix, request example, rejection behavior, and replay artifacts (`docs/native-ffmpeg-renderer.md`)
- [x] T003 [S0405] [P] Confirm no migration or seed update is required because renderer selection already persists on render records (`tests/test_alembic_migrations.py`)

---

## Foundation (6 tasks)

Core structures and base implementations.

- [x] T004 [S0405] Create renderer-neutral timeline duration and visual clip ordering helpers with types matching declared composition contracts (`app/renderers/timeline.py`)
- [x] T005 [S0405] Create native subset validation types and unsupported-feature issues with schema-validated input and explicit error mapping (`app/renderers/native_ffmpeg_subset.py`)
- [x] T006 [S0405] Build deterministic native render plan objects for resolved assets, output settings, z-order, fit, position, opacity, and simple timing (`app/renderers/native_ffmpeg_subset.py`)
- [x] T007 [S0405] Build native FFmpeg command and filter graph helpers with bounded inputs, deterministic labels, and no client-supplied filters (`app/renderers/native_ffmpeg_subset.py`)
- [x] T008 [S0405] Add native renderer replay metadata and JSON serialization helpers without raw secrets or full user payload dumps (`app/renderers/native_ffmpeg.py`)
- [x] T009 [S0405] Update renderer capability declarations for available `ffmpeg-native` support and bounded unsupported-feature context (`app/renderers/capabilities.py`)

---

## Implementation (9 tasks)

Main feature implementation.

- [x] T010 [S0405] Register and export `NativeFfmpegRenderer` in the renderer registry with availability enforced through existing selection rules (`app/renderers/__init__.py`)
- [x] T011 [S0405] Implement `NativeFfmpegRenderer.compile` to validate the subset, consume resolved assets, and write `compiled.ffmpeg.json` and `replay.json` (`app/renderers/native_ffmpeg.py`)
- [x] T012 [S0405] Implement `NativeFfmpegRenderer.render` with line-streamed stderr, timeout, cancellation checks, and cleanup on scope exit for all acquired resources (`app/renderers/native_ffmpeg.py`)
- [x] T013 [S0405] Classify native FFmpeg failures for missing binary, timeout, non-zero exit, missing output, and cancellation with explicit error mapping (`app/renderers/native_ffmpeg.py`)
- [x] T014 [S0405] Wire visual layer planning for color, image, video, and text PNG clips with deterministic overlay ordering and exhaustive asset-type handling (`app/renderers/native_ffmpeg_subset.py`)
- [x] T015 [S0405] Wire soundtrack and detached audio planning with delay, trim, volume, amix fallback, and failure-path handling (`app/renderers/native_ffmpeg_subset.py`)
- [x] T016 [S0405] Replace worker progress duration import with the renderer-neutral timeline helper without changing status transition behavior (`app/workers/render_worker.py`)
- [x] T017 [S0405] Update README and architecture docs for explicit native renderer selection, MP4 intermediate behavior, and subset boundaries (`README.md`)
- [x] T018 [S0405] Update renderer capability and native renderer docs with support matrix, examples, and redacted error semantics (`docs/renderer-capabilities.md`)

---

## Testing (4 tasks)

Verification and quality assurance.

- [x] T019 [S0405] [P] Write native subset validation and command/filter graph tests for supported clips, unsupported features, deterministic labels, and replay metadata (`tests/test_native_ffmpeg_renderer.py`)
- [x] T020 [S0405] [P] Write renderer capability tests for native availability, supported outputs, unsupported transitions/captions/posters, and redacted context (`tests/test_renderer_capabilities.py`)
- [x] T021 [S0405] Write API, render-service, and worker selection tests for explicit native requests with schema-validated input and explicit error mapping (`tests/test_renderer_selection_flow.py`)
- [x] T022 [S0405] Run targeted tests, ruff, mypy where feasible, and ASCII validation on all session artifacts (`tests/test_native_ffmpeg_renderer.py`)

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
