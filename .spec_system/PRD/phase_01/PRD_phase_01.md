# PRD Phase 01: Async Jobs and Multi-track

**Status**: In Progress
**Sessions**: 5 (initial estimate)
**Estimated Duration**: 10-15 days

**Progress**: 4/5 sessions (80%)

---

## Overview

Move rendering out of the synchronous API request path into an async worker powered by ARQ + Redis, implement the full render status state machine with progress tracking, add job cancellation and listing, support multi-track compositing with z-order and audio mixing, and ship a Docker Compose stack that runs API, worker, and Redis together.

---

## Progress Tracker

| Session | Name | Status | Est. Tasks | Validated |
|---------|------|--------|------------|-----------|
| 01 | Redis ARQ Queue Integration | Complete | 20 | 2026-05-05 |
| 02 | Worker Render Pipeline | Complete | 20 | 2026-05-05 |
| 03 | Progress Tracking and Cancellation | Complete | 21 | 2026-05-05 |
| 04 | Multi-track and Audio Mixing | Complete | 20 | 2026-05-05 |
| 05 | Docker Compose Stack | Not Started | ~18 | - |

---

## Completed Sessions

- Session 01: Redis ARQ Queue Integration (2026-05-05) - 20 tasks, 235 tests
- Session 02: Worker Render Pipeline (2026-05-05) - 20 tasks, 264 tests
- Session 03: Progress Tracking and Cancellation (2026-05-05) - 21 tasks, 308 tests
- Session 04: Multi-track and Audio Mixing (2026-05-05) - 20 tasks, 336 tests

---

## Upcoming Sessions

- Session 05: Docker Compose Stack

---

## Objectives

1. Decouple render execution from the API request path via ARQ + Redis queue
2. Implement the full render status state machine with progress reporting and job cancellation
3. Support multi-track compositing with z-order and soundtrack/detached audio mixing
4. Deliver a Docker Compose stack running API, worker, and Redis as independent services

---

## Prerequisites

- Phase 00 completed (Foundation - core JSON-to-video loop proven locally)
- Redis available for development (Docker or local install)

---

## Technical Considerations

### Architecture
- Worker runs as a separate process sharing the same DB and storage adapters
- ARQ connects API (enqueue) and worker (dequeue) through Redis
- Status updates flow from worker to DB; API reads current status on poll
- Workspace isolation prevents concurrent renders from corrupting each other

### Technologies
- ARQ (async Redis queue) for job dispatch
- Redis 7+ as the message broker
- Docker Compose for multi-service orchestration
- FFmpeg stderr parsing for progress extraction

### Risks
- ARQ connection pool exhaustion under burst render submissions: Mitigate with connection limits and rate limiting on POST /v1/renders
- Progress parsing fragility across FFmpeg/Editly versions: Keep parsing best-effort, never fail a render on progress parse errors
- Workspace cleanup race conditions: Use atomic move + TTL-based cleanup after artifacts are persisted
- Docker networking complexity: Keep services on a single bridge network for development

### Relevant Considerations
- [P00] **Synchronous render in POST handler**: This phase eliminates this tech debt by moving renders to ARQ workers
- [P00] **No rate limiting on POST /v1/renders**: Add basic rate limiting alongside async queue to prevent resource exhaustion
- [P00] **FFmpeg subprocess resource limits**: Worker should enforce timeout and consider memory limits on subprocesses
- [P00] **No render workspace cleanup**: Implement workspace lifecycle management in the worker

---

## Success Criteria

Phase complete when:
- [ ] All 5 sessions completed
- [ ] POST /v1/renders returns 202 Accepted immediately without blocking on render
- [ ] Worker completes render independently from the API process
- [ ] Polling GET /v1/renders/{id} reflects status changes through full state machine
- [ ] Multiple queued jobs complete without corrupting each other's workspaces
- [ ] GET /v1/renders returns paginated render list
- [ ] DELETE /v1/renders/{id} cancels queued jobs and best-effort cancels running jobs
- [ ] Multi-track compositions render with correct z-order by track index
- [ ] Soundtrack and detached audio clips mix correctly
- [ ] Docker Compose runs API, worker, and Redis with one command

---

## Dependencies

### Depends On
- Phase 00: Foundation

### Enables
- Phase 02: Templates and Polish
