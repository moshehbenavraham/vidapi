from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.models.composition import Composition
from app.renderers.base import CompiledRender
from app.renderers.hyperframes import (
    HyperFramesRenderer,
    HyperFramesRenderError,
    classify_hyperframes_render_error,
)
from app.renderers.hyperframes_compiler import HyperFramesCompileError


def _html_composition(**overrides: object) -> Composition:
    payload = {
        "renderer": "hyperframes",
        "timeline": {
            "background": "#000000",
            "tracks": [
                {
                    "clips": [
                        {
                            "asset": {
                                "type": "html",
                                "html": '<div class="title">Hello</div>',
                                "css": ".title { color: white; }",
                            },
                            "length": 1.0,
                        }
                    ]
                }
            ],
        },
        "output": {"format": "mp4", "width": 320, "height": 180, "fps": 24},
    }
    payload.update(overrides)
    return Composition.model_validate(payload)


def _fake_hyperframes(tmp_path: Path, body: str) -> Path:
    executable = tmp_path / "hyperframes"
    executable.write_text(
        "#!/bin/sh\n"
        "out=''\n"
        'while [ "$#" -gt 0 ]; do\n'
        "  if [ \"$1\" = '--output' ]; then\n"
        "    shift\n"
        '    out="$1"\n'
        "  fi\n"
        "  shift || true\n"
        "done\n"
        f"{body}\n",
        encoding="ascii",
    )
    executable.chmod(0o755)
    return executable


async def _compile_with_binary(
    tmp_path: Path,
    binary: Path,
    *,
    composition: Composition | None = None,
) -> tuple[HyperFramesRenderer, CompiledRender]:
    renderer = HyperFramesRenderer(Settings(hyperframes_bin=str(binary)))
    compiled = await renderer.compile(
        composition or _html_composition(),
        tmp_path / "workspace",
        render_id="render_hf",
    )
    return renderer, compiled


@pytest.mark.asyncio
async def test_compile_writes_project_artifacts_and_redacted_replay(
    tmp_path: Path,
) -> None:
    source = "https://cdn.example.com/image.png?token=secret"
    media_path = tmp_path / "image.png"
    media_path.write_bytes(b"image")
    composition = _html_composition(
        timeline={
            "tracks": [
                {
                    "clips": [
                        {
                            "asset": {
                                "type": "html",
                                "html": f'<img src="{source}">',
                                "media_refs": [source],
                            },
                            "length": 1.0,
                        }
                    ]
                }
            ]
        }
    )
    renderer = HyperFramesRenderer()

    compiled = await renderer.compile(
        composition,
        tmp_path / "workspace",
        render_id="render_hf",
        asset_path_resolver={source: str(media_path)},
    )

    index_html = (compiled.workspace / "index.html").read_text(encoding="ascii")
    compiled_json = json.loads(compiled.spec_path.read_text(encoding="ascii"))
    replay_text = compiled.replay_path.read_text(encoding="ascii")

    assert "gsap@3.14.2/dist/gsap.min.js" in index_html
    assert "window.__hf.seek = function(time)" in index_html
    assert 'data-composition-id="root"' in index_html
    assert "hyperframes-assets" in index_html
    assert "token=secret" not in index_html
    assert compiled_json["renderer"] == "hyperframes"
    assert compiled_json["inputs"][0]["source"] == "https://cdn.example.com/image.png"
    assert "<img" not in replay_text
    assert "token=secret" not in replay_text


@pytest.mark.asyncio
async def test_compile_rejects_direct_remote_reference_without_media_ref(
    tmp_path: Path,
) -> None:
    composition = _html_composition(
        timeline={
            "tracks": [
                {
                    "clips": [
                        {
                            "asset": {
                                "type": "html",
                                "html": '<img src="https://cdn.example.com/a.png">',
                            },
                            "length": 1.0,
                        }
                    ]
                }
            ]
        }
    )
    renderer = HyperFramesRenderer()

    with pytest.raises(HyperFramesCompileError) as exc_info:
        await renderer.compile(composition, tmp_path / "workspace", render_id="bad")

    context = exc_info.value.to_context()
    assert context["feature"].endswith(".remote_reference")
    assert context["requested"] == "https://cdn.example.com/a.png"


@pytest.mark.asyncio
async def test_render_success_streams_logs_and_returns_artifact(tmp_path: Path) -> None:
    binary = _fake_hyperframes(
        tmp_path,
        "echo 'progress 50'\nprintf 'video' > \"$out\"\nexit 0",
    )
    renderer, compiled = await _compile_with_binary(tmp_path, binary)
    progress: list[str] = []

    async def _progress(line: str) -> None:
        progress.append(line)

    artifact = await renderer.render(
        compiled,
        timeout_seconds=5,
        progress_callback=_progress,
    )

    assert artifact.output_path.is_file()
    assert artifact.duration_seconds == 1.0
    assert "progress 50" in artifact.log_path.read_text(encoding="utf-8")
    assert progress == ["progress 50"]


@pytest.mark.asyncio
async def test_render_missing_binary_classified(tmp_path: Path) -> None:
    renderer, compiled = await _compile_with_binary(tmp_path, tmp_path / "missing")

    with pytest.raises(HyperFramesRenderError) as exc_info:
        await renderer.render(compiled, timeout_seconds=1)

    assert exc_info.value.error_type == "missing_binary"


@pytest.mark.asyncio
async def test_render_timeout_classified(tmp_path: Path) -> None:
    binary = _fake_hyperframes(tmp_path, "sleep 5\nexit 0")
    renderer, compiled = await _compile_with_binary(tmp_path, binary)

    with pytest.raises(HyperFramesRenderError) as exc_info:
        await renderer.render(compiled, timeout_seconds=1)

    assert exc_info.value.error_type == "timeout"


@pytest.mark.asyncio
async def test_render_nonzero_node_version_classified(tmp_path: Path) -> None:
    binary = _fake_hyperframes(tmp_path, "echo 'requires Node >= 22' >&2\nexit 1")
    renderer, compiled = await _compile_with_binary(tmp_path, binary)

    with pytest.raises(HyperFramesRenderError) as exc_info:
        await renderer.render(compiled, timeout_seconds=5)

    assert exc_info.value.error_type == "node_version"


@pytest.mark.asyncio
async def test_render_missing_output_classified(tmp_path: Path) -> None:
    binary = _fake_hyperframes(tmp_path, "echo 'done'\nexit 0")
    renderer, compiled = await _compile_with_binary(tmp_path, binary)

    with pytest.raises(HyperFramesRenderError) as exc_info:
        await renderer.render(compiled, timeout_seconds=5)

    assert exc_info.value.error_type == "missing_output"


@pytest.mark.asyncio
async def test_render_cancellation_classified(tmp_path: Path) -> None:
    binary = _fake_hyperframes(tmp_path, "sleep 5\nexit 0")
    renderer, compiled = await _compile_with_binary(tmp_path, binary)

    async def _cancel() -> bool:
        return True

    with pytest.raises(HyperFramesRenderError) as exc_info:
        await renderer.render(compiled, timeout_seconds=5, cancel_check=_cancel)

    assert exc_info.value.error_type == "cancelled"


def test_classify_browser_launch_failure() -> None:
    error = classify_hyperframes_render_error(
        exit_code=1,
        stderr="Chrome browser launch failed",
        timed_out=False,
        cancelled=False,
        missing_binary=False,
        output_exists=False,
    )

    assert error.error_type == "browser_launch"
