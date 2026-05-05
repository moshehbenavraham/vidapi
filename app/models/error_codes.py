from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    """Stable machine-readable error codes for all render failure modes.

    These codes are returned in API responses and stored in the database.
    They MUST remain stable across versions for client compatibility.
    """

    RENDER_TIMEOUT = "RENDER_TIMEOUT"
    COMPILE_ERROR = "COMPILE_ERROR"
    RENDER_ERROR = "RENDER_ERROR"
    ASSET_FETCH_ERROR = "ASSET_FETCH_ERROR"
    MERGE_ERROR = "MERGE_ERROR"
    STORAGE_ERROR = "STORAGE_ERROR"
    NO_INPUT_DATA = "NO_INPUT_DATA"
    INPUT_FILE_MISSING = "INPUT_FILE_MISSING"
    QUEUE_UNAVAILABLE = "QUEUE_UNAVAILABLE"
    QUEUE_SATURATED = "QUEUE_SATURATED"
    REQUEST_BODY_TOO_LARGE = "REQUEST_BODY_TOO_LARGE"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
    MEDIA_LIMIT_EXCEEDED = "MEDIA_LIMIT_EXCEEDED"
    RENDER_CANCELLED = "RENDER_CANCELLED"
    WORKER_UNEXPECTED_ERROR = "WORKER_UNEXPECTED_ERROR"
    INVALID_COMPOSITION = "INVALID_COMPOSITION"
    TEMPLATE_EXPANSION_ERROR = "TEMPLATE_EXPANSION_ERROR"
    TEMPLATE_VARIABLE_ERROR = "TEMPLATE_VARIABLE_ERROR"


_EXCEPTION_MAP: dict[type, ErrorCode] = {}


def register_exception(exc_type: type, code: ErrorCode) -> None:
    """Register an exception type to an error code for lookup."""
    _EXCEPTION_MAP[exc_type] = code


def error_code_for_exception(exc: Exception) -> ErrorCode:
    """Resolve an exception to its registered error code.

    Walks the MRO to find the most specific registered type.
    Falls back to WORKER_UNEXPECTED_ERROR for unregistered exceptions.
    """
    for cls in type(exc).__mro__:
        if cls in _EXCEPTION_MAP:
            return _EXCEPTION_MAP[cls]
    return ErrorCode.WORKER_UNEXPECTED_ERROR


def _register_defaults() -> None:
    """Wire up default exception-to-code mappings.

    Called at module load. Additional mappings can be registered at runtime
    via register_exception() for plugin renderers.
    """
    from app.api.errors import AssetFetchError, MediaLimitError
    from app.renderers.base import CompileError, RenderError
    from app.services.limits import LimitExceededError
    from app.services.merge import MergeError
    from app.services.render_service import RenderServiceError
    from app.services.template_engine import (
        TemplateExpansionError,
        TemplateVariableError,
    )

    register_exception(CompileError, ErrorCode.COMPILE_ERROR)
    register_exception(RenderError, ErrorCode.RENDER_ERROR)
    register_exception(AssetFetchError, ErrorCode.ASSET_FETCH_ERROR)
    register_exception(MediaLimitError, ErrorCode.MEDIA_LIMIT_EXCEEDED)
    register_exception(LimitExceededError, ErrorCode.LIMIT_EXCEEDED)
    register_exception(MergeError, ErrorCode.MERGE_ERROR)
    register_exception(TimeoutError, ErrorCode.RENDER_TIMEOUT)
    register_exception(asyncio.TimeoutError, ErrorCode.RENDER_TIMEOUT)
    register_exception(OSError, ErrorCode.STORAGE_ERROR)
    register_exception(RenderServiceError, ErrorCode.RENDER_ERROR)
    register_exception(asyncio.CancelledError, ErrorCode.RENDER_CANCELLED)
    register_exception(TemplateExpansionError, ErrorCode.TEMPLATE_EXPANSION_ERROR)
    register_exception(TemplateVariableError, ErrorCode.TEMPLATE_VARIABLE_ERROR)


import asyncio  # noqa: E402

_register_defaults()
