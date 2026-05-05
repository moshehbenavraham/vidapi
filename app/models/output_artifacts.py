from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.composition import OutputFormat


class StoredOutputMetadata(BaseModel):
    """Durable render output metadata stored with a render record."""

    model_config = ConfigDict(frozen=True)

    format: OutputFormat
    media_type: str = Field(min_length=1, max_length=100)
    filename: str = Field(min_length=1, max_length=255)
    frame_count: int | None = Field(default=None, ge=0)
    manifest_path: str | None = Field(default=None, max_length=2048)


class RenderOutputMetadata(BaseModel):
    """Client-facing output metadata for status responses and webhooks."""

    model_config = ConfigDict(frozen=True)

    format: OutputFormat
    media_type: str = Field(min_length=1, max_length=100)
    filename: str = Field(min_length=1, max_length=255)
    frame_count: int | None = Field(default=None, ge=0)
    manifest_url: str | None = None


def output_metadata_from_render(
    render: Any,
    *,
    manifest_url: str | None = None,
) -> RenderOutputMetadata | None:
    """Build response-safe output metadata from persisted render columns."""
    if not render.output_format or not render.output_media_type:
        return None
    if not render.output_filename:
        return None

    return RenderOutputMetadata(
        format=OutputFormat(render.output_format),
        media_type=render.output_media_type,
        filename=render.output_filename,
        frame_count=render.output_frame_count,
        manifest_url=manifest_url,
    )
