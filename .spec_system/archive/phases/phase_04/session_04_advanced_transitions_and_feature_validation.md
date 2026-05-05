# Session 04: Advanced Transitions and Feature Validation

**Session ID**: `phase04-session04-advanced-transitions-and-feature-validation`
**Status**: Not Started
**Estimated Tasks**: ~18
**Estimated Duration**: 2-4 hours

---

## Objective

Extend transition support beyond basic fades while enforcing renderer-specific capability validation for transition timing, overlap, and fallback behavior.

---

## Scope

### In Scope (MVP)
- Additional transition schema values for renderer-supported effects
- Validation for transition duration, overlap, clip boundaries, and track interactions
- Editly compiler mapping for supported transition subset
- Capability checks that reject unsupported transitions for each renderer
- Focused compiler tests for transition edge cases and deterministic output specs

### Out of Scope
- Custom shader or arbitrary FFmpeg filter injection
- Keyframed transforms outside transition scope
- HyperFrames implementation
- Native FFmpeg renderer implementation

---

## Prerequisites

- [ ] Session 01 completed
- [ ] Existing fade and crossfade behavior remains covered by tests
- [ ] Segment compiler fixtures are available for overlapping clips and gaps

---

## Deliverables

1. Expanded transition schema and validation rules
2. Renderer capability mapping for supported transition effects
3. Editly compiler updates for the supported subset
4. Tests for valid transitions, invalid overlaps, and unsupported renderer combinations
5. Documentation updates for supported transition behavior

---

## Success Criteria

- [ ] Existing fade and crossfade renders remain compatible
- [ ] New supported transitions compile deterministically
- [ ] Invalid transition timing fails before renderer invocation
- [ ] Unsupported renderer-transition combinations return clear validation errors
