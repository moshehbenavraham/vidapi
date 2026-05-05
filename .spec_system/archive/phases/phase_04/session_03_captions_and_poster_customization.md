# Session 03: Captions and Poster Customization

**Session ID**: `phase04-session03-captions-and-poster-customization`
**Status**: Not Started
**Estimated Tasks**: ~18
**Estimated Duration**: 2-4 hours

---

## Objective

Add timed caption/subtitle rendering and configurable poster generation as output finishing controls that work through the existing render pipeline.

---

## Scope

### In Scope (MVP)
- Caption/subtitle schema for timed text cues
- Validation for cue timing, duration, style bounds, and renderer support
- FFmpeg-backed subtitle burn-in or sidecar generation for supported output types
- Poster customization by timestamp, default frame, and disabled poster mode where allowed
- Artifact persistence for captions, sidecars, and customized posters

### Out of Scope
- Speech-to-text caption generation
- Rich karaoke or word-level caption animation
- Browser editor or caption authoring UI
- Per-language localization workflow

---

## Prerequisites

- [ ] Session 01 completed
- [ ] Session 02 completed
- [ ] Poster generation and storage artifacts from previous phases are stable

---

## Deliverables

1. Caption and poster option schemas
2. Caption timing and style validation
3. Worker finishing steps for captions and poster customization
4. Artifact storage and status response updates
5. Tests for caption timing, poster modes, and output artifact persistence

---

## Success Criteria

- [ ] Invalid caption timing fails before rendering
- [ ] Supported captions render or export deterministically
- [ ] Poster timestamp customization produces the requested frame within bounds
- [ ] Existing default poster behavior remains unchanged when options are omitted
