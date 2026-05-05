# Environments

| Environment | URL | Purpose |
|-------------|-----|---------|
| Development (sync) | http://localhost:8000 | Local dev without Redis |
| Development (async) | http://localhost:8000 | Local dev with Redis + worker |
| Docker Dev | http://localhost:8000 | Docker Compose full stack |
| Production-like Compose | http://localhost:8000 | API, worker, Redis AUTH, PostgreSQL, MinIO |
| Staging | Deployment-specific | Pre-production testing |
| Production | Deployment-specific | Live system |

## Configuration Differences

| Config | Dev (sync) | Dev (async) | Docker Dev | Production-like Compose | Production |
|--------|------------|-------------|------------|-------------------------|------------|
| Render mode | sync | async | async | async | async |
| Database | SQLite file | SQLite file | SQLite file | PostgreSQL | PostgreSQL |
| Storage | Local filesystem | Local filesystem | Docker volume | MinIO/S3 | S3-compatible |
| Redis | Not used | localhost:6379 | redis:6379 internal | redis:// with AUTH | rediss:// with AUTH |
| Debug mode | true | true | false | false | false |
| Log format | Console | Console | JSON | JSON | JSON |
| Asset HTTP | Allowed | Allowed | Allowed | HTTPS only | HTTPS only |
| Auth | None | None | Optional | API key required | API key required |
| Webhook secret | Optional | Optional | Optional | Configured | Configured |
| Metrics | Optional ops endpoint | Optional ops endpoint | Ops endpoint | Ops endpoint | Ops endpoint plus scraper |
| Audio normalization | Disabled | Disabled | Disabled | Optional | Optional |
| CORS / hosts | Localhost allowlist | Localhost allowlist | Localhost allowlist | Explicit local allowlist | Explicit deployment allowlist |

## Required Environment Variables

- `DATABASE_URL`: Database connection string (SQLite for dev, PostgreSQL for prod)
- `DATABASE_AUTO_CREATE`: `false` for production and migration-verified startup
- `STORAGE_ROOT`: Root directory for render artifacts and asset cache
- `RENDER_MODE`: `sync` or `async` (determines whether Redis/ARQ is used)
- `REDIS_URL`: Redis connection string (required when `RENDER_MODE=async`)
- `REDIS_REQUIRE_AUTH_IN_PRODUCTION`: Require Redis credentials in production async mode
- `REDIS_REQUIRE_TLS_IN_PRODUCTION`: Require `rediss://` in production async mode
- `API_KEY_AUTH_ENABLED`: Require `X-API-Key` for non-health endpoints
- `API_KEY_HASHES`: Comma-separated SHA-256 hashes of accepted API keys
- `STORAGE_BACKEND`: `local` or `s3`
- `STORAGE_URL_MODE`: `proxy`, `signed`, or `public`
- `S3_BUCKET`: S3 or MinIO bucket for durable artifacts
- `S3_ENDPOINT_URL`: S3-compatible endpoint URL, such as MinIO
- `S3_ACCESS_KEY_ID`: S3 access key ID
- `S3_SECRET_ACCESS_KEY`: S3 secret access key
- `DEBUG`: Enable debug mode and console log output
- `LOG_LEVEL`: Logging verbosity (DEBUG, INFO, WARNING, ERROR)
- `WEBHOOK_SECRET`: HMAC secret for signed callbacks
- `CORS_ORIGINS`: Explicit list of allowed browser origins
- `ALLOWED_HOSTS`: Trusted host allowlist for the FastAPI app
- `MAX_ASYNC_QUEUE_DEPTH`: Queue admission depth limit
- `QUEUE_ADMISSION_TIMEOUT_SECONDS`: Redis queue depth timeout
- `RATE_LIMIT_DEFAULT`: Default API rate limit
- `RATE_LIMIT_RENDER_CREATE`: Render creation rate limit

See [development.md](development.md) for local development settings and
[deployment.md](deployment.md) for production-like compose and production
configuration examples.
