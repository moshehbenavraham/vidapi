# Session 01: Renderer Capability Registry

**Session ID**: `phase04-session01-renderer-capability-registry`
**Status**: Completed
**Estimated Tasks**: ~18
**Estimated Duration**: 2-4 hours

---

## Objective

Add an explicit renderer capability registry and selection path so VidAPI can validate renderer-feature combinations before compile/render while preserving Editly as the default renderer.

---

## Scope

### In Scope (MVP)
- Renderer capability model for supported assets, outputs, transitions, captions, and poster options
- Explicit `renderer` request handling for `editly`, `auto`, and future renderer names
- Clear validation errors for unsupported renderer-feature combinations
- Compatibility tests proving existing Editly behavior remains the default
- Metrics/log fields that identify selected renderer without leaking payloads

### Out of Scope
- Native FFmpeg renderer implementation
- HyperFrames renderer implementation
- New output formats beyond registry declarations
- Browser or FFmpeg runtime sandboxing changes

---

## Prerequisites

- [ ] Phase 03 completed
- [ ] Existing Editly renderer path and worker tests pass
- [ ] Current composition and output schemas are stable

---

## Deliverables

1. Renderer capability registry and validation helpers
2. Explicit renderer selection flow for API and worker paths
3. Stable unsupported-feature error model
4. Tests covering default Editly selection and invalid renderer requests
5. Documentation notes for renderer behavior and future adapters

---

## Success Criteria

- [ ] Requests without `renderer` continue to use Editly-compatible behavior
- [ ] Requests with unsupported renderer names fail before job execution
- [ ] Unsupported feature combinations fail with stable machine-readable errors
- [ ] Renderer selection is visible in logs and metrics without raw payload leakage
