# Session 02: Composition Schema and DB Models

**Session ID**: `phase00-session02-composition-schema-and-db-models`
**Status**: Not Started
**Estimated Tasks**: ~15-20
**Estimated Duration**: 2-4 hours

---

## Objective

Define the VidAPI JSON composition schema with Pydantic v2 discriminated unions and implement the render database model with SQLite persistence so render jobs can be created, tracked, and queried.

---

## Scope

### In Scope (MVP)
- Pydantic v2 composition models: Composition, Timeline, Track, Clip, Output
- Asset type discriminated unions: video, image, text, audio, color
- Position, Offset, Transition, Transform models
- Output model with format, dimensions, resolution presets, fps, quality
- Render DB model with SQLModel: id, status, progress, stage, timestamps, paths, error fields
- SQLite database session setup with aiosqlite
- Alembic initial migration
- Render status enum matching the state machine
- Schema validation tests for valid and invalid compositions

### Out of Scope
- Asset fetching and resolution (Session 03)
- Storage adapter (Session 03)
- Renderer implementation (Session 04)
- API route handlers (Session 05)
- HTML asset type (deferred to Phase 04)

---

## Prerequisites

- [ ] Session 01 completed (project skeleton exists)

---

## Deliverables

1. Pydantic v2 models in app/models/composition.py covering all MVP asset types
2. Output model with resolution presets and quality mapping
3. Render model in app/db/models.py with full state machine fields
4. SQLite async session factory in app/db/session.py
5. Alembic configuration and initial migration
6. Render status enum with allowed transitions
7. Comprehensive schema validation tests in tests/

---

## Success Criteria

- [ ] Valid VidAPI JSON compositions parse without errors
- [ ] Invalid compositions (missing fields, bad types, unknown assets) raise validation errors
- [ ] Render records can be created, read, and updated in SQLite
- [ ] Status transitions follow the defined state machine
- [ ] Resolution presets resolve to correct width/height for each aspect ratio
- [ ] Alembic migration applies and rolls back cleanly
