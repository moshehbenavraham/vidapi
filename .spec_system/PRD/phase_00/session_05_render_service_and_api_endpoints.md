# Session 05: Render Service and API Endpoints

**Session ID**: `phase00-session05-render-service-and-api-endpoints`
**Status**: Not Started
**Estimated Tasks**: ~15-20
**Estimated Duration**: 2-4 hours

---

## Objective

Wire the render service that orchestrates the full render pipeline (validate, resolve assets, compile, render, store artifacts) and expose the three MVP API endpoints: POST /v1/renders, GET /v1/renders/{id}, and GET /v1/renders/{id}/download. Prove the end-to-end loop with a golden-path integration test.

---

## Scope

### In Scope (MVP)
- Render service in app/services/render_service.py orchestrating the full pipeline
- Synchronous local render path behind the same service boundary the async worker will use
- Merge variable expansion (simple string substitution for inline renders)
- POST /v1/renders: validate composition, create render record, execute synchronous render, return 202
- GET /v1/renders/{id}: return status, progress, output URL, poster URL, timestamps, errors
- GET /v1/renders/{id}/download: stream rendered output file
- Request/response Pydantic models for all endpoints
- Error responses with proper HTTP status codes (404, 422, etc.)
- Artifact persistence: input.json, expanded.json, compiled.editly.json, replay.json, output.mp4, poster.jpg, logs.txt
- Golden-path end-to-end test: submit JSON -> render -> poll -> download -> verify artifacts
- API contract tests for validation errors and missing renders

### Out of Scope
- Async queue processing (Phase 01 - ARQ + Redis)
- List renders endpoint (Phase 01)
- Delete/cancel endpoint (Phase 01)
- Template endpoints (Phase 02)
- Authentication (Phase 03)

---

## Prerequisites

- [ ] Session 04 completed (renderer and segment compiler exist)

---

## Deliverables

1. Render service orchestrating validate -> expand -> resolve assets -> compile -> render -> store
2. POST /v1/renders route handler
3. GET /v1/renders/{id} route handler
4. GET /v1/renders/{id}/download route handler
5. Request/response Pydantic models for render endpoints
6. Synchronous render execution behind the service boundary
7. Full artifact persistence for successful and failed renders
8. Golden-path end-to-end integration test
9. API contract tests for error cases

---

## Success Criteria

- [ ] POST /v1/renders accepts valid composition JSON and returns 202 with render ID
- [ ] POST /v1/renders returns 422 for invalid compositions
- [ ] GET /v1/renders/{id} returns render status with all expected fields
- [ ] GET /v1/renders/{id} returns 404 for unknown render IDs
- [ ] GET /v1/renders/{id}/download streams the rendered MP4
- [ ] Successful render stores all 7 artifact files
- [ ] Failed render stores input JSON, compiled spec (when available), logs, and replay metadata
- [ ] Golden-path test: submit JSON with image background + text overlay -> render succeeds -> download works -> all artifacts present
- [ ] Render service uses the same interface the async worker will call in Phase 01
