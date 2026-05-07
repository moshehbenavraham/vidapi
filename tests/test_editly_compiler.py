from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.models.composition import (
    AudioAsset,
    AudioEffect,
    Clip,
    ColorAsset,
    Composition,
    FitMode,
    ImageAsset,
    Output,
    TextAsset,
    Timeline,
    Track,
    VideoAsset,
)
from app.renderers.base import CompiledRender, CompileError
from app.renderers.editly import (
    ActiveClip,
    EditlyRenderer,
    _fit_mode_to_resize,
    assemble_editly_spec,
    collect_boundaries,
    compute_total_duration,
    generate_segments,
    map_color_layer,
    map_image_layer,
    map_soundtrack,
    map_text_png_layer,
    map_video_layer,
    needs_audio_mixing,
    serialize_spec,
    spec_duration_seconds,
)
from app.services.audio_mixer import AudioMixPlan, AudioSource
from app.services.ffprobe import MediaInfo

# ---------------------------------------------------------------------------
# Layer Mapper Unit Tests
# ---------------------------------------------------------------------------


def test_spec_duration_seconds_sums_editly_clip_durations() -> None:
    spec_json = serialize_spec(
        {
            "clips": [
                {"duration": 1.25, "layers": []},
                {"duration": 2.5, "layers": []},
            ]
        }
    )

    assert spec_duration_seconds(spec_json) == 3.75


class TestFitModeTranslation:
    def test_cover(self):
        assert _fit_mode_to_resize(FitMode.COVER) == "cover"

    def test_contain(self):
        assert _fit_mode_to_resize(FitMode.CONTAIN) == "contain"

    def test_stretch(self):
        assert _fit_mode_to_resize(FitMode.STRETCH) == "stretch"

    def test_none(self):
        assert _fit_mode_to_resize(FitMode.NONE) is None


class TestVideoLayerMapper:
    def test_basic_video(self):
        clip = Clip(
            asset=VideoAsset(type="video", src="/path/to/video.mp4"),
            start=0.0,
            length=5.0,
        )
        ac = ActiveClip(clip=clip, track_index=0, clip_offset=0.0)
        layer = map_video_layer(clip, ac)

        assert layer["type"] == "video"
        assert layer["path"] == "/path/to/video.mp4"
        assert layer["resizeMode"] == "cover"
        assert "cutFrom" not in layer
        assert "cutTo" not in layer

    def test_video_with_trim(self):
        clip = Clip(
            asset=VideoAsset(type="video", src="v.mp4", trim=2.0),
            start=0.0,
            length=5.0,
        )
        ac = ActiveClip(clip=clip, track_index=0, clip_offset=0.0)
        layer = map_video_layer(clip, ac)

        assert layer["cutFrom"] == 2.0
        assert layer["cutTo"] == 7.0

    def test_video_with_clip_offset(self):
        clip = Clip(
            asset=VideoAsset(type="video", src="v.mp4"),
            start=0.0,
            length=10.0,
        )
        ac = ActiveClip(clip=clip, track_index=0, clip_offset=3.0)
        layer = map_video_layer(clip, ac)

        assert layer["cutFrom"] == 3.0
        assert layer["cutTo"] == 10.0

    def test_video_with_trim_and_offset(self):
        clip = Clip(
            asset=VideoAsset(type="video", src="v.mp4", trim=1.5),
            start=0.0,
            length=8.0,
        )
        ac = ActiveClip(clip=clip, track_index=0, clip_offset=2.0)
        layer = map_video_layer(clip, ac)

        assert layer["cutFrom"] == 3.5
        assert layer["cutTo"] == 9.5

    def test_video_volume(self):
        clip = Clip(
            asset=VideoAsset(type="video", src="v.mp4", volume=0.5),
            start=0.0,
            length=5.0,
        )
        ac = ActiveClip(clip=clip, track_index=0, clip_offset=0.0)
        layer = map_video_layer(clip, ac)

        assert layer["mixVolume"] == 0.5

    def test_video_contain_fit(self):
        clip = Clip(
            asset=VideoAsset(type="video", src="v.mp4"),
            start=0.0,
            length=5.0,
            fit=FitMode.CONTAIN,
        )
        ac = ActiveClip(clip=clip, track_index=0, clip_offset=0.0)
        layer = map_video_layer(clip, ac)

        assert layer["resizeMode"] == "contain"


class TestImageLayerMapper:
    def test_basic_image(self):
        clip = Clip(
            asset=ImageAsset(type="image", src="/path/to/img.png"),
            start=0.0,
            length=3.0,
        )
        layer = map_image_layer(clip)

        assert layer["type"] == "image-overlay"
        assert layer["path"] == "/path/to/img.png"
        assert layer["resizeMode"] == "cover"

    def test_image_contain(self):
        clip = Clip(
            asset=ImageAsset(type="image", src="img.png"),
            start=0.0,
            length=3.0,
            fit=FitMode.CONTAIN,
        )
        layer = map_image_layer(clip)

        assert layer["resizeMode"] == "contain"


class TestTextPngLayerMapper:
    def test_text_produces_image_overlay(self):
        clip = Clip(
            asset=TextAsset(type="text", text="Hello World"),
            start=0.0,
            length=3.0,
        )
        layer = map_text_png_layer(clip)

        assert layer["type"] == "image-overlay"
        assert "path" in layer


class TestColorLayerMapper:
    def test_color_fill(self):
        clip = Clip(
            asset=ColorAsset(type="color", color="#ff0000"),
            start=0.0,
            length=5.0,
        )
        layer = map_color_layer(clip)

        assert layer["type"] == "fill-color"
        assert layer["color"] == "#ff0000"


class TestSoundtrackMapper:
    def test_no_soundtrack(self):
        result = map_soundtrack(None)
        assert result == []

    def test_basic_soundtrack(self):
        audio = AudioAsset(type="audio", src="/music.mp3")
        result = map_soundtrack(audio)

        assert len(result) == 1
        assert result[0]["path"] == "/music.mp3"
        assert "mixVolume" not in result[0]

    def test_soundtrack_with_volume(self):
        audio = AudioAsset(type="audio", src="/music.mp3", volume=0.7)
        result = map_soundtrack(audio)

        assert result[0]["mixVolume"] == 0.7

    def test_soundtrack_with_effect_requires_external_audio(self):
        audio = AudioAsset(
            type="audio",
            src="/music.mp3",
            effect=AudioEffect.FADE_OUT,
        )
        with pytest.raises(CompileError, match="external audio"):
            map_soundtrack(audio)


# ---------------------------------------------------------------------------
# Full Compile Integration Tests
# ---------------------------------------------------------------------------


class TestAssembleEditlySpec:
    def _simple_composition(self) -> Composition:
        return Composition(
            timeline=Timeline(
                tracks=[
                    Track(
                        clips=[
                            Clip(
                                asset=ImageAsset(type="image", src="/bg.png"),
                                start=0.0,
                                length=5.0,
                            ),
                        ]
                    ),
                    Track(
                        clips=[
                            Clip(
                                asset=TextAsset(type="text", text="Title"),
                                start=1.0,
                                length=3.0,
                            ),
                        ]
                    ),
                ],
                soundtrack=AudioAsset(type="audio", src="/music.mp3", volume=0.8),
            ),
            output=Output(width=1920, height=1080, fps=30),
        )

    def test_spec_structure(self):
        comp = self._simple_composition()
        tracks = comp.timeline.tracks
        total_dur = compute_total_duration(tracks)
        boundaries = collect_boundaries(tracks, total_dur)
        segments = generate_segments(boundaries, tracks)

        spec = assemble_editly_spec(segments, comp, "/out/render.mp4")

        assert spec["width"] == 1920
        assert spec["height"] == 1080
        assert spec["fps"] == 30
        assert spec["outPath"] == "/out/render.mp4"
        assert "clips" in spec
        assert len(spec["clips"]) == len(segments)
        assert "audioTracks" in spec
        assert spec["audioTracks"][0]["path"] == "/music.mp3"

    def test_deterministic_output(self):
        comp = self._simple_composition()
        tracks = comp.timeline.tracks
        total_dur = compute_total_duration(tracks)
        boundaries = collect_boundaries(tracks, total_dur)
        segments = generate_segments(boundaries, tracks)

        spec1 = assemble_editly_spec(segments, comp, "/out/render.mp4")
        spec2 = assemble_editly_spec(segments, comp, "/out/render.mp4")

        json1 = serialize_spec(spec1)
        json2 = serialize_spec(spec2)

        assert json1 == json2

    def test_gap_produces_fill_color(self):
        comp = Composition(
            timeline=Timeline(
                tracks=[
                    Track(
                        clips=[
                            Clip(
                                asset=VideoAsset(type="video", src="v.mp4"),
                                start=0.0,
                                length=2.0,
                            ),
                            Clip(
                                asset=VideoAsset(type="video", src="v2.mp4"),
                                start=4.0,
                                length=1.0,
                            ),
                        ]
                    ),
                ],
                background="#333333",
            ),
            output=Output(width=1280, height=720, fps=24),
        )
        tracks = comp.timeline.tracks
        total_dur = compute_total_duration(tracks)
        boundaries = collect_boundaries(tracks, total_dur)
        segments = generate_segments(boundaries, tracks)

        spec = assemble_editly_spec(segments, comp, "/out.mp4")

        gap_clip = spec["clips"][1]
        assert gap_clip["layers"][0]["type"] == "fill-color"
        assert gap_clip["layers"][0]["color"] == "#333333"

    def test_positioned_layers_produce_editly_json(self):
        comp = Composition(
            timeline=Timeline(
                tracks=[
                    Track(
                        clips=[
                            Clip(
                                asset=ImageAsset(type="image", src="/overlay.png"),
                                start=0.0,
                                length=3.0,
                                position={"x": 0.25, "y": 0.75},
                                offset={"x": 128.0, "y": -72.0},
                                opacity=0.5,
                                scale=0.4,
                            ),
                        ]
                    ),
                ],
            ),
            output=Output(width=1280, height=720, fps=30),
        )
        tracks = comp.timeline.tracks
        total_dur = compute_total_duration(tracks)
        boundaries = collect_boundaries(tracks, total_dur)
        segments = generate_segments(boundaries, tracks)

        spec = assemble_editly_spec(segments, comp, "/out.mp4")

        layer = spec["clips"][0]["layers"][0]
        assert layer["position"] == {
            "x": 0.35,
            "y": 0.65,
            "originX": "left",
            "originY": "top",
        }
        assert layer["opacity"] == 0.5
        assert layer["width"] == 0.4
        assert layer["height"] == 0.4

    def test_transition_on_clip_produces_valid_spec(self):
        comp = Composition(
            timeline=Timeline(
                tracks=[
                    Track(
                        clips=[
                            Clip(
                                asset=VideoAsset(type="video", src="/v.mp4"),
                                start=0.0,
                                length=3.0,
                                transition={"name": "fade_out", "duration": 0.5},
                            ),
                        ]
                    ),
                ],
            ),
            output=Output(width=1280, height=720, fps=30),
        )
        tracks = comp.timeline.tracks
        total_dur = compute_total_duration(tracks)
        boundaries = collect_boundaries(tracks, total_dur)
        segments = generate_segments(boundaries, tracks)

        spec = assemble_editly_spec(segments, comp, "/out.mp4")

        assert spec["clips"][0]["transition"] == {"name": "fade", "duration": 0.5}

    def test_crossfade_between_sequential_clips(self):
        comp = Composition(
            timeline=Timeline(
                tracks=[
                    Track(
                        clips=[
                            Clip(
                                asset=VideoAsset(type="video", src="/a.mp4"),
                                start=0.0,
                                length=2.0,
                                transition={"name": "crossfade", "duration": 0.25},
                            ),
                            Clip(
                                asset=VideoAsset(type="video", src="/b.mp4"),
                                start=2.0,
                                length=2.0,
                            ),
                        ]
                    ),
                ],
            ),
            output=Output(width=1280, height=720, fps=30),
        )
        tracks = comp.timeline.tracks
        total_dur = compute_total_duration(tracks)
        boundaries = collect_boundaries(tracks, total_dur)
        segments = generate_segments(boundaries, tracks)

        spec = assemble_editly_spec(segments, comp, "/out.mp4")

        assert len(spec["clips"]) == 2
        assert spec["clips"][0]["transition"] == {"name": "fade", "duration": 0.25}

    def test_advanced_transition_maps_to_deterministic_editly_name(self):
        comp = Composition(
            timeline=Timeline(
                tracks=[
                    Track(
                        clips=[
                            Clip(
                                asset=VideoAsset(type="video", src="/a.mp4"),
                                start=0.0,
                                length=2.0,
                                transition={
                                    "name": "directional_left",
                                    "duration": 0.25,
                                },
                            ),
                            Clip(
                                asset=VideoAsset(type="video", src="/b.mp4"),
                                start=2.0,
                                length=2.0,
                            ),
                        ]
                    ),
                ],
            ),
            output=Output(width=1280, height=720, fps=30),
        )
        tracks = comp.timeline.tracks
        total_dur = compute_total_duration(tracks)
        boundaries = collect_boundaries(tracks, total_dur)
        segments = generate_segments(boundaries, tracks)

        spec = assemble_editly_spec(segments, comp, "/out.mp4")

        assert spec["clips"][0]["transition"] == {
            "name": "directional-left",
            "duration": 0.25,
        }

    def test_fixture_defaults_omit_new_visual_and_transition_keys(self):
        fixture_path = Path("tests/fixtures/sample_composition.json")
        comp = Composition.model_validate_json(fixture_path.read_text())
        tracks = comp.timeline.tracks
        total_dur = compute_total_duration(tracks)
        boundaries = collect_boundaries(tracks, total_dur)
        segments = generate_segments(boundaries, tracks)

        spec = assemble_editly_spec(segments, comp, "/out.mp4")

        for clip_spec in spec["clips"]:
            assert "transition" not in clip_spec
            for layer in clip_spec["layers"]:
                assert "position" not in layer
                assert "opacity" not in layer
                assert "width" not in layer
                assert "height" not in layer


@pytest.mark.asyncio
class TestEditlyRendererCompile:
    async def test_compile_creates_files(self, tmp_path: Path):
        comp = Composition(
            timeline=Timeline(
                tracks=[
                    Track(
                        clips=[
                            Clip(
                                asset=ImageAsset(type="image", src="/bg.png"),
                                start=0.0,
                                length=5.0,
                            ),
                        ]
                    ),
                ],
            ),
            output=Output(width=1920, height=1080, fps=30),
        )

        renderer = EditlyRenderer()
        result = await renderer.compile(comp, tmp_path, render_id="test-001")

        assert result.spec_path.exists()
        assert result.replay_path.exists()
        assert result.renderer_name == "editly"
        assert result.workspace == tmp_path

        spec_data = json.loads(result.spec_path.read_text())
        assert spec_data["width"] == 1920
        assert spec_data["height"] == 1080
        assert "clips" in spec_data

    async def test_compile_replay_json_contents(self, tmp_path: Path):
        comp = Composition(
            timeline=Timeline(
                tracks=[
                    Track(
                        clips=[
                            Clip(
                                asset=ColorAsset(type="color", color="#000"),
                                start=0.0,
                                length=3.0,
                            ),
                        ]
                    ),
                ],
            ),
            output=Output(width=1280, height=720, fps=24),
        )

        renderer = EditlyRenderer()
        result = await renderer.compile(comp, tmp_path, render_id="test-002")

        replay = json.loads(result.replay_path.read_text())
        assert replay["renderer"] == "editly"
        assert replay["command"] == "editly"
        assert "--json" in replay["args"]
        assert "timestamp" in replay
        assert "workspace" in replay

    async def test_compile_deterministic(self, tmp_path: Path):
        comp = Composition(
            timeline=Timeline(
                tracks=[
                    Track(
                        clips=[
                            Clip(
                                asset=ImageAsset(type="image", src="/bg.png"),
                                start=0.0,
                                length=5.0,
                            ),
                        ]
                    ),
                ],
            ),
            output=Output(width=1920, height=1080, fps=30),
        )

        workspace = tmp_path / "ws"
        renderer = EditlyRenderer()
        r1 = await renderer.compile(comp, workspace, render_id="det-001")
        r2 = await renderer.compile(comp, workspace, render_id="det-001")

        assert r1.spec_json == r2.spec_json


# ---------------------------------------------------------------------------
# Multi-Track Spec Assembly Tests
# ---------------------------------------------------------------------------


class TestMultiTrackAssembly:
    """Verify multi-track compositions produce correct multi-layer segments."""

    def _multi_track_composition(self) -> Composition:
        return Composition(
            timeline=Timeline(
                tracks=[
                    Track(
                        clips=[
                            Clip(
                                asset=VideoAsset(type="video", src="/bg.mp4"),
                                start=0.0,
                                length=10.0,
                            ),
                        ]
                    ),
                    Track(
                        clips=[
                            Clip(
                                asset=ImageAsset(type="image", src="/overlay.png"),
                                start=2.0,
                                length=4.0,
                            ),
                        ]
                    ),
                ],
            ),
            output=Output(width=1920, height=1080, fps=30),
        )

    def test_multi_layer_segment_layers(self):
        comp = self._multi_track_composition()
        tracks = comp.timeline.tracks
        total_dur = compute_total_duration(tracks)
        boundaries = collect_boundaries(tracks, total_dur)
        segments = generate_segments(boundaries, tracks)

        spec = assemble_editly_spec(segments, comp, "/out.mp4")

        overlap_clip = spec["clips"][1]
        assert len(overlap_clip["layers"]) == 2
        assert overlap_clip["layers"][0]["type"] == "video"
        assert overlap_clip["layers"][1]["type"] == "image-overlay"

    def test_multi_layer_z_order(self):
        comp = self._multi_track_composition()
        tracks = comp.timeline.tracks
        total_dur = compute_total_duration(tracks)
        boundaries = collect_boundaries(tracks, total_dur)
        segments = generate_segments(boundaries, tracks)

        overlap_segments = [s for s in segments if len(s.active_clips) > 1]
        assert len(overlap_segments) > 0
        for seg in overlap_segments:
            indices = [ac.track_index for ac in seg.active_clips]
            assert indices == sorted(indices)

    def test_audio_exclusion_with_external_audio(self):
        comp = Composition(
            timeline=Timeline(
                tracks=[
                    Track(
                        clips=[
                            Clip(
                                asset=VideoAsset(type="video", src="/v.mp4"),
                                start=0.0,
                                length=5.0,
                            ),
                        ]
                    ),
                ],
                soundtrack=AudioAsset(type="audio", src="/music.mp3"),
            ),
            output=Output(width=1920, height=1080, fps=30),
        )

        tracks = comp.timeline.tracks
        total_dur = compute_total_duration(tracks)
        boundaries = collect_boundaries(tracks, total_dur)
        segments = generate_segments(boundaries, tracks)

        spec = assemble_editly_spec(segments, comp, "/out.mp4", use_external_audio=True)

        assert "audioTracks" not in spec

    def test_backward_compatible_soundtrack_only(self):
        comp = Composition(
            timeline=Timeline(
                tracks=[
                    Track(
                        clips=[
                            Clip(
                                asset=VideoAsset(type="video", src="/v.mp4"),
                                start=0.0,
                                length=5.0,
                            ),
                        ]
                    ),
                ],
                soundtrack=AudioAsset(type="audio", src="/music.mp3", volume=0.8),
            ),
            output=Output(width=1920, height=1080, fps=30),
        )

        assert needs_audio_mixing(comp.timeline.tracks) is False

        tracks = comp.timeline.tracks
        total_dur = compute_total_duration(tracks)
        boundaries = collect_boundaries(tracks, total_dur)
        segments = generate_segments(boundaries, tracks)

        spec = assemble_editly_spec(segments, comp, "/out.mp4")

        assert "audioTracks" in spec
        assert spec["audioTracks"][0]["path"] == "/music.mp3"

    def test_multi_track_overlapping_three_layers(self):
        comp = Composition(
            timeline=Timeline(
                tracks=[
                    Track(
                        clips=[
                            Clip(
                                asset=ColorAsset(type="color", color="#000"),
                                start=0.0,
                                length=10.0,
                            ),
                        ]
                    ),
                    Track(
                        clips=[
                            Clip(
                                asset=VideoAsset(type="video", src="/v.mp4"),
                                start=0.0,
                                length=10.0,
                            ),
                        ]
                    ),
                    Track(
                        clips=[
                            Clip(
                                asset=TextAsset(type="text", text="Title"),
                                start=2.0,
                                length=3.0,
                            ),
                        ]
                    ),
                ],
            ),
            output=Output(width=1920, height=1080, fps=30),
        )

        tracks = comp.timeline.tracks
        total_dur = compute_total_duration(tracks)
        boundaries = collect_boundaries(tracks, total_dur)
        segments = generate_segments(boundaries, tracks)

        spec = assemble_editly_spec(segments, comp, "/out.mp4")

        three_layer_clips = [c for c in spec["clips"] if len(c["layers"]) == 3]
        assert len(three_layer_clips) == 1
        layers = three_layer_clips[0]["layers"]
        assert layers[0]["type"] == "fill-color"
        assert layers[1]["type"] == "video"
        assert layers[2]["type"] == "image-overlay"


@pytest.mark.asyncio
class TestEditlyRendererCompileWithAudio:
    async def test_compile_with_detached_audio_has_plan(self, tmp_path: Path):
        comp = Composition(
            timeline=Timeline(
                tracks=[
                    Track(
                        clips=[
                            Clip(
                                asset=ImageAsset(type="image", src="/bg.png"),
                                start=0.0,
                                length=5.0,
                            ),
                        ]
                    ),
                    Track(
                        clips=[
                            Clip(
                                asset=AudioAsset(type="audio", src="/sfx.mp3"),
                                start=1.0,
                                length=3.0,
                            ),
                        ]
                    ),
                ],
            ),
            output=Output(width=1920, height=1080, fps=30),
        )

        renderer = EditlyRenderer()
        result = await renderer.compile(comp, tmp_path, render_id="audio-001")

        assert result.audio_mix_plan is not None
        assert not result.audio_mix_plan.is_empty
        assert len(result.audio_mix_plan.sources) == 1
        assert result.audio_mix_plan.sources[0].path == "/sfx.mp3"

        spec_data = json.loads(result.spec_json)
        assert "audioTracks" not in spec_data

    async def test_compile_without_detached_audio_no_plan(self, tmp_path: Path):
        comp = Composition(
            timeline=Timeline(
                tracks=[
                    Track(
                        clips=[
                            Clip(
                                asset=ImageAsset(type="image", src="/bg.png"),
                                start=0.0,
                                length=5.0,
                            ),
                        ]
                    ),
                ],
                soundtrack=AudioAsset(type="audio", src="/music.mp3"),
            ),
            output=Output(width=1920, height=1080, fps=30),
        )

        renderer = EditlyRenderer()
        result = await renderer.compile(comp, tmp_path, render_id="noaudio-001")

        assert result.audio_mix_plan is None

        spec_data = json.loads(result.spec_json)
        assert "audioTracks" in spec_data

    async def test_compile_soundtrack_effect_has_external_plan(self, tmp_path: Path):
        comp = Composition(
            timeline=Timeline(
                tracks=[
                    Track(
                        clips=[
                            Clip(
                                asset=ImageAsset(type="image", src="/bg.png"),
                                start=0.0,
                                length=5.0,
                            ),
                        ]
                    ),
                ],
                soundtrack=AudioAsset(
                    type="audio",
                    src="/music.mp3",
                    effect=AudioEffect.FADE_OUT,
                ),
            ),
            output=Output(width=1920, height=1080, fps=30),
        )

        renderer = EditlyRenderer()
        result = await renderer.compile(comp, tmp_path, render_id="fade-001")

        assert result.audio_mix_plan is not None
        assert result.audio_mix_plan.sources[0].fade_out_duration == 1.0
        assert result.audio_mix_plan.sources[0].total_duration == 5.0

        spec_data = json.loads(result.spec_json)
        assert "audioTracks" not in spec_data

    async def test_compile_soundtrack_normalization_has_external_plan(
        self, tmp_path: Path
    ):
        comp = Composition(
            timeline=Timeline(
                tracks=[
                    Track(
                        clips=[
                            Clip(
                                asset=ImageAsset(type="image", src="/bg.png"),
                                start=0.0,
                                length=5.0,
                            ),
                        ]
                    ),
                ],
                soundtrack=AudioAsset(type="audio", src="/music.mp3"),
            ),
            output=Output(width=1920, height=1080, fps=30),
        )

        renderer = EditlyRenderer(settings=Settings(audio_normalization_enabled=True))
        result = await renderer.compile(comp, tmp_path, render_id="norm-001")

        assert result.audio_mix_plan is not None
        assert result.audio_mix_plan.normalize_audio is True

        spec_data = json.loads(result.spec_json)
        assert "audioTracks" not in spec_data

    async def test_compile_clips_detached_audio_to_video_duration(self, tmp_path: Path):
        comp = Composition(
            timeline=Timeline(
                tracks=[
                    Track(
                        clips=[
                            Clip(
                                asset=ImageAsset(type="image", src="/bg.png"),
                                start=0.0,
                                length=5.0,
                            ),
                        ]
                    ),
                    Track(
                        clips=[
                            Clip(
                                asset=AudioAsset(type="audio", src="/sfx.mp3"),
                                start=4.0,
                                length=3.0,
                            ),
                        ]
                    ),
                ],
            ),
            output=Output(width=1920, height=1080, fps=30),
        )

        renderer = EditlyRenderer()
        result = await renderer.compile(comp, tmp_path, render_id="clip-001")

        assert result.audio_mix_plan is not None
        assert result.audio_mix_plan.sources[0].trim_duration == 1.0

    async def test_compile_skips_detached_audio_at_video_duration(self, tmp_path: Path):
        comp = Composition(
            timeline=Timeline(
                tracks=[
                    Track(
                        clips=[
                            Clip(
                                asset=ImageAsset(type="image", src="/bg.png"),
                                start=0.0,
                                length=5.0,
                            ),
                        ]
                    ),
                    Track(
                        clips=[
                            Clip(
                                asset=AudioAsset(type="audio", src="/sfx.mp3"),
                                start=5.0,
                                length=3.0,
                            ),
                        ]
                    ),
                ],
            ),
            output=Output(width=1920, height=1080, fps=30),
        )

        renderer = EditlyRenderer()
        result = await renderer.compile(comp, tmp_path, render_id="skip-001")

        assert result.audio_mix_plan is not None
        assert result.audio_mix_plan.is_empty is True

    async def test_post_process_audio_detects_video_without_audio(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        renderer = EditlyRenderer()
        output_path = tmp_path / "render.mp4"
        output_path.write_bytes(b"video")
        compiled = CompiledRender(
            spec_path=tmp_path / "compiled.editly.json",
            replay_path=tmp_path / "replay.json",
            workspace=tmp_path,
            renderer_name="editly",
            spec_json="{}",
            audio_mix_plan=AudioMixPlan(sources=[AudioSource(path="/sfx.mp3")]),
        )
        captured: dict[str, AudioMixPlan] = {}

        async def fake_probe(*args: object, **kwargs: object) -> MediaInfo:
            return MediaInfo(
                duration=1.0,
                width=320,
                height=180,
                video_codec="h264",
                audio_codec=None,
                stream_count=1,
                format_name="mov,mp4,m4a,3gp,3g2,mj2",
            )

        async def fake_mix_audio(
            video_path: Path,
            mixed_path: Path,
            plan: AudioMixPlan,
            **kwargs: object,
        ) -> Path:
            captured["plan"] = plan
            mixed_path.write_bytes(video_path.read_bytes() + b"+audio")
            return mixed_path

        monkeypatch.setattr("app.renderers.editly.probe", fake_probe)
        monkeypatch.setattr("app.renderers.editly.mix_audio", fake_mix_audio)

        result = await renderer.post_process_audio(compiled, output_path)

        assert result == output_path
        assert captured["plan"].video_has_audio is False
        assert output_path.read_bytes() == b"video+audio"
