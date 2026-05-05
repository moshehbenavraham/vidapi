# PRD Phase 02: Templates and Polish

**Status**: Complete
**Sessions**: 5 (initial estimate)
**Estimated Duration**: 10-20 days

**Progress**: 5/5 sessions (100%)

---

## Overview

Make VidAPI useful for repeatable programmatic video generation by adding template CRUD with immutable versioning, strict Jinja2 variable substitution, webhook callbacks with HMAC signing and retry, named positions and offsets, and basic fade/crossfade transitions. This phase transforms VidAPI from a raw composition renderer into a template-driven video production API.

---

## Progress Tracker

| Session | Name | Status | Est. Tasks | Validated |
|---------|------|--------|------------|-----------|
| 01 | Template Models and CRUD API | Complete | 20/20 | 2026-05-05 |
| 02 | Template Variables and Rendering | Complete | 20/20 | 2026-05-05 |
| 03 | Webhook Delivery System | Complete | 18/18 | 2026-05-05 |
| 04 | Transitions and Positioning | Complete | 18/18 | 2026-05-05 |
| 05 | Audio Polish and Hardening | Complete | 19/19 | 2026-05-05 |

---

## Completed Sessions

- **Session 01** - Template Models and CRUD API (2026-05-05): 20 tasks, 376 tests passing
- **Session 02** - Template Variables and Rendering (2026-05-05): 20 tasks, 429 tests passing
- **Session 03** - Webhook Delivery System (2026-05-05): 18 tasks, 457 tests passing
- **Session 04** - Transitions and Positioning (2026-05-05): 18 tasks, 499 tests passing
- **Session 05** - Audio Polish and Hardening (2026-05-05): 19 tasks, 519 tests passing

---

## Upcoming Sessions

- None. Phase 02 is complete.

---

## Objectives

1. Enable reusable template-driven video generation with variable substitution and immutable versioning
2. Deliver reliable webhook callbacks with HMAC-SHA256 signing, retry, and delivery audit trail
3. Expand composition expressiveness with named positions, offsets, and basic transitions

---

## Prerequisites

- Phase 01 completed (async worker pipeline, multi-track compositing, Docker Compose stack)
- Redis + ARQ queue operational
- Render status state machine functional through all stages

---

## Technical Considerations

### Architecture
- Template system builds on existing composition schema and render pipeline
- Jinja2 sandbox operates on the JSON composition before it enters the render path
- Webhook delivery is async and decoupled from render completion -- never blocks the worker
- Transitions and positioning extend the segment compiler without breaking existing Editly mappings

### Technologies
- Jinja2 (SandboxedEnvironment) for variable substitution with strict undefined handling
- HMAC-SHA256 for webhook payload signing
- httpx for async webhook delivery
- Existing SQLModel/SQLite stack for template and webhook_attempts tables

### Risks
- Template variable injection in non-string fields could corrupt composition structure: mitigate with whitelisted-field-only substitution
- Webhook retry storms on consistently failing endpoints: mitigate with max 3 retries and exponential backoff (1s, 10s, 60s)
- Transition support varies by renderer: only expose transitions confirmed working with Editly; reject unsupported combinations

### Relevant Considerations
- [P00] **Single renderer implemented**: Transitions and positioning must be validated against Editly capabilities only
- [P00] **Text rendering via Pillow**: Template variable substitution in text assets must regenerate Pillow PNGs after expansion
- [P01] **No rate limiting on POST /v1/renders**: Wire rate_limit.py into routes during this phase (SECURITY-COMPLIANCE recommendation)
- [P00] **CORS wildcard origins**: Restrict for production deployments (SECURITY-COMPLIANCE recommendation)

---

## Success Criteria

Phase complete when:
- [x] All 5 sessions completed
- [x] A product-ad style template can render multiple variations with different merge data
- [x] Historical renders remain reproducible after template updates (immutable versions)
- [x] Webhook attempts are recorded and payloads are HMAC-SHA256 signed
- [x] Named positions, offsets, and fade/crossfade transitions work in rendered output
- [x] Expanded compositions are stored per render for template-based jobs

---

## Dependencies

### Depends On
- Phase 01: Async Jobs and Multi-track

### Enables
- Phase 03: Production Hardening

Phase 02 is complete and ready for the audit transition.
