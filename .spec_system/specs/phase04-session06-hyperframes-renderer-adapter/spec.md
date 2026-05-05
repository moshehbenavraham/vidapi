# Session Specification

**Session ID**: `phase04-session06-hyperframes-renderer-adapter`
**Phase**: 04 - Advanced Rendering
**Status**: Not Started
**Created**: 2026-05-05

---

## 1. Session Overview

This session adds a HyperFrames renderer adapter for HTML/CSS/GSAP-heavy VidAPI compositions. The adapter must sit behind the existing renderer protocol so clients continue to submit VidAPI-owned JSON rather than HyperFrames-native project files or renderer internals.

The session completes Phase 04 by making `hyperframes` an available renderer for compositions that contain HTML assets. Explicit `renderer: "hyperframes"` requests should be validated, compiled into a workspace-local HyperFrames project, rendered through a bounded browser/Node subprocess, and published through the same artifact, storage, webhook, log, metric, and status paths used by Editly and native FFmpeg.

The initial implementation should keep the public schema narrow and security-conscious. HTML support should focus on inline composition blocks with local resolved media references, deterministic dimensions/timing, redacted replay metadata, remote-script rejection, timeout/cancellation handling, and compatibility tests that prove Editly and native FFmpeg behavior remains unchanged.

---

## 2. Objectives

1. Add a VidAPI `html` asset shape and renderer capability rules that route HTML-backed compositions to HyperFrames.
2. Implement a HyperFrames renderer adapter that compiles VidAPI composition data into workspace-local HyperFrames artifacts.
3. Execute HyperFrames rendering through the existing renderer protocol with logs, replay metadata, timeout, cancellation, and bounded failure handling.
4. Cover explicit and auto HyperFrames selection, unsupported combinations, artifact persistence, and existing renderer regressions with focused tests and documentation.

---

## 3. Prerequisites

### Required Sessions
- [x] `phase04-session01-renderer-capability-registry` - Provides renderer selection and unsupported-feature validation.
- [x] `phase04-session02-output-formats-and-presets` - Provides shared finishing for MP4 intermediates and requested output formats.
- [x] `phase04-session05-native-ffmpeg-renderer-subset` - Provides the second renderer registration pattern and renderer-neutral progress plumbing.
- [x] `phase02-session02-template-variables-and-rendering` - Provides template expansion before renderer compile.
- [x] `phase01-session03-progress-tracking-and-cancellation` - Provides worker progress and cooperative cancellation behavior.
- [x] `phase03-session04-limits-resource-controls-and-asset-security-hardening` - Provides request, asset, and render guardrails.

### Required Tools/Knowledge
- Existing `RendererProtocol`, `CompiledRender`, and `RenderArtifact` contracts.
- Current capability registry and selection flow in `app/renderers/capabilities.py`.
- Current asset resolver and text/media staging behavior in `app/services/render_service.py`.
- HyperFrames CLI/producer model from `references/hyperframes`: HTML root attributes, clip data attributes, deterministic rendering, Node 22+, FFmpeg, and browser capture.
- Existing subprocess timeout, cancellation, progress, and log bounding patterns from Editly and native FFmpeg renderers.

### Environment Requirements
- Python 3.11+ dependencies installed with `uv`.
- Node.js 22+ available for HyperFrames, or installed in the worker image during this session.
- FFmpeg and ffprobe available through configured settings.
- Chromium/browser dependencies available in the worker runtime.
- No database migration is expected; renderer selection and artifact paths already persist on render records.

---

## 4. Scope

### In Scope (MVP)
- Client can submit inline `asset.type: "html"` clips through the VidAPI composition schema - add strict Pydantic validation for HTML, CSS, optional inline script, dimensions, and local media references.
- Client can explicitly request `renderer: "hyperframes"` for HTML-backed compositions - mark HyperFrames available and reject unsupported renderer-feature combinations with bounded machine-readable errors.
- System can auto-select HyperFrames when `renderer` is omitted or `auto` and an HTML asset is present - preserve Editly as the default for non-HTML compositions.
- System can compile VidAPI HTML, image, video, audio, text, and color clips into a workspace-local HyperFrames project - write `index.html`, local asset references, `compiled.hyperframes.json`, and `replay.json`.
- Worker can invoke HyperFrames through the renderer protocol - use configured binary/timeout, stream logs, report coarse progress where available, enforce cancellation, and clean up acquired browser/subprocess resources.
- System can store output, logs, compiled spec, replay metadata, posters, and downstream requested formats through existing storage and finishing paths.
- System can reject remote scripts, remote stylesheet imports, unsupported transitions, unsupported poster/caption controls, unresolved assets, and unsafe HTML project shapes before expensive browser work.
- Tests cover schema validation, capability selection, auto-selection, compile artifacts, subprocess success/failure/cancellation, worker integration, and regression coverage for existing Editly/native paths.
- Documentation explains supported HTML/CSS/GSAP use cases, renderer selection behavior, runtime dependencies, security boundaries, and replay artifacts.

### Out of Scope (Deferred)
- Browser-based editing UI - *Reason: PRD explicitly excludes a VidAPI editor UI.*
- Exposing HyperFrames-native schemas directly in public API responses - *Reason: VidAPI must keep a renderer-independent public contract.*
- Arbitrary remote script execution - *Reason: remote code in browser renders creates security and determinism risk.*
- Full CSS/animation authoring framework documentation - *Reason: link to HyperFrames docs and document VidAPI-specific boundaries only.*
- HyperFrames Docker mode orchestration inside each render - *Reason: worker container already provides the render isolation boundary for this MVP adapter.*
- Full alpha-channel WebM preservation - *Reason: initial adapter should produce the MP4 intermediate expected by shared finishing.*
- New database tables, migrations, or persisted renderer state - *Reason: current render records already persist renderer and artifact paths.*

---

## 5. Technical Approach

### Architecture

Add `HtmlAsset` to the composition schema and keep it renderer-neutral. The asset should accept an inline HTML fragment or document body, optional CSS, optional inline script for deterministic animation setup, and optional metadata needed by the compiler. Validation should bound payload size, reject blank content, reject remote script/style imports, and keep asset media references explicit so normal asset resolution can control remote fetches.

Update the capability registry so `hyperframes` is available for the supported MVP subset. Selection should preserve current behavior for non-HTML renders: omitted, `null`, and `auto` still choose Editly unless HTML assets are present. Explicit `editly` or `ffmpeg-native` with HTML assets should fail with `UNSUPPORTED_RENDERER_FEATURE`; explicit `hyperframes` without HTML can be rejected or allowed only for a documented minimal supported subset.

Create a `HyperFramesRenderer` under `app/renderers/hyperframes.py` and keep compile-time project generation in a focused helper such as `app/renderers/hyperframes_compiler.py`. Compile should build deterministic workspace files, map VidAPI timing/z-order to HyperFrames `data-*` attributes, copy or reference resolved local media paths, write `compiled.hyperframes.json`, and write redacted `replay.json` with command, args, environment facts, input files, output path, timeout, and browser dependency hints.

Render should mirror existing subprocess patterns: call the configured HyperFrames CLI or wrapper with `asyncio.create_subprocess_exec`, stream stdout/stderr without unbounded buffering, map progress lines when possible, poll the worker cancel check, terminate with the configured grace period, verify output, write bounded logs, classify missing binary, Node version failure, timeout, non-zero exit, cancellation, and missing output, and return a normal `RenderArtifact`. The adapter should produce an MP4 intermediate so shared finishing continues to handle WebM, GIF, PNG sequence, posters, storage, and webhooks.

### Design Patterns
- Renderer protocol implementation: keep HyperFrames interchangeable with Editly and native FFmpeg.
- Boundary validation: reject unsafe HTML and unsupported features before browser work.
- Workspace-local project generation: make the compiled HyperFrames project replayable and deterministic.
- Redacted replay metadata: capture enough operational facts without raw secrets or full payload dumps.
- Line-streamed subprocess output: preserve cancellation and log limits for long renders.
- Centralized artifact publication: route all outputs through existing storage and URL resolution helpers.

### Technology Stack
- Python 3.11+
- FastAPI 0.136.1 / Starlette 0.52.1
- Pydantic 2.11.2
- HyperFrames CLI/producer through Node.js 22+
- FFmpeg 6+
- pytest + pytest-asyncio, ruff, mypy

---

## 6. Deliverables

### Files to Create
| File | Purpose | Est. Lines |
|------|---------|------------|
| `app/renderers/hyperframes.py` | HyperFrames renderer protocol implementation, subprocess execution, replay metadata, and error classification | ~360 |
| `app/renderers/hyperframes_compiler.py` | HTML asset validation helpers, project artifact writer, asset mapping, and deterministic compiled spec builder | ~360 |
| `docs/hyperframes-renderer.md` | Public and operator documentation for HyperFrames support, security boundaries, and runtime dependencies | ~180 |
| `tests/test_hyperframes_renderer.py` | Unit and integration-style tests for schema support, compile artifacts, replay metadata, and subprocess behavior | ~380 |
| `tests/fixtures/hyperframes_simple_composition.json` | Short HTML-backed fixture for HyperFrames tests | ~100 |

### Files to Modify
| File | Changes | Est. Lines |
|------|---------|------------|
| `app/models/composition.py` | Add `HtmlAsset` to the discriminated union with strict field validation and bounded inline content | ~140 |
| `app/renderers/capabilities.py` | Mark HyperFrames available, add HTML asset support, implement HTML-aware auto-selection, and reject unsupported combinations | ~160 |
| `app/renderers/__init__.py` | Register and export `HyperFramesRenderer` | ~30 |
| `app/core/config.py` | Add HyperFrames binary, timeout, and payload/runtime guardrail settings | ~70 |
| `app/services/limits.py` | Enforce HTML payload size and renderer-specific limit checks with schema-validated input | ~80 |
| `Dockerfile.worker` | Upgrade worker Node runtime to Node 22+ and install/configure the HyperFrames CLI/browser dependencies | ~45 |
| `tests/test_composition_schema.py` | Cover HTML asset validation, unsafe remote script rejection, and existing asset discrimination behavior | ~160 |
| `tests/test_renderer_capabilities.py` | Cover HyperFrames availability, auto-selection, and unsupported renderer-feature errors | ~180 |
| `tests/test_renderer_selection_flow.py` | Cover API and render-service selection for explicit and auto HyperFrames requests | ~160 |
| `tests/test_worker_pipeline.py` | Cover worker pre-flight and progress/cancellation plumbing for HyperFrames with mocked renderer execution | ~120 |
| `tests/test_config.py` | Cover HyperFrames settings defaults and validation bounds | ~80 |
| `README.md` | Document HyperFrames renderer selection and runtime requirements | ~60 |
| `docs/ARCHITECTURE.md` | Add HyperFrames compile/render flow behind the renderer protocol | ~80 |
| `docs/renderer-capabilities.md` | Add HyperFrames support matrix and error semantics | ~90 |

---

## 7. Success Criteria

### Functional Requirements
- [ ] `asset.type: "html"` validates through the public composition schema with bounded inline HTML/CSS/script fields.
- [ ] `renderer: "hyperframes"` resolves to an available renderer and persists `hyperframes` on render records.
- [ ] `renderer: "auto"` or omitted renderer selects HyperFrames when an HTML asset is present and selects Editly for non-HTML compositions.
- [ ] HyperFrames compile writes deterministic `index.html`, `compiled.hyperframes.json`, and `replay.json` artifacts.
- [ ] HyperFrames render execution streams logs, respects timeout, terminates on cancellation, and returns a normal MP4 intermediate.
- [ ] Unsupported renderer-feature combinations fail before expensive browser work with stable, redacted error context.
- [ ] Existing Editly and native FFmpeg paths keep passing unchanged.

### Testing Requirements
- [ ] Unit tests written and passing for HTML asset schema validation and unsafe content rejection.
- [ ] Unit tests written and passing for capability selection, auto-selection, and unsupported-feature context.
- [ ] Unit tests written and passing for deterministic HyperFrames project generation and replay metadata.
- [ ] Renderer subprocess behavior tests written and passing for success, timeout, non-zero exit, missing binary, Node version/runtime failure, missing output, and cancellation where practical.
- [ ] Manual testing completed for one short HTML-backed render where Node 22, HyperFrames, Chromium, and FFmpeg are available locally or in the worker container.

### Non-Functional Requirements
- [ ] HyperFrames output and compiled artifacts are deterministic for identical input JSON and resolved asset paths.
- [ ] Browser and renderer subprocess logs are bounded by `max_subprocess_stderr_bytes`.
- [ ] Replay metadata avoids raw secrets, callback URLs, unredacted asset URLs, and full user payload dumps.
- [ ] Remote script and stylesheet imports are rejected by default.
- [ ] HyperFrames adapter consumes resolved local assets and does not fetch media directly outside the existing asset resolver.
- [ ] Runtime dependencies are documented and represented in the worker image.

### Quality Gates
- [ ] All files ASCII-encoded.
- [ ] Unix LF line endings.
- [ ] Code follows project conventions.

---

## 8. Implementation Notes

### Key Considerations
- `HYPERFRAMES_CAPABILITY` currently exists but is unavailable and has empty support sets.
- `get_renderer()` currently registers Editly and native FFmpeg only; HyperFrames must be added without weakening unsupported renderer behavior.
- HyperFrames requires Node.js 22+, while `Dockerfile.worker` currently uses a Node 20 base for Editly. The worker image should move to Node 22+ if compatibility checks pass.
- `Composition` currently rejects `asset.type: "html"`; this session must update the discriminated union and tests.
- `validate_renderer_capabilities()` currently uses `select_renderer()` without composition-aware auto-selection. HTML-aware auto-selection should be implemented in one shared path used by API and worker pre-flight.
- The adapter should produce an MP4 intermediate first so shared output finishing, storage URL resolution, webhooks, metrics, and default poster generation remain centralized.
- No Alembic migration is expected because renderer metadata and artifact paths already exist on render records.

### Potential Challenges
- HyperFrames CLI output and progress events may differ from FFmpeg/Editly stderr; progress mapping should be coarse and optional rather than brittle.
- Browser rendering can hang on readiness gates or media loading; enforce render timeout, cancel polling, and process cleanup consistently.
- Allowing useful GSAP while blocking arbitrary remote scripts requires explicit MVP boundaries. Inline deterministic script can be allowed, but remote `src`, `@import`, and external stylesheet loads should be rejected by default.
- Package/runtime installation may affect the worker image size and startup behavior; keep the first adapter CLI-based and document the dependency.
- HTML asset support can accidentally broaden SSRF or filesystem exposure; all media references should flow through the existing asset resolver or be rejected.

### Relevant Considerations
- [P03] **Guardrail tuning is deployment-specific**: HyperFrames must respect existing render duration, resolution, asset, queue, request body, and subprocess limits.
- [P03] **Redaction discipline**: Browser logs, replay metadata, errors, and docs must avoid raw secrets and full payload dumps.
- [P03] **Centralized artifact URL resolution**: HyperFrames outputs and logs must publish through existing storage and URL paths.
- [P02] **Replay metadata (`replay.json`)**: Capture command, args, environment facts, workspace, and input paths for reproducible debugging.
- [P01] **Cooperative cancellation via DB flag**: Continue to rely on worker-provided cancel checks during subprocess streaming.
- [P01] **`proc.communicate()` for long renders**: Avoid buffering long browser or renderer logs; stream line by line.

### Behavioral Quality Focus
Checklist active: Yes
Top behavioral risks for this session:
- HTML content executes unexpected remote code or bypasses the existing asset resolver.
- Auto-selection routes non-HTML renders away from Editly and breaks existing behavior.
- Browser or Node subprocess hangs, buffers unbounded logs, or ignores cancellation.
- Replay metadata or logs expose callback URLs, secret-bearing asset URLs, raw HTML payloads, or full renderer specs.
- Worker image dependency changes break Editly or native FFmpeg runtime behavior.

---

## 9. Testing Strategy

### Unit Tests
- Validate `HtmlAsset` acceptance for bounded inline HTML/CSS/script and rejection of blank HTML, remote script `src`, remote stylesheet `href`, CSS `@import`, oversized payloads, and unsafe media references.
- Validate HyperFrames capability selection for explicit `hyperframes`, auto-selection with HTML assets, Editly fallback for non-HTML, and rejection of HTML assets for Editly/native requests.
- Validate deterministic HyperFrames project files, root composition attributes, clip data attributes, local asset references, z-order, dimensions, fps, output path, and replay metadata JSON.
- Validate error classification for missing binary, Node version/runtime failure, timeout, non-zero exit, missing output, and cancellation.

### Integration Tests
- Submit explicit and auto HyperFrames render requests through the API and verify selection, persistence, and renderer resolution.
- Run `RenderService.stage_resolve_and_compile()` with a mocked HyperFrames renderer or compile-only project and verify compiled/replay artifact publication.
- Verify worker pre-flight handles HyperFrames capability errors before workspace creation and uses progress/cancellation callbacks when execution proceeds.
- Verify Editly and native FFmpeg capability tests still pass with the new HTML asset type.

### Manual Testing
- Render a short HTML-backed composition with an inline title animation and local image asset using `renderer: "hyperframes"`.
- Submit the same HTML-backed composition with `renderer: "editly"` and confirm a bounded `UNSUPPORTED_RENDERER_FEATURE` error.
- Submit a non-HTML composition with omitted renderer and confirm Editly remains selected.

### Edge Cases
- HTML asset with remote `<script src>` or stylesheet `@import`.
- HTML composition with unresolved media references.
- Multiple tracks containing HTML and non-HTML clips.
- `renderer: "auto"` with mixed HTML and image/video/text clips.
- HyperFrames binary missing, Node version too old, browser launch failure, timeout, user cancellation, and output file missing.

---

## 10. Dependencies

### External Libraries
- HyperFrames CLI/runtime through Node.js 22+.
- Chromium/browser dependency transitively required by HyperFrames/Puppeteer.
- No new Python runtime dependency expected.

### Other Sessions
- **Depends on**: `phase04-session01-renderer-capability-registry`, `phase04-session02-output-formats-and-presets`, `phase04-session05-native-ffmpeg-renderer-subset`, `phase02-session02-template-variables-and-rendering`, `phase01-session03-progress-tracking-and-cancellation`, `phase03-session04-limits-resource-controls-and-asset-security-hardening`
- **Depended by**: Phase 04 completion and the next phase transition workflow (`audit` after validation/updateprd completes Phase 04)

---

## Next Steps

Run the implement workflow step to begin AI-led implementation.
