from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass
from pathlib import Path

import structlog

from app.core.config import Settings, get_settings
from app.models.composition import CaptionMode, Captions
from app.renderers.base import RenderArtifact, RenderError
from app.services.caption_formats import (
    ASS_MEDIA_TYPE,
    CaptionSidecarSpec,
    ass_bytes,
    caption_sidecar_bytes,
    caption_sidecar_spec,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class CaptionSidecarArtifact:
    path: Path
    spec: CaptionSidecarSpec


@dataclass(frozen=True)
class CaptionFinishResult:
    video_artifact: RenderArtifact
    sidecar: CaptionSidecarArtifact | None = None
    burn_in_log_path: Path | None = None


class CaptionFinishingError(RenderError):
    """Raised when caption sidecar or burn-in finishing fails."""

    def __init__(
        self,
        message: str,
        *,
        exit_code: int | None = None,
        stderr: str = "",
        error_type: str = "caption_finishing_error",
    ) -> None:
        super().__init__(message, exit_code=exit_code)
        self.stderr = stderr
        self.error_type = error_type


class CaptionFinisher:
    """Prepare caption sidecars or captioned MP4 intermediates."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def finish(
        self,
        *,
        captions: Captions,
        artifact: RenderArtifact,
        render_id: str,
        workspace: Path,
    ) -> CaptionFinishResult:
        if captions.mode is CaptionMode.SIDECAR:
            sidecar = await self.prepare_sidecar(
                captions=captions,
                render_id=render_id,
                workspace=workspace,
            )
            return CaptionFinishResult(video_artifact=artifact, sidecar=sidecar)

        return await self.burn_in(
            captions=captions,
            artifact=artifact,
            render_id=render_id,
            workspace=workspace,
        )

    async def prepare_sidecar(
        self,
        *,
        captions: Captions,
        render_id: str,
        workspace: Path,
    ) -> CaptionSidecarArtifact:
        spec = caption_sidecar_spec(render_id, captions)
        path = workspace / spec.filename
        try:
            await asyncio.to_thread(path.write_bytes, caption_sidecar_bytes(captions))
        except OSError as exc:
            raise CaptionFinishingError(
                "Failed to write caption sidecar",
                error_type="sidecar_write_error",
            ) from exc
        if not path.is_file():
            raise CaptionFinishingError(
                "Caption sidecar file was not created",
                error_type="missing_sidecar",
            )
        return CaptionSidecarArtifact(path=path, spec=spec)

    async def burn_in(
        self,
        *,
        captions: Captions,
        artifact: RenderArtifact,
        render_id: str,
        workspace: Path,
    ) -> CaptionFinishResult:
        ass_path = workspace / f"{render_id}-captions.ass"
        output_path = workspace / f"{render_id}-captioned.mp4"
        log_path = workspace / f"{render_id}-caption-burn-in.log"
        try:
            await asyncio.to_thread(ass_path.write_bytes, ass_bytes(captions))
            await self._run_ffmpeg(
                build_caption_burn_in_command(
                    self._settings.ffmpeg_bin,
                    artifact.output_path,
                    ass_path,
                    output_path,
                ),
                log_path=log_path,
            )
            if not output_path.is_file():
                raise CaptionFinishingError(
                    "FFmpeg completed but captioned output is missing",
                    stderr=log_path.read_text(encoding="utf-8", errors="replace")
                    if log_path.exists()
                    else "",
                    error_type="missing_output",
                )
        except Exception:
            output_path.unlink(missing_ok=True)
            raise

        await logger.ainfo("caption_burn_in_complete", render_id=render_id)
        return CaptionFinishResult(
            video_artifact=RenderArtifact(
                output_path=output_path,
                poster_path=artifact.poster_path,
                log_path=log_path,
                duration_seconds=artifact.duration_seconds,
                exit_code=0,
            ),
            burn_in_log_path=log_path,
        )

    async def _run_ffmpeg(self, command: list[str], *, log_path: Path) -> None:
        start = time.monotonic()
        timed_out = False
        exit_code: int | None = None
        stderr = ""

        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self._settings.caption_burn_in_timeout_seconds,
                )
                exit_code = proc.returncode
                stderr = stderr_bytes.decode("utf-8", errors="replace")
            except TimeoutError:
                timed_out = True
                await self._terminate_process(proc)
                exit_code = proc.returncode
                stderr = "TIMEOUT: FFmpeg caption burn-in timed out"
        except FileNotFoundError:
            exit_code = 127
            stderr = f"FFmpeg binary not found: {self._settings.ffmpeg_bin}"

        bounded_stderr = stderr[-self._settings.max_subprocess_stderr_bytes :]
        log_path.write_text(bounded_stderr, encoding="utf-8")

        if timed_out:
            raise CaptionFinishingError(
                "Caption burn-in timed out",
                exit_code=exit_code,
                stderr=bounded_stderr,
                error_type="timeout",
            )
        if exit_code is not None and exit_code != 0:
            raise CaptionFinishingError(
                f"FFmpeg caption burn-in exited with code {exit_code}",
                exit_code=exit_code,
                stderr=bounded_stderr,
                error_type="exit_error",
            )

        await logger.ainfo(
            "caption_ffmpeg_complete",
            elapsed=round(time.monotonic() - start, 3),
        )

    async def _terminate_process(
        self,
        proc: asyncio.subprocess.Process,
    ) -> None:
        if proc.returncode is not None:
            return
        with contextlib.suppress(ProcessLookupError):
            proc.terminate()
        try:
            await asyncio.wait_for(
                proc.wait(),
                timeout=self._settings.subprocess_kill_grace_seconds,
            )
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await proc.wait()


def build_caption_burn_in_command(
    ffmpeg_bin: str,
    input_path: Path,
    ass_path: Path,
    output_path: Path,
) -> list[str]:
    """Build a deterministic FFmpeg command for ASS subtitle burn-in."""
    return [
        ffmpeg_bin,
        "-y",
        "-i",
        str(input_path),
        "-vf",
        f"subtitles={escape_subtitles_filter_path(ass_path)}",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def escape_subtitles_filter_path(path: Path) -> str:
    """Escape a local ASS path for FFmpeg's subtitles filter argument."""
    text = str(path)
    return (
        text.replace("\\", r"\\")
        .replace(":", r"\:")
        .replace(",", r"\,")
        .replace("[", r"\[")
        .replace("]", r"\]")
        .replace("'", r"\'")
    )


def caption_burn_in_media_type() -> str:
    """Return the internal media type used for generated ASS files."""
    return ASS_MEDIA_TYPE
