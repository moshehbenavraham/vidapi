# Session 04: Transitions and Positioning

**Session ID**: `phase02-session04-transitions-and-positioning`
**Status**: Not Started
**Estimated Tasks**: ~16
**Estimated Duration**: 2-3 hours

---

## Objective

Extend the composition schema and segment compiler to support named positions, coordinate offsets, and basic fade/crossfade transitions so clients can create more expressive video compositions.

---

## Scope

### In Scope (MVP)
- Named position enum: top, bottom, left, right, center, top-left, top-right, bottom-left, bottom-right
- Offset model: relative x/y adjustment from named position
- Position and offset mapping to Editly layer positioning
- Transition model: name (fadeIn, fadeOut, crossfade), duration
- Fade in/out transitions on individual clips
- Crossfade transitions between sequential clips on the same track
- Segment compiler updates to emit Editly transition directives
- Pydantic model updates for Position, Offset, and Transition types
- Validation: reject unsupported transition types with clear errors
- Composition schema backward compatibility (position/offset/transition remain optional)

### Out of Scope
- Complex transitions (wipe, slide, zoom, dissolve)
- Keyframed transforms or animations
- Per-renderer transition capability discovery API
- Position/transition support for non-Editly renderers

---

## Prerequisites

- [ ] Session 03 complete (webhook system)
- [ ] Segment compiler operational from Phase 01

---

## Deliverables

1. Position enum and Offset Pydantic models
2. Transition Pydantic model with validation
3. Editly position mapping logic
4. Segment compiler transition emission
5. Updated composition schema with backward compatibility

---

## Success Criteria

- [ ] Named positions correctly place clips in rendered output
- [ ] Offsets adjust position relative to named anchor
- [ ] fadeIn/fadeOut transitions render on individual clips
- [ ] Crossfade transitions work between sequential clips
- [ ] Unsupported transition types produce validation errors
- [ ] Existing compositions without positions/transitions still render correctly
