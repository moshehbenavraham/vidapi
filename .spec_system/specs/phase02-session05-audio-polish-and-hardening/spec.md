# Session Specification

**Session ID**: `phase02-session05-audio-polish-and-hardening`
**Phase**: 02 - Templates and Polish
**Status**: Not Started
**Created**: 2026-05-05

---

## 1. Session Overview

This session closes Phase 02 by hardening the API and renderer behavior that now sits around template-driven renders. The current codebase already supports template CRUD, template expansion, webhook delivery, transitions, positioning, multi-track rendering, detached audio clips, and global rate-limit middleware. The remaining Phase 02 stub focuses on making those pieces more reliable before the project moves into production hardening.

The main rendering work is audio polish: soundtrack fade effects must work consistently, detached audio clips must not crash when they overlap or extend past the final video duration, and final audio normalization must be explicit and testable. The current audio post-processing path only activates when detached audio clips exist, so soundtrack effects need a clear path through the FFmpeg mixer without regressing the existing Editly `audioTracks` behavior for simple soundtracks.

The API hardening work wires the existing rate-limit behavior into tests, restricts CORS for production-safe defaults, remediates the Starlette CVE backlog by updating dependency constraints, and improves OpenAPI/error documentation for Phase 02 endpoints. This produces a well-documented, safer Phase 02 baseline for the subsequent Production Hardening phase.

---

## 2. Objectives

1. Support soundtrack `fadeIn`, `fadeOut`, and `fadeInFadeOut` effects through a deterministic audio post-processing path
2. Harden detached audio timing so overlapping clips and clips extending past video duration mix without crashes
3. Enforce production-safe render submission rate limiting and CORS configuration with documented error behavior
4. Remediate the Starlette CVE backlog and document Phase 02 endpoint responses in OpenAPI

---

## 3. Prerequisites

### Required Sessions
- [x] `phase02-session04-transitions-and-positioning` - Named positions, offsets, and transitions are complete
- [x] `phase02-session03-webhook-delivery-system` - Webhook delivery and delivery-attempt storage are complete
- [x] `phase01-session04-multi-track-and-audio-mixing` - Detached audio collection and FFmpeg post-processing are operational
- [x] `phase01-session05-docker-compose-stack` - API, worker, Redis, and Docker Compose development stack are operational

### Required Tools/Knowledge
- FFmpeg audio filters: `atrim`, `adelay`, `volume`, `afade`, `amix`, and optional `dynaudnorm`
- FastAPI route metadata and generated OpenAPI schema
- Starlette/FastAPI dependency compatibility for upgrading Starlette to `>=0.49.1`
- Existing custom `RateLimitMiddleware` behavior

### Environment Requirements
- Python 3.11+ with project dependencies installed
- FFmpeg available for integration/manual audio verification
- Node.js and Editly available for renderer integration testing
- Redis available only when testing async queue behavior

---

## 4. Scope

### In Scope (MVP)
- Soundtrack fade effects: Apply `fadeIn`, `fadeOut`, and `fadeInFadeOut` without double-mixing soundtrack audio
- Audio normalization: Make final mix normalization explicit through settings and FFmpeg filter generation
- Audio validation: Preserve Pydantic volume bounds and add tests for invalid volumes and effect values
- Detached audio timing: Clip or skip detached audio sources that extend past total video duration
- Detached audio overlap: Keep deterministic source ordering and verify FFmpeg graph generation for overlapping sources
- Render rate limiting: Verify and tighten `POST /v1/renders` rate-limit behavior, including structured `429` responses and `Retry-After`
- CORS configuration: Replace production wildcard behavior with explicit production-safe defaults and validation
- Dependency remediation: Update FastAPI/Starlette constraints so Starlette resolves to `>=0.49.1`
- OpenAPI documentation: Add response metadata and error schemas for render and Phase 02 template endpoints
- Error response consistency audit: Normalize documented error shapes where route handlers currently return ad hoc payloads

### Out of Scope (Deferred)
- Advanced audio ducking or per-clip volume keyframes - *Reason: Deferred beyond Phase 02 audio polish*
- PostgreSQL migrations - *Reason: Phase 03 production hardening*
- API key authentication - *Reason: Phase 03 production hardening*
- S3-compatible storage adapter - *Reason: Phase 03 production hardening*
- New webhook retry semantics - *Reason: Existing Phase 02 webhook delivery behavior is already implemented*

---

## 5. Technical Approach

### Architecture
Audio polish stays behind the renderer/service boundary. `app/renderers/editly.py` remains responsible for translating VidAPI compositions into Editly specs and deciding when an external audio post-processing plan is required. `app/services/audio_mixer.py` remains responsible for FFmpeg command and filter graph generation. Soundtrack-only compositions without effects should keep using Editly `audioTracks`; compositions with soundtrack effects, detached audio clips, or normalization should move to the external audio plan so all final audio behavior is owned by one tested path.

API hardening stays at the FastAPI boundary. `app/core/config.py` owns settings defaults and validation, `app/main.py` wires middleware with those settings, `app/core/rate_limit.py` owns request limiting behavior, and route modules own OpenAPI response metadata. Error response documentation should use shared models/helpers so render, template, and queue-related failures describe the same envelope.

### Design Patterns
- Pure filter-graph construction: Keep FFmpeg graph creation as pure string construction with focused unit tests
- Boundary validation: Enforce CORS and rate-limit decisions at the app/middleware boundary closest to incoming requests
- Backward-compatible adapter: Use Editly `audioTracks` for the simple existing path and FFmpeg only when new behavior requires it
- Documented errors: Centralize error response models so route decorators do not drift across endpoints

### Technology Stack
- Python 3.11+ with Pydantic v2 and FastAPI
- Starlette `>=0.49.1` through a compatible FastAPI dependency set
- FFmpeg 6+ for audio post-processing
- pytest + pytest-asyncio for unit and API tests

---

## 6. Deliverables

### Files to Create
| File | Purpose | Est. Lines |
|------|---------|------------|
| `app/models/errors.py` | Shared OpenAPI error response models for documented API failures | ~70 |
| `tests/test_api_hardening.py` | API tests for render rate limiting, production CORS behavior, and OpenAPI error metadata | ~180 |

### Files to Modify
| File | Changes | Est. Lines Changed |
|------|---------|--------------------|
| `app/services/audio_mixer.py` | Add fade metadata, duration-aware filters, optional normalization, and explicit graph tests support | ~100 |
| `app/renderers/editly.py` | Trigger external audio plan for soundtrack effects/normalization and cap detached audio timing | ~90 |
| `app/models/composition.py` | Preserve audio volume/effect validation and add schema examples if needed for docs | ~20 |
| `app/core/config.py` | Add production-safe CORS defaults and audio normalization settings | ~40 |
| `app/core/rate_limit.py` | Tighten render-create limiting behavior and structured 429 payloads | ~30 |
| `app/main.py` | Apply CORS settings validation and middleware ordering behavior | ~25 |
| `app/api/routes_renders.py` | Add documented error responses for render create/list/status/download/cancel endpoints | ~40 |
| `app/api/routes_templates.py` | Add documented error responses for template CRUD and template render endpoints | ~60 |
| `pyproject.toml` | Upgrade dependency constraints for Starlette CVE remediation | ~10 |
| `tests/test_audio_mixer.py` | Cover fade filters, normalization filters, clipped durations, and invalid empty plans | ~120 |
| `tests/test_editly_compiler.py` | Cover external audio plan activation and backward-compatible simple soundtrack output | ~90 |
| `tests/test_composition_schema.py` | Cover invalid audio effect and volume validation paths | ~30 |
| `tests/test_config.py` | Cover CORS and audio normalization settings defaults/overrides | ~50 |

---

## 7. Success Criteria

### Functional Requirements
- [ ] Soundtrack `fadeIn` produces a bounded FFmpeg `afade=t=in` filter
- [ ] Soundtrack `fadeOut` produces a bounded FFmpeg `afade=t=out` filter based on final video duration
- [ ] Soundtrack `fadeInFadeOut` applies both fades without producing negative or overlapping fade windows
- [ ] Soundtrack-only compositions without effects continue to emit Editly `audioTracks`
- [ ] Soundtrack effects activate the external audio plan and avoid double-mixing
- [ ] Detached audio clips starting before the end but extending past final duration are trimmed to remaining duration
- [ ] Detached audio clips starting at or after final duration are skipped without crashing
- [ ] Overlapping detached audio sources produce deterministic `amix` input ordering
- [ ] `POST /v1/renders` returns `429` plus `Retry-After` after the configured limit is exceeded
- [ ] Production CORS configuration does not default to wildcard origins
- [ ] Starlette resolves to `>=0.49.1`
- [ ] Phase 02 endpoints expose documented OpenAPI response metadata for common errors

### Testing Requirements
- [ ] Unit tests written and passing for audio filter graph generation
- [ ] Unit tests written and passing for composition audio validation
- [ ] API tests written and passing for rate limit and CORS behavior
- [ ] OpenAPI schema tests written and passing for documented Phase 02 responses
- [ ] Full test suite passes after dependency changes

### Non-Functional Requirements
- [ ] No regression in existing render compile behavior for compositions without audio effects
- [ ] Audio graph generation remains deterministic for identical inputs
- [ ] Dependency changes do not introduce import-time settings or DB engine side effects

### Quality Gates
- [ ] All files ASCII-encoded
- [ ] Unix LF line endings
- [ ] Code follows project conventions
- [ ] Ruff formatting and linting pass
- [ ] Mypy strict checks pass

---

## 8. Implementation Notes

### Key Considerations
- `AudioAsset.effect` already exists in the public schema, so this session should implement the existing contract rather than adding a new public field
- `map_soundtrack()` currently has partial effect handling; this should become either complete for the simple Editly path or explicitly bypassed when the FFmpeg path is required
- `compile_audio_plan()` needs total composition duration to trim or skip detached sources safely
- `RateLimitMiddleware` is already globally registered; implementation should prove and tighten its behavior instead of introducing a second limiter
- Starlette `>=0.49.1` may require a compatible FastAPI upgrade because the current FastAPI pin may constrain Starlette below the required version

### Potential Challenges
- Fade-out timing: The fade start time must be computed from total output duration and capped for very short renders
- Audio normalization defaults: Enabling normalization by default can alter output loudness; keep behavior configurable and test the filter output
- Dependency compatibility: FastAPI and Starlette pins must resolve together; tests should catch route/middleware behavior changes
- CORS behavior in tests: Settings are cached through `get_settings()`, so tests must isolate settings overrides without mutating global state across cases

### Relevant Considerations
- [P01] **No rate limiting on POST /v1/renders**: Existing middleware must be verified and tightened for the render create path
- [P01] **Starlette CVE backlog**: Upgrade Starlette to `>=0.49.1` through compatible dependency constraints
- [P00] **CORS wildcard origins**: Replace wildcard defaults for production deployments
- [P01] **Two-pass audio overhead**: Only activate FFmpeg post-processing when effects, detached audio, or normalization require it
- [P01] **Conditional audio path**: Preserve the zero-regression Editly `audioTracks` path when no external audio behavior is needed
- [P00] **Single renderer implemented**: Audio polish targets the Editly renderer plus FFmpeg post-processing only

### Behavioral Quality Focus
Checklist active: Yes
Top behavioral risks for this session:
- State-mutating render submissions must not bypass rate limiting under duplicate or burst requests
- External FFmpeg calls must retain explicit timeout and failure-path handling
- Production CORS settings must fail predictably when unsafe wildcard origins are configured
- Endpoint error responses must stay stable enough for clients to handle validation, queue, and rate-limit failures

---

## 9. Testing Strategy

### Unit Tests
- `build_mix_filter_graph()` with fade-in, fade-out, combined fade, volume, delay, trim, and normalization
- `compile_audio_plan()` with total-duration clipping, zero-duration skips, overlapping sources, and resolver mapping
- `AudioAsset` validation for volume bounds and unsupported effect values
- `Settings` defaults and env overrides for CORS and audio normalization

### Integration Tests
- Editly compile path for soundtrack-only no effect keeps `audioTracks`
- Editly compile path for soundtrack effects returns an `AudioMixPlan` and omits Editly `audioTracks`
- Render create API returns 429 and `Retry-After` after limit exhaustion
- OpenAPI schema includes documented 422/429/503 responses for Phase 02 routes

### Manual Testing
- Render a short composition with `fadeIn`, `fadeOut`, and `fadeInFadeOut` soundtrack effects
- Render a composition with overlapping detached audio clips and confirm output completes
- Start the API with production-like CORS settings and verify unsafe wildcard behavior is rejected or disabled

### Edge Cases
- Final video duration shorter than the configured fade window
- Detached audio clip starts exactly at final duration
- Detached audio clip has `trim` plus length that exceeds final duration
- Soundtrack effect with no detached audio
- Burst render submissions from the same forwarded client IP
- Missing or unreachable Redis in async render mode

---

## 10. Dependencies

### External Libraries
- FastAPI: upgrade as needed for Starlette compatibility
- Starlette: `>=0.49.1`
- No new runtime library is expected beyond compatible web stack upgrades

### Other Sessions
- **Depends on**: `phase02-session04-transitions-and-positioning`, `phase02-session03-webhook-delivery-system`, `phase01-session04-multi-track-and-audio-mixing`
- **Depended by**: Phase 03 Production Hardening

---

## Next Steps

Run the implement workflow step to begin AI-led implementation.
