from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.render import RenderStatus


class OpsRenderItem(BaseModel):
    """Redacted render row for operational list views."""

    id: str
    status: RenderStatus
    progress: int = Field(default=0, ge=0, le=100)
    stage: str | None = None
    renderer: str | None = None
    template_id: str | None = None
    template_version_id: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class OpsRenderListResponse(BaseModel):
    """Paginated redacted render list."""

    items: list[OpsRenderItem]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)


class OpsRenderFailureItem(BaseModel):
    """Redacted failed render detail for troubleshooting."""

    id: str
    status: RenderStatus
    stage: str | None = None
    renderer: str | None = None
    error_code: str | None = None
    error_message_excerpt: str | None = None
    replay_available: bool
    log_available: bool
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class OpsRenderFailureListResponse(BaseModel):
    """Paginated failed render list."""

    items: list[OpsRenderFailureItem]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)


class OpsStatusCount(BaseModel):
    """Count of renders in one status."""

    status: RenderStatus
    count: int = Field(ge=0)


class OpsStatusCountsResponse(BaseModel):
    """Current render status counts."""

    counts: list[OpsStatusCount]


class OpsRendererFailureCount(BaseModel):
    """Count of failures grouped by renderer and code."""

    renderer: str
    error_code: str
    count: int = Field(ge=0)


class OpsRendererFailureCountsResponse(BaseModel):
    """Renderer failure count snapshot."""

    counts: list[OpsRendererFailureCount]


class OpsWebhookAttemptItem(BaseModel):
    """Redacted webhook attempt row."""

    id: int
    render_id: str
    webhook_event: str
    attempt_number: int = Field(ge=1)
    status_code: int | None = None
    success: bool
    response_body_excerpt: str | None = None
    error_excerpt: str | None = None
    scheduled_at: datetime
    delivered_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class OpsWebhookAttemptsResponse(BaseModel):
    """Paginated webhook attempt list."""

    items: list[OpsWebhookAttemptItem]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)


class OpsWebhookOutcomeCount(BaseModel):
    """Count of webhook outcomes grouped by event and outcome."""

    webhook_event: str
    outcome: str
    count: int = Field(ge=0)


class OpsWebhookOutcomeCountsResponse(BaseModel):
    """Webhook outcome count snapshot."""

    counts: list[OpsWebhookOutcomeCount]
