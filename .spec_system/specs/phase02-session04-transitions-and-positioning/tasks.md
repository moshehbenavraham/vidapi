# Task Checklist

**Session ID**: `phase02-session04-transitions-and-positioning`
**Total Tasks**: 18
**Estimated Duration**: 2-3 hours
**Created**: 2026-05-05

---

## Legend

- `[x]` = Completed
- `[ ]` = Pending
- `[P]` = Parallelizable (can run with other [P] tasks)
- `[SNNMM]` = Session reference (NN=phase number, MM=session number)
- `TNNN` = Task ID

---

## Progress Summary

| Category | Total | Done | Remaining |
|----------|-------|------|-----------|
| Setup | 2 | 2 | 0 |
| Foundation | 5 | 5 | 0 |
| Implementation | 7 | 7 | 0 |
| Testing | 4 | 4 | 0 |
| **Total** | **18** | **18** | **0** |

---

## Setup (2 tasks)

Initial configuration and environment preparation.

- [x] T001 [S0204] Verify prerequisites met: confirm 457+ tests pass, Editly renderer operational, segment compiler functional (`tests/`)
- [x] T002 [S0204] Review Editly documentation for layer position properties and clip-level transition format to confirm mapping targets (`app/renderers/editly.py`)

---

## Foundation (5 tasks)

Core structures and base implementations.

- [x] T003 [S0204] Replace free-form Transition.name string field with TransitionType StrEnum (fade_in, fade_out, crossfade) and add TransitionPlacement enum (in, out, between) with validation that rejects unsupported values (`app/models/composition.py`)
- [x] T004 [S0204] [P] Create position resolver module with resolve_named_position() that maps all 9 NamedPosition values to (x, y) normalized coordinates relative to output dimensions (`app/renderers/position.py`)
- [x] T005 [S0204] [P] Add resolve_coordinate_position() to position resolver that converts CoordinatePosition + optional Offset to final (x, y) coordinates with boundary handling (`app/renderers/position.py`)
- [x] T006 [S0204] Add resolve_position() dispatcher that accepts Position union type + Offset and returns resolved Editly-compatible position value (`app/renderers/position.py`)
- [x] T007 [S0204] Update Transition model validation to clamp or reject transition duration longer than the clip length with a clear error message (`app/models/composition.py`)

---

## Implementation (7 tasks)

Main feature implementation.

- [x] T008 [S0204] Update map_video_layer() to inject position, opacity, and scale properties into the Editly layer dict using the position resolver (`app/renderers/editly.py`)
- [x] T009 [S0204] Update map_image_layer() to inject position, opacity, and scale properties into the Editly layer dict using the position resolver (`app/renderers/editly.py`)
- [x] T010 [S0204] Update map_text_png_layer() to inject position, opacity, and scale properties into the Editly layer dict using the position resolver (`app/renderers/editly.py`)
- [x] T011 [S0204] Update map_color_layer() to inject opacity into the Editly layer dict (`app/renderers/editly.py`)
- [x] T012 [S0204] Update assemble_editly_spec() to emit clip-level transition property for fadeIn and fadeOut directives with duration from Transition model (`app/renderers/editly.py`)
- [x] T013 [S0204] Implement crossfade detection in assemble_editly_spec(): identify sequential clips on the same track and emit crossfade transition at the segment boundary with state reset or revalidation on re-entry (`app/renderers/editly.py`)
- [x] T014 [S0204] Verify backward compatibility: ensure assemble_editly_spec() produces identical output for compositions without position/offset/transition fields (`app/renderers/editly.py`)

---

## Testing (4 tasks)

Verification and quality assurance.

- [x] T015 [S0204] [P] Write unit tests for position resolver: all 9 named positions at 1920x1080 and 1080x1920, coordinate positions with and without offsets, boundary values (`tests/test_position_resolver.py`)
- [x] T016 [S0204] [P] Write unit tests for transition validation and emission: TransitionType enum validation, fadeIn/fadeOut/crossfade in Editly spec output, rejection of unsupported names, duration clamping (`tests/test_transitions.py`)
- [x] T017 [S0204] Add integration tests to test_editly_compiler.py: positioned layers produce correct Editly JSON, transitions on clips produce valid spec, crossfade between sequential clips, backward compat with existing fixtures (`tests/test_editly_compiler.py`)
- [x] T018 [S0204] Run full test suite and verify all tests passing with no regressions, validate ASCII encoding on all new and modified files (`tests/`)

---

## Completion Checklist

Before marking session complete:

- [x] All tasks marked `[x]`
- [x] All tests passing
- [x] All files ASCII-encoded
- [x] implementation-notes.md updated
- [x] Ready for the validate workflow step

---

## Next Steps

Run the validate workflow step to verify session completeness.
