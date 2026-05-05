# Session 05: Native FFmpeg Renderer Subset

**Session ID**: `phase04-session05-native-ffmpeg-renderer-subset`
**Status**: Not Started
**Estimated Tasks**: ~22
**Estimated Duration**: 3-4 hours

---

## Objective

Implement a constrained native FFmpeg renderer path for simple high-throughput timelines behind the existing renderer protocol.

---

## Scope

### In Scope (MVP)
- `ffmpeg-native` renderer adapter implementing the existing compile/render protocol
- Narrow supported subset for color, image, video, text PNG overlays, soundtrack, fit modes, and simple timing
- Deterministic filter graph generation for supported timelines
- Progress parsing, replay metadata, logs, timeout, cancellation, and resource limits
- Compatibility tests against Editly-backed behavior for the supported subset

### Out of Scope
- Full public schema parity
- HyperFrames support
- Arbitrary FFmpeg filter injection
- Complex animation, HTML, or unsupported transition effects

---

## Prerequisites

- [ ] Session 01 completed
- [ ] Session 02 completed
- [ ] Session 04 completed
- [ ] Existing asset resolution and text PNG generation are stable

---

## Deliverables

1. Native FFmpeg renderer adapter
2. Deterministic filter graph compiler for a narrow timeline subset
3. Worker integration with progress, cancellation, logs, and replay metadata
4. Compatibility and rejection tests for supported and unsupported features
5. Documentation for when `ffmpeg-native` is selected or rejected

---

## Success Criteria

- [ ] Simple supported timelines render through `ffmpeg-native`
- [ ] Unsupported features are rejected or routed according to capability rules
- [ ] Replay metadata captures FFmpeg command, args, environment, and input paths
- [ ] Existing Editly renders continue to pass unchanged
