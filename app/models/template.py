from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.composition import Composition


class CreateTemplateRequest(BaseModel):
    """Client request body for POST /v1/templates."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    composition: Composition
    variable_schema: dict[str, Any] | None = None


class UpdateTemplateRequest(BaseModel):
    """Client request body for PUT /v1/templates/{id}."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    composition: Composition | None = None
    variable_schema: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> UpdateTemplateRequest:
        if (
            self.name is None
            and self.description is None
            and self.composition is None
            and self.variable_schema is None
        ):
            msg = "At least one field must be provided for update"
            raise ValueError(msg)
        return self


class TemplateVersionResponse(BaseModel):
    """Embedded version info in template responses."""

    id: str
    version_number: int
    composition: dict[str, Any]
    variable_schema: dict[str, Any] | None = None
    created_at: datetime


class TemplateResponse(BaseModel):
    """Full template response for GET /v1/templates/{id}."""

    id: str
    name: str
    description: str | None = None
    active_version: TemplateVersionResponse | None = None
    is_deleted: bool = False
    created_at: datetime
    updated_at: datetime


class TemplateListItem(BaseModel):
    """Single item in the template list response."""

    id: str
    name: str
    description: str | None = None
    active_version_id: str | None = None
    version_count: int = 0
    created_at: datetime
    updated_at: datetime


class TemplateListResponse(BaseModel):
    """Paginated list of templates."""

    items: list[TemplateListItem]
    total: int
    offset: int
    limit: int


class CreateTemplateResponse(BaseModel):
    """Response for POST /v1/templates."""

    id: str
    name: str
    description: str | None = None
    active_version: TemplateVersionResponse
    created_at: datetime
    updated_at: datetime


class TemplateRenderRequest(BaseModel):
    """Client request body for POST /v1/templates/{id}/renders."""

    merge: dict[str, Any] = Field(default_factory=dict)
    callback: str | None = None


class TemplateRenderResponse(BaseModel):
    """Response for POST /v1/templates/{id}/renders."""

    id: str
    status: str
    progress: int = 0
    template_id: str
    template_version_id: str
    created_at: datetime
