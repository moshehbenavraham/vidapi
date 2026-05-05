# Task Checklist

**Session ID**: `phase01-session04-multi-track-and-audio-mixing`
**Total Tasks**: 20
**Estimated Duration**: 2.5-3.5 hours
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
| Foundation | 4 | 4 | 0 |
| Implementation | 9 | 9 | 0 |
| Testing | 5 | 5 | 0 |
| **Total** | **20** | **20** | **0** |

---

## Setup (2 tasks)

Initial configuration and environment preparation.

- [x] T001 [S0104] Verify prerequisites met -- 308 tests passing, FFmpeg available, venv active
- [x] T002 [S0104] Add ffmpeg_bin and audio_mix_timeout_seconds settings to config (`app/core/config.py`)

---

## Foundation (4 tasks)

Core data structures and helpers for audio mixing.

- [x] T003 [S0104] [P] Create AudioClipRef dataclass for detached audio clip references with start, length, trim, volume, src (`app/renderers/editly.py`)
- [x] T004 [S0104] [P] Create AudioSource, AudioMixPlan dataclasses and AudioMixError exception in new audio mixer module (`app/services/audio_mixer.py`)
- [x] T005 [S0104] Implement collect_track_audio() -- walk composition tracks, extract AudioAsset clips with timeline positions, volume, and trim (`app/renderers/editly.py`)
- [x] T006 [S0104] Extend CompiledRender with optional audio_mix_plan field (`app/renderers/base.py`)

---

## Implementation (9 tasks)

Main feature implementation.

- [x] T007 [S0104] Implement build_mix_filter_graph() -- construct FFmpeg complex filter string from AudioMixPlan with adelay, atrim, volume, amix filters, with deterministic ordering (`app/services/audio_mixer.py`)
- [x] T008 [S0104] Implement mix_audio() async subprocess -- invoke FFmpeg to combine rendered video with audio sources, copy video stream, with timeout and failure-path handling (`app/services/audio_mixer.py`)
- [x] T009 [S0104] Implement needs_audio_mixing() predicate and compile_audio_plan() -- extract soundtrack and detached audio into AudioMixPlan, resolve conditional path (Editly audioTracks vs FFmpeg post-process) (`app/renderers/editly.py`)
- [x] T010 [S0104] Update assemble_editly_spec() to accept use_external_audio flag -- when True, exclude soundtrack from Editly audioTracks to avoid double-mixing (`app/renderers/editly.py`)
- [x] T011 [S0104] Update EditlyRenderer.compile() to call compile_audio_plan(), set use_external_audio, and attach plan to CompiledRender (`app/renderers/editly.py`)
- [x] T012 [S0104] Add post_process_audio() method to EditlyRenderer -- calls mix_audio() when CompiledRender has an audio plan, replaces output file with mixed version (`app/renderers/editly.py`)
- [x] T013 [S0104] Update EditlyRenderer.render() to call post_process_audio() after subprocess completes, with cleanup on scope exit for intermediate file (`app/renderers/editly.py`)
- [x] T014 [S0104] Wire audio asset resolution in _resolve_all_assets() for track-level AudioAsset clips (`app/services/render_service.py`)
- [x] T015 [S0104] Update render_service.stage_resolve_and_compile() to pass resolved audio paths into audio plan via asset_path_resolver (`app/services/render_service.py`)

---

## Testing (5 tasks)

Verification and quality assurance.

- [x] T016 [S0104] [P] Write tests for collect_track_audio() -- empty tracks, single audio clip, multiple clips across tracks, mixed asset types ignored, volume/trim propagation (`tests/test_audio_mixer.py`)
- [x] T017 [S0104] [P] Write tests for build_mix_filter_graph() -- soundtrack only, single detached clip, multiple clips with timing/volume/trim, empty plan, adelay millisecond rounding (`tests/test_audio_mixer.py`)
- [x] T018 [S0104] [P] Write tests for multi-track Editly spec assembly -- multi-layer segments, audio exclusion with use_external_audio flag, backward-compatible soundtrack-only path (`tests/test_editly_compiler.py`)
- [x] T019 [S0104] Run full test suite and verify all tests pass (308+ existing + new)
- [x] T020 [S0104] Validate ASCII encoding and Unix LF line endings on all new and modified files

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

Run the implement workflow step to begin AI-led implementation.
