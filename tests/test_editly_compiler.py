from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.composition import (
    AudioAsset,
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
)

# ---------------------------------------------------------------------------
# Layer Mapper Unit Tests
# ---------------------------------------------------------------------------


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
