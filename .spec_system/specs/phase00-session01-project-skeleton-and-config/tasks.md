# Task Checklist

**Session ID**: `phase00-session01-project-skeleton-and-config`
**Total Tasks**: 20
**Estimated Duration**: 2-3 hours
**Created**: 2026-05-05

---

## Legend

- `[x]` = Completed
- `[ ]` = Pending
- `[P]` = Parallelizable (can run with other [P] tasks)
- `[S0001]` = Session reference (00=phase number, 01=session number)
- `TNNN` = Task ID

---

## Progress Summary

| Category | Total | Done | Remaining |
|----------|-------|------|-----------|
| Setup | 3 | 3 | 0 |
| Foundation | 5 | 5 | 0 |
| Implementation | 7 | 7 | 0 |
| Testing | 5 | 5 | 0 |
| **Total** | **20** | **20** | **0** |

---

## Setup (3 tasks)

Initial configuration and environment preparation.

- [x] T001 [S0001] Verify prerequisites met (Python 3.11+, Node.js, FFmpeg 6+, ffprobe on PATH)
- [x] T002 [S0001] Create directory structure with __init__.py for all app sub-packages (`app/`, `app/api/`, `app/core/`, `app/db/`, `app/models/`, `app/services/`, `app/renderers/`, `app/storage/`, `app/workers/`, `tests/`)
- [x] T003 [S0001] Create pyproject.toml with all MVP dependencies pinned and tool config for ruff, mypy, and pytest (`pyproject.toml`)

---

## Foundation (5 tasks)

Core structures and base implementations.

- [x] T004 [S0001] Create settings class with pydantic-settings loading DATABASE_URL, storage root, app name, debug flag, log level, and allowed asset dirs with sensible dev defaults (`app/core/config.py`)
- [x] T005 [S0001] Create structlog configuration with JSON output, request-context processors, and uvicorn log integration (`app/core/logging.py`)
- [x] T006 [S0001] Create custom exception hierarchy: VidAPIError base, RenderError, AssetFetchError, CompileError, StorageError, ValidationError with error_code and detail attributes (`app/api/errors.py`)
- [x] T007 [S0001] Create FastAPI dependency injection module with get_settings provider (`app/api/deps.py`)
- [x] T008 [S0001] Create FastAPI app in main.py with application factory, v1 router registration, CORS middleware, and startup/shutdown event hooks (`app/main.py`)

---

## Implementation (7 tasks)

Main feature implementation.

- [x] T009 [S0001] Implement GET /v1/health route returning JSON status with service name and version (`app/api/routes_health.py`)
- [x] T010 [S0001] Wire health route into v1 API router and register error handlers on the app (`app/main.py`)
- [x] T011 [S0001] [P] Create .gitignore with Python bytecode, venv, IDE, node_modules, data/, .env, and OS patterns (`.gitignore`)
- [x] T012 [S0001] [P] Create .dockerignore excluding .spec_system/, references/, tests/, docs/, .git, venv, __pycache__ (`.dockerignore`)
- [x] T013 [S0001] [P] Create README.md skeleton with project description, quickstart, API overview, and dev setup instructions (`README.md`)
- [x] T014 [S0001] [P] Create placeholder security module for future auth utilities (`app/core/security.py`)
- [x] T015 [S0001] Add request-ID middleware that generates a unique ID per request and injects it into structlog context (`app/main.py`)

---

## Testing (5 tasks)

Verification and quality assurance.

- [x] T016 [S0001] Create tests/conftest.py with async test client fixture using httpx.AsyncClient and FastAPI TestClient (`tests/conftest.py`)
- [x] T017 [S0001] [P] Write tests for /v1/health: 200 status, JSON response shape, content-type header (`tests/test_health.py`)
- [x] T018 [S0001] [P] Write tests for settings: default values load, env var overrides work, invalid types raise errors (`tests/test_config.py`)
- [x] T019 [S0001] Run ruff check, ruff format, and mypy across all source files and fix any issues
- [x] T020 [S0001] Manual verification: start uvicorn, curl /v1/health, confirm structured log output, run full test suite

---

## Completion Checklist

Before marking session complete:

- [x] All tasks marked `[x]`
- [x] All tests passing
- [x] All files ASCII-encoded
- [x] ruff check and ruff format clean
- [x] mypy passes with zero errors
- [x] implementation-notes.md updated
- [x] Ready for the validate workflow step

---

## Next Steps

Run the implement workflow step to begin AI-led implementation.
