from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from pathlib import Path

import structlog

from app.core.config import Settings, get_settings
from app.models.composition import PosterMode, PosterOptions

logger = structlog.get_logger(__name__)


class PosterError(Exception):
    """Raised when poster generation fails."""


@dataclass(frozen=True)
class PosterPlan:
    mode: PosterMode
    should_generate: bool
    seek_seconds: float | None = None


async def generate_poster(
    video_path: Path,
    output_path: Path,
    *,
    settings: Settings | None = None,
    timestamp_percent: float | None = None,
    video_duration: float | None = None,
    poster_options: PosterOptions | None = None,
) -> Path:
    """Extract a frame from a rendered video as a poster thumbnail.

    Uses FFmpeg to seek to a configurable timestamp and extract a single frame.
    Returns the path to the generated poster file.
    """
    if settings is None:
        settings = get_settings()

    if not video_path.is_file():
        raise PosterError(f"Video file not found: {video_path}")

    plan = resolve_poster_plan(
        poster_options,
        settings=settings,
        timestamp_percent=timestamp_percent,
        video_duration=video_duration,
    )
    if not plan.should_generate or plan.seek_seconds is None:
        raise PosterError("Poster generation is disabled for this render")

    cmd = build_poster_command(
        video_path=video_path,
        output_path=output_path,
        seek_seconds=plan.seek_seconds,
        quality=settings.poster_quality,
        ffmpeg_bin=settings.ffmpeg_bin,
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=settings.poster_timeout_seconds,
        )
    except TimeoutError:
        await _terminate_process(proc, settings.subprocess_kill_grace_seconds)
        raise PosterError(
            f"Poster generation timed out after {settings.poster_timeout_seconds}s"
        ) from None
    except FileNotFoundError:
        raise PosterError("ffmpeg not found on PATH -- is FFmpeg installed?") from None

    if proc.returncode != 0:
        stderr_text = stderr_bytes.decode(errors="replace").strip()
        logger.error(
            "poster_generation_failed",
            returncode=proc.returncode,
            stderr=stderr_text[:500],
        )
        raise PosterError(
            f"FFmpeg poster extraction exited with code {proc.returncode}: "
            f"{stderr_text[:200]}"
        )

    if not output_path.is_file():
        raise PosterError(f"Poster file not created at {output_path}")

    logger.info("poster_generated", path=str(output_path))
    return output_path


def resolve_poster_plan(
    poster_options: PosterOptions | None,
    *,
    settings: Settings,
    video_duration: float | None,
    timestamp_percent: float | None = None,
) -> PosterPlan:
    """Resolve request-level poster options to a concrete seek time."""
    if not settings.poster_enabled:
        return PosterPlan(mode=PosterMode.DISABLED, should_generate=False)

    options = poster_options or PosterOptions()
    if options.mode is PosterMode.DISABLED:
        return PosterPlan(mode=PosterMode.DISABLED, should_generate=False)

    if options.mode is PosterMode.TIMESTAMP:
        if video_duration is None or video_duration <= 0:
            raise PosterError("Video duration is required for poster timestamp mode")
        timestamp = options.timestamp or 0.0
        if timestamp > video_duration:
            raise PosterError("Poster timestamp exceeds video duration")
        return PosterPlan(
            mode=PosterMode.TIMESTAMP,
            should_generate=True,
            seek_seconds=max(0.0, timestamp),
        )

    if options.mode is PosterMode.PERCENT:
        if video_duration is None or video_duration <= 0:
            raise PosterError("Video duration is required for poster percent mode")
        percent = options.timestamp_percent or 0.0
        return PosterPlan(
            mode=PosterMode.PERCENT,
            should_generate=True,
            seek_seconds=max(0.0, video_duration * percent),
        )

    percent = (
        timestamp_percent
        if timestamp_percent is not None
        else settings.poster_timestamp_percent
    )
    if video_duration is not None and video_duration > 0:
        seek_seconds = video_duration * percent
    else:
        seek_seconds = 1.0
    return PosterPlan(
        mode=PosterMode.DEFAULT,
        should_generate=True,
        seek_seconds=max(0.0, seek_seconds),
    )


def build_poster_command(
    *,
    video_path: Path,
    output_path: Path,
    seek_seconds: float,
    quality: int = 85,
    ffmpeg_bin: str = "ffmpeg",
) -> list[str]:
    """Build the FFmpeg command for frame extraction."""
    return [
        ffmpeg_bin,
        "-y",
        "-ss",
        f"{seek_seconds:.3f}",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-q:v",
        str(max(1, min(31, (100 - quality) * 31 // 100 + 1))),
        str(output_path),
    ]


async def _terminate_process(
    proc: asyncio.subprocess.Process,
    grace_period: float,
) -> None:
    if proc.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=grace_period)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.wait()
