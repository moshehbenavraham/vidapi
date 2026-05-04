# Session Specification

**Session ID**: `phase00-session01-project-skeleton-and-config`
**Phase**: 00 - Foundation
**Status**: Not Started
**Created**: 2026-05-05

---

## 1. Session Overview

This session establishes the foundational project structure for VidAPI -- a self-hosted FastAPI service for programmatic video rendering. The work creates the Python package layout, dependency management, application entry point, configuration system, structured logging, error handling utilities, health endpoint, and developer tooling configuration.

Everything built here becomes the base that Sessions 02-05 build on. Getting the directory structure, config management, logging, and dev tooling right now prevents friction in every subsequent session. The health endpoint proves the FastAPI app boots and serves requests, giving a known-good starting point for adding render, storage, and composition endpoints later.

This is purely a scaffolding session -- no business logic, no database models, no rendering code. The focus is on project hygiene, conventions compliance, and a clean development experience.

---

## 2. Objectives

1. Create a well-organized Python package structure matching the PRD's suggested layout with all sub-packages initialized
2. Configure dependency management and dev tooling (ruff, mypy, pytest) in pyproject.toml so code quality checks work from day one
3. Implement a settings system that loads configuration from environment variables with sensible development defaults
4. Deliver a working /v1/health endpoint with structured logging and error handling middleware

---

## 3. Prerequisites

### Required Sessions
- None (first session in Phase 00)

### Required Tools/Knowledge
- Python 3.11+ with pip/uv
- Familiarity with FastAPI, Pydantic v2, structlog

### Environment Requirements
- Python 3.11+ installed and on PATH
- Node.js runtime installed (verified but not used in this session)
- FFmpeg 6+ and ffprobe installed (verified but not used in this session)

---

## 4. Scope

### In Scope (MVP)
- Developer can clone and set up the project with a single dependency install command
- Developer can run `uvicorn app.main:app` and hit /v1/health successfully
- Developer can run `ruff check`, `ruff format`, and `mypy` with zero errors
- Developer can run `pytest` with test discovery working
- All sub-packages under app/ have __init__.py files for import resolution
- Settings load from environment variables with documented defaults
- Structured logging emits JSON-formatted log lines with request context
- Custom exception hierarchy exists for domain errors used in later sessions
- .gitignore and .dockerignore cover Python, Node, IDE, and project-specific patterns

### Out of Scope (Deferred)
- Database models, migrations, SQLite session -- *Reason: Session 02*
- Pydantic composition schema -- *Reason: Session 02*
- Storage adapter and asset service -- *Reason: Session 03*
- Renderer code and segment compiler -- *Reason: Session 04*
- Render API endpoints (POST/GET renders) -- *Reason: Session 05*
- Docker Compose and Dockerfiles -- *Reason: Phase 01*

---

## 5. Technical Approach

### Architecture
Standard FastAPI application factory pattern. The app entry point in `app/main.py` creates the FastAPI instance, registers the v1 API router, attaches middleware, and configures startup/shutdown events. Settings are loaded once via pydantic-settings and injected via FastAPI's dependency system.

### Design Patterns
- **Application Factory**: FastAPI app created in a function for testability
- **Dependency Injection**: FastAPI `Depends()` for settings and future shared resources
- **Layered Package Structure**: api/ for routes, core/ for cross-cutting concerns, services/ for business logic, etc.
- **Configuration via Environment**: pydantic-settings with .env file support and typed defaults

### Technology Stack
- Python 3.11+
- FastAPI 0.115+
- Pydantic v2 / pydantic-settings
- structlog for structured logging
- Uvicorn as ASGI server
- ruff for formatting and linting
- mypy for type checking
- pytest + pytest-asyncio for testing

---

## 6. Deliverables

### Files to Create
| File | Purpose | Est. Lines |
|------|---------|------------|
| `pyproject.toml` | Dependencies, tool config (ruff, mypy, pytest) | ~120 |
| `app/__init__.py` | Package init | ~1 |
| `app/main.py` | FastAPI app factory, router registration, middleware | ~60 |
| `app/core/__init__.py` | Package init | ~1 |
| `app/core/config.py` | Settings class with pydantic-settings | ~80 |
| `app/core/logging.py` | structlog configuration | ~50 |
| `app/core/security.py` | Placeholder for auth utilities | ~5 |
| `app/api/__init__.py` | Package init | ~1 |
| `app/api/deps.py` | Dependency injection (get_settings) | ~20 |
| `app/api/errors.py` | Custom exceptions and error handler registration | ~80 |
| `app/api/routes_health.py` | GET /v1/health handler | ~25 |
| `app/db/__init__.py` | Package init | ~1 |
| `app/models/__init__.py` | Package init | ~1 |
| `app/services/__init__.py` | Package init | ~1 |
| `app/renderers/__init__.py` | Package init | ~1 |
| `app/storage/__init__.py` | Package init | ~1 |
| `app/workers/__init__.py` | Package init | ~1 |
| `tests/__init__.py` | Package init | ~1 |
| `tests/conftest.py` | Shared pytest fixtures, test client | ~40 |
| `tests/test_health.py` | Health endpoint tests | ~30 |
| `tests/test_config.py` | Settings loading tests | ~40 |
| `.gitignore` | Git ignore patterns | ~40 |
| `.dockerignore` | Docker build exclusions | ~25 |
| `README.md` | Project readme skeleton | ~50 |

### Files to Modify
| File | Changes | Est. Lines |
|------|---------|------------|
| (none -- greenfield session) | | |

---

## 7. Success Criteria

### Functional Requirements
- [ ] `uvicorn app.main:app` starts without errors on default settings
- [ ] GET /v1/health returns 200 with JSON `{"status": "ok"}` or equivalent
- [ ] Settings load DATABASE_URL, storage paths, and app metadata from env vars with defaults
- [ ] structlog emits structured JSON log lines

### Testing Requirements
- [ ] pytest discovers and runs all tests in tests/
- [ ] Health endpoint test verifies 200 status and response shape
- [ ] Settings test verifies default values and environment override

### Non-Functional Requirements
- [ ] Health endpoint responds in under 50ms
- [ ] All source files use ASCII-only characters and Unix LF line endings

### Quality Gates
- [ ] All files ASCII-encoded
- [ ] Unix LF line endings
- [ ] ruff check passes with zero warnings
- [ ] ruff format reports no changes needed
- [ ] mypy passes with zero errors
- [ ] Code follows CONVENTIONS.md patterns (snake_case, type hints, thin routes)

---

## 8. Implementation Notes

### Key Considerations
- pyproject.toml should pin exact versions for core dependencies (FastAPI, Pydantic, structlog, SQLModel) but use compatible ranges for dev tools
- Settings class needs defaults that work for local development without any .env file
- The custom exception hierarchy should anticipate domain errors from later sessions (RenderError, AssetFetchError, CompileError, StorageError) even though they are not used yet
- All __init__.py files should be empty or contain only __all__ exports -- no logic

### Potential Challenges
- **mypy strictness with FastAPI/Pydantic**: Use appropriate type stubs and configure mypy to handle Pydantic v2 plugin
- **structlog + uvicorn log integration**: Need to configure structlog processors to play nicely with uvicorn's own logging

### Relevant Considerations
- CONVENTIONS.md requires async by default for I/O operations -- the health endpoint should be async def
- CONVENTIONS.md requires structlog for observability -- set up from session 01
- CONVENTIONS.md requires ruff + mypy -- configure in pyproject.toml with strict settings
- Avoid synchronous rendering in API process (lesson from CONSIDERATIONS.md) -- not applicable yet but the architecture must not create blocking patterns

---

## 9. Testing Strategy

### Unit Tests
- Settings class loads defaults correctly
- Settings class overrides from environment variables
- Custom exception classes instantiate with expected attributes

### Integration Tests
- FastAPI test client hits /v1/health and gets 200 with expected JSON
- Unknown routes return 404 with structured error response

### Manual Testing
- Run `uvicorn app.main:app --reload` and curl /v1/health
- Verify structured log output in terminal
- Run `ruff check .` and `mypy app/` and confirm clean output

### Edge Cases
- Missing environment variables fall back to defaults without crashing
- Invalid environment variable types raise clear configuration errors at startup

---

## 10. Dependencies

### External Libraries
- fastapi: 0.115+
- pydantic: 2.x
- pydantic-settings: 2.x
- uvicorn: 0.30+
- structlog: 24.x+
- httpx: 0.27+ (for test client and future asset fetching)
- sqlmodel: 0.0.22+
- aiosqlite: 0.20+
- pillow: 10.x+
- pytest: 8.x+
- pytest-asyncio: 0.24+
- ruff: 0.7+
- mypy: 1.13+

### Other Sessions
- **Depends on**: None
- **Depended by**: Session 02, 03, 04, 05 (all subsequent Phase 00 sessions)

---

## Next Steps

Run the implement workflow step to begin AI-led implementation.
