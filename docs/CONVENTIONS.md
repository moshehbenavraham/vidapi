# CONVENTIONS.md

## Guiding Principles

- Optimize for readability over cleverness
- Code is written once, read many times
- Consistency beats personal preference
- If it can be automated, automate it
- When writing code: Make NO assumptions. Do not be lazy. Pattern match precisely. Do not skim when you need detailed info from documents. Validate systematically.

## Naming

- Be descriptive over concise: `get_render_by_id` > `get_render` > `fetch`
- Booleans read as questions: `is_active`, `has_permission`, `should_retry`
- Functions describe actions: `calculate_duration`, `validate_composition`, `send_webhook`
- Avoid abbreviations unless universally understood (`id`, `url`, `config`, `fps` are fine)
- Match domain language: use `timeline`, `track`, `clip`, `asset` consistently (from Shotstack/Creatomate terminology)

## Python Style

- Python 3.11+ with type hints on all public functions
- Use `snake_case` for functions, variables, modules
- Use `PascalCase` for classes and Pydantic models
- Use `UPPER_SNAKE_CASE` for constants
- Prefer `pathlib.Path` over `os.path`
- Use f-strings over `.format()` or `%`
- Async by default for I/O operations

## FastAPI Conventions

- Route functions are thin: validate input, call service, return response
- Business logic lives in `services/`, never in route handlers
- Use dependency injection (`Depends()`) for shared resources (DB sessions, settings)
- Pydantic models for all request/response schemas (no raw dicts crossing API boundaries)
- HTTP status codes: 201 for created resources, 202 for accepted async jobs, 404 for missing, 422 for validation errors

## Files & Structure

- One concept per file where practical
- File names reflect their primary export or purpose
- Group by feature/domain: `app/services/renderer.py` not `app/renderer/services.py`
- Keep nesting shallow -- max 3 levels under `app/`

## Functions & Modules

- Functions do one thing
- If a function needs a comment explaining what it does, consider renaming it
- Keep functions short enough to read without scrolling
- Avoid side effects where possible; be explicit when they exist
- Use dataclasses or Pydantic models to pass related parameters (not 5+ positional args)

## Comments

- Explain *why*, not *what*
- Delete commented-out code -- that's what git is for
- TODOs include context: `# TODO(username): reason, ticket if applicable`
- Update or remove comments when code changes

## Error Handling

- Fail fast and loud in development
- Fail gracefully in production
- Errors should be actionable -- include context for debugging
- Don't swallow errors silently
- Use custom exception classes for domain errors (`RenderError`, `AssetFetchError`, `CompileError`, etc.)
- FFmpeg and Editly failures must capture full stderr output for diagnostics
- Every failed render stores: input JSON, compiled renderer spec, stderr log, and a replay command

## Renderer and Subprocess

- All rendering happens via the `Renderer` protocol; never call Editly or FFmpeg directly from route handlers or services outside the renderer abstraction
- Editly is invoked as a Node subprocess via `asyncio.create_subprocess_exec`; never use `subprocess.run` (blocking)
- Always set explicit timeouts and resource limits on renderer subprocesses
- Write the compiled renderer spec (e.g., `compiled.editly.json`) to the job workspace before invoking -- this is the replay artifact
- Parse subprocess stderr for progress updates; do not rely on exit code alone
- Renderer output paths are always deterministic from the render job ID
- Keep VidAPI composition schema independent from any renderer's internal format; the compiler translates between them

## Database Layer

### Connection
- Connection string source: `DATABASE_URL` environment variable
- SQLite for development, PostgreSQL for production
- Async sessions via SQLModel + aiosqlite/asyncpg

### Migrations
- Tool: Alembic
- Location: `alembic/versions/`
- Naming convention: auto-generated with descriptive message
- Never modify a migration already applied to shared environments
- Every migration must have a reverse/down

### Models / Schema
- Location: `app/db/models.py`
- All models include `created_at` and `updated_at` timestamps
- Use UUID primary keys for render jobs (client-facing IDs)

### Queries
- Parameterized only (no string concatenation)
- Use SQLModel select() statements, not raw SQL unless performance-critical

### Testing
- Strategy: separate test database with transaction rollback
- Fixture location: `tests/fixtures/`

## Asset Handling

- Remote assets are fetched via `httpx` with async I/O; never use synchronous `requests`
- Always validate asset URLs before fetching: block localhost, link-local, private IPs, metadata service endpoints
- Content-address cached downloads by SHA-256 hash to avoid redundant fetches
- Run `ffprobe` on downloaded media to validate format, duration, and codec before rendering
- Enforce max download size, MIME type whitelist, and per-asset timeout
- Asset resolution happens in the worker, never in the API request path

## Testing

- Test behavior, not implementation
- A test's name should describe the scenario and expectation
- If it's hard to test, the design might need rethinking
- Flaky tests get fixed or deleted -- never ignored
- FFmpeg/Editly integration tests use short (1-2s) test assets to keep CI fast
- Segment compiler tests are critical: cover overlapping clips, gaps, single-clip, and edge cases
- Store sample JSON compositions in `tests/fixtures/` for golden-path tests

## Git & Version Control

- Commit messages: imperative mood, concise (`Add render status polling` not `Added some status stuff`)
- One logical change per commit
- Branch names: `type/short-description` (e.g., `feat/render-api`, `fix/ffmpeg-timeout`)
- Keep commits atomic enough to revert safely

## Pull Requests

- Small PRs get better reviews
- Description explains the *what* and *why* -- reviewers can see the *how*
- Link relevant tickets/context
- Review your own PR before requesting others

## Dependencies

- Fewer dependencies = less risk
- Justify additions; prefer well-maintained, focused libraries
- Pin versions in `requirements.txt`; use ranges in `pyproject.toml`
- Update intentionally, not automatically

## Docker

- Multi-stage builds: separate build and runtime stages
- Worker image includes both Python and Node runtimes, Editly, FFmpeg, and bundled fonts
- Non-root user in production containers
- `.dockerignore` excludes `references/`, `tests/`, docs
- Health checks on all services
- Render workspace directories are ephemeral and cleaned up after job completion

## Local Dev Tools

| Category | Tool | Config |
|----------|------|--------|
| Formatter | ruff format | pyproject.toml |
| Linter | ruff check | pyproject.toml |
| Type Safety | mypy (strict) | pyproject.toml |
| Testing | pytest + pytest-asyncio | pyproject.toml |
| Observability | structlog | app/core/logging.py |
| Git Hooks | pre-commit | .pre-commit-config.yaml |
| Database | SQLModel + Alembic | alembic.ini |

## CI/CD

Platform: GitHub Actions

| Bundle | Status | Workflow |
|--------|--------|----------|
| Code Quality | configured | .github/workflows/quality.yml |
| Build & Test | configured | .github/workflows/test.yml |
| Security | configured | .github/workflows/security.yml |
| Integration | configured | .github/workflows/integration.yml |
| Operations | not configured | - |

## Infrastructure

| Component | Provider | Details |
|-----------|----------|---------|
| Health | FastAPI /health | DB connectivity check, 30s Docker probe |
| Hosting | Docker | Multi-stage build (Python + Node + FFmpeg) |
| Database | SQLite (dev) / PostgreSQL (prod) | Async via SQLModel |
| Local Dev | docker compose up | Port 8000, healthcheck configured |
| WAF | FastAPI TrustedHostMiddleware | `allowed_hosts` allowlist, invalid Host headers rejected |
| Rate Limit | Custom middleware | 60/min default, 10/min POST /renders, health exempt |
| Backup | not configured | - |
| Deploy | not configured | - |

## When In Doubt

- Ask
- Leave it better than you found it
- Ship, learn, iterate
