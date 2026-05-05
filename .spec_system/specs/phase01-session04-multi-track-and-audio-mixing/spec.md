# Session Specification

**Session ID**: `phase01-session04-multi-track-and-audio-mixing`
**Phase**: 01 - Async Jobs and Multi-track
**Status**: Not Started
**Created**: 2026-05-05

---

## 1. Session Overview

This session extends the Editly renderer to fully support multi-track compositing with correct z-order and adds audio mixing capabilities for soundtrack and detached audio clips placed on tracks at specific timeline positions.

The segment compiler and layer mapper already handle multi-track visual composition (overlapping clips from different tracks with z-order by track index). However, audio clips on tracks are currently silently skipped -- `map_clip_to_layer()` returns `None` for `AudioAsset`. This session closes that gap by introducing an FFmpeg-based audio mixer that can combine video audio, soundtrack, and detached audio clips with precise timeline positioning, volume control, and trim support.

The session also adds targeted multi-track tests to the Editly spec assembler (verifying multi-layer segments produce correct Editly JSON) and comprehensive tests for the new audio mixing pipeline.

---

## 2. Objectives

1. Implement FFmpeg-based audio mixing service that combines multiple audio sources with precise timeline positioning
2. Support detached audio clips on tracks with start time, duration, volume, and trim controls
3. Integrate audio post-processing into the Editly renderer pipeline so mixed audio is applied after video rendering
4. Add comprehensive tests for multi-track spec assembly, audio collection, and audio mixing

---

## 3. Prerequisites

### Required Sessions
- [x] `phase00-session04-editly-renderer-and-segment-compiler` - Segment compiler, layer mapper, Editly renderer
- [x] `phase00-session05-render-service-and-api-endpoints` - Render service pipeline
- [x] `phase01-session02-worker-render-pipeline` - Worker pipeline with stage transitions
- [x] `phase01-session03-progress-tracking-and-cancellation` - Progress tracking, cancellation

### Required Tools/Knowledge
- FFmpeg 6+ with amix, adelay, atrim, volume filters
- Understanding of FFmpeg complex filter graphs for audio mixing

### Environment Requirements
- Python 3.11+ with project venv activated
- FFmpeg and ffprobe on PATH
- 308 existing tests passing

---

## 4. Scope

### In Scope (MVP)
- Audio clip collection from tracks - walk tracks, extract AudioAsset clips with timeline positions, volume, trim
- FFmpeg audio mixer service - build complex filter graphs, invoke FFmpeg subprocess, combine multiple audio sources
- Detached audio clip support - audio assets placed on timeline tracks at specific start times with duration
- Audio volume control per clip and per soundtrack
- Audio trim (cutFrom equivalent via atrim filter) for detached audio clips
- Conditional audio path: use Editly audioTracks when only soundtrack, use FFmpeg post-processing when detached audio exists
- Extended CompiledRender to carry audio mix plan alongside Editly spec
- Integration into render pipeline (render service stage_render_and_store)
- Multi-track Editly spec assembly tests (verify multi-layer segment JSON)
- Audio collection and mixing unit tests

### Out of Scope (Deferred)
- Advanced audio ducking - *Reason: Phase 02+ polish feature*
- Crossfade transitions between clips - *Reason: Phase 02 Templates and Polish*
- Audio normalization (loudness leveling) - *Reason: Future enhancement*
- Real-time audio preview - *Reason: Non-goal*
- Docker Compose stack - *Reason: Session 05*

---

## 5. Technical Approach

### Architecture

The audio mixing pipeline uses a two-pass approach:

1. **Video Pass (Editly)**: Renders video frames with visual layers. Video asset audio is preserved by Editly natively via `mixVolume`. When detached audio clips exist, soundtrack is excluded from Editly's `audioTracks` to avoid double-mixing.

2. **Audio Pass (FFmpeg)**: Post-processes the rendered video to mix in soundtrack and detached audio clips with precise timing. Uses FFmpeg complex filter graphs with `adelay`, `atrim`, `volume`, and `amix` filters.

The conditional logic:
- **Soundtrack only, no detached audio**: Use existing Editly `audioTracks` (backward compatible, zero regression risk)
- **Detached audio clips present**: Use FFmpeg post-processing for ALL non-video audio (soundtrack + detached clips)

### Design Patterns
- **Data-driven mix plan**: `AudioMixPlan` dataclass describes all audio sources declaratively; FFmpeg command is generated from it
- **Pure-function filter graph builder**: `build_mix_filter_graph()` is stateless and testable
- **Conditional post-processing**: Render pipeline checks if audio mixing is needed and applies it only when required

### Technology Stack
- FFmpeg 6+ complex filter graphs (amix, adelay, atrim, volume, anullsrc)
- asyncio.create_subprocess_exec for non-blocking FFmpeg invocation
- Existing Editly renderer with extended compile output

---

## 6. Deliverables

### Files to Create
| File | Purpose | Est. Lines |
|------|---------|------------|
| `app/services/audio_mixer.py` | FFmpeg audio mixing service | ~200 |
| `tests/test_audio_mixer.py` | Audio mixer and collection tests | ~250 |

### Files to Modify
| File | Changes | Est. Lines |
|------|---------|------------|
| `app/renderers/editly.py` | Add collect_track_audio(), compile_audio_plan(), conditional soundtrack handling | ~80 |
| `app/renderers/base.py` | Extend CompiledRender with optional audio_mix_plan field | ~10 |
| `app/services/render_service.py` | Wire audio post-processing into stage_render_and_store, resolve track audio assets | ~30 |
| `app/core/config.py` | Add ffmpeg_bin and audio_mix_timeout settings | ~5 |
| `tests/test_editly_compiler.py` | Add multi-track spec assembly tests | ~80 |

---

## 7. Success Criteria

### Functional Requirements
- [ ] Multi-track compositions render with correct z-order (higher track index on top)
- [ ] Overlapping clips from different tracks produce correct layered Editly segments
- [ ] Soundtrack plays behind video/image content at specified volume
- [ ] Detached audio clips play at specified timeline positions with correct timing
- [ ] Audio trim and volume controls work correctly in FFmpeg filter graph
- [ ] Compositions with only soundtrack use existing Editly audioTracks path (no regression)
- [ ] Compositions with detached audio use FFmpeg post-processing for all non-video audio

### Testing Requirements
- [ ] Unit tests for collect_track_audio() covering single/multi/empty cases
- [ ] Unit tests for build_mix_filter_graph() covering filter construction
- [ ] Unit tests for multi-track Editly spec assembly
- [ ] All 308+ existing tests continue to pass

### Non-Functional Requirements
- [ ] Audio mixing adds less than 10s overhead for a 30-second render
- [ ] FFmpeg subprocess has explicit timeout and failure handling

### Quality Gates
- [ ] All files ASCII-encoded
- [ ] Unix LF line endings
- [ ] Code follows project conventions

---

## 8. Implementation Notes

### Key Considerations
- Editly's `audioTracks` does not support per-track start times or trim -- only path and mixVolume. Detached audio clips with specific timeline positions require FFmpeg post-processing.
- When FFmpeg audio mixing is active, the video stream is copied (`-c:v copy`) to avoid re-encoding.
- If the source video has no audio stream, FFmpeg handles this gracefully (only mix external audio sources).

### Potential Challenges
- **FFmpeg filter graph complexity**: Complex compositions with many audio clips produce long filter graphs. Mitigation: Keep filter generation pure-functional and well-tested.
- **Video without audio stream**: FFmpeg `amix` requires at least one input. Mitigation: Use `anullsrc` to generate silent base when needed.
- **Floating-point timing**: adelay uses milliseconds (integer). Mitigation: Round to nearest millisecond.

### Relevant Considerations
- [P00] **Pure-function segment compiler**: Applying the same pattern to audio collection -- stateless functions that are easy to test and compose.
- [P00] **Non-fatal poster generation**: Audio mixing failures should be fatal (unlike poster), since missing audio is a broken output.
- [P00] **Replay metadata (replay.json)**: The audio mixing FFmpeg command should be captured in replay metadata for debugging.
- [P00] **FFmpeg subprocess resource limits**: Audio mixing subprocess must have explicit timeout.

### Behavioral Quality Focus
Checklist active: Yes
Top behavioral risks for this session's deliverables:
- FFmpeg subprocess timeout/failure without cleanup of intermediate files
- Audio clip with invalid trim producing silent or distorted output
- Race between video render completion and audio post-processing start

---

## 9. Testing Strategy

### Unit Tests
- collect_track_audio: empty tracks, single audio clip, multiple clips, mixed asset types, volume/trim propagation
- build_mix_filter_graph: soundtrack only, single detached clip, multiple clips with timing, volume and trim combinations
- AudioMixPlan construction from composition
- Multi-track assemble_editly_spec: verify layers per segment, audio exclusion when mixer active

### Integration Tests
- Full compile flow with multi-track composition including audio clips
- Audio plan generation alongside Editly spec

### Manual Testing
- Render a composition with background video + text overlay + soundtrack + detached audio clip
- Verify audio timing matches timeline specification

### Edge Cases
- Composition with audio-only track (no visual clips)
- Audio clip that extends beyond video duration
- Zero-volume audio clip
- Audio clip with trim exceeding source duration
- Multiple overlapping audio clips at same timeline position
- Soundtrack with no detached audio (backward compatibility)

---

## 10. Dependencies

### External Libraries
- FFmpeg 6+: amix, adelay, atrim, volume, anullsrc filters (already available)

### Other Sessions
- **Depends on**: phase01-session03-progress-tracking-and-cancellation
- **Depended by**: phase01-session05-docker-compose-stack

---

## Next Steps

Run the implement workflow step to begin AI-led implementation.
