# Session 03: Storage and Asset Service

**Session ID**: `phase00-session03-storage-and-asset-service`
**Status**: Not Started
**Estimated Tasks**: ~15-20
**Estimated Duration**: 2-4 hours

---

## Objective

Implement the local filesystem storage adapter for render artifacts and the asset resolution service with SSRF protection, size limits, MIME validation, text-to-image rendering, and SHA-256 content-addressed caching.

---

## Scope

### In Scope (MVP)
- Storage adapter protocol (base class)
- Local filesystem storage implementation with deterministic paths
- Render workspace creation and artifact persistence (input.json, expanded.json, compiled spec, replay.json, output, poster, logs)
- Asset service: remote asset fetching via httpx with async I/O
- SSRF protection: block localhost, loopback, link-local, private networks, metadata endpoints
- Redirect validation (block redirects to blocked networks)
- Max download size enforcement
- Per-asset timeout
- MIME type allowlist
- SHA-256 content-addressed asset cache
- Text-to-image rendering with Pillow and bundled font paths
- ffprobe integration for media validation (duration, codec, streams)
- Asset security tests

### Out of Scope
- S3-compatible storage (Phase 03)
- HTML asset rendering (Phase 04)
- Complex audio processing (Phase 01)

---

## Prerequisites

- [ ] Session 02 completed (composition models and DB models exist)

---

## Deliverables

1. Storage protocol in app/storage/base.py
2. Local filesystem storage in app/storage/local.py
3. Render workspace manager for deterministic artifact paths
4. Asset service in app/services/asset_service.py with secure fetching
5. SSRF validator with IP and network blocking
6. Text-to-image renderer using Pillow with Inter/Roboto/Noto Sans support
7. ffprobe wrapper for media validation
8. Asset security tests covering blocked URLs, oversized assets, bad MIME types
9. SHA-256 content cache under data/assets/sha256/

---

## Success Criteria

- [ ] Local storage creates deterministic workspace paths from render IDs
- [ ] All render artifacts can be written and read from local storage
- [ ] Remote HTTPS assets download successfully with proper validation
- [ ] Localhost, private IPs, and metadata endpoints are blocked
- [ ] Redirects to blocked networks are caught and rejected
- [ ] Assets exceeding size limits are rejected before full download
- [ ] Invalid MIME types are rejected
- [ ] Text renders to transparent PNG with specified font, size, and color
- [ ] ffprobe extracts duration, codec, and stream info from media files
- [ ] Downloaded assets are cached by SHA-256 hash
