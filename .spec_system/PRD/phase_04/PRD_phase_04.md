# PRD Phase 04: Advanced Rendering

**Status**: In Progress
**Sessions**: 6 (initial estimate)
**Estimated Duration**: 12-24 days

**Progress**: 2/6 sessions (33%)

---

## Overview

Expand VidAPI's creative ceiling and renderer performance options while preserving the public JSON API and existing Editly-backed behavior. Phase 04 adds explicit renderer capability validation, more output formats and presets, timed text and poster controls, advanced transitions, a constrained native FFmpeg renderer path, and a HyperFrames adapter for HTML/CSS/GSAP-heavy compositions.

---

## Progress Tracker

| Session | Name | Status | Est. Tasks | Validated |
|---------|------|--------|------------|-----------|
| 01 | Renderer Capability Registry | Completed | ~18 | 2026-05-05 |
| 02 | Output Formats and Presets | Completed | ~20 | 2026-05-05 |
| 03 | Captions and Poster Customization | Not Started | ~18 | - |
| 04 | Advanced Transitions and Feature Validation | Not Started | ~18 | - |
| 05 | Native FFmpeg Renderer Subset | Not Started | ~22 | - |
| 06 | HyperFrames Renderer Adapter | Not Started | ~22 | - |

---

## Completed Sessions

- Session 01: Renderer Capability Registry
- Session 02: Output Formats and Presets

---

## Upcoming Sessions

- Session 03: Captions and Poster Customization

---

## Objectives

1. Make renderer selection, output support, and unsupported feature errors explicit and testable.
2. Add advanced render outputs and finishing controls without changing existing API contracts.
3. Introduce native FFmpeg and HyperFrames renderer paths behind the existing renderer protocol.

---

## Prerequisites

- Phase 03 completed (Production Hardening)
- Editly renderer, async worker, storage adapters, authentication, limits, and observability are operational
- Existing render, template, webhook, storage, and production stack tests are passing before new renderer paths are added

---

## Technical Considerations

### Architecture
- Keep route handlers and high-level services independent from renderer internals.
- Add capability checks before compile/render so unsupported combinations fail with clear validation errors.
- Preserve Editly as the default renderer until native FFmpeg and HyperFrames compatibility tests prove supported subsets.
- Keep artifact URL resolution centralized for new output types, posters, and webhook payloads.

### Technologies
- Existing renderer protocol and worker orchestration
- FFmpeg and ffprobe for native rendering, transcodes, image sequences, posters, captions, and transition filters
- HyperFrames through a renderer adapter for browser-native HTML/CSS/GSAP output
- Pydantic v2 models for renderer, output, preset, captions, and feature validation
- Existing storage, metrics, logs, and webhook systems

### Risks
- Renderer behavior drift can break deterministic outputs: mitigate with capability matrices and compatibility tests for each renderer path.
- Output format expansion can fragment artifact handling: mitigate by routing all artifacts through existing storage and URL resolution services.
- Native FFmpeg filter graphs can become brittle: keep the initial subset narrow and reject unsupported features explicitly.
- HyperFrames may add browser runtime and sandboxing concerns: isolate adapter invocation and keep public schemas renderer-independent.

### Relevant Considerations
- [P03] **Migration-managed schema startup**: Any new persisted output metadata, caption model, or renderer state must update runtime metadata and migrations together.
- [P03] **Centralized artifact URL resolution**: New outputs, posters, and image sequences must use the same resolver as existing downloads and webhook payloads.
- [P03] **Redaction discipline**: Renderer diagnostics and browser/FFmpeg logs must avoid exposing secrets or raw user payloads.
- [P03] **Guardrail tuning is deployment-specific**: New formats, sequences, and renderer paths must respect duration, resolution, asset, queue, and subprocess limits.
- [P02] **Replay metadata (`replay.json`)**: Every renderer path should capture enough command and environment metadata for reproducible debugging.

---

## Success Criteria

Phase complete when:
- [ ] All 6 sessions completed
- [ ] Renderer selection works through the same protocol for Editly, native FFmpeg, and HyperFrames
- [ ] Existing Editly-backed renders keep passing without public API regressions
- [ ] GIF, WebM, PNG sequence, preset, caption, poster, and transition features are validated and covered by focused tests
- [ ] Unsupported renderer-feature combinations return clear validation errors
- [ ] New artifacts are stored, exposed, logged, and reported through existing storage, download, webhook, and metrics patterns

---

## Dependencies

### Depends On
- Phase 03: Production Hardening

### Enables
- Broader renderer compatibility, richer template output, and future public release hardening
