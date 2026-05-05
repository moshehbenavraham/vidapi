from __future__ import annotations

import asyncio
import contextlib
import shutil
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import structlog

from app.core.config import Settings, get_settings
from app.models.composition import Composition, OutputFormat
from app.renderers.base import RenderArtifact, RenderError
from app.services.output_formats import (
    OutputFormatPlan,
    build_png_sequence_manifest,
    manifest_bytes,
    plan_output_format,
    sequence_frame_name,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class FinishedOutput:
    output_path: Path
    media_type: str
    filename: str
    suffix: str
    frame_count: int | None = None
    manifest_path: Path | None = None
    log_path: Path | None = None


class OutputPostprocessError(RenderError):
    """Raised when FFmpeg output finishing fails."""

    def __init__(
        self,
        message: str,
        *,
        exit_code: int | None = None,
        stderr: str = "",
        error_type: str = "postprocess_error",
    ) -> None:
        super().__init__(message, exit_code=exit_code)
        self.stderr = stderr
        self.error_type = error_type


class OutputPostprocessor:
    """Finish requested output formats from an Editly MP4 intermediate."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def finish(
        self,
        *,
        composition: Composition,
        artifact: RenderArtifact,
        render_id: str,
        workspace: Path,
    ) -> FinishedOutput:
        plan = plan_output_format(render_id, composition.output)
        if composition.output.format is OutputFormat.MP4:
            return FinishedOutput(
                output_path=artifact.output_path,
                media_type=plan.media_type,
                filename=plan.filename,
                suffix=plan.storage_suffix,
                log_path=artifact.log_path,
            )

        if composition.output.format is OutputFormat.WEBM:
            return await self._finish_single_file(
                plan=plan,
                input_path=artifact.output_path,
                target_path=workspace / plan.filename,
                command=build_webm_command(
                    self._settings.ffmpeg_bin,
                    artifact.output_path,
                    workspace / plan.filename,
                ),
            )

        if composition.output.format is OutputFormat.GIF:
            return await self._finish_single_file(
                plan=plan,
                input_path=artifact.output_path,
                target_path=workspace / plan.filename,
                command=build_gif_command(
                    self._settings.ffmpeg_bin,
                    artifact.output_path,
                    workspace / plan.filename,
                    width=composition.output.width or 1920,
                    height=composition.output.height or 1080,
                    fps=composition.output.fps,
                ),
            )

        if composition.output.format is OutputFormat.PNG_SEQUENCE:
            return await self._finish_png_sequence(
                plan=plan,
                composition=composition,
                input_path=artifact.output_path,
                render_id=render_id,
                workspace=workspace,
            )

        msg = f"Unsupported output format: {composition.output.format.value}"
        raise OutputPostprocessError(msg, error_type="unsupported_format")

    async def _finish_single_file(
        self,
        *,
        plan: OutputFormatPlan,
        input_path: Path,
        target_path: Path,
        command: list[str],
    ) -> FinishedOutput:
        log_path = target_path.with_suffix(target_path.suffix + ".log")
        try:
            await self._run_ffmpeg(command, log_path=log_path)
            if not target_path.is_file():
                raise OutputPostprocessError(
                    "FFmpeg completed but output file is missing",
                    stderr=log_path.read_text(encoding="utf-8", errors="replace")
                    if log_path.exists()
                    else "",
                    error_type="missing_output",
                )
            return FinishedOutput(
                output_path=target_path,
                media_type=plan.media_type,
                filename=plan.filename,
                suffix=plan.storage_suffix,
                log_path=log_path,
            )
        except Exception:
            if target_path != input_path:
                target_path.unlink(missing_ok=True)
            raise

    async def _finish_png_sequence(
        self,
        *,
        plan: OutputFormatPlan,
        composition: Composition,
        input_path: Path,
        render_id: str,
        workspace: Path,
    ) -> FinishedOutput:
        frame_dir = workspace / "png-sequence"
        archive_path = workspace / plan.filename
        manifest_path = workspace / (plan.manifest_filename or "manifest.json")
        log_path = archive_path.with_suffix(archive_path.suffix + ".log")

        try:
            await asyncio.to_thread(frame_dir.mkdir, parents=True, exist_ok=True)
            frame_pattern = frame_dir / "frame_%06d.png"
            await self._run_ffmpeg(
                build_png_sequence_command(
                    self._settings.ffmpeg_bin,
                    input_path,
                    frame_pattern,
                    fps=composition.output.fps,
                ),
                log_path=log_path,
            )
            frames = sorted(frame_dir.glob("frame_*.png"))
            if not frames:
                raise OutputPostprocessError(
                    "FFmpeg completed but no PNG sequence frames were created",
                    stderr=log_path.read_text(encoding="utf-8", errors="replace")
                    if log_path.exists()
                    else "",
                    error_type="missing_frames",
                )

            expected_names = [
                sequence_frame_name(index) for index in range(1, len(frames) + 1)
            ]
            for frame_path, expected_name in zip(frames, expected_names, strict=True):
                if frame_path.name != expected_name:
                    frame_path.rename(frame_dir / expected_name)

            frame_names = [
                frame.name for frame in sorted(frame_dir.glob("frame_*.png"))
            ]
            manifest = build_png_sequence_manifest(
                render_id=render_id,
                output=composition.output,
                frame_names=frame_names,
            )
            manifest_data = manifest_bytes(manifest)
            await asyncio.to_thread(manifest_path.write_bytes, manifest_data)
            await asyncio.to_thread(
                _write_sequence_zip,
                archive_path,
                frame_dir,
                manifest_path,
            )

            return FinishedOutput(
                output_path=archive_path,
                media_type=plan.media_type,
                filename=plan.filename,
                suffix=plan.storage_suffix,
                frame_count=len(frame_names),
                manifest_path=manifest_path,
                log_path=log_path,
            )
        except Exception:
            archive_path.unlink(missing_ok=True)
            manifest_path.unlink(missing_ok=True)
            with contextlib.suppress(OSError):
                await asyncio.to_thread(shutil.rmtree, frame_dir)
            raise

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
                    timeout=self._settings.output_postprocess_timeout_seconds,
                )
                exit_code = proc.returncode
                stderr = stderr_bytes.decode("utf-8", errors="replace")
            except TimeoutError:
                timed_out = True
                await self._terminate_process(proc)
                exit_code = proc.returncode
                stderr = "TIMEOUT: FFmpeg output post-processing timed out"
        except FileNotFoundError:
            exit_code = 127
            stderr = f"FFmpeg binary not found: {self._settings.ffmpeg_bin}"

        bounded_stderr = stderr[-self._settings.max_subprocess_stderr_bytes :]
        log_path.write_text(bounded_stderr, encoding="utf-8")

        if timed_out:
            raise OutputPostprocessError(
                "Output post-processing timed out",
                exit_code=exit_code,
                stderr=bounded_stderr,
                error_type="timeout",
            )
        if exit_code is not None and exit_code != 0:
            raise OutputPostprocessError(
                f"FFmpeg output post-processing exited with code {exit_code}",
                exit_code=exit_code,
                stderr=bounded_stderr,
                error_type="exit_error",
            )

        await logger.ainfo(
            "output_postprocess_complete",
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


def build_webm_command(
    ffmpeg_bin: str,
    input_path: Path,
    output_path: Path,
) -> list[str]:
    return [
        ffmpeg_bin,
        "-y",
        "-i",
        str(input_path),
        "-c:v",
        "libvpx-vp9",
        "-b:v",
        "0",
        "-crf",
        "32",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "libopus",
        str(output_path),
    ]


def build_gif_command(
    ffmpeg_bin: str,
    input_path: Path,
    output_path: Path,
    *,
    width: int,
    height: int,
    fps: int,
) -> list[str]:
    return [
        ffmpeg_bin,
        "-y",
        "-i",
        str(input_path),
        "-vf",
        f"fps={fps},scale={width}:{height}:flags=lanczos",
        "-loop",
        "0",
        str(output_path),
    ]


def build_png_sequence_command(
    ffmpeg_bin: str,
    input_path: Path,
    frame_pattern: Path,
    *,
    fps: int,
) -> list[str]:
    return [
        ffmpeg_bin,
        "-y",
        "-i",
        str(input_path),
        "-vf",
        f"fps={fps}",
        str(frame_pattern),
    ]


def _write_sequence_zip(
    archive_path: Path,
    frame_dir: Path,
    manifest_path: Path,
) -> None:
    with zipfile.ZipFile(archive_path, "w") as archive:
        _write_zip_entry(archive, manifest_path, "manifest.json")
        for frame_path in sorted(frame_dir.glob("frame_*.png")):
            _write_zip_entry(archive, frame_path, frame_path.name)


def _write_zip_entry(
    archive: zipfile.ZipFile,
    source_path: Path,
    archive_name: str,
) -> None:
    info = zipfile.ZipInfo(archive_name)
    info.date_time = (1980, 1, 1, 0, 0, 0)
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, source_path.read_bytes())
