# Session 05: Audio Polish and Hardening

**Session ID**: `phase02-session05-audio-polish-and-hardening`
**Status**: Not Started
**Estimated Tasks**: ~15
**Estimated Duration**: 2-3 hours

---

## Objective

Improve audio mixing reliability, wire rate limiting into render submission, restrict CORS for production, and polish API documentation to close out Phase 02 with a hardened, well-documented template-driven video API.

---

## Scope

### In Scope (MVP)
- Audio fade effects on soundtrack (fadeIn, fadeOut, fadeInFadeOut)
- Audio volume normalization and validation
- Detached audio clip timing edge cases (clips extending past video duration, overlapping audio)
- Wire existing rate_limit.py into POST /v1/renders route
- Restrict CORS allowed_origins via configuration (replace wildcard default for production)
- OpenAPI documentation review and update for all new Phase 02 endpoints
- Error response consistency audit across template and webhook endpoints
- Starlette upgrade to >= 0.49.1 to resolve CVE-2025-54121 and CVE-2025-62727

### Out of Scope
- Advanced audio ducking or per-clip volume keyframes
- PostgreSQL migration (Phase 03)
- API key authentication (Phase 03)
- S3 storage adapter (Phase 03)

---

## Prerequisites

- [ ] Session 04 complete (transitions and positioning)
- [ ] Rate limit module exists but unwired (from Phase 01)

---

## Deliverables

1. Audio fade effects on soundtrack
2. Audio edge case handling improvements
3. Rate limiting wired into render submission endpoint
4. CORS configuration restricted for production
5. Starlette CVE remediation
6. OpenAPI documentation updates for Phase 02 endpoints

---

## Success Criteria

- [ ] Soundtrack fadeIn/fadeOut/fadeInFadeOut effects render correctly
- [ ] Detached audio clips handle edge cases without crashes
- [ ] Rate limiting enforced on POST /v1/renders
- [ ] CORS origins configurable and not wildcard in production mode
- [ ] Starlette upgraded to resolve known CVEs
- [ ] All Phase 02 endpoints documented in OpenAPI spec
