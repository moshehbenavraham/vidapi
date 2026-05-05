# Environments

| Environment | URL | Purpose |
|-------------|-----|---------|
| Development (sync) | http://localhost:8000 | Local dev without Redis |
| Development (async) | http://localhost:8000 | Local dev with Redis + worker |
| Docker Dev | http://localhost:8000 | Docker Compose full stack |
| Staging | TBD (Phase 03) | Pre-production testing |
| Production | TBD (Phase 03) | Live system |

## Configuration Differences

| Config | Dev (sync) | Dev (async) | Docker Dev | Production (planned) |
|--------|------------|-------------|------------|----------------------|
| Render mode | sync | async | async | async |
| Database | SQLite file | SQLite file | SQLite file | PostgreSQL |
| Storage | Local filesystem | Local filesystem | Docker volume | S3-compatible |
| Redis | Not used | localhost:6379 | redis:6379 (internal) | Redis cluster |
| Debug mode | true | true | true | false |
| Log format | Console | Console | Console | JSON |
| Asset HTTP | Allowed | Allowed | Allowed | HTTPS only |
| Auth | None | None | None | API key required |
| Webhook secret | Optional | Optional | Optional | Configured |
| Audio normalization | Disabled | Disabled | Disabled | Optional |
| CORS / hosts | Localhost allowlist | Localhost allowlist | Localhost allowlist | Explicit deployment allowlist |

## Required Environment Variables

- `DATABASE_URL`: Database connection string (SQLite for dev, PostgreSQL for prod)
- `STORAGE_ROOT`: Root directory for render artifacts and asset cache
- `RENDER_MODE`: `sync` or `async` (determines whether Redis/ARQ is used)
- `REDIS_URL`: Redis connection string (required when `RENDER_MODE=async`)
- `DEBUG`: Enable debug mode and console log output
- `LOG_LEVEL`: Logging verbosity (DEBUG, INFO, WARNING, ERROR)
- `WEBHOOK_SECRET`: HMAC secret for signed callbacks
- `CORS_ORIGINS`: Explicit list of allowed browser origins
- `ALLOWED_HOSTS`: Trusted host allowlist for the FastAPI app

See [development.md](development.md) for the full environment variable reference.
