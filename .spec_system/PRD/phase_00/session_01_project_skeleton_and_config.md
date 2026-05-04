# Session 01: Project Skeleton and Config

**Session ID**: `phase00-session01-project-skeleton-and-config`
**Status**: Not Started
**Estimated Tasks**: ~15-20
**Estimated Duration**: 2-4 hours

---

## Objective

Establish the FastAPI project structure, configuration management, health endpoint, structured logging, dev tooling, and dependency management so all subsequent sessions build on a consistent foundation.

---

## Scope

### In Scope (MVP)
- Project directory structure matching PRD layout (app/, tests/, etc.)
- pyproject.toml with all MVP dependencies and tool config (ruff, mypy, pytest)
- FastAPI application factory or main.py entry point
- Settings management with pydantic-settings (DATABASE_URL, storage paths, etc.)
- GET /v1/health endpoint
- Structured logging setup with structlog
- Basic error handling middleware
- .gitignore, .dockerignore
- README skeleton

### Out of Scope
- Database models and migrations (Session 02)
- Pydantic composition schema (Session 02)
- Storage adapter implementation (Session 03)
- Renderer code (Session 04)
- Render API endpoints beyond health (Session 05)

---

## Prerequisites

- [ ] Python 3.11+ available
- [ ] Node.js runtime available
- [ ] FFmpeg 6+ and ffprobe available

---

## Deliverables

1. Project directory structure under app/ with api/, core/, db/, models/, services/, renderers/, storage/, workers/ packages
2. pyproject.toml with pinned dependencies and tool configuration
3. FastAPI app with /v1/health endpoint returning service status
4. Settings class with environment variable loading via pydantic-settings
5. Structured logging configuration with structlog
6. Error handling utilities and custom exception classes
7. Dev tooling config: ruff, mypy, pytest
8. .gitignore and .dockerignore files

---

## Success Criteria

- [ ] `uvicorn app.main:app` starts without errors
- [ ] GET /v1/health returns 200 with JSON status
- [ ] ruff check and ruff format pass cleanly
- [ ] mypy passes with no errors
- [ ] pytest discovers and runs (even with zero tests)
- [ ] Settings load from environment variables with sensible defaults
