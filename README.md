# VidAPI

Self-hosted Python FastAPI service for programmatic video rendering.

## Overview

VidAPI accepts JSON timeline compositions and renders video via FFmpeg/Editly.
It is a self-hosted, open-source alternative to commercial JSON video APIs
such as Creatomate and JSON2Video.

## Quickstart

```bash
# Create virtual environment
uv venv .venv
source .venv/bin/activate

# Install dependencies
uv pip install -e ".[dev]"

# Run the API server
uvicorn app.main:app --reload

# Verify
curl http://localhost:8000/v1/health
```

## Prerequisites

- Python 3.11+
- Node.js (for Editly renderer)
- FFmpeg 6+ and ffprobe

## API Overview

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/v1/health` | Health check |
| `POST` | `/v1/renders` | Create a render job |
| `GET` | `/v1/renders/{id}` | Get render status |
| `GET` | `/v1/renders/{id}/download` | Download rendered output |

## Development

```bash
# Lint and format
ruff check .
ruff format .

# Type checking
mypy app/

# Run tests
pytest
```

## Project Structure

```
app/
  main.py            # FastAPI application factory
  api/               # Route handlers and dependencies
  core/              # Config, logging, security
  db/                # Database models and sessions
  models/            # Pydantic schemas
  services/          # Business logic
  renderers/         # Renderer implementations
  storage/           # Storage adapters
  workers/           # Background job workers
tests/               # Test suite
```

## License

MIT
