from __future__ import annotations

import pytest

from app.models.composition import Composition
from app.renderers.capabilities import (
    DEFAULT_RENDERER,
    EDITLY_CAPABILITY,
    EDITLY_RENDERER,
    FFMPEG_NATIVE_CAPABILITY,
    FFMPEG_NATIVE_RENDERER,
    RENDERER_CAPABILITIES,
    RendererCapability,
    UnsupportedRendererError,
    UnsupportedRendererFeatureError,
    available_renderer_names,
    known_renderer_names,
    select_renderer,
    validate_renderer_capabilities,
)


def _composition(**overrides: object) -> Composition:
    payload = {
        "timeline": {
            "tracks": [
                {
                    "clips": [
                        {
                            "asset": {
                                "type": "image",
                                "src": "https://example.com/image.png?secret=token",
                            },
                            "length": 1.0,
                        }
                    ]
                }
            ]
        },
        "output": {"format": "mp4", "width": 1280, "height": 720},
    }
    payload.update(overrides)
    return Composition.model_validate(payload)


def test_renderer_registry_exposes_known_and_available_names() -> None:
    assert available_renderer_names() == ("editly", "ffmpeg-native")
    assert known_renderer_names() == ("editly", "ffmpeg-native", "hyperframes")
    assert EDITLY_CAPABILITY.available is True
    assert EDITLY_CAPABILITY.output_formats == {
        "gif",
        "mp4",
        "png-sequence",
        "webm",
    }
    assert FFMPEG_NATIVE_CAPABILITY.available is True


@pytest.mark.parametrize("requested", [None, "auto", "editly"])
def test_select_renderer_defaults_to_editly(requested: str | None) -> None:
    selection = select_renderer(requested)

    assert selection.renderer == DEFAULT_RENDERER
    assert selection.capability.name == DEFAULT_RENDERER


def test_select_renderer_accepts_explicit_native_renderer() -> None:
    selection = select_renderer("ffmpeg-native")

    assert selection.renderer == FFMPEG_NATIVE_RENDERER
    assert selection.capability.name == FFMPEG_NATIVE_RENDERER


@pytest.mark.parametrize("requested", ["hyperframes"])
def test_select_renderer_rejects_unavailable_future_renderers(
    requested: str,
) -> None:
    with pytest.raises(UnsupportedRendererError) as exc_info:
        select_renderer(requested)

    exc = exc_info.value
    assert exc.code == "UNSUPPORTED_RENDERER"
    assert exc.to_context()["renderer"] == requested
    assert exc.to_context()["reason"] == "unavailable"


def test_select_renderer_rejects_unknown_renderer() -> None:
    with pytest.raises(UnsupportedRendererError) as exc_info:
        select_renderer("not-a-renderer")

    context = exc_info.value.to_context()
    assert context["renderer"] == "not-a-renderer"
    assert context["reason"] == "unknown"


def test_validate_renderer_capabilities_accepts_supported_editly_composition() -> None:
    composition = _composition(renderer="editly")

    selection = validate_renderer_capabilities(composition)

    assert selection.renderer == "editly"


def test_editly_capability_declares_advanced_transitions() -> None:
    requested = {
        "crossfade",
        "directional_left",
        "wipe_left",
        "cross_zoom",
        "simple_zoom",
        "circle_open",
        "linear_blur",
    }

    assert requested.issubset(
        {transition.value for transition in EDITLY_CAPABILITY.transitions}
    )


def test_native_capability_declares_subset_without_transitions_or_finishers() -> None:
    assert FFMPEG_NATIVE_CAPABILITY.asset_types == {
        "audio",
        "color",
        "image",
        "text",
        "video",
    }
    assert FFMPEG_NATIVE_CAPABILITY.output_formats == {
        "gif",
        "mp4",
        "png-sequence",
        "webm",
    }
    assert FFMPEG_NATIVE_CAPABILITY.transitions == frozenset()
    assert FFMPEG_NATIVE_CAPABILITY.supports_captions is False
    assert FFMPEG_NATIVE_CAPABILITY.supports_poster_options is False


@pytest.mark.parametrize("output_format", ["mp4", "webm", "gif", "png-sequence"])
def test_validate_renderer_capabilities_accepts_implemented_output_formats(
    output_format: str,
) -> None:
    composition = _composition(
        output={"format": output_format, "width": 1280, "height": 720}
    )

    selection = validate_renderer_capabilities(composition)

    assert selection.renderer == "editly"


def test_capability_error_context_does_not_include_asset_or_callback_urls() -> None:
    composition = _composition(
        renderer="not-a-renderer",
        output={"format": "gif", "width": 1280, "height": 720},
        callback="https://callback.example.com/hook?token=secret",
    )

    with pytest.raises(UnsupportedRendererError) as exc_info:
        validate_renderer_capabilities(composition)

    context_text = repr(exc_info.value.to_context())
    assert "example.com" not in context_text
    assert "secret" not in context_text


def test_native_rejects_transitions_with_redacted_context() -> None:
    composition = _composition(
        renderer="ffmpeg-native",
        callback="https://callback.example.com/hook?token=secret",
        timeline={
            "tracks": [
                {
                    "clips": [
                        {
                            "asset": {
                                "type": "image",
                                "src": "https://example.com/image.png?secret=token",
                            },
                            "length": 1.0,
                            "transition": {"name": "wipe_left", "duration": 0.2},
                        }
                    ]
                }
            ]
        },
    )

    with pytest.raises(UnsupportedRendererFeatureError) as exc_info:
        validate_renderer_capabilities(composition)

    context = exc_info.value.to_context()
    assert context["renderer"] == "ffmpeg-native"
    assert context["feature"] == "timeline.tracks[0].clips[0].transition.name"
    assert context["requested"] == "wipe_left"
    assert context["supported"] == []
    context_text = repr(context)
    assert "example.com" not in context_text
    assert "secret" not in context_text


def test_native_rejects_captions_and_poster_controls() -> None:
    composition = _composition(
        renderer="ffmpeg-native",
        captions={
            "mode": "sidecar",
            "format": "srt",
            "cues": [{"start": 0.0, "end": 1.0, "text": "Hello"}],
        },
        output={
            "format": "mp4",
            "width": 1280,
            "height": 720,
            "poster": {"mode": "timestamp", "timestamp": 0.2},
        },
    )

    with pytest.raises(UnsupportedRendererFeatureError) as exc_info:
        validate_renderer_capabilities(composition)

    context = exc_info.value.to_context()
    assert context["renderer"] == "ffmpeg-native"
    assert context["feature"] == "captions.mode"
    assert context["issue_count"] == 3


def test_unsupported_transition_context_is_bounded_and_redacted(monkeypatch) -> None:
    limited_capability = RendererCapability(
        name=EDITLY_RENDERER,
        available=True,
        asset_types=EDITLY_CAPABILITY.asset_types,
        output_formats=EDITLY_CAPABILITY.output_formats,
        transitions=frozenset(),
        supports_captions=EDITLY_CAPABILITY.supports_captions,
        supports_poster_options=EDITLY_CAPABILITY.supports_poster_options,
    )
    monkeypatch.setitem(RENDERER_CAPABILITIES, EDITLY_RENDERER, limited_capability)
    composition = _composition(
        callback="https://callback.example.com/hook?token=secret",
        timeline={
            "tracks": [
                {
                    "clips": [
                        {
                            "asset": {
                                "type": "image",
                                "src": "https://example.com/image.png?secret=token",
                            },
                            "length": 1.0,
                            "transition": {"name": "wipe_left", "duration": 0.2},
                        },
                        {
                            "asset": {
                                "type": "image",
                                "src": "https://example.com/b.png",
                            },
                            "start": 1.0,
                            "length": 1.0,
                        },
                    ]
                }
            ]
        },
    )

    with pytest.raises(UnsupportedRendererFeatureError) as exc_info:
        validate_renderer_capabilities(composition)

    context = exc_info.value.to_context()
    assert context["feature"] == "timeline.tracks[0].clips[0].transition.name"
    assert context["requested"] == "wipe_left"
    context_text = repr(context)
    assert "example.com" not in context_text
    assert "secret" not in context_text
