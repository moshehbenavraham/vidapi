# Operations Guide

This guide covers the production-hardening operator surface: health checks,
operational endpoints, metrics, logs, and common triage commands.

## Authentication

Health endpoints are public:

- `GET /health`
- `GET /v1/health`

All operational endpoints are mounted under `/v1/ops` and use the same
`X-API-Key` protection as render and template endpoints when
`API_KEY_AUTH_ENABLED=true`.

```bash
export VIDAPI_API_KEY="replace-with-operator-key"
curl -H "X-API-Key: $VIDAPI_API_KEY" http://localhost:8000/v1/ops/renders
```

## Operational Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /v1/ops/renders` | Recent renders with bounded pagination and optional `status_filter` |
| `GET /v1/ops/renders/failures` | Recent failed renders with redacted error excerpts |
| `GET /v1/ops/renders/status-counts` | Current render counts by status |
| `GET /v1/ops/renders/renderer-failures` | Failed render counts by renderer and error code |
| `GET /v1/ops/webhooks` | Recent webhook attempts, optionally filtered by `render_id` or `failures_only=true` |
| `GET /v1/ops/webhooks/outcome-counts` | Webhook attempt counts by event and outcome |
| `GET /v1/ops/metrics` | Prometheus-style text metrics |

List endpoints clamp `limit` to `1..100` and clamp negative `offset` values to
0. Operational responses expose IDs, statuses, timestamps, stages, counts, and
bounded error excerpts. They do not expose raw compositions, callback URLs,
storage credentials, artifact paths, or presigned URLs.

## Metrics

```bash
curl -H "X-API-Key: $VIDAPI_API_KEY" \
  http://localhost:8000/v1/ops/metrics
```

The metrics response includes:

- `vidapi_render_status_total`
- `vidapi_renderer_failures_total`
- `vidapi_webhook_attempts_total`
- `vidapi_queue_available`
- `vidapi_queue_depth`
- `vidapi_queue_wait_seconds_count`, `_sum`, and `_max`
- `vidapi_render_duration_seconds_count`, `_sum`, and `_max`

When Redis is unavailable or the API is running in sync mode, queue metrics
remain present and include `vidapi_queue_available 0` plus a stable reason label.

## Logs

API request completion logs include:

- `request_id`
- `method`
- `path`
- `status_code`
- `duration_ms`

Worker logs include `render_id`, stage/status transitions, queue wait seconds,
render duration seconds when timestamps are present, and stable failure codes.
Webhook logs include `render_id`, `webhook_event`, attempt number, outcome,
status code, and bounded error or response excerpts.

Do not add log fields containing raw compositions, API keys, callback URLs,
authorization headers, Redis URLs, S3 credentials, presigned URLs, or full asset
URLs.

## Production-Like Compose Stack

Create a local production-like environment file:

```bash
cp .env.production.example .env.production
# Replace every change-me value and API_KEY_HASHES.
```

Start the stack:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up --build
```

Verify services:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml ps
curl http://localhost:8000/v1/health
curl -H "X-API-Key: $VIDAPI_API_KEY" http://localhost:8000/v1/ops/metrics
```

Stop without deleting durable volumes:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml down
```

Stop and delete volumes for a clean validation run:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml down -v
```

The compose overlay runs Redis with AUTH on a private Docker bridge. Real
production deployments should use `rediss://` with TLS and external secret
management.

## Triage

### API Unhealthy

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml logs api
docker compose --env-file .env.production -f docker-compose.prod.yml logs postgres
```

Check `DATABASE_URL`, `DATABASE_AUTO_CREATE=false`, and Alembic migration state.

### Queue Unavailable

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml logs redis
docker compose --env-file .env.production -f docker-compose.prod.yml logs worker
curl -H "X-API-Key: $VIDAPI_API_KEY" http://localhost:8000/v1/ops/metrics
```

Confirm `REDIS_URL` includes the password and that `REDIS_PASSWORD` matches the
Redis service password.

### Renders Failing

```bash
curl -H "X-API-Key: $VIDAPI_API_KEY" \
  http://localhost:8000/v1/ops/renders/failures
curl -H "X-API-Key: $VIDAPI_API_KEY" \
  http://localhost:8000/v1/ops/renders/renderer-failures
```

Use the returned `render_id` to correlate API logs, worker logs, and durable
replay/log artifacts. Do not expose replay artifacts through public channels.

### Webhooks Failing

```bash
curl -H "X-API-Key: $VIDAPI_API_KEY" \
  "http://localhost:8000/v1/ops/webhooks?failures_only=true"
curl -H "X-API-Key: $VIDAPI_API_KEY" \
  http://localhost:8000/v1/ops/webhooks/outcome-counts
```

Check endpoint reachability, receiver status codes, and HMAC secret alignment.
Webhook operational responses intentionally omit the callback URL.
