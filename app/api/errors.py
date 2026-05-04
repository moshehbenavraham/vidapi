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
    ) -> None:
        self.detail = detail or self.__class__.detail
        self.error_code = error_code or self.__class__.error_code
        self.status_code = status_code or self.__class__.status_code
        self.context = context or {}
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


class NotFoundError(VidAPIError):
    error_code = "NOT_FOUND"
    status_code = 404
    detail = "Resource not found."


async def vidapi_error_handler(request: Request, exc: VidAPIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
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
