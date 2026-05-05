# Session Specification

**Session ID**: `phase04-session05-native-ffmpeg-renderer-subset`
**Phase**: 04 - Advanced Rendering
**Status**: Not Started
**Created**: 2026-05-05

---

## 1. Session Overview

This session introduces a constrained `ffmpeg-native` renderer behind VidAPI's existing renderer protocol. The goal is not full schema parity with Editly; it is a fast, deterministic path for simple high-throughput timelines that use supported media assets, text PNG overlays, fit modes, simple timing, soundtrack, and detached audio clips.

The native renderer will preserve the public JSON composition contract and the current worker/service orchestration. Clients should be able to explicitly request `ffmpeg-native` for supported compositions, while unsupported transitions, caption requests, poster controls, transforms, or complex timeline features fail through the same bounded renderer capability and validation errors used by the rest of Phase 04.

The implementation should reuse existing asset resolution, text PNG generation, output finishing, progress parsing, cancellation checks, log bounding, and replay artifact patterns. The renderer produces a deterministic MP4 intermediate, then existing shared finishing can handle WebM, GIF, PNG sequence, storage, webhooks, metrics, and default poster generation where capability rules allow them.

---

## 2. Objectives

1. Add an available `ffmpeg-native` renderer implementation that satisfies the existing `RendererProtocol`.
2. Compile a narrow supported timeline subset into deterministic FFmpeg command and filter graph artifacts.
3. Execute the native FFmpeg subprocess with progress parsing, timeout, cancellation, bounded logs, and replay metadata.
4. Validate and document unsupported native-renderer combinations with clear, redacted error context.

---

## 3. Prerequisites

### Required Sessions
- [x] `phase04-session01-renderer-capability-registry` - Provides renderer selection and unsupported-feature validation.
- [x] `phase04-session02-output-formats-and-presets` - Provides shared output finishing for MP4 intermediates.
- [x] `phase04-session04-advanced-transitions-and-feature-validation` - Provides explicit transition semantics and capability validation.
- [x] `phase01-session03-progress-tracking-and-cancellation` - Provides worker progress and cooperative cancellation behavior.
- [x] `phase01-session04-multi-track-and-audio-mixing` - Provides audio timing patterns and FFmpeg audio filter helpers.
- [x] `phase00-session03-storage-and-asset-service` - Provides remote/local/text asset resolution before renderer compile.

### Required Tools/Knowledge
- Existing `RendererProtocol`, `CompiledRender`, and `RenderArtifact` contracts.
- Current renderer capability registry in `app/renderers/capabilities.py`.
- FFmpeg `filter_complex` construction for scale, pad/crop, overlay, concat, trim, audio delay, audio trim, and amix.
- Existing FFmpeg stderr progress parser in `app/services/ffmpeg_progress.py`.
- Existing subprocess timeout, cancellation, and log bounding patterns from `app/renderers/editly.py` and finishing services.

### Environment Requirements
- Python 3.11+ dependencies installed with `uv`.
- FFmpeg available through `settings.ffmpeg_bin`.
- Existing targeted tests runnable with pytest.
- No database migration or seed update is expected; renderer metadata already exists on render records.

---

## 4. Scope

### In Scope (MVP)
- Client can explicitly request `renderer: "ffmpeg-native"` for supported simple timelines - implement availability, registry wiring, and API admission behavior.
- System can compile color, image, video, and text PNG clips into a deterministic FFmpeg filter graph - use resolved local asset paths and stable input ordering.
- System can apply simple timing, z-order, fit modes, position, opacity, soundtrack, and detached audio clips - keep the subset narrow and explicitly validated.
- Worker can run native FFmpeg renders through the existing renderer protocol - stream stderr line by line with progress, timeout, cancellation, bounded logs, and explicit failure mapping.
- System can store `compiled.ffmpeg.json`, `replay.json`, output, logs, and downstream artifacts using existing render service and storage paths.
- System can reject unsupported native-renderer features before expensive work - transitions, transforms, arbitrary filters, captions, poster controls, unsupported asset types, and unsupported timeline shapes must produce clear errors.
- Tests cover capability selection, subset validation, deterministic command/filter generation, replay metadata, subprocess failure paths, and render-service integration.
- Documentation explains when `ffmpeg-native` is selected, what it supports, and why unsupported requests are rejected.

### Out of Scope (Deferred)
- Full public schema parity with Editly - *Reason: session objective is a constrained high-throughput subset.*
- HyperFrames support - *Reason: Session 06 owns the HyperFrames adapter.*
- Arbitrary FFmpeg filter injection or client-supplied filter graphs - *Reason: unsafe and explicitly excluded by the session stub.*
- Advanced transition implementation in native FFmpeg - *Reason: native transition parity needs separate compatibility work.*
- HTML/CSS layout, browser rendering, or GSAP animation - *Reason: this belongs to HyperFrames.*
- New database tables, migrations, or persisted renderer state - *Reason: renderer selection is already stored on render records.*
- New public API endpoints - *Reason: renderer selection already exists on the composition schema.*

---

## 5. Technical Approach

### Architecture

Add a `NativeFfmpegRenderer` under `app/renderers/native_ffmpeg.py` and register it through the existing renderer registry. The renderer should implement `compile()` by validating the native subset, building an immutable render plan, writing `compiled.ffmpeg.json`, and writing `replay.json` with the exact command, args, environment facts, workspace path, input paths, and timeout settings.

Keep subset validation separate from command execution. A helper module such as `app/renderers/native_ffmpeg_subset.py` should own deterministic plan objects, unsupported-feature detection, field paths, and filter graph generation. This keeps capability-level errors and compiler errors testable without spawning FFmpeg. The native subset should accept resolved local asset paths supplied by `RenderService.stage_resolve_and_compile()`.

`render()` should mirror the Editly subprocess pattern: use `asyncio.create_subprocess_exec`, stream stderr one line at a time, invoke the provided progress callback, poll the provided cancel check, terminate with the configured grace period, bound log output, classify missing binary, timeout, non-zero exit, and missing output, and return a `RenderArtifact`. Shared output post-processing can continue to finish non-MP4 requested outputs from the MP4 intermediate.

### Design Patterns
- Renderer protocol implementation: keep the adapter interchangeable with Editly.
- Explicit subset validation: reject unsupported combinations before subprocess work.
- Immutable render plan: make command and filter graph generation deterministic and unit-testable.
- Boundary validation: enforce renderer support at API admission, worker revalidation, and compile time.
- Line-streamed subprocess output: preserve progress, cancellation, and bounded logs for long renders.
- Replay metadata: make native FFmpeg failures reproducible without exposing raw secrets.

### Technology Stack
- Python 3.11+
- FastAPI 0.136.1 / Starlette 0.52.1
- Pydantic 2.11.2
- FFmpeg 6+
- pytest + pytest-asyncio, ruff, mypy

---

## 6. Deliverables

### Files to Create
| File | Purpose | Est. Lines |
|------|---------|------------|
| `app/renderers/native_ffmpeg.py` | Native FFmpeg renderer protocol implementation, subprocess execution, replay metadata, and error classification | ~360 |
| `app/renderers/native_ffmpeg_subset.py` | Native subset validation, render plan objects, command construction, and deterministic filter graph helpers | ~320 |
| `app/renderers/timeline.py` | Shared renderer-neutral timeline duration and clip ordering helpers | ~90 |
| `docs/native-ffmpeg-renderer.md` | Public and operator documentation for the native renderer subset | ~180 |
| `tests/test_native_ffmpeg_renderer.py` | Unit and integration-style tests for subset validation, command building, replay metadata, and subprocess behavior | ~360 |
| `tests/fixtures/native_ffmpeg_simple_composition.json` | Short supported fixture for native renderer tests | ~80 |

### Files to Modify
| File | Changes | Est. Lines |
|------|---------|------------|
| `app/renderers/capabilities.py` | Mark `ffmpeg-native` available with explicit supported assets, outputs, and unsupported feature behavior | ~90 |
| `app/renderers/__init__.py` | Register and export the native renderer implementation | ~35 |
| `app/renderers/editly.py` | Reuse shared timeline duration helper where appropriate without changing Editly behavior | ~30 |
| `app/workers/render_worker.py` | Use renderer-neutral duration helper for progress denominator | ~20 |
| `tests/test_renderer_capabilities.py` | Cover native availability, supported subset, and redacted unsupported-feature context | ~120 |
| `tests/test_renderer_selection_flow.py` | Cover API selection and render-service resolution for explicit native requests | ~120 |
| `tests/test_worker_pipeline.py` | Cover worker persistence of native renderer selection and progress plumbing with mocked service | ~90 |
| `README.md` | Document explicit native renderer selection and subset limitations | ~50 |
| `docs/ARCHITECTURE.md` | Add native FFmpeg adapter compile/render flow | ~60 |
| `docs/renderer-capabilities.md` | Add native renderer support matrix and error semantics | ~80 |

---

## 7. Success Criteria

### Functional Requirements
- [ ] `renderer: "ffmpeg-native"` resolves to an available renderer and persists `ffmpeg-native` on render records.
- [ ] Supported simple timelines with color, image, video, text PNG overlays, soundtrack, detached audio, fit modes, position, opacity, and simple timing compile successfully.
- [ ] The native renderer writes deterministic `compiled.ffmpeg.json` and `replay.json` artifacts.
- [ ] Native FFmpeg render execution streams stderr, reports progress, respects timeout, and terminates on cancellation.
- [ ] Unsupported transitions, transforms, captions, poster controls, arbitrary filters, and unsupported timeline shapes are rejected before expensive render work.
- [ ] Existing Editly-backed renders, output finishing, captions, posters, webhooks, storage, and worker status transitions continue to pass unchanged.

### Testing Requirements
- [ ] Unit tests written and passing for native subset validation and unsupported-feature field paths.
- [ ] Unit tests written and passing for deterministic command/filter graph generation.
- [ ] Renderer capability and API selection tests written and passing for explicit native requests.
- [ ] Render subprocess behavior tests written and passing for success, timeout, non-zero exit, missing binary, missing output, and cancellation where practical.
- [ ] Manual testing completed for one short native render where FFmpeg is available locally.

### Non-Functional Requirements
- [ ] Native renderer output is deterministic for identical input JSON and asset paths.
- [ ] Subprocess stderr is bounded by `max_subprocess_stderr_bytes`.
- [ ] Replay metadata contains command, args, environment facts, input paths, output path, workspace, and timeout without raw secrets.
- [ ] Unsupported-feature errors include renderer names, feature paths, enum-like requested values, and supported values only.
- [ ] The native path uses existing resolved local assets and does not fetch remote URLs inside the renderer.

### Quality Gates
- [ ] All files ASCII-encoded.
- [ ] Unix LF line endings.
- [ ] Code follows project conventions.

---

## 8. Implementation Notes

### Key Considerations
- `FFMPEG_NATIVE_CAPABILITY` currently exists but is unavailable and has empty support sets.
- `get_renderer()` currently registers only `EditlyRenderer`; native must be added without weakening unsupported renderer behavior.
- `RenderService` already resolves assets and text PNGs before renderer compile; native should consume the provided `asset_path_resolver`.
- `render_worker.py` currently imports `compute_total_duration` from `app.renderers.editly`; use a renderer-neutral helper before native progress plumbing depends on it.
- The native renderer should produce an MP4 intermediate so shared output finishing can keep WebM, GIF, and PNG sequence behavior centralized.
- No Alembic migration is needed because renderer metadata is already stored in the existing render model.

### Potential Challenges
- FFmpeg overlay and concat graphs are sensitive to input ordering, labels, and timestamps; keep the supported plan simple and deterministic.
- Video clips may or may not contain audio streams; soundtrack and detached audio mixing should handle missing video audio without failing unsupported simple renders.
- Cancellation must terminate the FFmpeg process promptly while still writing bounded logs and allowing failure cleanup.
- Capability validation is coarse today, so native-specific semantic rejection may need a focused validator in the compile path and targeted admission tests for explicit native requests.
- Existing output finishing expects a valid MP4 intermediate; native render artifacts must match that contract exactly.

### Relevant Considerations
- [P03] **Guardrail tuning is deployment-specific**: Native FFmpeg must respect existing duration, resolution, asset, queue, and subprocess limits.
- [P03] **Redaction discipline**: Native command logs and capability errors must avoid secrets, callback URLs, and raw payload dumps.
- [P03] **Centralized artifact URL resolution**: Native outputs and logs must publish through existing storage and URL paths.
- [P02] **Pure-function segment compiler**: Keep native plan and filter graph generation stateless and deterministic.
- [P02] **Replay metadata (`replay.json`)**: Capture enough command and environment metadata to reproduce native FFmpeg failures.
- [P01] **Cooperative cancellation via DB flag**: Continue to rely on worker-provided cancel checks during stderr streaming.
- [P01] **`proc.communicate()` for long renders**: Avoid buffering long renders; stream stderr line by line.

### Behavioral Quality Focus
Checklist active: Yes
Top behavioral risks for this session:
- Native renderer accepts a composition it cannot faithfully render and produces silent drift from Editly behavior.
- FFmpeg subprocess hangs, buffers unbounded stderr, or ignores cancellation.
- Replay metadata or logs expose raw secrets, callback URLs, storage paths beyond local workspace facts, or full user payloads.
- Asset paths bypass the existing resolver and reintroduce remote fetch or SSRF risk inside the renderer.
- Existing Editly, output finishing, caption, poster, and worker flows regress while adding native support.

---

## 9. Testing Strategy

### Unit Tests
- Validate native subset acceptance for supported color, image, video, text PNG, soundtrack, detached audio, fit modes, position, opacity, and simple timing.
- Validate native subset rejection for transitions, transforms, captions, poster controls, unsupported asset/timeline shapes, and missing resolved assets.
- Validate deterministic filter graph labels, input ordering, command args, and replay metadata JSON.
- Validate error classification for timeout, missing binary, non-zero exit, missing output, and cancellation.

### Integration Tests
- Submit explicit `ffmpeg-native` render requests through the API and verify selection, persistence, and renderer resolution.
- Run `RenderService.stage_resolve_and_compile()` with a mocked native renderer or real compile-only native plan and verify artifact publication paths.
- Verify worker progress plumbing uses renderer-neutral timeline duration and keeps status transitions unchanged.

### Manual Testing
- Render a short supported two-clip composition with one text overlay and soundtrack using `renderer: "ffmpeg-native"`.
- Submit a native request with an advanced transition and confirm a bounded validation error before queueing or compile.
- Compare output artifact publication and download behavior with an equivalent Editly-backed render.

### Edge Cases
- Timeline with leading gap and background fill.
- Image/text overlay on top of a video clip.
- Soundtrack plus detached audio clip with delay and trim.
- Video asset with trim and fit mode.
- Native request with captions or poster controls.
- FFmpeg binary missing, subprocess timeout, user cancellation, and output file missing.

---

## 10. Dependencies

### External Libraries
- None added.

### Other Sessions
- **Depends on**: `phase04-session01-renderer-capability-registry`, `phase04-session02-output-formats-and-presets`, `phase04-session04-advanced-transitions-and-feature-validation`, `phase01-session03-progress-tracking-and-cancellation`, `phase01-session04-multi-track-and-audio-mixing`
- **Depended by**: `phase04-session06-hyperframes-renderer-adapter`

---

## Next Steps

Run the implement workflow step to begin AI-led implementation.
