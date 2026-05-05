from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from app.core.config import Settings
from app.models.composition import Clip, Composition, TextAsset
from app.renderers.base import CompiledRender
from app.renderers.native_ffmpeg import (
    NativeFfmpegRenderer,
    NativeFfmpegRenderError,
    generate_native_replay_metadata,
)
from app.renderers.native_ffmpeg_subset import (
    NativeSubsetError,
    build_native_render_plan,
    serialize_native_plan,
)
from app.renderers.timeline import asset_resolver_key

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_native_fixture() -> Composition:
    return Composition.model_validate_json(
        (FIXTURES_DIR / "native_ffmpeg_simple_composition.json").read_text(
            encoding="utf-8"
        )
    )


def _resolver(tmp_path: Path, composition: Composition) -> dict[str, str]:
    resolver: dict[str, str] = {}
    for track in composition.timeline.tracks:
        for clip in track.clips:
            key = asset_resolver_key(clip)
            if key is None:
                continue
            path = tmp_path / f"asset-{len(resolver)}.dat"
            path.write_bytes(b"asset")
            resolver[key] = str(path)
    if composition.timeline.soundtrack is not None:
        path = tmp_path / "soundtrack.dat"
        path.write_bytes(b"audio")
        resolver[composition.timeline.soundtrack.src] = str(path)
    return resolver


def test_native_plan_is_deterministic_for_supported_visual_subset(
    tmp_path: Path,
) -> None:
    composition = _load_native_fixture()
    resolver = _resolver(tmp_path, composition)

    first = build_native_render_plan(
        composition,
        tmp_path / "out.mp4",
        asset_path_resolver=resolver,
        ffmpeg_bin="ffmpeg",
    )
    second = build_native_render_plan(
        composition,
        tmp_path / "out.mp4",
        asset_path_resolver=resolver,
        ffmpeg_bin="ffmpeg",
    )

    assert serialize_native_plan(first) == serialize_native_plan(second)
    assert first.command[0] == "ffmpeg"
    assert "-filter_complex" in first.command
    assert "[vout]" in first.command
    assert "overlay=x=(320.000000-overlay_w/2)" in first.filter_complex
    assert first.visual_layers[0].asset_type == "color"
    assert first.visual_layers[1].asset_type == "image"


def test_native_subset_rejects_transition_with_bounded_context(
    tmp_path: Path,
) -> None:
    payload = json.loads(
        (FIXTURES_DIR / "native_ffmpeg_simple_composition.json").read_text(
            encoding="utf-8"
        )
    )
    payload["timeline"]["tracks"][1]["clips"][0]["transition"] = {
        "name": "wipe_left",
        "duration": 0.2,
    }
    composition = Composition.model_validate(payload)

    with pytest.raises(NativeSubsetError) as exc_info:
        build_native_render_plan(
            composition,
            tmp_path / "out.mp4",
            asset_path_resolver=_resolver(tmp_path, composition),
            ffmpeg_bin="ffmpeg",
        )

    context = exc_info.value.to_context()
    assert context["renderer"] == "ffmpeg-native"
    assert context["feature"] == "timeline.tracks[1].clips[0].transition.name"
    assert context["requested"] == "wipe_left"
    assert "image://title" not in repr(context)


def test_native_plan_supports_text_png_and_audio_mix_filters(tmp_path: Path) -> None:
    text_clip = Clip(
        asset=TextAsset(type="text", text="Hello"),
        start=0.0,
        length=1.0,
    )
    composition = Composition.model_validate(
        {
            "renderer": "ffmpeg-native",
            "timeline": {
                "background": "#000000",
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {"type": "color", "color": "#000000"},
                                "length": 1.0,
                            }
                        ]
                    },
                    {"clips": [text_clip.model_dump(mode="json")]},
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "audio",
                                    "src": "audio://voice",
                                    "trim": 0.1,
                                    "volume": 0.5,
                                },
                                "start": 0.2,
                                "length": 0.7,
                            }
                        ]
                    },
                ],
                "soundtrack": {
                    "type": "audio",
                    "src": "audio://music",
                    "volume": 0.25,
                },
            },
            "output": {"format": "mp4", "width": 320, "height": 180, "fps": 24},
        }
    )
    resolver = _resolver(tmp_path, composition)

    plan = build_native_render_plan(
        composition,
        tmp_path / "out.mp4",
        asset_path_resolver=resolver,
        ffmpeg_bin="ffmpeg",
    )

    assert any(layer.asset_type == "text" for layer in plan.visual_layers)
    assert len(plan.audio_layers) == 2
    assert "adelay=200|200" in plan.filter_complex
    assert "volume=0.500000" in plan.filter_complex
    assert "amix=inputs=2" in plan.filter_complex


@pytest.mark.asyncio
async def test_native_compile_writes_compiled_and_replay_json(tmp_path: Path) -> None:
    composition = _load_native_fixture()
    resolver = _resolver(tmp_path, composition)
    renderer = NativeFfmpegRenderer(settings=Settings(ffmpeg_bin="ffmpeg"))

    compiled = await renderer.compile(
        composition,
        tmp_path,
        render_id="render_native",
        asset_path_resolver=resolver,
    )

    assert compiled.renderer_name == "ffmpeg-native"
    assert compiled.spec_path.name == "compiled.ffmpeg.json"
    spec = json.loads(compiled.spec_path.read_text(encoding="ascii"))
    replay = json.loads(compiled.replay_path.read_text(encoding="ascii"))
    assert spec["renderer"] == "ffmpeg-native"
    assert replay["renderer"] == "ffmpeg-native"
    assert replay["command"] == "ffmpeg"
    assert "image://title" not in repr(replay)


def test_native_replay_metadata_contains_safe_command_facts(tmp_path: Path) -> None:
    composition = _load_native_fixture()
    resolver = _resolver(tmp_path, composition)
    plan = build_native_render_plan(
        composition,
        tmp_path / "out.mp4",
        asset_path_resolver=resolver,
        ffmpeg_bin="ffmpeg",
    )

    replay = generate_native_replay_metadata(
        plan,
        tmp_path / "compiled.ffmpeg.json",
        tmp_path,
        settings=Settings(ffmpeg_bin="ffmpeg"),
    )

    assert replay["command"] == "ffmpeg"
    assert replay["args"]
    assert replay["output_path"].endswith("out.mp4")
    assert "image://title" not in repr(replay)


def _compiled_for_command(tmp_path: Path, command: list[str]) -> CompiledRender:
    spec = {
        "renderer": "ffmpeg-native",
        "duration": 1.0,
        "output_path": str(tmp_path / "out.mp4"),
        "command": command,
    }
    spec_path = tmp_path / "compiled.ffmpeg.json"
    replay_path = tmp_path / "replay.json"
    spec_path.write_text(json.dumps(spec), encoding="ascii")
    replay_path.write_text("{}", encoding="ascii")
    return CompiledRender(
        spec_path=spec_path,
        replay_path=replay_path,
        workspace=tmp_path,
        renderer_name="ffmpeg-native",
        spec_json=json.dumps(spec),
    )


@pytest.mark.asyncio
async def test_native_render_success_streams_progress(tmp_path: Path) -> None:
    output_path = tmp_path / "out.mp4"
    script = (
        "import pathlib, sys; "
        "sys.stderr.write('frame=1 time=00:00:00.50\\n'); "
        "sys.stderr.flush(); "
        f"pathlib.Path({str(output_path)!r}).write_bytes(b'video')"
    )
    compiled = _compiled_for_command(tmp_path, [sys.executable, "-c", script])
    renderer = NativeFfmpegRenderer(settings=Settings())
    lines: list[str] = []

    async def _progress(line: str) -> None:
        lines.append(line)

    artifact = await renderer.render(compiled, progress_callback=_progress)

    assert artifact.output_path == output_path
    assert artifact.exit_code == 0
    assert lines == ["frame=1 time=00:00:00.50"]


@pytest.mark.asyncio
async def test_native_render_classifies_non_zero_exit(tmp_path: Path) -> None:
    compiled = _compiled_for_command(
        tmp_path,
        [sys.executable, "-c", "import sys; sys.stderr.write('bad\\n'); sys.exit(3)"],
    )
    renderer = NativeFfmpegRenderer(settings=Settings())

    with pytest.raises(NativeFfmpegRenderError) as exc_info:
        await renderer.render(compiled)

    assert exc_info.value.error_type == "exit_error"
    assert exc_info.value.exit_code == 3


@pytest.mark.asyncio
async def test_native_render_classifies_missing_binary(tmp_path: Path) -> None:
    compiled = _compiled_for_command(tmp_path, ["ffmpeg-definitely-missing"])
    renderer = NativeFfmpegRenderer(settings=Settings())

    with pytest.raises(NativeFfmpegRenderError) as exc_info:
        await renderer.render(compiled)

    assert exc_info.value.error_type == "missing_binary"
    assert exc_info.value.exit_code == 127


@pytest.mark.asyncio
async def test_native_render_classifies_missing_output(tmp_path: Path) -> None:
    compiled = _compiled_for_command(tmp_path, [sys.executable, "-c", ""])
    renderer = NativeFfmpegRenderer(settings=Settings())

    with pytest.raises(NativeFfmpegRenderError) as exc_info:
        await renderer.render(compiled)

    assert exc_info.value.error_type == "missing_output"


@pytest.mark.asyncio
async def test_native_render_classifies_timeout(tmp_path: Path) -> None:
    compiled = _compiled_for_command(
        tmp_path,
        [sys.executable, "-c", "import time; time.sleep(30)"],
    )
    renderer = NativeFfmpegRenderer(
        settings=Settings(subprocess_kill_grace_seconds=0.1)
    )

    with pytest.raises(NativeFfmpegRenderError) as exc_info:
        await renderer.render(compiled, timeout_seconds=0.1)

    assert exc_info.value.error_type == "timeout"


@pytest.mark.asyncio
async def test_native_render_classifies_cancellation(tmp_path: Path) -> None:
    script = (
        "import sys, time; "
        "sys.stderr.write('frame=1 time=00:00:00.10\\n'); "
        "sys.stderr.flush(); "
        "time.sleep(30)"
    )
    compiled = _compiled_for_command(tmp_path, [sys.executable, "-c", script])
    renderer = NativeFfmpegRenderer(
        settings=Settings(subprocess_kill_grace_seconds=0.1)
    )

    async def _cancel() -> bool:
        return True

    with pytest.raises(NativeFfmpegRenderError) as exc_info:
        await renderer.render(compiled, cancel_check=_cancel)

    assert exc_info.value.error_type == "cancelled"
