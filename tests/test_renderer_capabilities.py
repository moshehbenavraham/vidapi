from __future__ import annotations

import pytest

from app.models.composition import Composition
from app.renderers.capabilities import (
    DEFAULT_RENDERER,
    EDITLY_CAPABILITY,
    UnsupportedRendererError,
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
    assert available_renderer_names() == ("editly",)
    assert known_renderer_names() == ("editly", "ffmpeg-native", "hyperframes")
    assert EDITLY_CAPABILITY.available is True
    assert EDITLY_CAPABILITY.output_formats == {
        "gif",
        "mp4",
        "png-sequence",
        "webm",
    }


@pytest.mark.parametrize("requested", [None, "auto", "editly"])
def test_select_renderer_defaults_to_editly(requested: str | None) -> None:
    selection = select_renderer(requested)

    assert selection.renderer == DEFAULT_RENDERER
    assert selection.capability.name == DEFAULT_RENDERER


@pytest.mark.parametrize("requested", ["ffmpeg-native", "hyperframes"])
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
