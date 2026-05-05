# Session 03: API Key Authentication and Access Control

**Session ID**: `phase03-session03-api-key-authentication-and-access-control`
**Status**: Not Started
**Estimated Tasks**: ~18
**Estimated Duration**: 2-4 hours

---

## Objective

Protect all non-health public API routes with configurable API key authentication and clear access-control behavior.

---

## Scope

### In Scope (MVP)
- API key settings and enable/disable switch for local development
- Hashed API key storage or configured hashed key list
- FastAPI dependency for API key extraction from headers
- Authentication enforcement on render, template, download, and admin routes
- `/v1/health` remains unauthenticated
- Consistent 401 and 403 error responses
- OpenAPI security scheme for API key auth
- Tests covering enabled, disabled, missing, invalid, and valid key cases
- Secret redaction in logs and error responses

### Out of Scope
- Multi-tenant user accounts and billing
- OAuth, JWT, or session cookies
- Fine-grained per-template or per-render authorization

---

## Prerequisites

- [ ] Session 01 and Session 02 public route behavior understood
- [ ] Existing route dependency patterns are stable

---

## Deliverables

1. API key configuration and validation helpers
2. Route dependency enforcing API key authentication
3. OpenAPI security documentation
4. Auth-aware tests for all public route groups
5. Secret redaction checks

---

## Success Criteria

- [ ] `/v1/health` works without authentication
- [ ] Non-health API routes reject missing or invalid keys when auth is enabled
- [ ] Valid API keys can create, inspect, cancel, download, and template-render jobs
- [ ] Auth can be disabled explicitly for local development
- [ ] API keys never appear in structured logs or error payloads
