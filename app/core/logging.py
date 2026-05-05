from __future__ import annotations

import json
import logging
import sys
import traceback
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

LOGS_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
MAX_LOG_EXCERPT_CHARS = 500
REDACTED_LOG_VALUE = "[REDACTED]"
SENSITIVE_LOG_FIELD_PARTS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "callback",
        "composition",
        "cookie",
        "credential",
        "password",
        "presigned",
        "secret",
        "signature",
        "token",
        "url",
    }
)


def setup_logging(log_level: str = "INFO", json_output: bool = True) -> None:
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper()))

    for noisy_logger in ("uvicorn.access", "uvicorn.error"):
        logging.getLogger(noisy_logger).handlers.clear()
        logging.getLogger(noisy_logger).propagate = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]


def build_request_log_fields(
    *,
    request_id: str,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
) -> dict[str, Any]:
    """Return safe structured fields for request completion logs."""
    return {
        "request_id": request_id,
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 3),
    }


def redact_log_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Redact known sensitive fields before they are attached to logs."""
    return {
        key: REDACTED_LOG_VALUE if is_sensitive_log_field(key) else value
        for key, value in fields.items()
    }


def is_sensitive_log_field(field_name: str) -> bool:
    normalized = field_name.lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_LOG_FIELD_PARTS)


def safe_log_excerpt(
    value: str | None,
    *,
    limit: int = MAX_LOG_EXCERPT_CHARS,
) -> str | None:
    if value is None:
        return None
    return value[:limit]


def write_last_error(
    exc: BaseException,
    *,
    context: dict[str, Any] | None = None,
) -> Path:
    """Write structured error JSON to logs/last_error_<timestamp>.json."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=UTC)
    payload = {
        "timestamp": ts.isoformat(),
        "level": "error",
        "msg": str(exc),
        "error": {
            "type": type(exc).__name__,
            "message": str(exc),
            "stack": traceback.format_exception(exc),
        },
        "context": context or {},
    }
    safe_ts = ts.strftime("%Y-%m-%dT%H_%M_%S_%fZ")
    path = LOGS_DIR / f"last_error_{safe_ts}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path
