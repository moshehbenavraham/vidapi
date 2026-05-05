# Session 02: Output Formats and Presets

**Session ID**: `phase04-session02-output-formats-and-presets`
**Status**: Not Started
**Estimated Tasks**: ~20
**Estimated Duration**: 2-4 hours

---

## Objective

Expand output handling to support render presets plus GIF, WebM, and PNG sequence outputs through the existing storage, download, webhook, and artifact metadata paths.

---

## Scope

### In Scope (MVP)
- Output preset normalization for TikTok, Reels, Shorts, YouTube, square ads, and low-resolution previews
- Explicit format support for MP4, WebM, GIF, and PNG sequence outputs
- Artifact metadata and storage handling for single-file and multi-file outputs
- Download URL behavior for public, signed, and proxied storage modes
- Validation for unsupported format, preset, duration, fps, and resolution combinations

### Out of Scope
- Native FFmpeg renderer parity work
- HyperFrames output generation
- Multi-output batch rendering in one job
- UI or client SDK changes

---

## Prerequisites

- [ ] Session 01 completed
- [ ] Existing storage URL resolver supports configured local, public, signed, and proxied modes
- [ ] Production limits from Phase 03 are enforced

---

## Deliverables

1. Preset definitions and output normalization
2. Output format validation and artifact metadata updates
3. Storage/download support for WebM, GIF, and PNG sequence artifacts
4. Worker post-processing hooks where format conversion is needed
5. Tests for presets, formats, storage URLs, and limit failures

---

## Success Criteria

- [ ] Explicit dimensions override presets consistently
- [ ] WebM, GIF, and PNG sequence outputs produce retrievable artifacts
- [ ] Multi-file outputs have deterministic storage keys and URL behavior
- [ ] Webhook payloads include correct output metadata without duplicating URL logic
