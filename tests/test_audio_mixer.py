from __future__ import annotations

from app.models.composition import (
    AudioAsset,
    Clip,
    ColorAsset,
    ImageAsset,
    Track,
    VideoAsset,
)
from app.renderers.editly import (
    AudioClipRef,
    collect_track_audio,
    compile_audio_plan,
    needs_audio_mixing,
)
from app.services.audio_mixer import (
    AudioMixPlan,
    AudioSource,
    build_mix_filter_graph,
)

# ---------------------------------------------------------------------------
# collect_track_audio tests
# ---------------------------------------------------------------------------


class TestCollectTrackAudio:
    def test_empty_tracks(self):
        tracks = [
            Track(clips=[Clip(asset=ColorAsset(type="color"), start=0, length=5)])
        ]
        result = collect_track_audio(tracks)
        assert result == []

    def test_single_audio_clip(self):
        tracks = [
            Track(
                clips=[
                    Clip(
                        asset=AudioAsset(type="audio", src="/music.mp3", volume=0.8),
                        start=2.0,
                        length=10.0,
                    ),
                ]
            ),
        ]
        result = collect_track_audio(tracks)
        assert len(result) == 1
        assert result[0].src == "/music.mp3"
        assert result[0].start == 2.0
        assert result[0].length == 10.0
        assert result[0].volume == 0.8
        assert result[0].trim is None

    def test_multiple_clips_across_tracks(self):
        tracks = [
            Track(
                clips=[
                    Clip(
                        asset=AudioAsset(type="audio", src="/a1.mp3"),
                        start=0.0,
                        length=5.0,
                    ),
                ]
            ),
            Track(
                clips=[
                    Clip(
                        asset=AudioAsset(
                            type="audio", src="/a2.wav", trim=1.0, volume=0.5
                        ),
                        start=3.0,
                        length=7.0,
                    ),
                ]
            ),
        ]
        result = collect_track_audio(tracks)
        assert len(result) == 2
        assert result[0].src == "/a1.mp3"
        assert result[1].src == "/a2.wav"
        assert result[1].trim == 1.0
        assert result[1].volume == 0.5

    def test_mixed_asset_types_ignored(self):
        tracks = [
            Track(
                clips=[
                    Clip(
                        asset=VideoAsset(type="video", src="/v.mp4"),
                        start=0.0,
                        length=5.0,
                    ),
                    Clip(
                        asset=AudioAsset(type="audio", src="/a.mp3"),
                        start=0.0,
                        length=5.0,
                    ),
                    Clip(
                        asset=ImageAsset(type="image", src="/i.png"),
                        start=0.0,
                        length=5.0,
                    ),
                ]
            ),
        ]
        result = collect_track_audio(tracks)
        assert len(result) == 1
        assert result[0].src == "/a.mp3"

    def test_volume_and_trim_propagation(self):
        tracks = [
            Track(
                clips=[
                    Clip(
                        asset=AudioAsset(
                            type="audio", src="/clip.mp3", trim=2.5, volume=0.3
                        ),
                        start=1.0,
                        length=4.0,
                    ),
                ]
            ),
        ]
        result = collect_track_audio(tracks)
        assert len(result) == 1
        ref = result[0]
        assert ref.trim == 2.5
        assert ref.volume == 0.3
        assert ref.start == 1.0
        assert ref.length == 4.0


# ---------------------------------------------------------------------------
# needs_audio_mixing tests
# ---------------------------------------------------------------------------


class TestNeedsAudioMixing:
    def test_no_audio_clips(self):
        tracks = [
            Track(
                clips=[
                    Clip(
                        asset=VideoAsset(type="video", src="/v.mp4"),
                        start=0.0,
                        length=5.0,
                    ),
                ]
            ),
        ]
        assert needs_audio_mixing(tracks) is False

    def test_has_audio_clip(self):
        tracks = [
            Track(
                clips=[
                    Clip(
                        asset=AudioAsset(type="audio", src="/a.mp3"),
                        start=0.0,
                        length=5.0,
                    ),
                ]
            ),
        ]
        assert needs_audio_mixing(tracks) is True


# ---------------------------------------------------------------------------
# compile_audio_plan tests
# ---------------------------------------------------------------------------


class TestCompileAudioPlan:
    def test_soundtrack_only(self):
        soundtrack = AudioAsset(type="audio", src="/music.mp3", volume=0.7)
        plan = compile_audio_plan([], soundtrack)
        assert len(plan.sources) == 1
        assert plan.sources[0].path == "/music.mp3"
        assert plan.sources[0].volume == 0.7
        assert plan.sources[0].delay_ms == 0

    def test_detached_audio_only(self):
        refs = [
            AudioClipRef(src="/sfx.wav", start=2.5, length=3.0, trim=None, volume=0.9),
        ]
        plan = compile_audio_plan(refs, None)
        assert len(plan.sources) == 1
        assert plan.sources[0].path == "/sfx.wav"
        assert plan.sources[0].delay_ms == 2500
        assert plan.sources[0].volume == 0.9

    def test_soundtrack_plus_detached(self):
        soundtrack = AudioAsset(type="audio", src="/bg.mp3", volume=0.5)
        refs = [
            AudioClipRef(src="/sfx.wav", start=1.0, length=2.0, trim=0.5, volume=1.0),
        ]
        plan = compile_audio_plan(refs, soundtrack)
        assert len(plan.sources) == 2
        assert plan.sources[0].path == "/bg.mp3"
        assert plan.sources[1].path == "/sfx.wav"
        assert plan.sources[1].delay_ms == 1000
        assert plan.sources[1].trim_start == 0.5

    def test_asset_path_resolver(self):
        soundtrack = AudioAsset(type="audio", src="/remote.mp3")
        refs = [
            AudioClipRef(
                src="/remote2.wav", start=0.0, length=5.0, trim=None, volume=1.0
            ),
        ]
        resolver = {"/remote.mp3": "/local/music.mp3", "/remote2.wav": "/local/sfx.wav"}
        plan = compile_audio_plan(refs, soundtrack, asset_path_resolver=resolver)
        assert plan.sources[0].path == "/local/music.mp3"
        assert plan.sources[1].path == "/local/sfx.wav"

    def test_empty_plan(self):
        plan = compile_audio_plan([], None)
        assert plan.is_empty is True


# ---------------------------------------------------------------------------
# build_mix_filter_graph tests
# ---------------------------------------------------------------------------


class TestBuildMixFilterGraph:
    def test_empty_plan(self):
        plan = AudioMixPlan(sources=[])
        graph, count = build_mix_filter_graph(plan)
        assert graph == ""
        assert count == 0

    def test_single_source_with_video_audio(self):
        plan = AudioMixPlan(
            sources=[AudioSource(path="/music.mp3")],
            video_has_audio=True,
        )
        graph, count = build_mix_filter_graph(plan)
        assert count == 2
        assert "[0:a]" in graph
        assert "amix=inputs=2" in graph
        assert "[aout]" in graph

    def test_single_source_no_video_audio(self):
        plan = AudioMixPlan(
            sources=[AudioSource(path="/music.mp3")],
            video_has_audio=False,
        )
        graph, count = build_mix_filter_graph(plan)
        assert count == 2
        assert "anullsrc" in graph
        assert "amix=inputs=2" in graph

    def test_source_with_delay(self):
        plan = AudioMixPlan(
            sources=[AudioSource(path="/sfx.wav", delay_ms=2500)],
            video_has_audio=True,
        )
        graph, _count = build_mix_filter_graph(plan)
        assert "adelay=2500|2500" in graph

    def test_source_with_trim(self):
        plan = AudioMixPlan(
            sources=[AudioSource(path="/clip.mp3", trim_start=1.5, trim_duration=3.0)],
            video_has_audio=True,
        )
        graph, _count = build_mix_filter_graph(plan)
        assert "atrim=start=1.500000" in graph
        assert "duration=3.000000" in graph
        assert "asetpts=PTS-STARTPTS" in graph

    def test_source_with_volume(self):
        plan = AudioMixPlan(
            sources=[AudioSource(path="/clip.mp3", volume=0.5)],
            video_has_audio=True,
        )
        graph, _count = build_mix_filter_graph(plan)
        assert "volume=0.500000" in graph

    def test_multiple_sources(self):
        plan = AudioMixPlan(
            sources=[
                AudioSource(path="/music.mp3", volume=0.5),
                AudioSource(path="/sfx.wav", delay_ms=3000),
                AudioSource(path="/vo.mp3", delay_ms=1000, trim_start=2.0),
            ],
            video_has_audio=True,
        )
        graph, count = build_mix_filter_graph(plan)
        assert count == 4
        assert "amix=inputs=4" in graph

    def test_adelay_millisecond_rounding(self):
        plan = AudioMixPlan(
            sources=[AudioSource(path="/a.mp3", delay_ms=1500)],
            video_has_audio=True,
        )
        graph, _ = build_mix_filter_graph(plan)
        assert "adelay=1500|1500" in graph

    def test_combined_trim_delay_volume(self):
        plan = AudioMixPlan(
            sources=[
                AudioSource(
                    path="/clip.mp3",
                    delay_ms=500,
                    trim_start=1.0,
                    trim_duration=2.0,
                    volume=0.7,
                ),
            ],
            video_has_audio=True,
        )
        graph, count = build_mix_filter_graph(plan)
        assert count == 2
        assert "atrim" in graph
        assert "adelay=500|500" in graph
        assert "volume=0.700000" in graph
        assert "asetpts=PTS-STARTPTS" in graph
