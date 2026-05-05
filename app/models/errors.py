from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    """Stable error object for documented API failures."""

    code: str = Field(examples=["NOT_FOUND"])
    message: str = Field(examples=["Requested resource was not found."])
    context: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    """Envelope used by VidAPI-managed error responses."""

    error: ErrorDetail


class DetailErrorResponse(BaseModel):
    """Envelope used by FastAPI HTTPException string details."""

    detail: str


class StructuredDetailErrorResponse(BaseModel):
    """Envelope used when HTTPException detail is a structured object."""

    model_config = ConfigDict(extra="allow")

    detail: dict[str, Any]


class ValidationErrorResponse(BaseModel):
    """Envelope used by FastAPI request validation failures."""

    detail: list[dict[str, Any]]


class RateLimitErrorResponse(BaseModel):
    """Structured rate-limit response with retry metadata."""

    detail: str
    retry_after: int
    error: ErrorDetail


def documented_error(
    description: str,
    model: type[BaseModel] = DetailErrorResponse,
) -> dict[str, Any]:
    return {"description": description, "model": model}


VALIDATION_ERROR = documented_error(
    "Request validation failed.",
    ValidationErrorResponse,
)
RATE_LIMIT_ERROR = documented_error(
    "Rate limit exceeded.",
    RateLimitErrorResponse,
)
QUEUE_UNAVAILABLE_ERROR = documented_error(
    "Render queue is unavailable.",
    DetailErrorResponse,
)
NOT_FOUND_ERROR = documented_error(
    "Requested resource was not found.",
    DetailErrorResponse,
)
CONFLICT_ERROR = documented_error(
    "Request conflicts with current resource state.",
    DetailErrorResponse,
)
