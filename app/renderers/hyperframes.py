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
from app.renderers.capabilities import HYPERFRAMES_RENDERER
from app.renderers.hyperframes_compiler import (
    HyperFramesProject,
    build_hyperframes_project,
    serialize_hyperframes_project,
)

logger = structlog.get_logger(__name__)


class HyperFramesRenderError(RenderError):
    """Structured error from the HyperFrames subprocess."""

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


def generate_hyperframes_replay_metadata(
    project: HyperFramesProject,
    spec_path: Path,
    *,
    settings: Settings | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Capture safe HyperFrames replay facts without raw HTML or secrets."""
    if settings is None:
        settings = get_settings()
    timeout = timeout_seconds or settings.hyperframes_timeout_seconds
    command = list(project.command)
    return {
        "renderer": HYPERFRAMES_RENDERER,
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "command": command[0],
        "args": command[1:],
        "environment": {
            "PATH": os.environ.get("PATH", ""),
            "NODE_PATH": os.environ.get("NODE_PATH", ""),
        },
        "runtime": {
            "requires_node_major": 22,
            "requires_ffmpeg": True,
            "requires_browser": True,
            "workers": settings.hyperframes_workers,
        },
        "input_spec": str(spec_path),
        "entrypoint": str(project.index_path),
        "output_path": str(project.output_path),
        "workspace": str(project.workspace),
        "timeout_seconds": timeout,
        "inputs": [item.to_jsonable() for item in project.inputs],
        "requested_output": {
            "intermediate_format": "mp4",
            "width": project.width,
            "height": project.height,
            "fps": project.fps,
            "duration": round(project.duration, 6),
        },
    }


def classify_hyperframes_render_error(
    *,
    exit_code: int | None,
    stderr: str,
    timed_out: bool,
    cancelled: bool,
    missing_binary: bool,
    output_exists: bool,
) -> HyperFramesRenderError:
    """Map HyperFrames failure conditions to structured error types."""
    if cancelled:
        return HyperFramesRenderError(
            "HyperFrames render cancelled by user",
            exit_code=exit_code,
            error_type="cancelled",
            stderr=stderr,
        )
    if missing_binary:
        return HyperFramesRenderError(
            "HyperFrames binary not found",
            exit_code=exit_code,
            error_type="missing_binary",
            stderr=stderr,
        )
    if timed_out:
        return HyperFramesRenderError(
            "HyperFrames render timed out",
            exit_code=exit_code,
            error_type="timeout",
            stderr=stderr,
        )

    lowered = stderr.lower()
    if exit_code is not None and exit_code != 0:
        if "node" in lowered and (
            "version" in lowered or "requires" in lowered or ">= 22" in lowered
        ):
            return HyperFramesRenderError(
                "HyperFrames requires Node.js 22 or newer",
                exit_code=exit_code,
                error_type="node_version",
                stderr=stderr,
            )
        if any(term in lowered for term in ("chrome", "chromium", "browser")) and any(
            term in lowered for term in ("launch", "executable", "failed", "missing")
        ):
            return HyperFramesRenderError(
                "HyperFrames browser launch failed",
                exit_code=exit_code,
                error_type="browser_launch",
                stderr=stderr,
            )
        return HyperFramesRenderError(
            f"HyperFrames exited with code {exit_code}",
            exit_code=exit_code,
            error_type="exit_error",
            stderr=stderr,
        )

    if not output_exists:
        return HyperFramesRenderError(
            "HyperFrames completed but output file not found",
            exit_code=exit_code,
            error_type="missing_output",
            stderr=stderr,
        )

    return HyperFramesRenderError(
        "Unknown HyperFrames render failure",
        exit_code=exit_code,
        error_type="unknown",
        stderr=stderr,
    )


class HyperFramesRenderer:
    """Renderer backend that compiles VidAPI HTML compositions to HyperFrames."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def name(self) -> str:
        return HYPERFRAMES_RENDERER

    async def compile(
        self,
        composition: Composition,
        workspace: Path,
        *,
        render_id: str,
        asset_path_resolver: dict[str, str] | None = None,
    ) -> CompiledRender:
        """Compile a VidAPI composition into HyperFrames project artifacts."""
        project = build_hyperframes_project(
            composition,
            workspace,
            render_id=render_id,
            asset_path_resolver=asset_path_resolver,
            hyperframes_bin=self._settings.hyperframes_bin,
            workers=self._settings.hyperframes_workers,
        )
        spec_json = serialize_hyperframes_project(project)
        spec_path = project.workspace / "compiled.hyperframes.json"
        spec_path.write_text(spec_json, encoding="ascii")

        replay = generate_hyperframes_replay_metadata(
            project,
            spec_path,
            settings=self._settings,
            timeout_seconds=self._settings.hyperframes_timeout_seconds,
        )
        replay_path = project.workspace / "replay.json"
        replay_path.write_text(
            json.dumps(replay, sort_keys=True, indent=2, ensure_ascii=True),
            encoding="ascii",
        )

        logger.info(
            "hyperframes_compile_complete",
            render_id=render_id,
            clips=len(project.clips),
            inputs=len(project.inputs),
            spec_path=str(spec_path),
        )

        return CompiledRender(
            spec_path=spec_path,
            replay_path=replay_path,
            workspace=project.workspace,
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
        """Invoke HyperFrames and produce an MP4 intermediate artifact."""
        if timeout_seconds is None:
            timeout_seconds = self._settings.hyperframes_timeout_seconds

        spec = json.loads(compiled.spec_json)
        command = [str(part) for part in spec["command"]]
        output_path = Path(spec["output_path"])
        log_path = compiled.workspace / "render.log"

        output_path.unlink(missing_ok=True)
        start_time = time.monotonic()
        timed_out = False
        cancelled = False
        missing_binary = False
        exit_code: int | None = None
        log_lines: list[str] = []

        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(compiled.workspace),
            )
            stdout_task = asyncio.create_task(
                self._stream_pipe(
                    proc.stdout,
                    log_lines,
                    progress_callback=progress_callback,
                )
            )
            stderr_task = asyncio.create_task(
                self._stream_pipe(
                    proc.stderr,
                    log_lines,
                    progress_callback=progress_callback,
                )
            )
            try:
                exit_code, timed_out, cancelled = await self._wait_for_process(
                    proc,
                    timeout_seconds=timeout_seconds,
                    start_time=start_time,
                    cancel_check=cancel_check,
                )
            finally:
                await asyncio.gather(
                    stdout_task,
                    stderr_task,
                    return_exceptions=True,
                )
        except FileNotFoundError:
            missing_binary = True
            exit_code = 127
            log_lines = [
                f"HyperFrames binary not found: {self._settings.hyperframes_bin}"
            ]

        elapsed = time.monotonic() - start_time
        log_text = "\n".join(log_lines)[-self._settings.max_subprocess_stderr_bytes :]
        log_path.write_text(log_text, encoding="utf-8")

        output_exists = output_path.is_file()
        if (
            cancelled
            or missing_binary
            or timed_out
            or (exit_code is not None and exit_code != 0)
            or not output_exists
        ):
            output_path.unlink(missing_ok=True)
            error = classify_hyperframes_render_error(
                exit_code=exit_code,
                stderr=log_text,
                timed_out=timed_out,
                cancelled=cancelled,
                missing_binary=missing_binary,
                output_exists=output_exists,
            )
            logger.error(
                "hyperframes_render_failed",
                error_type=error.error_type,
                exit_code=exit_code,
                elapsed=round(elapsed, 3),
            )
            raise error

        logger.info(
            "hyperframes_render_complete",
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

    async def _wait_for_process(
        self,
        proc: asyncio.subprocess.Process,
        *,
        timeout_seconds: int,
        start_time: float,
        cancel_check: Any | None,
    ) -> tuple[int | None, bool, bool]:
        timed_out = False
        cancelled = False

        while proc.returncode is None:
            if time.monotonic() - start_time > timeout_seconds:
                timed_out = True
                await self._terminate_process(proc)
                break
            if cancel_check is not None:
                try:
                    if await cancel_check():
                        cancelled = True
                        await self._terminate_process(proc)
                        break
                except Exception:
                    pass
            await asyncio.sleep(0.2)

        exit_code = await proc.wait()
        return exit_code, timed_out, cancelled

    async def _stream_pipe(
        self,
        pipe: asyncio.StreamReader | None,
        lines: list[str],
        *,
        progress_callback: Any | None = None,
    ) -> None:
        if pipe is None:
            return
        while True:
            line_bytes = await pipe.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="replace").rstrip("\n\r")
            self._append_bounded_line(lines, line)
            if progress_callback is not None:
                with contextlib.suppress(Exception):
                    await progress_callback(line)

    def _append_bounded_line(self, lines: list[str], line: str) -> None:
        lines.append(line)
        total = sum(len(item.encode("utf-8", errors="replace")) + 1 for item in lines)
        while total > self._settings.max_subprocess_stderr_bytes and lines:
            removed = lines.pop(0)
            total -= len(removed.encode("utf-8", errors="replace")) + 1

    async def _terminate_process(
        self,
        proc: asyncio.subprocess.Process,
        grace_period: float | None = None,
    ) -> None:
        """Terminate HyperFrames with a grace period and kill fallback."""
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
