# Local Dev Testing Anomalies - 2026-05-05

## Context

- Local stack was started with `scripts/dev.sh`.
- Target URL: `http://127.0.0.1:8005`.
- Test evidence: `dogfood-output/vidapi-local-20260505/`.
- Browser session: closed after testing.
- Automated test result: `scripts/dev.sh test` passed with `785 passed, 1 skipped`.
- Remediation started on 2026-05-05. Status updates are recorded inline below
  so the document remains useful if the implementation session is interrupted.
- Final remediation verification completed on 2026-05-05:
  `ruff check .`, `ruff format --check .`, `mypy app/`, and
  `scripts/dev.sh test` all pass. The final test run reported
  `791 passed, 1 skipped`.
- Live remediation smoke used an isolated sync stack at
  `http://127.0.0.1:8005` with state under
  `dogfood-output/vidapi-local-20260505-remediation/`.

## Remediation Progress

- [x] Fix generic artifact downloads for all persisted deterministic artifacts.
  Implemented in `app/api/routes_renders.py`; focused route verification passed.
- [x] Persist and return completed output media duration. Implemented with
  Alembic revision `008`; focused API, migration, and Editly duration
  verification passed.
- [x] Clarify local API-key auth behavior in generated API documentation. The
  OpenAPI schema now removes `APIKeyAuth` when auth is disabled and keeps it
  when auth is enabled; focused auth documentation tests passed.
- [x] Decide and document `HEAD /download` behavior. The API now supports
  `HEAD /v1/renders/{id}/download`; focused route verification passed.
- [x] Decide and document Swagger CDN behavior for local development.
  Documentation added in `README.md` and `docs/development.md`; live smoke
  confirmed the standard FastAPI CDN references are still present and now
  explicitly documented.
- [x] Improve local Editly availability guidance. Documentation added in
  `docs/development.md`; startup warning remains visible and documented.
- [x] Confirm `scripts/dev.sh` and `dogfood-output/` repository hygiene.
  `scripts/dev.sh` is already tracked from the previous push and
  `dogfood-output/` remains ignored; verified with `git check-ignore -v`.
- [x] Add local smoke-test cleanup guidance. Added `scripts/dev.sh clean-state`
  and documentation; verified `scripts/dev.sh --help` and a non-default
  `clean-state` invocation that safely skipped custom paths.
- [x] Run full verification. Targeted remediation tests passed
  (`110 passed, 1 skipped`). Cleanup findings from the first resumed pass were
  fixed; `ruff check .`, `ruff format --check .`, and `mypy app/` pass. The
  final full pytest run passes with `791 passed, 1 skipped`.
- [x] Fix sync-mode render status transition failure. Live smoke render
  `render_moszqsad863g2mbw` produced output metadata and `duration: 1.0`, then
  failed with `RENDER_PIPELINE_ERROR` / `Invalid status transition: queued ->
  succeeded`. `RenderService.execute_render()` now moves sync renders through
  the same status sequence before final success; regression tests passed.
- [x] Complete live local smoke verification for the remediated API behavior.
  Isolated sync stack at `http://127.0.0.1:8005` with state under
  `dogfood-output/vidapi-local-20260505-remediation/` passed health,
  auth-disabled OpenAPI, Swagger CDN detection, one-second `ffmpeg-native`
  render, `duration: 1.0`, direct download/poster, `HEAD /download`, generic
  artifact aliases, and unknown artifact 404 checks. Passing render:
  `render_moszu1e41i2rda16`.

## Resolved Issues

### 1. Generic render artifact endpoint returns 404 for published artifacts

**Severity:** Medium
**Area:** API / artifact retrieval
**Status:** Resolved

The OpenAPI surface exposes `GET /v1/renders/{render_id}/artifacts/{artifact_name}` as a generic artifact download endpoint. A smoke render completed successfully and exposed working direct artifact routes:

- `GET /v1/renders/render_mosxzjxf96303yrw/download` returned `200 video/mp4`.
- `GET /v1/renders/render_mosxzjxf96303yrw/poster` returned `200 image/jpeg`.
- The worker log reported publishing artifacts including `input.json`, `expanded.json`, `compiled.editly.json`, `replay.json`, `output`, `poster.jpg`, and `logs.txt`.

The generic artifact endpoint returned `404 application/json` for every known or likely artifact name tested:

- `output`
- `output.mp4`
- `render_mosxzjxf96303yrw.mp4`
- `poster`
- `poster.jpg`
- `render_mosxzjxf96303yrw.jpg`
- `input`
- `input.json`
- `expanded`
- `expanded.json`
- `compiled`
- `compiled.editly.json`
- `replay`
- `replay.json`
- `logs`
- `logs.txt`

**Impact:** clients cannot use the documented generic artifact route, even though the render and direct download/poster routes work.

**Evidence:**

- `dogfood-output/vidapi-local-20260505/evidence-artifact-output-404.txt`
- `dogfood-output/vidapi-local-20260505/evidence-artifact-logs-404.txt`
- `dogfood-output/vidapi-local-20260505/evidence-download-headers.txt`
- `dogfood-output/vidapi-local-20260505/render-status.json`
- `dogfood-output/vidapi-local-20260505/screenshots/artifact-endpoint-docs.png`

**Resolution:** `GET /v1/renders/{render_id}/artifacts/{artifact_name}` now resolves persisted deterministic artifact paths for output, poster, input, expanded, compiled, replay, log, manifest, and caption sidecar artifacts.

**Verification:** live smoke render `render_moszu1e41i2rda16` returned `200` for `output`, `output.mp4`, `{render_id}.mp4`, `poster`, `poster.jpg`, `{render_id}.jpg`, `input`, `input.json`, `expanded`, `expanded.json`, `compiled`, `compiled.editly.json`, `replay`, `replay.json`, `logs`, and `logs.txt`; `unknown.txt` returned `404`.

### 1a. Sync-mode render status transition failure during remediation smoke

**Severity:** Medium
**Area:** API / sync render lifecycle
**Status:** Resolved

During the remediation smoke pass, sync-mode render `render_moszqsad863g2mbw` produced output metadata and `duration: 1.0`, then failed with `RENDER_PIPELINE_ERROR` / `Invalid status transition: queued -> succeeded`.

**Impact:** sync local development renders could appear as failed even after media artifacts were produced.

**Resolution:** `RenderService.execute_render()` now moves sync renders through the same state-machine sequence used by the async worker: `FETCHING -> COMPILING -> RENDERING -> UPLOADING -> SUCCEEDED`.

**Verification:** regression tests cover the sync service and direct sync API path. The final live smoke render `render_moszu1e41i2rda16` completed with `status: succeeded`, `stage: complete`, and `duration: 1.0`.

## Warnings And Observations

### 2. Render status reports `duration: null` for a valid one-second MP4

**Severity:** Low / needs product decision
**Area:** API response metadata
**Status:** Resolved

The completed render status payload reported `"duration": null`, while the downloaded MP4 probed as exactly `1.000000` seconds with `ffprobe`.

**Impact:** client UIs may not be able to display media duration from the render status response.

**Resolution:** `RenderResponse.duration` now means completed output media duration in seconds. The value is stored on the render record via Alembic revision `008`.

**Verification:** focused API, migration, and Editly duration tests pass. Live smoke render `render_moszu1e41i2rda16` returned `duration: 1.0`.

### 3. OpenAPI advertises API-key security while local dev accepts unauthenticated requests

**Severity:** Low
**Area:** Local dev API docs / auth UX
**Status:** Resolved

Local dev has `API_KEY_AUTH_ENABLED=false`, and unauthenticated calls to render/template endpoints succeeded. The OpenAPI schema still marks these endpoints with `APIKeyAuth`, so Swagger shows auth controls even though no key is required locally.

**Impact:** local testers may think they need an API key when they do not, or may miss that production behavior differs.

**Resolution:** generated OpenAPI now reflects the active auth mode: it removes `APIKeyAuth` operation security when `API_KEY_AUTH_ENABLED=false` and keeps the scheme when auth is enabled. README/development docs also describe the local-vs-production behavior.

**Verification:** focused auth documentation tests pass. Live smoke confirmed `/openapi.json` omits `APIKeyAuth` in the auth-disabled local stack.

### 4. `HEAD /v1/renders/{id}/download` returns 405

**Severity:** Low / compatibility note
**Area:** API ergonomics
**Status:** Resolved

`HEAD /v1/renders/render_mosxzjxf96303yrw/download` returned `405 Method Not Allowed` with `allow: GET`. OpenAPI only advertises `GET`, so this is not necessarily a bug.

**Impact:** some clients, download managers, or proxies may use `HEAD` to inspect file metadata before downloading.

**Resolution:** added `HEAD /v1/renders/{id}/download` to return output headers without streaming the body.

**Verification:** focused route test passes. Live smoke returned `200 video/mp4` and a `Content-Disposition` filename for `HEAD /download`.

### 5. Swagger UI depends on external CDN assets

**Severity:** Low
**Area:** Local dev docs reliability
**Status:** Resolved as documented behavior

Swagger UI loaded these external assets:

- `https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css`
- `https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js`
- `https://fastapi.tiangolo.com/img/favicon.png`

**Impact:** local API docs may degrade or fail when offline, behind strict firewalls, or if CDN access is blocked.

**Resolution:** accepted as standard FastAPI behavior for now and documented in `README.md` and `docs/development.md`; `/openapi.json` remains the offline/firewall-safe source of API metadata.

**Verification:** live smoke confirmed `/docs` still references `cdn.jsdelivr.net` and the FastAPI favicon, matching the documented behavior.

### 6. `editly` is not on PATH in the tested local environment

**Severity:** Medium environment risk
**Area:** Renderer tooling
**Status:** Resolved as documented environment guidance

`hyperframes` is available on PATH, but `editly` is not. The dev script warns that default non-HTML renders use Editly and recommends either installing Editly or requesting `renderer=ffmpeg-native`.

The smoke render explicitly used `renderer=ffmpeg-native`, so this did not block the tested workflow.

**Impact:** default render requests may fail locally if they select the Editly renderer.

**Resolution:** `docs/development.md` now documents the default Editly selection behavior and recommends installing Editly for full coverage or explicitly using `renderer: "ffmpeg-native"` for simple local smoke renders.

**Verification:** `scripts/dev.sh sync` still emits the Editly warning when `editly` is not on PATH, and the remediation smoke used `renderer: "ffmpeg-native"` successfully.

### 7. `scripts/dev.sh` is untracked even though it is the dev startup path

**Severity:** Low repo hygiene
**Area:** Project workflow
**Status:** Resolved

`git status --short` reported:

```text
?? scripts/dev.sh
```

The same script is the local startup entrypoint used for this test run.

**Impact:** if this script is intended to be shared by the team or CI-adjacent workflows, leaving it untracked makes local setup non-reproducible for other clones.

**Resolution:** `scripts/dev.sh` is tracked project tooling, and `dogfood-output/` is ignored.

**Verification:** `git status --short` no longer reports `scripts/dev.sh` as untracked; `git check-ignore -v dogfood-output dogfood-output/vidapi-local-20260505-remediation` confirms the dogfood output tree is ignored.

### 8. Test run left local render data behind

**Severity:** Low local-state note
**Area:** Local dev data hygiene
**Status:** Resolved with cleanup guidance

The smoke test created a successful render record:

```text
render_mosxzjxf96303yrw
```

Templates created during the smoke test were soft-deleted and no longer appear in the template list, but the successful render remains in local dev state and operations counts.

**Impact:** subsequent local tests may see one succeeded render in list/ops endpoints.

**Resolution:** added `scripts/dev.sh clean-state` and documented it in `README.md` and `docs/development.md`. The remediation live smoke used isolated state under ignored `dogfood-output/`.

**Verification:** `scripts/dev.sh --help` lists `clean-state`; a non-default invocation skipped custom DB, artifact, and workspace paths as intended.

## Non-Issues Confirmed During Testing

- `/v1/health` returned healthy database and Redis state.
- Swagger UI loaded and had no browser console/page errors during the run.
- Template CRUD worked after corrected shell parsing.
- Invalid template payload returned useful `422` validation errors.
- The `ffmpeg-native` worker path completed successfully.
- The downloaded MP4 and poster file were valid media files.
- Ops status counts reflected the successful render.
- Full pytest suite passed.
