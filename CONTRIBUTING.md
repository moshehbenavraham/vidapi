# Contributing

## Branch Conventions

- `main` - Production-ready code
- `develop` - Integration branch
- `feature/*` - New features
- `fix/*` - Bug fixes

## Commit Style

Use conventional commits in imperative mood:

- `feat:` - New features
- `fix:` - Bug fixes
- `docs:` - Documentation changes
- `refactor:` - Code restructuring
- `test:` - Test additions or changes

Examples: `feat: Add render status polling`, `fix: Handle FFmpeg timeout`

## Pull Request Process

1. Create a feature branch from `develop`
2. Make changes with clear, atomic commits
3. Write or update tests for the affected code paths
4. Run quality gates before pushing:
   ```bash
   ruff check . && ruff format --check . && mypy app/ && pytest
   ```
5. Open PR with a description of the what and why
6. Address review feedback, squash and merge

## Development Setup

See [docs/onboarding.md](docs/onboarding.md) for environment setup.

## Code Standards

See [.spec_system/CONVENTIONS.md](.spec_system/CONVENTIONS.md) for full coding standards.

Key points:

- Python 3.11+ with type hints on all public functions
- Async by default for I/O operations
- Route handlers are thin; business logic lives in `services/`
- Custom exception classes for domain errors
- All rendering goes through the `Renderer` protocol
