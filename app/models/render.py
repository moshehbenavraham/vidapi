from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.composition import Composition

# ---------------------------------------------------------------------------
# Render Status Enum with State Machine
# ---------------------------------------------------------------------------


class RenderStatus(StrEnum):
    QUEUED = "queued"
    FETCHING = "fetching"
    COMPILING = "compiling"
    RENDERING = "rendering"
    UPLOADING = "uploading"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def allowed_transitions(self) -> frozenset[RenderStatus]:
        return _TRANSITIONS.get(self, frozenset())

    def can_transition_to(self, target: RenderStatus) -> bool:
        return target in self.allowed_transitions()

    def transition_to(self, target: RenderStatus) -> RenderStatus:
        if not self.can_transition_to(target):
            msg = f"Invalid status transition: {self.value} -> {target.value}"
            raise ValueError(msg)
        return target

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_STATES


_TRANSITIONS: dict[RenderStatus, frozenset[RenderStatus]] = {
    RenderStatus.QUEUED: frozenset(
        {
            RenderStatus.FETCHING,
            RenderStatus.CANCELLED,
            RenderStatus.FAILED,
        }
    ),
    RenderStatus.FETCHING: frozenset(
        {
            RenderStatus.COMPILING,
            RenderStatus.CANCELLED,
            RenderStatus.FAILED,
        }
    ),
    RenderStatus.COMPILING: frozenset(
        {
            RenderStatus.RENDERING,
            RenderStatus.CANCELLED,
            RenderStatus.FAILED,
        }
    ),
    RenderStatus.RENDERING: frozenset(
        {
            RenderStatus.UPLOADING,
            RenderStatus.CANCELLED,
            RenderStatus.FAILED,
        }
    ),
    RenderStatus.UPLOADING: frozenset(
        {
            RenderStatus.SUCCEEDED,
            RenderStatus.CANCELLED,
            RenderStatus.FAILED,
        }
    ),
    RenderStatus.SUCCEEDED: frozenset(),
    RenderStatus.FAILED: frozenset(),
    RenderStatus.CANCELLED: frozenset(),
}

_TERMINAL_STATES: frozenset[RenderStatus] = frozenset(
    {
        RenderStatus.SUCCEEDED,
        RenderStatus.FAILED,
        RenderStatus.CANCELLED,
    }
)


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------


class CreateRenderRequest(BaseModel):
    """Client request body for POST /v1/renders."""

    composition: Composition


class CreateRenderResponse(BaseModel):
    """Immediate response for POST /v1/renders."""

    id: str
    status: RenderStatus
    progress: int = 0
    created_at: datetime


class RenderResponse(BaseModel):
    """Full render status response for GET /v1/renders/{id}."""

    id: str
    status: RenderStatus
    stage: str | None = None
    progress: int = Field(default=0, ge=0, le=100)
    url: str | None = None
    poster: str | None = None
    duration: float | None = None
    template_id: str | None = None
    template_version_id: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: RenderError | None = None


class RenderError(BaseModel):
    """Error detail embedded in RenderResponse."""

    code: str
    message: str


# ---------------------------------------------------------------------------
# List / Pagination Models
# ---------------------------------------------------------------------------


class RenderListItem(BaseModel):
    """Single item in the render list response."""

    id: str
    status: RenderStatus
    progress: int = Field(default=0, ge=0, le=100)
    template_id: str | None = None
    template_version_id: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class RenderListResponse(BaseModel):
    """Paginated list of render jobs."""

    items: list[RenderListItem]
    total: int
    offset: int
    limit: int
