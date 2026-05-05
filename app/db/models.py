from __future__ import annotations

import os
import time
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

from app.models.render import RenderStatus


def _generate_render_id() -> str:
    """Generate a sortable render ID with ``render_`` prefix.

    Uses a base-36 timestamp for rough ordering. A production system
    would use a proper ULID library; this keeps the dependency list small
    for the MVP.
    """
    ts = int(time.time() * 1000)
    rand = int.from_bytes(os.urandom(5))
    encoded = _base36(ts) + _base36(rand).zfill(8)
    return f"render_{encoded}"


def _base36(n: int) -> str:
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    if n == 0:
        return "0"
    result: list[str] = []
    while n:
        n, rem = divmod(n, 36)
        result.append(chars[rem])
    return "".join(reversed(result))


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class Render(SQLModel, table=True):
    __tablename__ = "renders"

    id: str = Field(default_factory=_generate_render_id, primary_key=True)
    status: str = Field(default=RenderStatus.QUEUED.value, index=True)
    progress: int = Field(default=0)
    stage: str | None = Field(default=None)
    renderer: str | None = Field(default=None)

    input_path: str | None = Field(default=None)
    expanded_path: str | None = Field(default=None)
    compiled_path: str | None = Field(default=None)
    output_path: str | None = Field(default=None)
    output_format: str | None = Field(default=None, max_length=32)
    output_media_type: str | None = Field(default=None, max_length=100)
    output_filename: str | None = Field(default=None, max_length=255)
    output_frame_count: int | None = Field(default=None)
    output_manifest_path: str | None = Field(default=None, max_length=2048)
    poster_path: str | None = Field(default=None)
    caption_mode: str | None = Field(default=None, max_length=32)
    caption_format: str | None = Field(default=None, max_length=32)
    caption_sidecar_path: str | None = Field(default=None, max_length=2048)
    caption_sidecar_media_type: str | None = Field(default=None, max_length=100)
    caption_sidecar_filename: str | None = Field(default=None, max_length=255)
    caption_cue_count: int | None = Field(default=None)
    caption_burned_in: bool | None = Field(default=None)
    poster_mode: str | None = Field(default=None, max_length=32)
    poster_timestamp_seconds: float | None = Field(default=None)
    poster_media_type: str | None = Field(default=None, max_length=100)
    poster_filename: str | None = Field(default=None, max_length=255)
    replay_path: str | None = Field(default=None)
    log_path: str | None = Field(default=None)

    template_id: str | None = Field(default=None, index=True)
    template_version_id: str | None = Field(default=None)

    error_code: str | None = Field(default=None)
    error_message: str | None = Field(default=None)

    callback_url: str | None = Field(default=None)

    cancel_requested_at: datetime | None = Field(default=None)

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
