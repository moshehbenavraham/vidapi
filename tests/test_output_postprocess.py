from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path

import pytest

from app.core.config import Settings
from app.models.composition import Composition
from app.renderers.base import RenderArtifact
from app.services.output_postprocess import (
    OutputPostprocessError,
    OutputPostprocessor,
    build_gif_command,
    build_png_sequence_command,
    build_webm_command,
)


class FakeProcess:
    def __init__(
        self,
        *,
        returncode: int | None = 0,
        stderr: bytes = b"",
        sleep_forever: bool = False,
    ) -> None:
        self.returncode = returncode
        self.stderr = None
        self._stderr = stderr
        self._sleep_forever = sleep_forever
        self.was_terminated = False
        self.was_killed = False

    async def communicate(self) -> tuple[bytes, bytes]:
        if self._sleep_forever:
            await asyncio.sleep(60)
        return b"", self._stderr

    def terminate(self) -> None:
        self.was_terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self.was_killed = True
        self.returncode = -9

    async def wait(self) -> int | None:
        return self.returncode


def _composition(output: dict) -> Composition:
    return Composition.model_validate(
        {
            "timeline": {
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {"type": "color", "color": "#000000"},
                                "length": 1.0,
                            }
                        ]
                    }
                ]
            },
            "output": output,
        }
    )


def _artifact(workspace: Path) -> RenderArtifact:
    output_path = workspace / "render_abc123.mp4"
    output_path.write_bytes(b"mp4")
    log_path = workspace / "render.log"
    log_path.write_text("render log", encoding="utf-8")
    return RenderArtifact(
        output_path=output_path,
        poster_path=None,
        log_path=log_path,
        duration_seconds=1.0,
        exit_code=0,
    )


def test_ffmpeg_command_builders_are_deterministic(tmp_path: Path) -> None:
    input_path = tmp_path / "input.mp4"

    assert build_webm_command("ffmpeg", input_path, tmp_path / "out.webm")[-1] == str(
        tmp_path / "out.webm"
    )
    assert build_gif_command(
        "ffmpeg",
        input_path,
        tmp_path / "out.gif",
        width=320,
        height=180,
        fps=12,
    )[-3:] == ["-loop", "0", str(tmp_path / "out.gif")]
    assert build_png_sequence_command(
        "ffmpeg",
        input_path,
        tmp_path / "frame_%06d.png",
        fps=10,
    )[-2:] == ["fps=10", str(tmp_path / "frame_%06d.png")]


@pytest.mark.asyncio
async def test_mp4_finish_returns_intermediate(tmp_path: Path) -> None:
    postprocessor = OutputPostprocessor(Settings())
    artifact = _artifact(tmp_path)

    finished = await postprocessor.finish(
        composition=_composition({"format": "mp4"}),
        artifact=artifact,
        render_id="render_abc123",
        workspace=tmp_path,
    )

    assert finished.output_path == artifact.output_path
    assert finished.media_type == "video/mp4"
    assert finished.filename == "render_abc123.mp4"


@pytest.mark.asyncio
async def test_ffmpeg_timeout_writes_log_and_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_process = FakeProcess(returncode=None, sleep_forever=True)

    async def _fake_exec(*args, **kwargs):
        return fake_process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
    postprocessor = OutputPostprocessor(Settings(output_postprocess_timeout_seconds=1))
    log_path = tmp_path / "ffmpeg.log"

    with pytest.raises(OutputPostprocessError) as exc_info:
        await postprocessor._run_ffmpeg(["ffmpeg", "-version"], log_path=log_path)

    assert exc_info.value.error_type == "timeout"
    assert fake_process.was_terminated is True
    assert "TIMEOUT" in log_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_ffmpeg_failure_bounds_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    stderr = b"x" * 5000

    async def _fake_exec(*args, **kwargs):
        return FakeProcess(returncode=1, stderr=stderr)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
    postprocessor = OutputPostprocessor(Settings(max_subprocess_stderr_bytes=4096))
    log_path = tmp_path / "ffmpeg.log"

    with pytest.raises(OutputPostprocessError) as exc_info:
        await postprocessor._run_ffmpeg(["ffmpeg", "-bad"], log_path=log_path)

    assert exc_info.value.error_type == "exit_error"
    assert len(exc_info.value.stderr) == 4096
    assert len(log_path.read_text(encoding="utf-8")) == 4096


@pytest.mark.asyncio
async def test_png_sequence_finish_writes_manifest_and_zip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def _fake_exec(*args, **kwargs):
        frame_pattern = Path(args[-1])
        frame_pattern.parent.mkdir(parents=True, exist_ok=True)
        (frame_pattern.parent / "frame_000001.png").write_bytes(b"one")
        (frame_pattern.parent / "frame_000002.png").write_bytes(b"two")
        return FakeProcess(returncode=0, stderr=b"ok")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
    postprocessor = OutputPostprocessor(Settings())
    artifact = _artifact(tmp_path)

    finished = await postprocessor.finish(
        composition=_composition(
            {
                "format": "png-sequence",
                "width": 320,
                "height": 180,
                "fps": 10,
            }
        ),
        artifact=artifact,
        render_id="render_abc123",
        workspace=tmp_path,
    )

    assert finished.frame_count == 2
    assert finished.manifest_path is not None
    assert finished.output_path.name == "render_abc123.zip"
    manifest_text = finished.manifest_path.read_text(encoding="ascii")
    assert '"frame_count": 2' in manifest_text

    with zipfile.ZipFile(finished.output_path) as archive:
        assert archive.namelist() == [
            "manifest.json",
            "frame_000001.png",
            "frame_000002.png",
        ]
