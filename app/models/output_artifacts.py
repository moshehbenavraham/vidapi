from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.composition import CaptionFormat, CaptionMode, OutputFormat, PosterMode


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


class StoredCaptionMetadata(BaseModel):
    """Durable caption metadata stored with a render record."""

    model_config = ConfigDict(frozen=True)

    mode: CaptionMode
    format: CaptionFormat | None = None
    sidecar_media_type: str | None = Field(default=None, max_length=100)
    sidecar_filename: str | None = Field(default=None, max_length=255)
    cue_count: int = Field(ge=0)
    burned_in: bool = False


class RenderCaptionMetadata(BaseModel):
    """Client-facing caption metadata for status responses and webhooks."""

    model_config = ConfigDict(frozen=True)

    mode: CaptionMode
    format: CaptionFormat | None = None
    cue_count: int = Field(ge=0)
    burned_in: bool = False
    sidecar_url: str | None = None
    media_type: str | None = None
    filename: str | None = None


class StoredPosterMetadata(BaseModel):
    """Durable poster metadata stored with a render record."""

    model_config = ConfigDict(frozen=True)

    mode: PosterMode
    timestamp_seconds: float | None = Field(default=None, ge=0.0)
    media_type: str | None = Field(default=None, max_length=100)
    filename: str | None = Field(default=None, max_length=255)


class RenderPosterMetadata(BaseModel):
    """Client-facing poster metadata for status responses and webhooks."""

    model_config = ConfigDict(frozen=True)

    mode: PosterMode
    timestamp_seconds: float | None = Field(default=None, ge=0.0)
    url: str | None = None
    media_type: str | None = None
    filename: str | None = None


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


def caption_metadata_from_render(
    render: Any,
    *,
    sidecar_url: str | None = None,
) -> RenderCaptionMetadata | None:
    """Build response-safe caption metadata from persisted render columns."""
    if not getattr(render, "caption_mode", None):
        return None

    caption_format = getattr(render, "caption_format", None)
    cue_count = getattr(render, "caption_cue_count", None)
    return RenderCaptionMetadata(
        mode=CaptionMode(render.caption_mode),
        format=CaptionFormat(caption_format) if caption_format else None,
        cue_count=cue_count or 0,
        burned_in=bool(getattr(render, "caption_burned_in", False)),
        sidecar_url=sidecar_url,
        media_type=getattr(render, "caption_sidecar_media_type", None),
        filename=getattr(render, "caption_sidecar_filename", None),
    )


def poster_metadata_from_render(
    render: Any,
    *,
    poster_url: str | None = None,
) -> RenderPosterMetadata | None:
    """Build response-safe poster metadata from persisted render columns."""
    if not getattr(render, "poster_mode", None):
        return None

    return RenderPosterMetadata(
        mode=PosterMode(render.poster_mode),
        timestamp_seconds=getattr(render, "poster_timestamp_seconds", None),
        url=poster_url,
        media_type=getattr(render, "poster_media_type", None),
        filename=getattr(render, "poster_filename", None),
    )
