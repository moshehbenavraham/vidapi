# Task Checklist

**Session ID**: `phase02-session05-audio-polish-and-hardening`
**Total Tasks**: 19
**Estimated Duration**: 2-3 hours
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
| Setup | 2 | 2 | 0 |
| Foundation | 5 | 5 | 0 |
| Implementation | 8 | 8 | 0 |
| Testing | 4 | 4 | 0 |
| **Total** | **19** | **19** | **0** |

---

## Setup (2 tasks)

Initial configuration and environment preparation.

- [x] T001 [S0205] Verify prerequisites met: Phase 02 session 04 complete, audio mixer tests present, rate-limit middleware registered, and current test baseline known (`tests/`)
- [x] T002 [S0205] Review FastAPI/Starlette dependency compatibility for Starlette `>=0.49.1` CVE remediation (`pyproject.toml`)

---

## Foundation (5 tasks)

Core structures and base implementations.

- [x] T003 [S0205] Extend audio mix data structures with total duration, fade metadata, and optional normalization flags (`app/services/audio_mixer.py`)
- [x] T004 [S0205] Add duration-aware audio plan construction that clips or skips detached sources extending beyond final render duration with deterministic ordering (`app/renderers/editly.py`)
- [x] T005 [S0205] Add production-safe CORS defaults and audio normalization settings with isolated settings override support (`app/core/config.py`)
- [x] T006 [S0205] [P] Create shared API error response models for documented OpenAPI failures (`app/models/errors.py`)
- [x] T007 [S0205] Update dependency constraints so Starlette resolves to `>=0.49.1` through a compatible FastAPI version (`pyproject.toml`)

---

## Implementation (8 tasks)

Main feature implementation.

- [x] T008 [S0205] Implement FFmpeg `afade` graph generation for soundtrack `fadeIn`, `fadeOut`, and `fadeInFadeOut` with duration caps and explicit failure-path handling (`app/services/audio_mixer.py`)
- [x] T009 [S0205] Add optional final audio normalization filter generation controlled by settings without changing default loudness unless enabled (`app/services/audio_mixer.py`)
- [x] T010 [S0205] Trigger the external audio plan for soundtrack effects or normalization while preserving Editly `audioTracks` for simple soundtrack-only compositions (`app/renderers/editly.py`)
- [x] T011 [S0205] Replace partial soundtrack effect mapping with complete external-audio behavior and no double-mixing in compiled Editly specs (`app/renderers/editly.py`)
- [x] T012 [S0205] Tighten production CORS setup so wildcard origins are rejected or disabled outside debug/local mode with deterministic startup behavior (`app/main.py`)
- [x] T013 [S0205] Tighten render-create rate limiting for `POST /v1/renders` with bounded client key extraction, health exemptions, structured 429 payloads, and `Retry-After` (`app/core/rate_limit.py`)
- [x] T014 [S0205] Add documented OpenAPI response metadata for render endpoints, including validation, rate-limit, queue-unavailable, not-found, conflict, and download errors (`app/api/routes_renders.py`)
- [x] T015 [S0205] Add documented OpenAPI response metadata for Phase 02 template endpoints with consistent error envelopes for validation, deleted, not-found, and queue-unavailable cases (`app/api/routes_templates.py`)

---

## Testing (4 tasks)

Verification and quality assurance.

- [x] T016 [S0205] [P] Write unit tests for fade filters, normalization filters, clipped durations, empty plans, and invalid audio plans (`tests/test_audio_mixer.py`)
- [x] T017 [S0205] [P] Write compiler tests for soundtrack effect audio plans, detached audio clipping/skipping, and backward-compatible Editly `audioTracks` output (`tests/test_editly_compiler.py`)
- [x] T018 [S0205] [P] Write API hardening tests for render rate limiting, production CORS behavior, and OpenAPI error metadata (`tests/test_api_hardening.py`)
- [x] T019 [S0205] Run full quality gates: test suite, ruff format/check, mypy, dependency resolution check, and ASCII/LF validation (`tests/`)

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

Run the implement workflow step to begin AI-led implementation.
