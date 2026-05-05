from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


class FFProbeError(Exception):
    """Raised when ffprobe fails to extract media metadata."""


@dataclass(frozen=True)
class MediaInfo:
    """Parsed ffprobe output for a media file."""

    duration: float | None
    width: int | None
    height: int | None
    video_codec: str | None
    audio_codec: str | None
    stream_count: int
    format_name: str | None


async def probe(
    file_path: Path,
    *,
    ffprobe_bin: str = "ffprobe",
    timeout_seconds: int = 30,
    kill_grace_seconds: float = 5.0,
) -> MediaInfo:
    """Run ffprobe on a file and return parsed metadata.

    Uses ``asyncio.create_subprocess_exec`` for non-blocking I/O.
    """
    cmd = [
        ffprobe_bin,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(file_path),
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        await _terminate_process(proc, kill_grace_seconds)
        logger.error("ffprobe_timeout", path=str(file_path))
        raise FFProbeError(
            f"ffprobe timed out after {timeout_seconds}s for {file_path}"
        ) from None
    except FileNotFoundError as exc:
        raise FFProbeError("ffprobe not found on PATH -- is FFmpeg installed?") from exc

    if proc.returncode != 0:
        stderr_text = stderr.decode(errors="replace").strip()
        logger.error(
            "ffprobe_failed",
            path=str(file_path),
            returncode=proc.returncode,
            stderr=stderr_text[:500],
        )
        raise FFProbeError(
            f"ffprobe exited with code {proc.returncode}: {stderr_text[:200]}"
        )

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise FFProbeError(f"Failed to parse ffprobe JSON output: {exc}") from exc

    return _parse_probe_output(data)


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


def _parse_probe_output(data: dict[str, object]) -> MediaInfo:
    """Extract structured fields from raw ffprobe JSON."""
    streams = data.get("streams", [])
    if not isinstance(streams, list):
        streams = []

    fmt = data.get("format", {})
    if not isinstance(fmt, dict):
        fmt = {}

    duration_str = fmt.get("duration")
    duration: float | None = None
    if duration_str is not None:
        with contextlib.suppress(ValueError, TypeError):
            duration = float(str(duration_str))

    video_codec: str | None = None
    audio_codec: str | None = None
    width: int | None = None
    height: int | None = None

    for stream in streams:
        if not isinstance(stream, dict):
            continue
        codec_type = stream.get("codec_type")
        if codec_type == "video" and video_codec is None:
            video_codec = str(stream["codec_name"]) if "codec_name" in stream else None
            w = stream.get("width")
            h = stream.get("height")
            if isinstance(w, int) and isinstance(h, int):
                width = w
                height = h
        elif codec_type == "audio" and audio_codec is None:
            audio_codec = str(stream["codec_name"]) if "codec_name" in stream else None

    return MediaInfo(
        duration=duration,
        width=width,
        height=height,
        video_codec=video_codec,
        audio_codec=audio_codec,
        stream_count=len(streams),
        format_name=str(fmt["format_name"]) if "format_name" in fmt else None,
    )
