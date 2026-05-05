# Incident Response

| Level | Description | Response Time |
|-------|-------------|---------------|
| P0 | API completely down | Immediate |
| P1 | All renders failing | < 1 hour |
| P2 | Specific render types failing | < 4 hours |
| P3 | Minor feature broken, cosmetic | Next business day |

## Common Incidents

### API Not Responding
**Symptoms**: Health check returns non-200 or times out
**Resolution**:
1. Check container status: `docker compose ps`
2. Check logs: `docker compose logs api`
3. Restart: `docker compose restart api`
4. If persistent, rebuild: `docker compose up --build`
5. For the production-like stack, also check Postgres and Redis health:
   `docker compose --env-file .env.production -f docker-compose.prod.yml ps`

### Renders Failing with Editly Timeout
**Symptoms**: Renders stuck in `rendering` status, eventually fail with timeout error
**Resolution**:
1. Check recent failures: `curl -H "X-API-Key: $VIDAPI_API_KEY" http://localhost:8000/v1/ops/renders/failures`
2. Check renderer failure counts: `curl -H "X-API-Key: $VIDAPI_API_KEY" http://localhost:8000/v1/ops/renders/renderer-failures`
3. Check render logs at `data/renders/<render_id>/logs.txt`
4. Check system resources (CPU, memory, disk)
5. Review the compiled spec at `data/renders/<render_id>/compiled.editly.json`
6. Replay the render manually using `data/renders/<render_id>/replay.json`
7. If asset-related, check asset cache under `data/assets/`

### Renders Failing with Missing Editly Binary
**Symptoms**: Renders fail immediately with `FileNotFoundError` for editly
**Resolution**:
1. Verify Node.js is installed: `node --version`
2. Verify Editly is installed: `which editly` or `npx editly --help`
3. Check `EDITLY_BIN` environment variable

### Database Migration Errors
**Symptoms**: API fails to start, migration-related errors in logs
**Resolution**:
1. Check current migration state: `alembic current`
2. Apply pending migrations: `alembic upgrade head`
3. If corrupted, reset (dev only): `alembic downgrade base && alembic upgrade head`

### Queue Saturated or Unavailable
**Symptoms**: Render creation returns 429 or 503, metrics show queue unavailable
**Resolution**:
1. Check metrics: `curl -H "X-API-Key: $VIDAPI_API_KEY" http://localhost:8000/v1/ops/metrics`
2. Check worker logs: `docker compose logs worker`
3. Check Redis logs: `docker compose logs redis`
4. Confirm `REDIS_URL` includes the expected password and database.
5. Confirm `REDIS_PASSWORD` matches the Redis service password in the compose stack.
6. If production uses TLS, confirm `REDIS_URL` starts with `rediss://`.

### PostgreSQL Unavailable
**Symptoms**: Health check is degraded, API startup fails, or ops endpoints return 503
**Resolution**:
1. Check health: `curl http://localhost:8000/v1/health`
2. Check Postgres status: `docker compose --env-file .env.production -f docker-compose.prod.yml ps postgres`
3. Check logs: `docker compose --env-file .env.production -f docker-compose.prod.yml logs postgres`
4. Verify `DATABASE_URL`, user, password, database name, and migrations.
5. Apply migrations if needed: `docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api alembic upgrade head`

### MinIO or S3 Unavailable
**Symptoms**: Renders fail with storage errors or downloads return storage unavailable
**Resolution**:
1. Check MinIO health: `docker compose --env-file .env.production -f docker-compose.prod.yml ps minio`
2. Check worker and API logs for `STORAGE_ERROR`.
3. Confirm `STORAGE_BACKEND=s3`, `S3_ENDPOINT_URL`, bucket, access key, and secret match the storage service.
4. Confirm the bucket exists and is writable by the configured credentials.

### Webhook Delivery Failing
**Symptoms**: Receivers do not get callbacks or webhook failures increase
**Resolution**:
1. Check failed attempts: `curl -H "X-API-Key: $VIDAPI_API_KEY" "http://localhost:8000/v1/ops/webhooks?failures_only=true"`
2. Check outcome counts: `curl -H "X-API-Key: $VIDAPI_API_KEY" http://localhost:8000/v1/ops/webhooks/outcome-counts`
3. Verify receiver availability and returned status codes.
4. Verify `WEBHOOK_SECRET` matches receiver signature verification.
5. Use `render_id` and `webhook_event` to correlate API and worker logs.
