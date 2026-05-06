# Production Deployment Plan: VPS

Date: 2026-05-06

## Objective

Deploy VidAPI as a production-ready, single-node VPS service with a clear path to
future hardening. The first production target is Docker Compose on this VPS:
FastAPI API, ARQ worker, PostgreSQL, Redis, and S3-compatible artifact storage
using MinIO or an external object store.

This document started as the deployment plan and now also records the production
bring-up completed on this server. The status sections below reflect verified
server state as of 2026-05-06.

## Project Understanding

VidAPI is a self-hosted video rendering API. The API validates render/template
requests, writes metadata to PostgreSQL in production, and enqueues async render
jobs into Redis. A separate worker consumes ARQ jobs, creates isolated render
workspaces, fetches and validates media assets, runs the selected renderer
through Editly, HyperFrames, or native FFmpeg, post-processes outputs, persists
artifacts to local scratch plus S3-compatible durable storage, and updates render
status. Operational endpoints under `/v1/ops` expose render, webhook, and metric
visibility behind API-key auth.

The repository already contains most of the one-node deployment surface:

- `Dockerfile.api` builds the FastAPI/Uvicorn container.
- `Dockerfile.worker` builds the renderer container with Node.js, Editly,
  HyperFrames, FFmpeg, fonts, browser libraries, and Xvfb.
- `docker-compose.prod.yml` defines API, worker, PostgreSQL, Redis with AUTH,
  and MinIO.
- `.env.production.example` defines required production-like settings.
- Alembic migrations are required because production disables automatic table
  creation.
- Health endpoints remain public at `/health` and `/v1/health`; render,
  template, and ops endpoints require `X-API-Key` when auth is enabled.

## Target Production Shape

For the initial VPS deployment, use the repo's production Compose stack with
these production boundaries:

- API exposed only through a reverse proxy with TLS, not directly as a raw public
  Docker port.
- Worker kept private on the Docker network.
- PostgreSQL, Redis, and MinIO kept private on the Docker network unless an
  explicit external managed service replaces them.
- API key authentication enabled with only SHA-256 key hashes stored in
  `.env.production`.
- PostgreSQL migrations run before API and worker startup.
- Durable artifacts stored through the S3 adapter. MinIO is acceptable for the
  first single-node VPS deployment if backups are in place; external S3 is
  preferable for stronger durability.
- JSON logs emitted to Docker logs for collection by host-level logging or a
  future metrics/logging stack.

## High-Level Deployment Phases

### 1. VPS Baseline

- Confirm OS, CPU, RAM, disk size, and available swap are sufficient for video
  rendering workloads.
- Install or verify Docker Engine 24+ and Docker Compose v2.
- Create a dedicated deploy user and keep the repo under a predictable path,
  such as `/home/vidapi/vidapi`.
- Configure firewall rules so only SSH, HTTP, and HTTPS are public.
- Decide the public hostname, such as `api.example.com`, before setting
  `ALLOWED_HOSTS` and CORS.

### 2. Secrets And Environment

- Copy `.env.production.example` to `.env.production`.
- Replace every `change-me` value.
- Generate one raw production API key for clients/operators and store only its
  SHA-256 hash in `API_KEY_HASHES`.
- Set `ALLOWED_HOSTS` to the real domain, proxy hostnames, localhost, and the
  internal `api` service name as needed.
- Set `CORS_ORIGINS` to the real browser origins that may call the API.
- Keep `.env.production` untracked; `.gitignore` already excludes `.env.*`
  except committed examples.
- Decide whether MinIO remains in-process for launch or whether `STORAGE_BACKEND`
  points at external S3-compatible storage.

### 3. Reverse Proxy And TLS

- Put Nginx, Caddy, or Traefik in front of the API.
- Terminate TLS at the proxy using Let's Encrypt or provider-managed
  certificates.
- Proxy only the API service to the public internet.
- Forward `X-Forwarded-*` headers consistently.
- Keep MinIO console/API ports private unless there is a specific administrative
  access plan.
- Add request body and timeout settings that match VidAPI render limits.

### 4. Compose Production Bring-Up

- Build the API and worker images from the checked-out commit.
- Start PostgreSQL, Redis, and MinIO first.
- Create the `S3_BUCKET` in MinIO if using local MinIO, because the app expects
  the bucket to exist.
- Run `alembic upgrade head` through the API image before starting long-running
  API/worker services.
- Start API, then worker.
- Confirm container health checks are healthy.
- Confirm `/v1/health` reports healthy database and Redis status.

### 5. Verification

- Run authenticated operator checks against `/v1/ops/metrics` and
  `/v1/ops/renders`.
- Submit a small authenticated render request and poll it to terminal state.
- Verify output URL/download behavior through the configured storage URL mode.
- Check API logs, worker logs, PostgreSQL logs, Redis logs, and MinIO logs.
- Confirm failed-auth requests are rejected and health checks remain public.
- Capture the exact deploy commands in a runbook after the first successful
  launch.

### 6. Production Hardening

- Add backup procedures for PostgreSQL and MinIO volumes or move those services
  to managed/external providers.
- Add host disk monitoring, especially for Docker volumes and worker scratch
  space.
- Tune render limits, queue depth, timeouts, and worker concurrency to match the
  VPS size.
- Add log retention and rotation for Docker logs.
- Add uptime checks for `/v1/health`.
- Add authenticated metrics scraping for `/v1/ops/metrics`.
- Add an explicit deploy workflow or documented manual deploy process; the
  current GitHub deploy/release workflows are placeholders for real deployment.
- Add a rollback plan based on git commit, Docker image tag, database migration
  compatibility, and volume backup state.

## Known Gaps To Resolve Before Live Traffic

- `docker-compose.prod.yml` still publishes API port `8000` and MinIO ports
  `9000` and `9001` by default. The committed `docker-compose.vps.yml` override
  fixes this on this server by clearing those host port mappings, so future VPS
  runs must include both Compose files.
- Redis TLS is disabled in the provided production-like Compose template because
  it runs on a private bridge network. That is acceptable only for single-host
  private networking; external Redis should use `rediss://`.
- The generic `scripts/smoke-test.sh` does not send `X-API-Key`; production
  verification needs authenticated curl steps or a production-aware smoke script.
- MinIO bucket creation has been performed manually on this server but is not
  automated.
- Reverse proxy routing is committed as Traefik labels in `docker-compose.vps.yml`
  for this Coolify server; there is still no standalone Nginx/Caddy/Traefik
  config for other hosts.
- There is no committed VPS-specific backup, restore, or rollback runbook yet.
- The health endpoint returns service health details but should still be exposed
  through TLS and rate-limited at the proxy if public.

## Resolved Decisions For This VPS

- Public hostname: `vidapi.aiwithapex.com`.
- Reverse proxy: existing Coolify Traefik proxy on the external `coolify`
  network.
- Initial durable artifact storage: bundled MinIO through the S3 adapter.
- API exposure: API is reachable only through Traefik/TLS; it does not publish a
  host port directly.
- Internal service names: unique aliases `vidapi-postgres`, `vidapi-redis`, and
  `vidapi-minio` avoid collisions on shared Docker networks.
- API key storage: `.env.production` stores only SHA-256 key hashes; raw operator
  key material is kept in ignored local operator files.

## Remaining Decisions

- What backup retention period is required for PostgreSQL metadata and MinIO
  artifacts?
- Should MinIO stay on this VPS after launch, or should artifacts move to an
  external S3-compatible provider?
- What render concurrency should this VPS support after real workload testing?
- What API key rotation cadence should operators follow?

## Proposed Next Step

Create a VPS runbook that covers authenticated smoke testing, backup and restore,
rollback, image rebuild/redeploy, and API key rotation.

## VPS Implementation Status

Updated: 2026-05-06

Last verified: 2026-05-06 18:50 UTC

Completed on this VPS:

- Verified Docker Engine and Docker Compose are installed and usable through the
  `docker` group. The current non-login shell does not include the `docker`
  group in `id`, but `sg docker -c ...` works because `vidapi` is listed in the
  `docker` group.
- Audited existing containers and host ports. Coolify/Traefik already owns
  public `80`, `443`, `8080`, and Coolify owns `8000`, so VidAPI must not bind
  its default API `8000:8000` mapping on this host.
- Pulled production dependency images for PostgreSQL 16, Redis 7, and MinIO.
- Built local API and worker images as `vidapi-api:local` and
  `vidapi-worker:local`.
- Added `docker-compose.vps.yml` to reset public host port mappings and keep API
  and MinIO network-internal by default.
- Created local ignored secret files `.env.production` and
  `.env.production.operator` with mode `600`.
- Started only PostgreSQL, Redis, and MinIO through the production Compose stack
  plus the VPS override.
- Created the configured MinIO bucket.
- Ran Alembic migrations to revision `008 (head)`.
- Started the full production Compose stack with API, worker, PostgreSQL, Redis,
  and MinIO.
- Committed and pushed the deployment support changes to `origin/main` as
  `b679d7e Prepare VPS deployment support`.
- Bumped repository metadata during bring-up to version `0.1.34`; source
  metadata has since been bumped to `0.1.36`.
- Installed `uv` and `uvx` version `0.11.9` under
  `/home/vidapi/.npm-global/bin` so `scripts/dev.sh test ...` works on this
  server.
- Rebuilt and recreated the API and worker images from current `main` with
  package version `0.1.35`.

Current state:

- Long-running VidAPI containers: `api`, `worker`, `postgres`, `redis`, and
  `minio`.
- All five VidAPI containers are healthy.
- No VidAPI service is publishing host ports. Compose shows only container
  ports: API `8000/tcp`, PostgreSQL `5432/tcp`, Redis `6379/tcp`, and MinIO
  `9000-9001/tcp`.
- The API is routed through the existing Coolify Traefik proxy at
  `https://vidapi.aiwithapex.com`.
- The API container is attached to both the private `vidapi-prod` network and
  the shared `coolify` proxy network.
- PostgreSQL, Redis, MinIO, and the worker remain private to the VidAPI network.
- VidAPI uses unique internal aliases (`vidapi-postgres`, `vidapi-redis`, and
  `vidapi-minio`) so service discovery cannot collide with Coolify services that
  use generic names on the proxy network.
- Public `/v1/health` returns healthy database and Redis status.
- Public `/v1/health` reports application version `0.1.35`.
- Authenticated `/v1/ops/metrics` returns Prometheus text over HTTPS.
- Unauthenticated `/v1/ops/metrics` returns `401`.
- Authenticated `/v1/renders` returns the existing successful smoke render.
- An authenticated one-second `ffmpeg-native` render completed successfully over
  the public hostname and downloaded as `video/mp4`.
- A reported Cloudflare `1010` block from another server account was not
  reproduced from the `vidapi` account: authenticated protected endpoints worked
  through the public hostname over both IPv4 and IPv6, and with common curl,
  Python, Go, and browser-like user agents.
- Redis authentication is active; unauthenticated `redis-cli ping` returns
  `NOAUTH`, while authenticated ping returns `PONG`.
- The MinIO bucket `vidapi-renders` exists, is private, and currently contains
  the smoke render artifacts.

Production fix applied during bring-up:

- PostgreSQL rejected render creation because the application wrote
  timezone-aware Python datetimes into `TIMESTAMP WITHOUT TIME ZONE` columns.
  The DB timestamp factories and CRUD timestamp writes now store UTC-naive
  datetimes consistently with the existing schema.
- API startup logging no longer emits the full Redis URL with credentials; it
  logs only the Redis scheme, host, port, and DB number.
- The application version default now comes from local `pyproject.toml` or
  installed package metadata. The live VPS `.env.production` has
  `APP_VERSION=0.1.35`, matching the currently deployed API and worker images.
- The API and worker Dockerfiles disable standard pip root-user and version
  check notices during image builds.
- The worker image now creates `/tmp/.X11-unix` with sticky `1777` permissions
  before switching to the non-root `vidapi` user, so Xvfb no longer needs to
  create that directory at runtime.

Verification commands run on 2026-05-06:

```bash
sg docker -c "docker compose --env-file .env.production -f docker-compose.prod.yml -f docker-compose.vps.yml ps"
curl -fsS https://vidapi.aiwithapex.com/v1/health
curl -fsS -o /dev/null -w "%{http_code}\n" https://vidapi.aiwithapex.com/v1/ops/metrics
sg docker -c "docker exec vidapi-api-1 alembic current"
sg docker -c "docker exec vidapi-postgres-1 pg_isready -U vidapi -d vidapi"
```

Authenticated checks were also run using the ignored
`.env.production.operator` file:

```bash
curl -fsS -H "X-API-Key: ${VIDAPI_API_KEY}" https://vidapi.aiwithapex.com/v1/ops/metrics
curl -fsS -H "X-API-Key: ${VIDAPI_API_KEY}" https://vidapi.aiwithapex.com/v1/renders
```

If a same-host agent receives a Cloudflare-generated `1010` page, capture the
UTC timestamp, public egress IP, `cf-ray`, and `cf-error-type` response headers.
That response is generated before Traefik and will not appear in VidAPI origin
logs. Same-host agents can also bypass Cloudflare for diagnostics through local
Traefik while preserving the production hostname:

```bash
curl --resolve vidapi.aiwithapex.com:443:127.0.0.1 \
  -H "X-API-Key: ${VIDAPI_API_KEY}" \
  https://vidapi.aiwithapex.com/v1/renders
```
