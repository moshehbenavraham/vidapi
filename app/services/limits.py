from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.models.composition import (
    AudioAsset,
    ColorAsset,
    Composition,
    ImageAsset,
    TextAsset,
    VideoAsset,
)
from app.services.ffprobe import MediaInfo

COMPOSITION_LIMIT_EXCEEDED = "COMPOSITION_LIMIT_EXCEEDED"
MEDIA_LIMIT_EXCEEDED = "MEDIA_LIMIT_EXCEEDED"


@dataclass(frozen=True)
class LimitViolation:
    """Stable details for one exceeded resource limit."""

    code: str
    message: str
    field: str
    limit: int | float
    observed: int | float

    def to_context(self) -> dict[str, int | float | str]:
        return {
            "field": self.field,
            "limit": self.limit,
            "observed": self.observed,
        }


class LimitExceededError(Exception):
    """Raised when a composition or media asset exceeds configured limits."""

    def __init__(self, violation: LimitViolation) -> None:
        self.violation = violation
        super().__init__(violation.message)


@dataclass(frozen=True)
class CompositionLimitStats:
    """Computed resource footprint for a composition."""

    duration_seconds: float
    output_width: int
    output_height: int
    output_fps: int
    track_count: int
    clip_count: int
    asset_count: int


def summarize_composition(composition: Composition) -> CompositionLimitStats:
    """Compute deterministic limit-relevant facts without side effects."""
    track_count = len(composition.timeline.tracks)
    clip_count = 0
    asset_count = 0
    duration_seconds = 0.0

    for track in composition.timeline.tracks:
        clip_count += len(track.clips)
        for clip in track.clips:
            duration_seconds = max(duration_seconds, clip.start + clip.length)
            if not isinstance(clip.asset, ColorAsset):
                asset_count += 1

    if composition.timeline.soundtrack is not None:
        asset_count += 1

    return CompositionLimitStats(
        duration_seconds=duration_seconds,
        output_width=composition.output.width or 0,
        output_height=composition.output.height or 0,
        output_fps=composition.output.fps,
        track_count=track_count,
        clip_count=clip_count,
        asset_count=asset_count,
    )


def validate_composition_limits(
    composition: Composition,
    settings: Settings,
) -> None:
    """Raise LimitExceededError if a composition exceeds app limits."""
    stats = summarize_composition(composition)
    _raise_if_exceeds(
        field="timeline.duration",
        observed=stats.duration_seconds,
        limit=settings.max_render_duration_seconds,
        code=COMPOSITION_LIMIT_EXCEEDED,
    )
    _raise_if_exceeds(
        field="output.width",
        observed=stats.output_width,
        limit=settings.max_output_width,
        code=COMPOSITION_LIMIT_EXCEEDED,
    )
    _raise_if_exceeds(
        field="output.height",
        observed=stats.output_height,
        limit=settings.max_output_height,
        code=COMPOSITION_LIMIT_EXCEEDED,
    )
    _raise_if_exceeds(
        field="output.fps",
        observed=stats.output_fps,
        limit=settings.max_fps,
        code=COMPOSITION_LIMIT_EXCEEDED,
    )
    _raise_if_exceeds(
        field="timeline.tracks",
        observed=stats.track_count,
        limit=settings.max_tracks_per_render,
        code=COMPOSITION_LIMIT_EXCEEDED,
    )
    _raise_if_exceeds(
        field="timeline.clips",
        observed=stats.clip_count,
        limit=settings.max_clips_per_render,
        code=COMPOSITION_LIMIT_EXCEEDED,
    )
    _raise_if_exceeds(
        field="timeline.assets",
        observed=stats.asset_count,
        limit=settings.max_assets_per_render,
        code=COMPOSITION_LIMIT_EXCEEDED,
    )


def validate_media_limits(
    media_info: MediaInfo,
    settings: Settings,
) -> None:
    """Raise LimitExceededError if probed media exceeds app limits."""
    if media_info.duration is not None:
        _raise_if_exceeds(
            field="media.duration",
            observed=media_info.duration,
            limit=settings.max_media_duration_seconds,
            code=MEDIA_LIMIT_EXCEEDED,
        )
    if media_info.width is not None:
        _raise_if_exceeds(
            field="media.width",
            observed=media_info.width,
            limit=settings.max_media_width,
            code=MEDIA_LIMIT_EXCEEDED,
        )
    if media_info.height is not None:
        _raise_if_exceeds(
            field="media.height",
            observed=media_info.height,
            limit=settings.max_media_height,
            code=MEDIA_LIMIT_EXCEEDED,
        )
    _raise_if_exceeds(
        field="media.streams",
        observed=media_info.stream_count,
        limit=settings.max_media_streams_per_asset,
        code=MEDIA_LIMIT_EXCEEDED,
    )


def is_media_asset(asset: object) -> bool:
    return isinstance(asset, (AudioAsset, ImageAsset, TextAsset, VideoAsset))


def _raise_if_exceeds(
    *,
    field: str,
    observed: int | float,
    limit: int | float,
    code: str,
) -> None:
    if observed <= limit:
        return
    raise LimitExceededError(
        LimitViolation(
            code=code,
            message=f"{field} exceeds configured limit",
            field=field,
            limit=limit,
            observed=observed,
        )
    )
