# Considerations

> Institutional memory for AI assistants. Updated between phases via carryforward.
> **Line budget**: 600 max | **Last updated**: Phase 02 (2026-05-05)

---

## Active Concerns

Items requiring attention in upcoming phases. Review before each session.

### Technical Debt
<!-- Max 5 items -->

- [P00] **Base-36 render IDs**: Custom ID generation is sortable but non-standard. Migrate to python-ulid in Phase 03 production hardening.
- [P01] **TTL-based workspace cleanup**: Orphaned workspaces from crashed workers still accumulate. Happy-path cleanup exists, but there is no periodic orphan scan.

### External Dependencies
<!-- Max 5 items -->

- [P01] **ARQ version sensitivity**: 0.28.0 expects redis_settings via attribute access. Keep the expected contract pinned or documented before any upgrade.
- [P01] **Editly headless GL in Docker**: Requires Xvfb plus GL runtime libs. Worker startup must keep the explicit Xvfb launch path.
- [P00] **Editly Node.js binary on PATH**: Local dev still depends on a manual Node/Editly install. Availability is only discovered at render time.
- [P00] **Font availability**: Inter, Roboto, and Noto Sans must be installed. Startup does not yet validate font presence.

### Performance / Security
<!-- Max 5 items -->

- [P00] **FFmpeg subprocess resource limits**: No memory, CPU time, or disk limits on spawned processes. This remains a DoS surface.
- [P00] **No authentication**: Render access is still effectively bearer-by-ID. Scope to authenticated users in Phase 03.
- [P01] **Redis connection TLS not enforced**: `REDIS_URL` supports `rediss://`, but production guidance and enforcement are still missing.
- [P01] **Redis AUTH not configured**: Docker Redis still runs without a password. Production must require authentication.
- [P02] **Webhook delivery durability**: Fire-and-forget dispatch is non-blocking, but worker crashes can still drop in-flight callback attempts. A durable queue or persisted retry scheduler would harden this.

### Architecture
<!-- Max 5 items -->

- [P00] **FFmpeg filter graph complexity**: Runtime grows non-linearly with track and clip count. Very large compositions may need chunked rendering.
- [P00] **Text rendering via Pillow**: Typography remains limited. A Playwright-based HTML asset path may still be needed later.
- [P00] **Single renderer implemented**: Only Editly exists today. Future renderers must keep the compiler protocol stable.
- [P01] **No WebSocket/SSE progress streaming**: Polling is fine for MVP, but real-time UIs will need push-based progress.
- [P02] **Template render traceability**: Template renders are async-only and pre-create render rows. Any future sync path must preserve template/version pointers and expanded.json parity.

---

## Lessons Learned

Proven patterns and anti-patterns. Reference during implementation.

### What Worked
<!-- Max 15 items -->

- [P00] **Pure-function segment compiler**: Stateless compiler functions are easier to test and compose than class-based alternatives.
- [P00] **Discriminated unions for asset types**: Pydantic type discrimination on a `type` literal gives clean validation and serialization.
- [P00] **Atomic file writes (tmp + rename)**: Prevents corrupted artifacts. The same pattern held for audio intermediates.
- [P00] **Manual redirect following for SSRF**: Per-hop validation prevents redirect-to-private-IP bypass attacks.
- [P00] **Replay metadata (`replay.json`)**: Capturing command, args, and env makes subprocess failures reproducible.
- [P00] **Content-addressed SHA-256 asset cache**: Avoids redundant downloads across renders.
- [P01] **Worker drives status transitions externally**: RenderService stays stateless while the worker owns transitions and cancellation checkpoints.
- [P01] **Cooperative cancellation via DB flag**: Renderer-agnostic and race-safe across queue backends.
- [P01] **Rate-limited progress updates (2% + 2s)**: Prevents DB write storms while staying responsive.
- [P01] **Persist `input.json` before enqueue**: Avoids msgpack serialization issues and keeps worker input source-of-truth on disk.
- [P01] **Conditional audio path**: Use Editly `audioTracks` for simple soundtrack-only cases and FFmpeg post-processing only when detached audio exists.
- [P01] **Best-effort progress parsing**: Never raise on unknown FFmpeg stderr formats; skip unparseable lines.
- [P02] **ID-based CRUD re-fetching**: Re-loading rows by ID avoids async SQLAlchemy expired-state and MissingGreenlet failures.
- [P02] **Jinja2 SandboxedEnvironment with StrictUndefined**: Strong isolation without custom sandbox code.
- [P02] **Whitelist field expansion**: Expanding only approved composition fields is simpler and more robust than path-pattern matching.
- [P02] **Async-only template render creation**: Pre-creating render rows with template pointers keeps traceability simple.
- [P02] **Fire-and-forget webhook dispatch with task tracking**: Non-blocking worker hooks work well when failures stay fully contained.
- [P02] **External audio plan ownership**: Routing soundtrack effects and normalization through FFmpeg prevents partial behavior and double-mixing.
- [P02] **Pure position resolver**: Keeping position math isolated makes Editly mapping easier to test and clamp.

### What to Avoid
<!-- Max 10 items -->

- [P00] **MoviePy wrapper**: It hides the filter graph control needed for precise timing.
- [P00] **Synchronous rendering in API process**: It blocks the event loop. Always use workers.
- [P00] **Import-time DB engine creation**: It blocks test overrides. Use lazy initialization.
- [P01] **ARQ `@staticmethod` for `redis_settings`**: ARQ 0.28.0 expects attribute access. Use class attribute assignment.
- [P01] **`proc.communicate()` for long renders**: It buffers all output. Use line-by-line stderr streaming for progress and cancel checks.
- [P01] **Settings singleton mutation in tests**: It causes cross-test contamination. Create isolated Settings instances.
- [P01] **`xvfb-run` in Docker CMD**: Process management is unreliable. Keep the explicit background Xvfb launch with signal trapping.
- [P02] **SQLAlchemy `Relationship()` declarations with generic list types in async models**: Explicit SELECTs are safer and avoid mapper/init failures.
- [P02] **Passing ORM objects across async session boundaries**: Re-fetch by ID before mutation to avoid stale state errors.
- [P02] **Partial soundtrack effect mapping into Editly `audioTracks`**: Once effects or normalization are enabled, route the full audio plan through FFmpeg.

### Tool/Library Notes
<!-- Max 5 items -->

- [P00] **uv for dependency management**: Faster than pip and handles PEP 668 cleanly.
- [P00] **Editly `allowRemoteRequests: false`**: All fetching should go through VidAPI's SSRF-validated asset service.
- [P01] **ARQ 0.28.0**: `redis_settings` must be a class attribute; `max_tries=1` prevents retry storms; `job_timeout` should be dynamic.
- [P02] **Jinja2 SandboxedEnvironment + StrictUndefined**: Safe defaults for user-provided template variables.
- [P02] **FastAPI 0.136.1 / Starlette 0.52.1**: This pairing clears the Phase 02 CVE floor while preserving compatibility.
- [P02] **structlog event naming**: `ainfo` and `awarning` reserve `event`; use a different key such as `webhook_event`.

---

## Resolved

Recently closed items (buffer - rotates out after 2 phases).

| Phase | Item | Resolution |
|-------|------|------------|
| P02 | No rate limiting on `POST /v1/renders` | Added bounded rate limiting and structured 429 responses in Phase 02.
| P02 | Wildcard production CORS | Phase 02 now rejects wildcard origins outside debug mode.
| P02 | Starlette CVE backlog | Upgraded FastAPI and raised the Starlette floor to `>=0.49.1`.
| P01 | Synchronous render in POST handler | ARQ async worker pipeline with `RENDER_MODE` toggle.
| P01 | No render workspace cleanup | WorkspaceManager with configurable cleanup on success/failure.

---

*Auto-generated by carryforward. Manual edits allowed but may be overwritten.*
