from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from app.core.config import Settings, get_settings
from app.models.composition import Composition
from app.renderers.base import CompiledRender, RenderArtifact, RenderError
from app.renderers.capabilities import FFMPEG_NATIVE_RENDERER
from app.renderers.native_ffmpeg_subset import (
    NativeRenderPlan,
    build_native_render_plan,
    serialize_native_plan,
)

logger = structlog.get_logger(__name__)


class NativeFfmpegRenderError(RenderError):
    """Structured error from the native FFmpeg subprocess."""

    def __init__(
        self,
        message: str,
        *,
        exit_code: int | None = None,
        error_type: str,
        stderr: str = "",
    ) -> None:
        super().__init__(message, exit_code=exit_code)
        self.error_type = error_type
        self.stderr = stderr


def generate_native_replay_metadata(
    plan: NativeRenderPlan,
    spec_path: Path,
    workspace: Path,
    *,
    settings: Settings | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Capture safe native FFmpeg replay metadata."""
    if settings is None:
        settings = get_settings()
    timeout = timeout_seconds or settings.render_timeout_seconds
    command = list(plan.command)
    return {
        "renderer": FFMPEG_NATIVE_RENDERER,
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "command": command[0],
        "args": command[1:],
        "environment": {
            "PATH": os.environ.get("PATH", ""),
        },
        "input_spec": str(spec_path),
        "output_path": str(plan.output_path),
        "workspace": str(workspace),
        "timeout_seconds": timeout,
        "inputs": [
            {
                "index": item.index,
                "kind": item.kind,
                "path": item.path,
            }
            for item in plan.inputs
        ],
        "filter_complex": plan.filter_complex,
    }


def classify_native_render_error(
    *,
    exit_code: int | None,
    stderr: str,
    timed_out: bool,
    cancelled: bool,
    missing_binary: bool,
    output_exists: bool,
) -> NativeFfmpegRenderError:
    """Map native FFmpeg failure conditions to structured error types."""
    if cancelled:
        return NativeFfmpegRenderError(
            "Native FFmpeg render cancelled by user",
            exit_code=exit_code,
            error_type="cancelled",
            stderr=stderr,
        )
    if missing_binary:
        return NativeFfmpegRenderError(
            "FFmpeg binary not found",
            exit_code=exit_code,
            error_type="missing_binary",
            stderr=stderr,
        )
    if timed_out:
        return NativeFfmpegRenderError(
            "Native FFmpeg render timed out",
            exit_code=exit_code,
            error_type="timeout",
            stderr=stderr,
        )
    if exit_code is not None and exit_code != 0:
        return NativeFfmpegRenderError(
            f"Native FFmpeg exited with code {exit_code}",
            exit_code=exit_code,
            error_type="exit_error",
            stderr=stderr,
        )
    if not output_exists:
        return NativeFfmpegRenderError(
            "Native FFmpeg completed but output file not found",
            exit_code=exit_code,
            error_type="missing_output",
            stderr=stderr,
        )
    return NativeFfmpegRenderError(
        "Unknown native FFmpeg render failure",
        exit_code=exit_code,
        error_type="unknown",
        stderr=stderr,
    )


class NativeFfmpegRenderer:
    """Renderer backend that compiles a narrow VidAPI subset to FFmpeg."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def name(self) -> str:
        return FFMPEG_NATIVE_RENDERER

    async def compile(
        self,
        composition: Composition,
        workspace: Path,
        *,
        render_id: str,
        asset_path_resolver: dict[str, str] | None = None,
    ) -> CompiledRender:
        """Compile a supported composition into deterministic FFmpeg artifacts."""
        workspace.mkdir(parents=True, exist_ok=True)
        workspace = workspace.resolve()
        output_path = workspace / f"{render_id}.mp4"
        plan = build_native_render_plan(
            composition,
            output_path,
            asset_path_resolver=asset_path_resolver,
            ffmpeg_bin=self._settings.ffmpeg_bin,
        )
        spec_json = serialize_native_plan(plan)

        spec_path = workspace / "compiled.ffmpeg.json"
        spec_path.write_text(spec_json, encoding="ascii")

        replay = generate_native_replay_metadata(
            plan,
            spec_path,
            workspace,
            settings=self._settings,
            timeout_seconds=self._settings.render_timeout_seconds,
        )
        replay_path = workspace / "replay.json"
        replay_path.write_text(
            json.dumps(replay, sort_keys=True, indent=2, ensure_ascii=True),
            encoding="ascii",
        )

        logger.info(
            "native_ffmpeg_compile_complete",
            render_id=render_id,
            inputs=len(plan.inputs),
            visual_layers=len(plan.visual_layers),
            audio_layers=len(plan.audio_layers),
            spec_path=str(spec_path),
        )

        return CompiledRender(
            spec_path=spec_path,
            replay_path=replay_path,
            workspace=workspace,
            renderer_name=self.name,
            spec_json=spec_json,
        )

    async def render(
        self,
        compiled: CompiledRender,
        *,
        timeout_seconds: int | None = None,
        progress_callback: Any | None = None,
        cancel_check: Any | None = None,
    ) -> RenderArtifact:
        """Execute the compiled native FFmpeg command."""
        if timeout_seconds is None:
            timeout_seconds = self._settings.render_timeout_seconds

        spec = json.loads(compiled.spec_json)
        command = [str(part) for part in spec["command"]]
        output_path = Path(spec["output_path"])
        log_path = compiled.workspace / "render.log"

        start_time = time.monotonic()
        timed_out = False
        cancelled = False
        missing_binary = False
        exit_code: int | None = None
        stderr_lines: list[str] = []

        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(compiled.workspace),
            )
            try:
                stderr_lines = await asyncio.wait_for(
                    self._stream_stderr(
                        proc,
                        progress_callback=progress_callback,
                        cancel_check=cancel_check,
                    ),
                    timeout=timeout_seconds,
                )
                exit_code = proc.returncode
            except TimeoutError:
                timed_out = True
                await self._terminate_process(proc)
                exit_code = proc.returncode
                stderr_lines.append("TIMEOUT: FFmpeg killed after exceeding time limit")
            except _CancelledByUserError:
                cancelled = True
                await self._terminate_process(proc)
                exit_code = proc.returncode
                stderr_lines.append("CANCELLED: FFmpeg killed by user request")
        except FileNotFoundError:
            missing_binary = True
            exit_code = 127
            stderr_lines = [f"FFmpeg binary not found: {command[0]}"]

        elapsed = time.monotonic() - start_time
        stderr_text = "\n".join(stderr_lines)
        stderr_text = stderr_text[-self._settings.max_subprocess_stderr_bytes :]
        log_path.write_text(stderr_text, encoding="utf-8")

        output_exists = output_path.is_file()
        if (
            cancelled
            or missing_binary
            or timed_out
            or (exit_code is not None and exit_code != 0)
            or not output_exists
        ):
            output_path.unlink(missing_ok=True)
            error = classify_native_render_error(
                exit_code=exit_code,
                stderr=stderr_text,
                timed_out=timed_out,
                cancelled=cancelled,
                missing_binary=missing_binary,
                output_exists=output_exists,
            )
            logger.error(
                "native_ffmpeg_render_failed",
                error_type=error.error_type,
                exit_code=exit_code,
                elapsed=round(elapsed, 3),
            )
            raise error

        logger.info(
            "native_ffmpeg_render_complete",
            output_path=str(output_path),
            elapsed=round(elapsed, 3),
        )
        return RenderArtifact(
            output_path=output_path,
            poster_path=None,
            log_path=log_path,
            duration_seconds=round(float(spec["duration"]), 3),
            exit_code=exit_code or 0,
        )

    async def _stream_stderr(
        self,
        proc: asyncio.subprocess.Process,
        *,
        progress_callback: Any | None = None,
        cancel_check: Any | None = None,
    ) -> list[str]:
        """Read stderr line by line with bounded memory and cancellation."""
        lines: list[str] = []
        line_bytes_total = 0
        max_bytes = self._settings.max_subprocess_stderr_bytes
        assert proc.stderr is not None

        while True:
            line_bytes = await proc.stderr.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="replace").rstrip("\n\r")
            lines.append(line)
            line_bytes_total += len(line.encode("utf-8", errors="replace")) + 1
            while line_bytes_total > max_bytes and lines:
                removed = lines.pop(0)
                line_bytes_total -= len(removed.encode("utf-8", errors="replace")) + 1

            if progress_callback is not None:
                with contextlib.suppress(Exception):
                    await progress_callback(line)

            if cancel_check is not None:
                try:
                    if await cancel_check():
                        raise _CancelledByUserError()
                except _CancelledByUserError:
                    raise
                except Exception:
                    pass

        await proc.wait()
        return lines

    async def _terminate_process(
        self,
        proc: asyncio.subprocess.Process,
        grace_period: float | None = None,
    ) -> None:
        """Terminate FFmpeg with grace period and kill fallback."""
        if proc.returncode is not None:
            return
        if grace_period is None:
            grace_period = self._settings.subprocess_kill_grace_seconds
        with contextlib.suppress(ProcessLookupError):
            proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=grace_period)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await proc.wait()


class _CancelledByUserError(Exception):
    """Internal signal for cooperative render cancellation."""
