from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.composition import (
    AspectRatio,
    AudioAsset,
    Clip,
    ColorAsset,
    Composition,
    CoordinatePosition,
    FitMode,
    ImageAsset,
    NamedPosition,
    Offset,
    Output,
    OutputFormat,
    QualityPreset,
    ResolutionPreset,
    TextAsset,
    Timeline,
    Track,
    Transform,
    Transition,
    VideoAsset,
    resolve_quality,
    resolve_resolution,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_composition(**overrides: object) -> dict:
    base: dict = {
        "timeline": {
            "tracks": [
                {
                    "clips": [
                        {
                            "asset": {"type": "color", "color": "#ff0000"},
                            "length": 3.0,
                        }
                    ]
                }
            ]
        }
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Asset type discrimination
# ---------------------------------------------------------------------------


class TestAssetDiscrimination:
    def test_video_asset(self) -> None:
        clip = Clip(
            asset={"type": "video", "src": "https://example.com/video.mp4"},
            length=5.0,
        )
        assert isinstance(clip.asset, VideoAsset)
        assert clip.asset.type == "video"

    def test_image_asset(self) -> None:
        clip = Clip(
            asset={"type": "image", "src": "https://example.com/image.jpg"},
            length=3.0,
        )
        assert isinstance(clip.asset, ImageAsset)
        assert clip.asset.type == "image"

    def test_text_asset(self) -> None:
        clip = Clip(
            asset={"type": "text", "text": "Hello World"},
            length=2.0,
        )
        assert isinstance(clip.asset, TextAsset)
        assert clip.asset.type == "text"
        assert clip.asset.font_family == "Inter"
        assert clip.asset.font_size == 48

    def test_audio_asset(self) -> None:
        clip = Clip(
            asset={"type": "audio", "src": "https://example.com/music.mp3"},
            length=10.0,
        )
        assert isinstance(clip.asset, AudioAsset)
        assert clip.asset.type == "audio"

    def test_color_asset(self) -> None:
        clip = Clip(
            asset={"type": "color", "color": "#00ff00"},
            length=4.0,
        )
        assert isinstance(clip.asset, ColorAsset)
        assert clip.asset.type == "color"

    def test_unknown_asset_type_raises(self) -> None:
        with pytest.raises(ValidationError, match="type"):
            Clip(
                asset={"type": "html", "src": "https://example.com"},
                length=3.0,
            )


# ---------------------------------------------------------------------------
# Clip validation
# ---------------------------------------------------------------------------


class TestClipValidation:
    def test_minimal_clip(self) -> None:
        clip = Clip(
            asset={"type": "color", "color": "#000"},
            length=1.0,
        )
        assert clip.start == 0.0
        assert clip.opacity == 1.0
        assert clip.scale == 1.0
        assert clip.fit == FitMode.COVER
        assert clip.position == NamedPosition.CENTER

    def test_full_clip(self) -> None:
        clip = Clip(
            asset={"type": "video", "src": "https://example.com/v.mp4"},
            start=1.5,
            length=5.0,
            fit="contain",
            position="top-left",
            offset={"x": 0.1, "y": -0.2},
            scale=1.5,
            opacity=0.8,
            transition={"name": "crossfade", "duration": 0.5},
            transform={"rotation": 45},
        )
        assert clip.start == 1.5
        assert clip.fit == FitMode.CONTAIN
        assert clip.position == NamedPosition.TOP_LEFT
        assert clip.offset == Offset(x=0.1, y=-0.2)
        assert clip.scale == 1.5
        assert clip.opacity == 0.8
        assert isinstance(clip.transition, Transition)
        assert isinstance(clip.transform, Transform)

    def test_zero_length_clip_rejected(self) -> None:
        with pytest.raises(ValidationError, match="greater_than"):
            Clip(
                asset={"type": "color", "color": "#000"},
                length=0.0,
            )

    def test_negative_length_clip_rejected(self) -> None:
        with pytest.raises(ValidationError, match="greater_than"):
            Clip(
                asset={"type": "color", "color": "#000"},
                length=-1.0,
            )

    def test_negative_start_rejected(self) -> None:
        with pytest.raises(ValidationError, match="greater_than_equal"):
            Clip(
                asset={"type": "color", "color": "#000"},
                start=-0.5,
                length=1.0,
            )

    def test_opacity_above_1_rejected(self) -> None:
        with pytest.raises(ValidationError, match="less_than_equal"):
            Clip(
                asset={"type": "color", "color": "#000"},
                length=1.0,
                opacity=1.5,
            )

    def test_opacity_below_0_rejected(self) -> None:
        with pytest.raises(ValidationError, match="greater_than_equal"):
            Clip(
                asset={"type": "color", "color": "#000"},
                length=1.0,
                opacity=-0.1,
            )

    def test_scale_zero_rejected(self) -> None:
        with pytest.raises(ValidationError, match="greater_than"):
            Clip(
                asset={"type": "color", "color": "#000"},
                length=1.0,
                scale=0.0,
            )

    def test_scale_negative_rejected(self) -> None:
        with pytest.raises(ValidationError, match="greater_than"):
            Clip(
                asset={"type": "color", "color": "#000"},
                length=1.0,
                scale=-1.0,
            )

    def test_coordinate_position(self) -> None:
        clip = Clip(
            asset={"type": "color", "color": "#000"},
            length=1.0,
            position={"x": 0.25, "y": 0.75},
        )
        assert isinstance(clip.position, CoordinatePosition)
        assert clip.position.x == 0.25
        assert clip.position.y == 0.75


# ---------------------------------------------------------------------------
# Track / Timeline
# ---------------------------------------------------------------------------


class TestTrackTimeline:
    def test_empty_clips_rejected(self) -> None:
        with pytest.raises(ValidationError, match="too_short"):
            Track(clips=[])

    def test_empty_tracks_rejected(self) -> None:
        with pytest.raises(ValidationError, match="too_short"):
            Timeline(tracks=[])

    def test_soundtrack(self) -> None:
        tl = Timeline(
            tracks=[
                Track(
                    clips=[
                        Clip(
                            asset={"type": "color", "color": "#000"},
                            length=5.0,
                        )
                    ]
                )
            ],
            soundtrack=AudioAsset(
                type="audio",
                src="https://example.com/music.mp3",
                volume=0.35,
            ),
        )
        assert tl.soundtrack is not None
        assert tl.soundtrack.volume == 0.35

    def test_invalid_soundtrack_volume_rejected(self) -> None:
        with pytest.raises(ValidationError, match="less than or equal"):
            AudioAsset(
                type="audio",
                src="https://example.com/music.mp3",
                volume=1.5,
            )

    def test_invalid_soundtrack_effect_rejected(self) -> None:
        with pytest.raises(ValidationError, match="fadeInFadeOut"):
            AudioAsset(
                type="audio",
                src="https://example.com/music.mp3",
                effect="pulse",  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


class TestOutput:
    def test_default_output(self) -> None:
        out = Output()
        assert out.width == 1920
        assert out.height == 1080
        assert out.fps == 30
        assert out.format == OutputFormat.MP4
        assert out.quality == QualityPreset.MEDIUM

    def test_explicit_dimensions_override(self) -> None:
        out = Output(width=720, height=1280)
        assert out.width == 720
        assert out.height == 1280

    def test_resolution_preset_16_9(self) -> None:
        out = Output(resolution="1080", aspect_ratio="16:9")
        assert out.width == 1920
        assert out.height == 1080

    def test_resolution_preset_9_16(self) -> None:
        out = Output(resolution="1080", aspect_ratio="9:16")
        assert out.width == 1080
        assert out.height == 1920

    def test_resolution_preset_1_1(self) -> None:
        out = Output(resolution="720", aspect_ratio="1:1")
        assert out.width == 720
        assert out.height == 720

    def test_resolution_preset_4_5(self) -> None:
        out = Output(resolution="720", aspect_ratio="4:5")
        assert out.width == 720
        assert out.height == 900

    def test_resolution_without_aspect_defaults_16_9(self) -> None:
        out = Output(resolution="480")
        assert out.width == 854
        assert out.height == 480

    def test_explicit_dims_win_over_preset(self) -> None:
        out = Output(width=500, height=500, resolution="1080", aspect_ratio="16:9")
        assert out.width == 500
        assert out.height == 500

    def test_fps_zero_rejected(self) -> None:
        with pytest.raises(ValidationError, match="greater_than"):
            Output(fps=0)

    def test_fps_over_max_rejected(self) -> None:
        with pytest.raises(ValidationError, match="less_than_equal"):
            Output(fps=120)


# ---------------------------------------------------------------------------
# Resolution preset resolver
# ---------------------------------------------------------------------------


class TestResolutionPreset:
    @pytest.mark.parametrize(
        ("resolution", "aspect", "expected_w", "expected_h"),
        [
            (ResolutionPreset.R360, AspectRatio.AR_16_9, 640, 360),
            (ResolutionPreset.R360, AspectRatio.AR_9_16, 360, 640),
            (ResolutionPreset.R360, AspectRatio.AR_1_1, 360, 360),
            (ResolutionPreset.R360, AspectRatio.AR_4_5, 360, 450),
            (ResolutionPreset.R480, AspectRatio.AR_16_9, 854, 480),
            (ResolutionPreset.R480, AspectRatio.AR_9_16, 480, 854),
            (ResolutionPreset.R480, AspectRatio.AR_1_1, 480, 480),
            (ResolutionPreset.R480, AspectRatio.AR_4_5, 480, 600),
            (ResolutionPreset.R720, AspectRatio.AR_16_9, 1280, 720),
            (ResolutionPreset.R720, AspectRatio.AR_9_16, 720, 1280),
            (ResolutionPreset.R720, AspectRatio.AR_1_1, 720, 720),
            (ResolutionPreset.R720, AspectRatio.AR_4_5, 720, 900),
            (ResolutionPreset.R1080, AspectRatio.AR_16_9, 1920, 1080),
            (ResolutionPreset.R1080, AspectRatio.AR_9_16, 1080, 1920),
            (ResolutionPreset.R1080, AspectRatio.AR_1_1, 1080, 1080),
            (ResolutionPreset.R1080, AspectRatio.AR_4_5, 1080, 1350),
            (ResolutionPreset.R4K, AspectRatio.AR_16_9, 3840, 2160),
            (ResolutionPreset.R4K, AspectRatio.AR_9_16, 2160, 3840),
            (ResolutionPreset.R4K, AspectRatio.AR_1_1, 2160, 2160),
            (ResolutionPreset.R4K, AspectRatio.AR_4_5, 2160, 2700),
        ],
    )
    def test_all_resolution_aspect_combos(
        self,
        resolution: ResolutionPreset,
        aspect: AspectRatio,
        expected_w: int,
        expected_h: int,
    ) -> None:
        w, h = resolve_resolution(resolution, aspect)
        assert w == expected_w
        assert h == expected_h


# ---------------------------------------------------------------------------
# Quality preset resolver
# ---------------------------------------------------------------------------


class TestQualityPreset:
    def test_low_quality(self) -> None:
        crf, preset = resolve_quality(QualityPreset.LOW)
        assert crf == 28
        assert preset == "veryfast"

    def test_medium_quality(self) -> None:
        crf, preset = resolve_quality(QualityPreset.MEDIUM)
        assert crf == 23
        assert preset == "medium"

    def test_high_quality(self) -> None:
        crf, preset = resolve_quality(QualityPreset.HIGH)
        assert crf == 18
        assert preset == "slow"

    def test_output_crf_property(self) -> None:
        out = Output(quality="high")
        assert out.crf == 18
        assert out.ffmpeg_preset == "slow"


# ---------------------------------------------------------------------------
# Composition (top-level)
# ---------------------------------------------------------------------------


class TestComposition:
    def test_minimal_valid(self) -> None:
        comp = Composition(**_minimal_composition())
        assert len(comp.timeline.tracks) == 1
        assert comp.output.width == 1920
        assert comp.renderer is None
        assert comp.merge is None
        assert comp.callback is None

    def test_with_all_asset_types(self) -> None:
        data = {
            "timeline": {
                "background": "#000000",
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "video",
                                    "src": "https://example.com/bg.mp4",
                                },
                                "start": 0,
                                "length": 10,
                            }
                        ]
                    },
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "image",
                                    "src": "https://example.com/overlay.png",
                                },
                                "start": 1,
                                "length": 3,
                            }
                        ]
                    },
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "text",
                                    "text": "Hello",
                                    "font_size": 72,
                                    "color": "#ffffff",
                                },
                                "start": 2,
                                "length": 4,
                                "position": "bottom",
                                "opacity": 0.9,
                            }
                        ]
                    },
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "audio",
                                    "src": "https://example.com/sfx.mp3",
                                    "volume": 0.5,
                                },
                                "start": 0,
                                "length": 10,
                            }
                        ]
                    },
                    {
                        "clips": [
                            {
                                "asset": {"type": "color", "color": "#333333"},
                                "start": 0,
                                "length": 10,
                            }
                        ]
                    },
                ],
                "soundtrack": {
                    "type": "audio",
                    "src": "https://example.com/music.mp3",
                    "volume": 0.35,
                    "effect": "fadeOut",
                },
            },
            "output": {
                "format": "mp4",
                "resolution": "1080",
                "aspect_ratio": "9:16",
                "fps": 30,
                "quality": "high",
            },
            "merge": {"name": "World"},
            "callback": "https://example.com/webhook",
            "renderer": "editly",
        }
        comp = Composition(**data)
        assert len(comp.timeline.tracks) == 5
        assert comp.output.width == 1080
        assert comp.output.height == 1920
        assert comp.merge == {"name": "World"}
        assert comp.renderer == "editly"
        assert comp.timeline.soundtrack is not None
        assert comp.timeline.soundtrack.effect is not None

    def test_prd_example_composition(self) -> None:
        """Parse the exact example from the PRD."""
        data = {
            "timeline": {
                "background": "#000000",
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "image",
                                    "src": "https://example.com/photo.jpg",
                                },
                                "start": 0,
                                "length": 4,
                                "fit": "cover",
                            }
                        ]
                    },
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "text",
                                    "text": "Hello {{name}}",
                                    "font_family": "Inter",
                                    "font_size": 64,
                                    "color": "#ffffff",
                                    "background": "rgba(0,0,0,0.45)",
                                    "padding": 16,
                                },
                                "start": 0.5,
                                "length": 3,
                                "position": "center",
                                "opacity": 1,
                            }
                        ]
                    },
                ],
                "soundtrack": {
                    "type": "audio",
                    "src": "https://example.com/music.mp3",
                    "volume": 0.35,
                    "effect": "fadeOut",
                },
            },
            "output": {
                "format": "mp4",
                "width": 1080,
                "height": 1920,
                "fps": 30,
                "quality": "medium",
            },
            "merge": {"name": "World"},
            "callback": "https://example.com/webhooks/render",
        }
        comp = Composition(**data)
        assert comp.output.width == 1080
        assert comp.output.height == 1920

    def test_missing_timeline_rejected(self) -> None:
        with pytest.raises(ValidationError, match="timeline"):
            Composition(**{"output": {}})  # type: ignore[arg-type]

    def test_empty_tracks_rejected(self) -> None:
        with pytest.raises(ValidationError, match="too_short"):
            Composition(
                **{
                    "timeline": {"tracks": []},
                }
            )

    def test_missing_asset_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Composition(**{"timeline": {"tracks": [{"clips": [{"length": 3.0}]}]}})
