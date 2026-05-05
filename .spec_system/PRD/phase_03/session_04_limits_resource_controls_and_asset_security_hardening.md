# Session 04: Limits, Resource Controls, and Asset Security Hardening

**Session ID**: `phase03-session04-limits-resource-controls-and-asset-security-hardening`
**Status**: Not Started
**Estimated Tasks**: ~20
**Estimated Duration**: 3-4 hours

---

## Objective

Enforce production-grade request, asset, render, queue, and subprocess limits to reduce denial-of-service and SSRF risk.

---

## Scope

### In Scope (MVP)
- Request body size limits for render and template submissions
- Configurable max render duration, resolution, fps, tracks, clips, and asset count
- Per-asset size, timeout, MIME, redirect, and stream-count enforcement review
- FFmpeg and renderer subprocess timeout hardening
- Workspace disk usage guardrails where portable
- Queue depth or submission limit checks with clear 429 responses
- Periodic orphan workspace cleanup for crashed workers
- Redis production security guidance for AUTH and TLS
- Tests for rejected over-limit compositions and blocked asset cases

### Out of Scope
- Full cgroup or namespace isolation
- Distributed scheduler admission control
- WAF or network perimeter controls

---

## Prerequisites

- [ ] Existing asset service SSRF checks are passing
- [ ] Worker status and cancellation paths from Phase 01 remain operational
- [ ] Rate limiting module from Phase 02 is available

---

## Deliverables

1. Centralized limit settings
2. Composition and request limit validators
3. Renderer subprocess timeout and guardrail updates
4. Orphan workspace cleanup process
5. Security-focused tests for limits and SSRF regressions

---

## Success Criteria

- [ ] Over-size requests are rejected before enqueueing render work
- [ ] Over-limit duration, resolution, fps, track, clip, and asset counts return clear validation errors
- [ ] Remote asset redirects to blocked networks remain rejected
- [ ] Renderer subprocesses cannot run beyond configured timeouts
- [ ] Orphan workspaces can be cleaned without deleting active jobs
