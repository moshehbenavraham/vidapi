# Task Checklist

**Session ID**: `phase03-session04-limits-resource-controls-and-asset-security-hardening`
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

- [x] T001 [S0304] Verify current limit, auth, rate-limit, SSRF, subprocess, and workspace coverage before changing behavior (`app/core/config.py`)
- [x] T002 [S0304] Create the session scaffolds for request limits, composition limits, queue admission, and focused tests (`app/services/limits.py`)
- [x] T003 [S0304] Review existing client, settings, storage, Redis, and worker fixtures for isolated limit overrides (`tests/conftest.py`)

---

## Foundation (6 tasks)

Core structures and base implementations.

- [x] T004 [S0304] Add bounded request, composition, asset, queue, workspace, subprocess, and production Redis settings with explicit validation failures (`app/core/config.py`)
- [x] T005 [S0304] [P] Create request body size middleware with early 413 responses and streamed-body enforcement (`app/core/request_limits.py`)
- [x] T006 [S0304] [P] Create pure composition and media limit validators with schema-validated input and explicit error mapping (`app/services/limits.py`)
- [x] T007 [S0304] [P] Create queue admission helper using bounded Redis calls with timeout, retry-after, and failure-path handling (`app/services/queue_admission.py`)
- [x] T008 [S0304] Add documented request-size, limit-exceeded, and queue-saturated response metadata (`app/models/errors.py`)
- [x] T009 [S0304] Add stable limit and request-size error codes plus VidAPI domain errors without leaking internal paths (`app/api/errors.py`)

---

## Implementation (9 tasks)

Main feature implementation.

- [x] T010 [S0304] Wire request body size middleware into app creation before route parsing with explicit loading, empty, error, and oversized states (`app/main.py`)
- [x] T011 [S0304] Enforce direct render composition limits before persistence or enqueue with schema-validated input and explicit error mapping (`app/api/routes_renders.py`)
- [x] T012 [S0304] Enforce template create and update composition limits with authorization preserved at the router boundary (`app/api/routes_templates.py`)
- [x] T013 [S0304] Enforce expanded template render limits before persistence or enqueue with idempotency protection and compensation on failure (`app/api/routes_templates.py`)
- [x] T014 [S0304] Enforce queue depth admission for direct render submissions with bounded Redis calls and clear 429 responses (`app/api/routes_renders.py`)
- [x] T015 [S0304] Enforce queue depth admission for template render submissions with bounded Redis calls and clear 429 responses (`app/api/routes_templates.py`)
- [x] T016 [S0304] Apply ffprobe media duration, resolution, and stream-count limits after SSRF, redirect, MIME, and size validation (`app/services/asset_service.py`)
- [x] T017 [S0304] Harden Editly, ffprobe, poster, and audio subprocess timeout paths with cleanup on scope exit for all acquired resources (`app/renderers/editly.py`)
- [x] T018 [S0304] Implement orphan workspace cleanup with active-render protection, TTL checks, and workspace-root containment (`app/workers/workspace.py`)

---

## Testing (4 tasks)

Verification and quality assurance.

- [x] T019 [S0304] [P] Write unit tests for settings validation, composition limits, media limits, and request-size middleware (`tests/test_limits.py`)
- [x] T020 [S0304] Write API hardening tests for oversized bodies, over-limit render/template submissions, and queue saturation (`tests/test_api_hardening.py`)
- [x] T021 [S0304] [P] Extend asset, SSRF redirect, subprocess timeout, and media metadata regression tests (`tests/test_asset_security.py`)
- [x] T022 [S0304] Write workspace orphan cleanup tests, run targeted suites, and validate ASCII encoding on changed files (`tests/test_workspace.py`)

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
