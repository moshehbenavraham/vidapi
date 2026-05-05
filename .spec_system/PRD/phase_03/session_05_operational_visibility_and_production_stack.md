# Session 05: Operational Visibility and Production Stack

**Session ID**: `phase03-session05-operational-visibility-and-production-stack`
**Status**: Not Started
**Estimated Tasks**: ~20
**Estimated Duration**: 3-4 hours

---

## Objective

Add operational/admin visibility, structured metrics, and a production-like Docker Compose stack for API, worker, Redis, Postgres, and MinIO.

---

## Scope

### In Scope (MVP)
- Admin or operational endpoints for render job inspection, status counts, errors, and webhook attempts
- Structured logs with request IDs and render IDs across API and worker paths
- Basic metrics for queue wait time, render duration, status counts, renderer failures, and webhook delivery outcomes
- Docker Compose production-like profile with API, worker, Redis, Postgres, and MinIO
- Redis AUTH configuration and production TLS documentation
- Container health checks for API and worker-adjacent services
- Environment sample updates for production deployment
- Documentation for operating, troubleshooting, and verifying the stack

### Out of Scope
- Full dashboard UI
- Alerting integrations such as PagerDuty or Slack
- Kubernetes, Terraform, or Helm deployment assets

---

## Prerequisites

- [ ] Sessions 01-04 complete or stable enough to wire into the stack
- [ ] Existing Docker Compose API, worker, and Redis stack is functional

---

## Deliverables

1. Operational/admin endpoints
2. Structured logging and request/render correlation
3. Basic metrics endpoint or exporter
4. Production-like Docker Compose profile
5. Operations and deployment documentation updates

---

## Success Criteria

- [ ] Operators can list recent jobs, inspect failures, and review webhook attempts
- [ ] Logs include request_id and render_id where applicable
- [ ] Metrics expose queue, render, status, renderer, and webhook outcomes
- [ ] Docker Compose can run API, worker, Redis, Postgres, and MinIO together
- [ ] Production Redis authentication and TLS expectations are documented
