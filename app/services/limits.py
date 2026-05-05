from __future__ import annotations

import math
from dataclasses import dataclass

from app.core.config import Settings
from app.models.composition import (
    AudioAsset,
    ColorAsset,
    Composition,
    ImageAsset,
    OutputFormat,
    PosterMode,
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
    validate_output_format_limits(composition, settings, stats=stats)
    validate_caption_limits(composition, settings, stats=stats)
    validate_poster_limits(composition, stats=stats)


def validate_output_format_limits(
    composition: Composition,
    settings: Settings,
    *,
    stats: CompositionLimitStats | None = None,
) -> None:
    """Raise if the requested output format exceeds format guardrails."""
    if stats is None:
        stats = summarize_composition(composition)

    output_pixels = stats.output_width * stats.output_height
    if composition.output.format is OutputFormat.GIF:
        _raise_if_exceeds(
            field="output.gif.duration",
            observed=stats.duration_seconds,
            limit=settings.max_gif_duration_seconds,
            code=COMPOSITION_LIMIT_EXCEEDED,
        )
        _raise_if_exceeds(
            field="output.gif.fps",
            observed=stats.output_fps,
            limit=settings.max_gif_fps,
            code=COMPOSITION_LIMIT_EXCEEDED,
        )
        _raise_if_exceeds(
            field="output.gif.pixels",
            observed=output_pixels,
            limit=settings.max_gif_pixels,
            code=COMPOSITION_LIMIT_EXCEEDED,
        )
        return

    if composition.output.format is OutputFormat.PNG_SEQUENCE:
        frame_count = math.ceil(stats.duration_seconds * stats.output_fps)
        _raise_if_exceeds(
            field="output.png_sequence.duration",
            observed=stats.duration_seconds,
            limit=settings.max_png_sequence_duration_seconds,
            code=COMPOSITION_LIMIT_EXCEEDED,
        )
        _raise_if_exceeds(
            field="output.png_sequence.fps",
            observed=stats.output_fps,
            limit=settings.max_png_sequence_fps,
            code=COMPOSITION_LIMIT_EXCEEDED,
        )
        _raise_if_exceeds(
            field="output.png_sequence.frames",
            observed=frame_count,
            limit=settings.max_png_sequence_frames,
            code=COMPOSITION_LIMIT_EXCEEDED,
        )
        _raise_if_exceeds(
            field="output.png_sequence.pixels",
            observed=output_pixels,
            limit=settings.max_png_sequence_pixels,
            code=COMPOSITION_LIMIT_EXCEEDED,
        )


def validate_caption_limits(
    composition: Composition,
    settings: Settings,
    *,
    stats: CompositionLimitStats | None = None,
) -> None:
    """Raise if caption cues or payload size exceed configured guardrails."""
    if composition.captions is None:
        return
    if stats is None:
        stats = summarize_composition(composition)

    captions = composition.captions
    _raise_if_exceeds(
        field="captions.cues",
        observed=len(captions.cues),
        limit=settings.max_caption_cues,
        code=COMPOSITION_LIMIT_EXCEEDED,
    )

    total_chars = 0
    for index, cue in enumerate(captions.cues):
        text_length = len(cue.text)
        total_chars += text_length
        _raise_if_exceeds(
            field=f"captions.cues[{index}].text",
            observed=text_length,
            limit=settings.max_caption_text_chars,
            code=COMPOSITION_LIMIT_EXCEEDED,
        )
        _raise_if_exceeds(
            field=f"captions.cues[{index}].end",
            observed=cue.end or cue.start,
            limit=stats.duration_seconds,
            code=COMPOSITION_LIMIT_EXCEEDED,
        )

    _raise_if_exceeds(
        field="captions.total_text",
        observed=total_chars,
        limit=settings.max_caption_total_text_chars,
        code=COMPOSITION_LIMIT_EXCEEDED,
    )


def validate_poster_limits(
    composition: Composition,
    *,
    stats: CompositionLimitStats | None = None,
) -> None:
    """Raise if explicit poster timestamps exceed render duration."""
    poster = composition.output.poster
    if poster is None or poster.mode is not PosterMode.TIMESTAMP:
        return
    if stats is None:
        stats = summarize_composition(composition)
    _raise_if_exceeds(
        field="output.poster.timestamp",
        observed=poster.timestamp or 0.0,
        limit=stats.duration_seconds,
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
