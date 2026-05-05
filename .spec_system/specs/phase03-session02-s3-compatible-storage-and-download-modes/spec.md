# Session Specification

**Session ID**: `phase03-session02-s3-compatible-storage-and-download-modes`
**Phase**: 03 - Production Hardening
**Status**: Not Started
**Created**: 2026-05-05

---

## 1. Session Overview

This session makes render artifacts portable beyond a single local filesystem by adding an S3-compatible artifact backend while preserving the current local workspace path for development and tests. The current implementation uses local paths for both renderer scratch files and persisted artifacts, which works for a single process but breaks when API and worker containers do not share a volume.

The implementation should keep the renderer writing to local scratch workspaces, then publish durable artifacts through a storage adapter. Render status, webhook payloads, and download endpoints should resolve URLs through a single storage URL service so local proxy downloads, public object URLs, and signed S3 URLs behave consistently.

This is the natural next Phase 03 session because PostgreSQL persistence is now complete and later authentication, limits, and operational visibility need artifact locations that are stable across production deploys.

---

## 2. Objectives

1. Add configurable local and S3-compatible artifact storage backends without breaking local filesystem mode.
2. Persist input, expanded composition, compiled renderer spec, replay metadata, output, poster, and logs through the selected backend.
3. Return correct output and poster URLs for proxy, signed, and public download modes.
4. Add focused tests and documentation for MinIO/S3-compatible storage configuration and failure paths.

---

## 3. Prerequisites

### Required Sessions
- [x] `phase03-session01-postgresql-persistence-and-alembic-migrations` - Stable PostgreSQL-capable metadata and migration-managed render path fields.
- [x] `phase02-session03-webhook-delivery-system` - Webhook payloads that include render artifact URLs.
- [x] `phase02-session05-audio-polish-and-hardening` - Current artifact set for output, poster, logs, replay metadata, and expanded inputs.

### Required Tools/Knowledge
- S3-compatible object storage semantics, including AWS S3, Cloudflare R2, and MinIO path-style endpoints.
- boto3 or botocore client configuration and presigned URL generation.
- FastAPI streaming responses and redirect responses.
- Existing VidAPI render pipeline and worker workspace lifecycle.

### Environment Requirements
- Existing local filesystem tests must keep passing without external services.
- S3 tests should use mocks/stubs by default; any MinIO check must be optional and gated by environment variables.
- No database migration should be required for this session unless a path field cannot safely store backend URIs.

---

## 4. Scope

### In Scope (MVP)
- Operator can select `local` or `s3` artifact storage through settings - add backend, bucket, endpoint, region, credentials, object prefix, path-style, and URL mode settings.
- Operator can use proxy, signed, or public URL modes - centralize URL generation for render output and poster links.
- API and worker can share artifact state through the backend - store input and expanded JSON where the worker can read them.
- Worker can publish durable render artifacts - upload output, poster, logs, replay metadata, input, expanded composition, and compiled renderer spec.
- Client can download output through `/v1/renders/{id}/download` in proxy/local mode - stream local files or S3 objects without exposing credentials.
- Client can access poster URLs through the same mode logic - add proxied poster behavior where needed.
- Maintainer can test S3 behavior without real cloud credentials - use mocked clients/stubbed presign/upload/download paths.
- Developer can run MinIO-compatible manual checks - document optional local S3 smoke setup.

### Out of Scope (Deferred)
- Database schema changes for normalized artifact rows - *Reason: existing render path string fields are sufficient for MVP storage URIs.*
- Lifecycle policies, replication, object locks, or bucket provisioning - *Reason: operational concerns for later deployment hardening.*
- Browser direct uploads or client-side signed uploads - *Reason: VidAPI workers own artifact writes in this phase.*
- API key protection for artifact endpoints - *Reason: Phase 03 Session 03 owns authentication and access control.*
- Full production Compose MinIO wiring - *Reason: Phase 03 Session 05 owns production stack composition.*

---

## 5. Technical Approach

### Architecture

Separate scratch workspace management from durable artifact storage. Renderers should continue writing local files in a per-render workspace because Editly and FFmpeg require filesystem paths. After each durable artifact is produced, the storage adapter persists it and returns a stable artifact URI. Local mode can keep absolute file paths or `file://` style references; S3 mode should store `s3://bucket/key` style references while URL generation handles public, signed, and proxy presentation.

Add a small storage factory in API dependencies and worker startup so both processes use the same backend settings. Route handlers and webhook payload builders should not construct artifact URLs directly from path fields; they should call a storage URL resolver that understands render status, artifact type, URL mode, media type, and fallback behavior.

### Design Patterns
- Protocol-based storage backends: Keeps local and S3 implementations swappable behind explicit async methods.
- Settings-driven backend selection: Matches existing database adapter and render mode patterns.
- Local scratch plus durable publish: Preserves renderer filesystem assumptions while enabling S3 persistence.
- Centralized URL resolver: Prevents route handlers, webhooks, and tests from duplicating signed/public/proxy logic.
- Mocked S3 boundaries: Keeps CI deterministic without real cloud credentials.

### Technology Stack
- Python 3.11+
- FastAPI 0.136.1
- boto3 or botocore for S3-compatible upload, download, and presigned URLs
- SQLModel render path fields from Phase 03 Session 01
- pytest and pytest-asyncio
- Optional MinIO for manual smoke testing

---

## 6. Deliverables

### Files to Create
| File | Purpose | Est. Lines |
|------|---------|------------|
| `app/storage/s3.py` | S3-compatible artifact backend with upload, read, exists, and presign support | ~220 |
| `app/storage/factory.py` | Settings-driven storage backend and URL resolver construction | ~100 |
| `app/storage/urls.py` | Artifact URL mode resolver for proxy, signed, and public URLs | ~140 |
| `tests/test_s3_storage.py` | Unit tests for object keys, upload/download, errors, and presigned URLs | ~180 |
| `tests/test_storage_urls.py` | URL mode tests for local, proxy, signed, and public behavior | ~140 |

### Files to Modify
| File | Changes | Est. Lines |
|------|---------|------------|
| `pyproject.toml` | Add S3 client dependency | ~2 |
| `app/core/config.py` | Add storage backend, S3, and URL mode settings with production validation | ~80 |
| `app/storage/base.py` | Extend storage protocol around artifact URI, media type, and publish/read operations | ~90 |
| `app/storage/local.py` | Implement the expanded artifact backend while preserving local workspace behavior | ~80 |
| `app/api/deps.py` | Provide configured storage backend and URL resolver dependencies | ~60 |
| `app/services/render_service.py` | Publish durable artifacts and store backend URIs after render stages | ~120 |
| `app/workers/render_worker.py` | Read input through storage backend and publish worker artifacts safely | ~80 |
| `app/api/routes_renders.py` | Use URL resolver, support signed/public redirects, and add proxied poster endpoint | ~120 |
| `app/api/routes_templates.py` | Persist template render input/expanded JSON through configured storage | ~50 |
| `app/services/webhook_service.py` | Build storage-aware output and poster URLs | ~50 |
| `tests/conftest.py` | Add storage and URL resolver test fixtures | ~40 |
| `tests/test_storage.py` | Preserve and extend local storage behavior tests | ~80 |
| `tests/test_api_renders.py` | Cover proxy/signed/public download and poster URL behavior | ~100 |
| `tests/test_webhook_service.py` | Cover storage-aware webhook URL payloads | ~40 |
| `docs/development.md` | Document local and optional MinIO storage settings | ~60 |
| `docs/deployment.md` | Document S3-compatible production storage and URL modes | ~80 |

---

## 7. Success Criteria

### Functional Requirements
- [ ] Local filesystem storage remains the default and existing render tests keep passing.
- [ ] S3 backend uploads all required artifacts under deterministic render-scoped keys.
- [ ] API and worker can read render input through the configured storage backend.
- [ ] `GET /v1/renders/{id}` returns output and poster URLs according to proxy, signed, or public mode.
- [ ] `/v1/renders/{id}/download` streams local or S3 objects in proxy mode without leaking credentials.
- [ ] `/v1/renders/{id}/poster` streams or redirects poster artifacts consistently with the selected URL mode.

### Testing Requirements
- [ ] Unit tests cover local storage compatibility and S3 key/upload/download behavior.
- [ ] URL resolver tests cover proxy, signed, public, missing artifact, and credential-leak cases.
- [ ] API route tests cover download and poster behavior for local and mocked S3 storage.
- [ ] Webhook payload tests use storage-aware URLs.
- [ ] Optional MinIO smoke path is documented and safe to skip when not configured.

### Non-Functional Requirements
- [ ] S3 calls use timeouts and explicit error mapping to actionable `StorageError` responses.
- [ ] Signed URLs never include access keys or secret keys outside the provider-generated signature parameters.
- [ ] Object keys are deterministic, render-scoped, and do not trust client-provided path fragments.
- [ ] Local development remains one-command friendly with no S3 credentials required.

### Quality Gates
- [ ] All files ASCII-encoded.
- [ ] Unix LF line endings.
- [ ] Code follows project conventions.
- [ ] `ruff check .` passes.
- [ ] `ruff format --check .` passes.
- [ ] `mypy app/` passes.
- [ ] `pytest` passes, or any optional MinIO smoke check is clearly documented as skipped.

---

## 8. Implementation Notes

### Key Considerations
- Do not make S3 the renderer workspace. Editly and FFmpeg need local paths; S3 should be the durable artifact layer after files are created.
- The async API path currently writes `input.json` before enqueueing. In S3 mode, this must be published before enqueue so the worker can read it from its own container.
- Existing render path fields can store either local paths or backend URIs. Keep URL presentation separate from stored location.
- `ArtifactType` currently has names that do not fully match actual files (`compiled.editly.json`, `replay.json`, `logs.txt`, `poster.jpg`). Align naming during this session to avoid broken S3 keys.
- Webhook payloads currently build `/download` and `/poster` strings directly. Route and webhook code should share URL resolution.

### Potential Challenges
- S3-compatible endpoint differences: Make endpoint URL, region, path-style addressing, and public base URL explicit settings.
- boto3 is synchronous: Wrap blocking upload/download/presign operations in `asyncio.to_thread` or isolate them behind a small async adapter.
- Proxy downloads can be large: Use streaming responses and avoid loading full video objects into memory.
- Credential leakage: Tests should assert generated public URLs and route responses do not contain configured access or secret keys.

### Relevant Considerations
- [P00] **Atomic file writes (tmp + rename)**: Preserve local atomic writes for scratch files and publish only completed artifacts.
- [P00] **Replay metadata (`replay.json`)**: Ensure replay metadata remains persisted in durable storage for failed render diagnostics.
- [P02] **Template render traceability**: Template renders must keep input and expanded composition artifacts available after worker handoff.
- [P02] **Webhook delivery durability**: Storage-aware URLs should make webhook payloads useful even when API and worker run separately.
- [P00] **No authentication**: Artifact proxy endpoints stay unauthenticated in this session because Session 03 owns access control.

### Behavioral Quality Focus
Checklist active: Yes
Top behavioral risks for this session:
- API enqueues a render whose input is only available on the API container filesystem.
- S3 signed/public URL mode leaks credentials or returns a URL that cannot be dereferenced.
- Proxy downloads buffer large videos into memory or return stale local paths in S3 mode.

---

## 9. Testing Strategy

### Unit Tests
- Settings validation for storage backend, S3 credentials, URL modes, and public base URL requirements.
- Local storage protocol compatibility and deterministic artifact path behavior.
- S3 object key generation, upload, read, missing object, and presigned URL behavior with mocked clients.
- URL resolver behavior for proxy, signed, and public modes.

### Integration Tests
- Render create path persists input and expanded JSON through configured storage before enqueue.
- Render status and download routes return expected URLs/responses for local and mocked S3 backends.
- Worker preflight reads input through storage, not only through `Path.is_file`.
- Webhook payload builder returns storage-aware URLs.

### Manual Testing
- Run local mode with filesystem storage and verify `/download` still streams output.
- If MinIO is available, configure `STORAGE_BACKEND=s3`, render once, and verify objects exist under the configured prefix.
- Verify signed URL expiry and public URL modes against a disposable bucket or MinIO setup.

### Edge Cases
- Missing S3 bucket or credentials.
- S3 endpoint using path-style addressing.
- Public URL mode without a public base URL.
- Render succeeded but output or poster object missing.
- Template render input handoff between API and worker containers.
- Artifact key construction for unusual render IDs.

---

## 10. Dependencies

### External Libraries
- `boto3` or `botocore`: S3-compatible client and presigned URL support.
- `SQLModel`: Existing render metadata fields.
- `FastAPI`: Streaming and redirect responses.
- `pytest`: Mocked backend and route tests.

### Other Sessions
- **Depends on**: `phase03-session01-postgresql-persistence-and-alembic-migrations`
- **Depended by**: `phase03-session03-api-key-authentication-and-access-control`, `phase03-session05-operational-visibility-and-production-stack`

---

## Next Steps

Run the implement workflow step to begin AI-led implementation.
