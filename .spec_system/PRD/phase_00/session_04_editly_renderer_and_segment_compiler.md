# Session 04: Editly Renderer and Segment Compiler

**Session ID**: `phase00-session04-editly-renderer-and-segment-compiler`
**Status**: Not Started
**Estimated Tasks**: ~20-25
**Estimated Duration**: 3-4 hours

---

## Objective

Implement the renderer protocol, Editly renderer bridge, segment compiler that converts VidAPI absolute-time timelines to Editly sequential clips, and poster generation. This is the highest-risk session in Phase 00 due to segment compiler complexity.

---

## Scope

### In Scope (MVP)
- Renderer protocol (base class) with compile() and render() methods
- Editly renderer implementation
- Segment compiler algorithm: collect boundaries, sort, deduplicate, generate non-overlapping segments
- VidAPI-to-Editly mapping for image, video, text, audio, and color assets
- Fit mode translation (cover, contain, stretch)
- Position mapping where Editly supports it
- Soundtrack and basic audio mapping to Editly audioTracks
- Editly subprocess invocation via asyncio.create_subprocess_exec
- Timeout and resource limits on subprocess
- Full stderr capture and logging
- Replay metadata generation (command, args, environment, paths)
- Poster generation via FFmpeg (extract frame from rendered output)
- Deterministic compiled.editly.json output
- Focused segment compiler tests (single clip, sequential, overlapping, gaps, text overlay, z-order, trim)

### Out of Scope
- Multi-track advanced compositing improvements (Phase 01)
- Complex transitions beyond basic fade (Phase 02)
- Native FFmpeg renderer (Phase 04)
- HyperFrames renderer (Phase 04)

---

## Prerequisites

- [ ] Session 03 completed (storage and asset service exist)
- [ ] Editly installed (npm install -g editly or available via npx)

---

## Deliverables

1. Renderer protocol in app/renderers/base.py
2. Editly renderer in app/renderers/editly.py with compile() and render()
3. Segment compiler that converts absolute-time clips to Editly sequential clips
4. VidAPI-to-Editly layer mapping for all MVP asset types
5. Subprocess invocation with timeout, stderr capture, and exit code handling
6. Replay metadata (replay.json) with command, args, and environment
7. Poster generation via FFmpeg frame extraction
8. Segment compiler test suite covering all core scenarios
9. Deterministic JSON output for reproducible tests

---

## Success Criteria

- [ ] Segment compiler correctly splits overlapping clips into non-overlapping segments
- [ ] Single clip, sequential clips, overlapping clips, and gap cases produce correct Editly JSON
- [ ] Track z-order is preserved in segment layer ordering
- [ ] Video and image assets map to correct Editly layer types
- [ ] Text assets use pre-rendered Pillow PNGs as image overlays
- [ ] Soundtrack maps to Editly audioTracks or audioFilePath
- [ ] Editly subprocess runs with explicit timeout and captures stderr
- [ ] Non-zero exit code, timeout, and missing output are treated as failures
- [ ] Poster is generated from rendered output via FFmpeg
- [ ] compiled.editly.json is deterministic for the same input
- [ ] replay.json captures enough info to manually re-run the render
