from __future__ import annotations

import pytest

from app.core.config import Settings
from app.models.composition import Output, OutputFormat, QualityPreset
from app.services.limits import LimitExceededError, validate_composition_limits
from app.services.output_formats import (
    build_png_sequence_manifest,
    manifest_bytes,
    plan_output_format,
)


def _composition_payload(*, output: dict, length: float = 3.0) -> dict:
    return {
        "timeline": {
            "tracks": [
                {
                    "clips": [
                        {
                            "asset": {"type": "color", "color": "#000000"},
                            "length": length,
                        }
                    ]
                }
            ]
        },
        "output": output,
    }


@pytest.mark.parametrize(
    ("preset", "width", "height", "fps", "quality"),
    [
        ("tiktok", 1080, 1920, 30, QualityPreset.HIGH),
        ("reels", 1080, 1920, 30, QualityPreset.HIGH),
        ("shorts", 1080, 1920, 30, QualityPreset.HIGH),
        ("youtube", 1920, 1080, 30, QualityPreset.HIGH),
        ("square-ad", 1080, 1080, 30, QualityPreset.MEDIUM),
        ("preview-low", 640, 360, 24, QualityPreset.LOW),
    ],
)
def test_output_presets_apply_deterministic_defaults(
    preset: str,
    width: int,
    height: int,
    fps: int,
    quality: QualityPreset,
) -> None:
    output = Output(preset=preset)

    assert output.width == width
    assert output.height == height
    assert output.fps == fps
    assert output.quality == quality


def test_explicit_dimensions_win_over_output_preset() -> None:
    output = Output(preset="tiktok", width=720, height=1280)

    assert output.width == 720
    assert output.height == 1280
    assert output.fps == 30
    assert output.quality == QualityPreset.HIGH


@pytest.mark.parametrize(
    ("output_format", "suffix", "media_type"),
    [
        (OutputFormat.MP4, ".mp4", "video/mp4"),
        (OutputFormat.WEBM, ".webm", "video/webm"),
        (OutputFormat.GIF, ".gif", "image/gif"),
        (OutputFormat.PNG_SEQUENCE, ".zip", "application/zip"),
    ],
)
def test_output_format_plan_sets_filename_suffix_and_media_type(
    output_format: OutputFormat,
    suffix: str,
    media_type: str,
) -> None:
    plan = plan_output_format("render_abc123", Output(format=output_format))

    assert plan.storage_suffix == suffix
    assert plan.filename == f"render_abc123{suffix}"
    assert plan.media_type == media_type


def test_png_sequence_manifest_serializes_ascii_json() -> None:
    output = Output(format="png-sequence", width=320, height=180, fps=10)
    manifest = build_png_sequence_manifest(
        render_id="render_abc123",
        output=output,
        frame_names=["frame_000001.png", "frame_000002.png"],
    )

    data = manifest_bytes(manifest)

    assert data.decode("ascii")
    assert b'"frame_count": 2' in data
    assert b'"format": "png-sequence"' in data


def test_gif_duration_guardrail_rejects_over_limit() -> None:
    from app.models.composition import Composition

    composition = Composition.model_validate(
        _composition_payload(output={"format": "gif"}, length=3.0)
    )
    settings = Settings(max_gif_duration_seconds=2)

    with pytest.raises(LimitExceededError) as exc_info:
        validate_composition_limits(composition, settings)

    assert exc_info.value.violation.field == "output.gif.duration"


def test_png_sequence_frame_guardrail_rejects_over_limit() -> None:
    from app.models.composition import Composition

    composition = Composition.model_validate(
        _composition_payload(
            output={
                "format": "png-sequence",
                "width": 320,
                "height": 180,
                "fps": 10,
            },
            length=2.0,
        )
    )
    settings = Settings(
        max_png_sequence_duration_seconds=60,
        max_png_sequence_frames=10,
    )

    with pytest.raises(LimitExceededError) as exc_info:
        validate_composition_limits(composition, settings)

    assert exc_info.value.violation.field == "output.png_sequence.frames"
