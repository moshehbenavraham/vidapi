# Considerations

> Institutional memory for AI assistants. Updated between phases via carryforward.
> **Line budget**: 600 max | **Last updated**: Phase 04 (2026-05-05)

---

## Active Concerns

Items requiring attention in upcoming phases. Review before each session.

### Technical Debt
<!-- Max 5 items -->

- [P03] **Migration-managed schema startup**: Production still depends on Alembic and metadata alignment. Any new table or model must update runtime metadata and migrations together or startup will fail closed.
- [P04] **Renderer capability parity**: Admission, service execution, worker preflight, and docs now share a capability registry, but future renderer additions can drift if support rules are duplicated.

### External Dependencies
<!-- Max 5 items -->

- [P03] **S3 and URL mode drift**: Storage backend, public/signed/proxy URL mode, and webhook URLs still depend on consistent deployment settings. Misconfiguration can break downloads or expose artifacts.
- [P04] **HyperFrames runtime pinning**: The adapter depends on the worker image, browser binaries, and Node 22 runtime staying in sync across local and production environments.

### Performance / Security
<!-- Max 5 items -->

- [P03] **Guardrail tuning is deployment-specific**: Body size, composition, queue depth, asset limits, and worker cleanup intervals are bounded now, but operators still need sane per-environment values.
- [P04] **Replay and redaction discipline**: Native FFmpeg and HyperFrames paths add replay metadata and stderr capture surfaces. Keep them bounded and redacted as the renderer set grows.

### Architecture
<!-- Max 5 items -->

- [P03] **Centralized artifact URL resolution**: Keep one resolver for local, proxy, signed, and public artifact URLs so routes and webhook payloads stay aligned.
- [P04] **Single renderer selection path**: Admission, service compile, and worker execution must continue using the same selection logic to avoid API/worker drift.

---

## Lessons Learned

Proven patterns and anti-patterns. Reference during implementation.

### What Worked
<!-- Max 15 items -->

- [P04] **Shared capability registry**: Centralizing support rules kept API admission, service execution, and worker preflight aligned.
- [P04] **Early selected-renderer persistence**: Saving the chosen renderer before execution improved replay fidelity and operational reporting.
- [P04] **Shared metadata shapes**: One output-artifact model kept status responses, downloads, storage URLs, and webhooks consistent.
- [P04] **Renderer-neutral timeline helpers**: Shared duration and ordering logic reduced duplication across Editly, native FFmpeg, and HyperFrames paths.
- [P03] **Fail-closed production startup**: Requiring validated config and satisfied migrations is safer than silently creating schema at boot.
- [P03] **Config-driven backend selection**: One settings layer for DB, storage, auth, and limits keeps local and production behavior predictable.
- [P03] **Bounded observability**: Authenticated ops endpoints plus redacted structured logs expose enough context without leaking payloads.
- [P02] **Pure-function segment compiler**: Stateless compiler functions are easier to test and compose than class-based alternatives.
- [P02] **Discriminated unions for asset types**: Pydantic type discrimination on a `type` literal gives clean validation and serialization.
- [P01] **Worker drives status transitions externally**: RenderService stays stateless while the worker owns transitions and cancellation checkpoints.

### What to Avoid
<!-- Max 10 items -->

- [P04] **Parallel capability logic**: Do not duplicate support rules in API, service, worker, and docs.
- [P04] **Best-effort renderer fallback**: Unsupported HTML, transitions, or renderer features should fail before expensive execution.
- [P03] **Duplicating storage URL logic across routes**: It causes inconsistencies in downloads and webhook payloads.
- [P03] **Raw secrets in responses or logs**: Redaction must stay centralized and test-covered.
- [P02] **Synchronous rendering in API process**: It blocks the event loop. Always use workers.
- [P01] **`proc.communicate()` for long renders**: It buffers all output. Use line-by-line stderr streaming for progress and cancel checks.

### Tool/Library Notes
<!-- Max 5 items -->

- [P04] **HyperFrames worker runtime**: Node 22 plus browser dependencies are required for the adapter path.
- [P04] **Deterministic FFmpeg subprocess handling**: Keep argv construction explicit and stderr bounded for native and post-processing paths.
- [P03] **`asyncpg`**: Works cleanly as the PostgreSQL async driver behind the settings-driven DB path.
- [P02] **Jinja2 SandboxedEnvironment + StrictUndefined**: Safe defaults for user-provided template variables.
- [P02] **FastAPI 0.136.1 / Starlette 0.52.1**: This pairing clears the Phase 02 CVE floor while preserving compatibility.

---

## Resolved

Recently closed items (buffer - rotates out after 2 phases).

| Phase | Item | Resolution |
|-------|------|------------|
| P03 | No API auth on non-health routes | Added API-key auth for render, template, and ops routes while keeping health endpoints public.
| P03 | Orphaned workspace accumulation | Worker startup now prunes inactive workspaces and keeps cleanup bounded.
| P03 | Implicit schema creation in production | Startup now requires migration readiness instead of mutating schema on boot.
| P03 | Unbounded request and queue exposure | Request size, composition, asset, and queue guardrails now fail closed.
| P03 | Redis health probe host parsing | Worker health checks now use the configured Redis URL directly.
| P02 | No rate limiting on `POST /v1/renders` | Added bounded rate limiting and structured 429 responses in Phase 02.
| P02 | Wildcard production CORS | Phase 02 now rejects wildcard origins outside debug mode.
| P02 | Starlette CVE backlog | Upgraded FastAPI and raised the Starlette floor to `>=0.49.1`.
| P01 | Synchronous render in POST handler | ARQ async worker pipeline with `RENDER_MODE` toggle.
| P01 | No render workspace cleanup | WorkspaceManager with configurable cleanup on success/failure.

---

*Auto-generated by carryforward. Manual edits allowed but may be overwritten.*
