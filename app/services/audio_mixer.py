from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from app.core.config import Settings, get_settings

logger = structlog.get_logger(__name__)


class AudioMixError(Exception):
    """Raised when audio mixing fails."""

    def __init__(
        self,
        message: str,
        *,
        exit_code: int | None = None,
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.stderr = stderr


@dataclass(frozen=True)
class AudioSource:
    """A single audio input for the FFmpeg mix."""

    path: str
    delay_ms: int = 0
    trim_start: float | None = None
    trim_duration: float | None = None
    volume: float = 1.0
    fade_in_duration: float | None = None
    fade_out_duration: float | None = None
    total_duration: float | None = None


@dataclass(frozen=True)
class AudioMixPlan:
    """Declarative description of all audio sources to mix into the final video."""

    sources: list[AudioSource] = field(default_factory=list)
    video_has_audio: bool = True
    total_duration: float | None = None
    normalize_audio: bool = False

    @property
    def is_empty(self) -> bool:
        return len(self.sources) == 0


def _validate_source(source: AudioSource) -> None:
    if not source.path:
        raise AudioMixError("Cannot mix audio: source path is empty")
    if source.delay_ms < 0:
        raise AudioMixError("Cannot mix audio: source delay cannot be negative")
    if not 0.0 <= source.volume <= 1.0:
        raise AudioMixError("Cannot mix audio: source volume must be between 0 and 1")
    if source.trim_start is not None and source.trim_start < 0.0:
        raise AudioMixError("Cannot mix audio: trim start cannot be negative")
    if source.trim_duration is not None and source.trim_duration <= 0.0:
        raise AudioMixError("Cannot mix audio: trim duration must be positive")
    if source.fade_in_duration is not None and source.fade_in_duration <= 0.0:
        raise AudioMixError("Cannot mix audio: fade-in duration must be positive")
    if source.fade_out_duration is not None and source.fade_out_duration <= 0.0:
        raise AudioMixError("Cannot mix audio: fade-out duration must be positive")
    if source.total_duration is not None and source.total_duration <= 0.0:
        raise AudioMixError("Cannot mix audio: source total duration must be positive")


def _resolve_source_duration(
    source: AudioSource,
    plan: AudioMixPlan,
) -> float | None:
    if source.total_duration is not None:
        return source.total_duration
    if source.trim_duration is not None:
        return source.trim_duration
    return plan.total_duration


def _fade_filters(source: AudioSource, plan: AudioMixPlan) -> list[str]:
    duration = _resolve_source_duration(source, plan)
    if source.fade_in_duration is None and source.fade_out_duration is None:
        return []
    if duration is None:
        raise AudioMixError("Cannot mix audio: fade requires a bounded duration")

    fade_in = source.fade_in_duration
    fade_out = source.fade_out_duration
    if fade_in is not None and fade_out is not None:
        max_each = duration / 2.0
        fade_in = min(fade_in, max_each)
        fade_out = min(fade_out, max_each)
    elif fade_in is not None:
        fade_in = min(fade_in, duration)
    elif fade_out is not None:
        fade_out = min(fade_out, duration)

    filters: list[str] = []
    if fade_in is not None and fade_in > 0.0:
        filters.append(f"afade=t=in:st=0.000000:d={fade_in:.6f}")
    if fade_out is not None and fade_out > 0.0:
        start = max(duration - fade_out, 0.0)
        filters.append(f"afade=t=out:st={start:.6f}:d={fade_out:.6f}")
    return filters


def build_mix_filter_graph(plan: AudioMixPlan) -> tuple[str, int]:
    """Build an FFmpeg complex filter string from an AudioMixPlan.

    Returns (filter_graph_string, total_input_count) where total_input_count
    includes the video file as input [0].
    """
    if plan.is_empty:
        return "", 0

    filters: list[str] = []
    mix_inputs: list[str] = []
    input_index = 1

    for source in plan.sources:
        _validate_source(source)
        label = f"a{input_index}"
        chain_parts: list[str] = []

        if source.trim_start is not None or source.trim_duration is not None:
            trim_start = source.trim_start or 0.0
            atrim = f"atrim=start={trim_start:.6f}"
            if source.trim_duration is not None:
                atrim += f":duration={source.trim_duration:.6f}"
            chain_parts.append(atrim)
            chain_parts.append("asetpts=PTS-STARTPTS")

        if abs(source.volume - 1.0) > 1e-6:
            chain_parts.append(f"volume={source.volume:.6f}")

        chain_parts.extend(_fade_filters(source, plan))

        if source.delay_ms > 0:
            chain_parts.append(f"adelay={source.delay_ms}|{source.delay_ms}")

        if chain_parts:
            chain = ",".join(chain_parts)
            filters.append(f"[{input_index}:a]{chain}[{label}]")
        else:
            label = f"{input_index}:a"

        mix_inputs.append(f"[{label}]")
        input_index += 1

    total_inputs = input_index

    if plan.video_has_audio:
        mix_inputs.insert(0, "[0:a]")
    else:
        filters.append("anullsrc=channel_layout=stereo:sample_rate=44100[silence]")
        mix_inputs.insert(0, "[silence]")

    n = len(mix_inputs)
    mix_input_str = "".join(mix_inputs)
    if plan.normalize_audio:
        filters.append(f"{mix_input_str}amix=inputs={n}:duration=longest[mixed]")
        filters.append("[mixed]dynaudnorm[aout]")
    else:
        filters.append(f"{mix_input_str}amix=inputs={n}:duration=longest[aout]")

    filter_graph = ";".join(filters)
    return filter_graph, total_inputs


async def mix_audio(
    video_path: Path,
    output_path: Path,
    plan: AudioMixPlan,
    *,
    settings: Settings | None = None,
) -> Path:
    """Invoke FFmpeg to mix audio sources into the rendered video.

    Copies the video stream and replaces/adds the audio stream.
    Returns the output path on success.
    """
    if settings is None:
        settings = get_settings()

    if plan.is_empty:
        raise AudioMixError("Cannot mix audio: plan has no sources")

    filter_graph, _total_inputs = build_mix_filter_graph(plan)

    cmd: list[str] = [settings.ffmpeg_bin, "-y"]
    cmd.extend(["-i", str(video_path)])

    for source in plan.sources:
        cmd.extend(["-i", source.path])

    cmd.extend(["-filter_complex", filter_graph])
    cmd.extend(["-map", "0:v", "-map", "[aout]"])
    cmd.extend(["-c:v", "copy"])
    cmd.extend(["-shortest"])
    cmd.append(str(output_path))

    logger.info(
        "audio_mix_start",
        video=str(video_path),
        sources=len(plan.sources),
        cmd=" ".join(cmd),
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=settings.audio_mix_timeout_seconds,
            )
        except TimeoutError as err:
            proc.kill()
            await proc.wait()
            raise AudioMixError(
                f"Audio mixing timed out after {settings.audio_mix_timeout_seconds}s",
                exit_code=proc.returncode,
                stderr="TIMEOUT",
            ) from err
    except FileNotFoundError as err:
        raise AudioMixError(
            f"FFmpeg binary not found: {settings.ffmpeg_bin}",
            exit_code=127,
        ) from err

    stderr_text = stderr.decode(errors="replace") if stderr else ""

    if proc.returncode != 0:
        raise AudioMixError(
            f"FFmpeg exited with code {proc.returncode}",
            exit_code=proc.returncode,
            stderr=stderr_text[-2000:],
        )

    if not output_path.is_file():
        raise AudioMixError(
            "FFmpeg completed but output file not found",
            exit_code=proc.returncode,
            stderr=stderr_text[-2000:],
        )

    logger.info(
        "audio_mix_complete",
        output=str(output_path),
    )

    return output_path
