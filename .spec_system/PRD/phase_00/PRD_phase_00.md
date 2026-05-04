# PRD Phase 00: Foundation

**Status**: In Progress
**Sessions**: 5 (initial estimate)
**Estimated Duration**: 10-20 hours

**Progress**: 1/5 sessions (20%)

---

## Overview

Prove the core JSON-to-video loop locally. Build the FastAPI skeleton, Pydantic composition schema, SQLite metadata store, local filesystem storage, Editly renderer bridge with segment compiler, synchronous render service, and the three MVP API endpoints. By the end of this phase a sample JSON with one image/video background, one text overlay, optional music, and vertical MP4 output renders successfully end-to-end.

---

## Progress Tracker

| Session | Name | Status | Est. Tasks | Validated |
|---------|------|--------|------------|-----------|
| 01 | Project Skeleton and Config | Complete | 20 | 2026-05-05 |
| 02 | Composition Schema and DB Models | Not Started | ~15-20 | - |
| 03 | Storage and Asset Service | Not Started | ~15-20 | - |
| 04 | Editly Renderer and Segment Compiler | Not Started | ~20-25 | - |
| 05 | Render Service and API Endpoints | Not Started | ~15-20 | - |

---

## Completed Sessions

- **Session 01: Project Skeleton and Config** -- Completed 2026-05-05. Delivered FastAPI skeleton with health endpoint, config system, structured logging, error handling, dev tooling (ruff, mypy, pytest), 20/20 tasks, 13/13 tests.

---

## Upcoming Sessions

- Session 02: Composition Schema and DB Models

---

## Objectives

1. Establish a working FastAPI project with health endpoint, config management, and dev tooling
2. Define the VidAPI JSON composition schema with Pydantic v2 discriminated unions
3. Implement local filesystem storage and secure asset resolution with SSRF protection
4. Build the Editly renderer bridge and segment compiler for absolute-to-sequential timeline conversion
5. Wire synchronous render service behind MVP API endpoints and prove the full render loop

---

## Prerequisites

- Python 3.11+ installed
- Node.js runtime installed for Editly
- FFmpeg 6+ and ffprobe installed
- Editly installed globally or available via npx

---

## Technical Considerations

### Architecture
- Synchronous local render service in Phase 00 uses the same service boundary the async worker will use in Phase 01
- Renderer protocol interface must be established even though only Editly is implemented
- Segment compiler is the highest-risk component and needs focused tests before broad feature work

### Technologies
- FastAPI with Uvicorn
- Pydantic v2 with discriminated unions for asset types
- SQLite via SQLModel + aiosqlite
- Pillow + fonttools for text-to-image rendering
- httpx for asset downloads
- structlog for structured logging
- ruff + mypy for code quality

### Risks
- Editly segment compiler complexity: mitigated by building focused tests in Session 04
- Font rendering differences across machines: mitigated by bundling Inter, Roboto, Noto Sans
- Editly subprocess failures hard to debug: mitigated by saving compiled spec, stderr, and replay metadata

### Relevant Considerations
- FFmpeg subprocess spawning needs resource limits (memory, CPU time, disk)
- Remote asset fetching needs timeouts and size limits
- Avoid MoviePy wrapper (abstracts away filter graph control)
- Avoid synchronous rendering in API process (blocks event loop)

---

## Success Criteria

Phase complete when:
- [ ] All 5 sessions completed
- [ ] FastAPI app serves /v1/health
- [ ] Pydantic models validate VidAPI composition JSON
- [ ] SQLite stores render metadata with proper status tracking
- [ ] Local filesystem storage persists render artifacts deterministically
- [ ] Asset resolution enforces SSRF protection, size limits, MIME validation
- [ ] Editly segment compiler converts absolute-time timelines to sequential clips
- [ ] Synchronous render service produces MP4 from JSON composition
- [ ] POST /v1/renders creates render job and returns 202
- [ ] GET /v1/renders/{id} returns status with progress
- [ ] GET /v1/renders/{id}/download serves rendered output
- [ ] Stored artifacts include input.json, expanded.json, compiled.editly.json, replay.json, output.mp4, poster.jpg, logs.txt
- [ ] Segment compiler tests cover single-clip, overlay, and gap cases
- [ ] Golden-path end-to-end render test passes

---

## Dependencies

### Depends On
- None (first phase)

### Enables
- Phase 01: Async Jobs and Multi-track
