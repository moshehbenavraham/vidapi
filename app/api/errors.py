from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class VidAPIError(Exception):
    error_code: str = "VIDAPI_ERROR"
    status_code: int = 500
    detail: str = "An unexpected error occurred."

    def __init__(
        self,
        detail: str | None = None,
        error_code: str | None = None,
        status_code: int | None = None,
        context: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.detail = detail or self.__class__.detail
        self.error_code = error_code or self.__class__.error_code
        self.status_code = status_code or self.__class__.status_code
        self.context = context or {}
        self.headers = headers or {}
        super().__init__(self.detail)


class RenderError(VidAPIError):
    error_code = "RENDER_ERROR"
    status_code = 500
    detail = "Render operation failed."


class AssetFetchError(VidAPIError):
    error_code = "ASSET_FETCH_ERROR"
    status_code = 502
    detail = "Failed to fetch remote asset."


class CompileError(VidAPIError):
    error_code = "COMPILE_ERROR"
    status_code = 500
    detail = "Failed to compile composition for renderer."


class StorageError(VidAPIError):
    error_code = "STORAGE_ERROR"
    status_code = 500
    detail = "Storage operation failed."


class CompositionValidationError(VidAPIError):
    error_code = "VALIDATION_ERROR"
    status_code = 422
    detail = "Composition validation failed."


class RequestBodyTooLargeError(VidAPIError):
    error_code = "REQUEST_BODY_TOO_LARGE"
    status_code = 413
    detail = "Request body exceeds configured size limit."


class LimitExceededAPIError(VidAPIError):
    error_code = "COMPOSITION_LIMIT_EXCEEDED"
    status_code = 422
    detail = "Request exceeds configured resource limits."

    @classmethod
    def from_violation(cls, violation: Any) -> LimitExceededAPIError:
        return cls(
            detail=str(violation.message),
            error_code=str(violation.code),
            context=dict(violation.to_context()),
        )


class MediaLimitError(AssetFetchError):
    error_code = "MEDIA_LIMIT_EXCEEDED"
    status_code = 422
    detail = "Media asset exceeds configured limits."

    @classmethod
    def from_violation(cls, violation: Any) -> MediaLimitError:
        return cls(
            detail=str(violation.message),
            error_code=str(violation.code),
            context=dict(violation.to_context()),
        )


class QueueSaturatedAPIError(VidAPIError):
    error_code = "QUEUE_SATURATED"
    status_code = 429
    detail = "Render queue is at capacity."

    def __init__(self, *, depth: int, max_depth: int, retry_after: int) -> None:
        super().__init__(
            context={
                "field": "queue.depth",
                "limit": max_depth,
                "observed": depth,
                "retry_after": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )


class NotFoundError(VidAPIError):
    error_code = "NOT_FOUND"
    status_code = 404
    detail = "Resource not found."


class MissingAPIKeyError(VidAPIError):
    error_code = "AUTHENTICATION_REQUIRED"
    status_code = 401
    detail = "Missing API key."


class InvalidAPIKeyError(VidAPIError):
    error_code = "INVALID_API_KEY"
    status_code = 403
    detail = "Invalid API key."


async def vidapi_error_handler(request: Request, exc: VidAPIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "error": {
                "code": exc.error_code,
                "message": exc.detail,
                "context": exc.context if exc.context else None,
            }
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(VidAPIError, vidapi_error_handler)  # type: ignore[arg-type]
