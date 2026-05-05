# Session 06: HyperFrames Renderer Adapter

**Session ID**: `phase04-session06-hyperframes-renderer-adapter`
**Status**: Not Started
**Estimated Tasks**: ~22
**Estimated Duration**: 3-4 hours

---

## Objective

Add a HyperFrames renderer adapter for HTML/CSS/GSAP-heavy compositions while keeping HyperFrames internals behind VidAPI's renderer protocol and public schema.

---

## Scope

### In Scope (MVP)
- HTML asset or composition block schema accepted only through explicit capability rules
- HyperFrames renderer adapter implementing compile/render behind the existing protocol
- Compilation from VidAPI composition/template data into HyperFrames-compatible artifacts
- Browser/runtime invocation with logs, replay metadata, timeout, cancellation, and resource limits
- Focused tests for renderer selection, unsupported combinations, and successful HTML-backed render fixtures

### Out of Scope
- Browser-based editing UI
- Exposing HyperFrames-native schemas directly as the VidAPI public API
- Arbitrary remote script execution
- Full CSS/animation authoring framework documentation

---

## Prerequisites

- [ ] Session 01 completed
- [ ] Session 02 completed
- [ ] Session 05 completed
- [ ] Runtime packaging approach for browser/HyperFrames dependencies is defined

---

## Deliverables

1. HyperFrames-capable schema and capability validation
2. HyperFrames renderer adapter and compiler artifact writer
3. Worker integration with replay metadata, logs, timeout, cancellation, and resource limits
4. Tests for explicit HyperFrames selection and auto-selection when HTML blocks are present
5. Documentation for supported HTML/CSS/GSAP use cases and security boundaries

---

## Success Criteria

- [ ] HTML-backed compositions route to HyperFrames through the renderer protocol
- [ ] HyperFrames internals are not exposed through public API responses
- [ ] Runtime logs and replay metadata are captured and redacted consistently
- [ ] Existing Editly and native FFmpeg paths keep passing their compatibility tests
