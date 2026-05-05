# Task Checklist

**Session ID**: `phase04-session06-hyperframes-renderer-adapter`
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

- [x] T001 [S0406] Verify renderer protocol, registry, asset resolution, worker subprocess, and HyperFrames reference runtime assumptions before adding the adapter (`app/renderers/base.py`)
- [x] T002 [S0406] [P] Create HyperFrames renderer documentation scaffold covering selection, runtime dependencies, security boundaries, and replay artifacts (`docs/hyperframes-renderer.md`)
- [x] T003 [S0406] Confirm no migration or seed update is required because renderer selection and artifact paths already persist on render records (`tests/test_alembic_migrations.py`)

---

## Foundation (6 tasks)

Core structures and base implementations.

- [x] T004 [S0406] Add `HtmlAsset` composition schema support with bounded inline HTML/CSS/script fields and remote script/style rejection (`app/models/composition.py`)
- [x] T005 [S0406] Add HyperFrames settings for binary path, timeout, HTML payload limits, and runtime guardrails with validation bounds (`app/core/config.py`)
- [x] T006 [S0406] Create HyperFrames compiler types and safe HTML project validation with schema-validated input and explicit error mapping (`app/renderers/hyperframes_compiler.py`)
- [x] T007 [S0406] Build deterministic HyperFrames project artifact writer for `index.html`, local asset references, clip data attributes, z-order, and output metadata (`app/renderers/hyperframes_compiler.py`)
- [x] T008 [S0406] Update renderer capability declarations for available `hyperframes`, HTML asset support, and HTML-aware auto-selection without changing non-HTML defaults (`app/renderers/capabilities.py`)
- [x] T009 [S0406] Update render limit validation for HTML payload size and renderer-specific unsupported shapes with bounded context (`app/services/limits.py`)

---

## Implementation (9 tasks)

Main feature implementation.

- [x] T010 [S0406] Register and export `HyperFramesRenderer` in the renderer registry with availability enforced through existing selection rules (`app/renderers/__init__.py`)
- [x] T011 [S0406] Implement HyperFrames replay metadata serialization without raw secrets, callback URLs, asset query strings, or full HTML payload dumps (`app/renderers/hyperframes.py`)
- [x] T012 [S0406] Implement `HyperFramesRenderer.compile` to consume resolved assets and write `compiled.hyperframes.json`, `index.html`, and `replay.json` (`app/renderers/hyperframes.py`)
- [x] T013 [S0406] Implement `HyperFramesRenderer.render` with line-streamed logs, timeout, cancellation checks, and cleanup on scope exit for all acquired resources (`app/renderers/hyperframes.py`)
- [x] T014 [S0406] Classify HyperFrames failures for missing binary, old Node/runtime failure, browser launch failure, timeout, non-zero exit, missing output, and cancellation with explicit error mapping (`app/renderers/hyperframes.py`)
- [x] T015 [S0406] Wire API and render-service selection tests for explicit and auto HyperFrames requests with duplicate validation between admission and worker pre-flight (`tests/test_renderer_selection_flow.py`)
- [x] T016 [S0406] Update worker image packaging for Node 22+, HyperFrames CLI availability, browser dependencies, and Editly compatibility (`Dockerfile.worker`)
- [x] T017 [S0406] Update README and architecture docs for HyperFrames renderer selection, MP4 intermediate behavior, runtime dependencies, and security boundaries (`README.md`)
- [x] T018 [S0406] Update renderer capability docs with HyperFrames support matrix, auto-selection rules, and redacted unsupported-feature semantics (`docs/renderer-capabilities.md`)

---

## Testing (4 tasks)

Verification and quality assurance.

- [x] T019 [S0406] [P] Write composition schema and capability tests for HTML asset validation, auto-selection, unsupported renderers, and redacted context (`tests/test_composition_schema.py`)
- [x] T020 [S0406] [P] Write HyperFrames compiler and renderer tests for project artifacts, replay metadata, subprocess success, timeout, failure, cancellation, and missing output (`tests/test_hyperframes_renderer.py`)
- [x] T021 [S0406] Write worker pipeline tests for HyperFrames pre-flight, renderer persistence, progress callback, cancellation callback, and failure mapping (`tests/test_worker_pipeline.py`)
- [x] T022 [S0406] Run targeted tests, ruff, mypy where feasible, and ASCII validation on all session artifacts (`tests/test_hyperframes_renderer.py`)

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
