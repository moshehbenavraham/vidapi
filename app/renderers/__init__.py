from __future__ import annotations

from app.renderers.base import (
    CompiledRender,
    CompileError,
    RenderArtifact,
    RendererProtocol,
    RendererResolver,
    RenderError,
)
from app.renderers.capabilities import (
    DEFAULT_RENDERER,
    FFMPEG_NATIVE_RENDERER,
    HYPERFRAMES_RENDERER,
    RENDERER_CAPABILITIES,
    RendererCapability,
    RendererCapabilityError,
    RendererSelection,
    UnsupportedRendererError,
    UnsupportedRendererFeatureError,
    available_renderer_names,
    get_capability,
    known_renderer_names,
    select_renderer,
    validate_renderer_capabilities,
)
from app.renderers.editly import EditlyRenderer
from app.renderers.hyperframes import HyperFramesRenderer
from app.renderers.native_ffmpeg import NativeFfmpegRenderer
from app.renderers.poster import PosterError, generate_poster

_RENDERER_REGISTRY: dict[str, type[RendererProtocol]] = {
    DEFAULT_RENDERER: EditlyRenderer,
    FFMPEG_NATIVE_RENDERER: NativeFfmpegRenderer,
    HYPERFRAMES_RENDERER: HyperFramesRenderer,
}


def get_renderer(name: str | None = None) -> RendererProtocol:
    """Resolve an available renderer implementation by requested name."""
    selection = select_renderer(name)

    renderer_cls = _RENDERER_REGISTRY.get(selection.renderer)
    if renderer_cls is None:
        raise UnsupportedRendererError(
            selection.renderer,
            reason="unavailable",
        )

    return renderer_cls()


__all__ = [
    "DEFAULT_RENDERER",
    "FFMPEG_NATIVE_RENDERER",
    "HYPERFRAMES_RENDERER",
    "RENDERER_CAPABILITIES",
    "CompileError",
    "CompiledRender",
    "EditlyRenderer",
    "HyperFramesRenderer",
    "NativeFfmpegRenderer",
    "PosterError",
    "RenderArtifact",
    "RenderError",
    "RendererCapability",
    "RendererCapabilityError",
    "RendererProtocol",
    "RendererResolver",
    "RendererSelection",
    "UnsupportedRendererError",
    "UnsupportedRendererFeatureError",
    "available_renderer_names",
    "generate_poster",
    "get_capability",
    "get_renderer",
    "known_renderer_names",
    "select_renderer",
    "validate_renderer_capabilities",
]
