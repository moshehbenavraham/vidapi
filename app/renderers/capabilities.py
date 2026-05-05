from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.models.composition import (
    CaptionFormat,
    CaptionMode,
    Composition,
    OutputFormat,
    PosterMode,
    TransitionType,
)
from app.renderers.transitions import EDITLY_SUPPORTED_TRANSITIONS
from app.services.output_formats import supported_output_formats

AUTO_RENDERER = "auto"
DEFAULT_RENDERER = "editly"
EDITLY_RENDERER = "editly"
FFMPEG_NATIVE_RENDERER = "ffmpeg-native"
HYPERFRAMES_RENDERER = "hyperframes"
UNSUPPORTED_RENDERER = "UNSUPPORTED_RENDERER"
UNSUPPORTED_RENDERER_FEATURE = "UNSUPPORTED_RENDERER_FEATURE"
MAX_CONTEXT_ITEMS = 10
MAX_CONTEXT_VALUE_LENGTH = 100
SUPPORTED_CAPTION_MODES = frozenset({CaptionMode.SIDECAR, CaptionMode.BURN_IN})
SUPPORTED_CAPTION_FORMATS = frozenset({CaptionFormat.SRT, CaptionFormat.WEBVTT})
SUPPORTED_POSTER_MODES = frozenset(
    {
        PosterMode.DEFAULT,
        PosterMode.TIMESTAMP,
        PosterMode.PERCENT,
        PosterMode.DISABLED,
    }
)


@dataclass(frozen=True)
class RendererCapability:
    """Immutable support declaration for a renderer backend."""

    name: str
    available: bool
    asset_types: frozenset[str]
    output_formats: frozenset[OutputFormat]
    transitions: frozenset[TransitionType]
    supports_captions: bool = False
    supports_poster_options: bool = False


@dataclass(frozen=True)
class RendererSelection:
    """Resolved renderer selection for a composition."""

    requested: str | None
    renderer: str
    capability: RendererCapability


@dataclass(frozen=True)
class RendererFeatureIssue:
    """Single unsupported feature found during capability validation."""

    feature: str
    requested: str
    supported: tuple[str, ...]

    def to_context(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "requested": self.requested,
            "supported": list(self.supported),
        }


class RendererCapabilityError(Exception):
    """Base exception for safe renderer capability failures."""

    code = "RENDERER_CAPABILITY_ERROR"
    message = "Renderer capability validation failed."

    def __init__(
        self,
        *,
        renderer: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.renderer = renderer
        self.context = context or {}
        super().__init__(self.message)

    def to_context(self) -> dict[str, Any]:
        return dict(self.context)


class UnsupportedRendererError(RendererCapabilityError):
    """Raised when a renderer is unknown or known but unavailable."""

    code = UNSUPPORTED_RENDERER
    message = "Requested renderer is not supported."

    def __init__(
        self,
        requested_renderer: str | None,
        *,
        reason: str,
    ) -> None:
        renderer = _safe_value(requested_renderer)
        context: dict[str, Any] = {
            "renderer": renderer,
            "reason": reason,
            "available_renderers": list(available_renderer_names()),
        }
        if reason == "unavailable":
            context["known_renderers"] = list(known_renderer_names())
        super().__init__(renderer=renderer, context=context)


class UnsupportedRendererFeatureError(RendererCapabilityError):
    """Raised when a renderer cannot handle one or more composition features."""

    code = UNSUPPORTED_RENDERER_FEATURE
    message = "Renderer does not support requested feature."

    def __init__(
        self,
        renderer: str,
        issues: list[RendererFeatureIssue],
    ) -> None:
        if not issues:
            msg = "UnsupportedRendererFeatureError requires at least one issue"
            raise ValueError(msg)

        first_issue = issues[0]
        bounded_issues = issues[:MAX_CONTEXT_ITEMS]
        context: dict[str, Any] = {
            "renderer": renderer,
            "feature": first_issue.feature,
            "requested": first_issue.requested,
            "supported": list(first_issue.supported),
        }
        if len(issues) > 1:
            context["issues"] = [issue.to_context() for issue in bounded_issues]
            context["issue_count"] = len(issues)
        super().__init__(renderer=renderer, context=context)
        self.issues = tuple(issues)


EDITLY_CAPABILITY = RendererCapability(
    name=EDITLY_RENDERER,
    available=True,
    asset_types=frozenset({"video", "image", "text", "audio", "color"}),
    output_formats=supported_output_formats(),
    transitions=EDITLY_SUPPORTED_TRANSITIONS,
    supports_captions=True,
    supports_poster_options=True,
)

FFMPEG_NATIVE_CAPABILITY = RendererCapability(
    name=FFMPEG_NATIVE_RENDERER,
    available=True,
    asset_types=frozenset({"video", "image", "text", "audio", "color"}),
    output_formats=supported_output_formats(),
    transitions=frozenset(),
)

HYPERFRAMES_CAPABILITY = RendererCapability(
    name=HYPERFRAMES_RENDERER,
    available=False,
    asset_types=frozenset(),
    output_formats=frozenset(),
    transitions=frozenset(),
)

RENDERER_CAPABILITIES: dict[str, RendererCapability] = {
    EDITLY_CAPABILITY.name: EDITLY_CAPABILITY,
    FFMPEG_NATIVE_CAPABILITY.name: FFMPEG_NATIVE_CAPABILITY,
    HYPERFRAMES_CAPABILITY.name: HYPERFRAMES_CAPABILITY,
}


def get_capability(renderer_name: str) -> RendererCapability | None:
    """Return a capability record without applying availability checks."""
    return RENDERER_CAPABILITIES.get(renderer_name)


def available_renderer_names() -> tuple[str, ...]:
    """Return deterministic available renderer names."""
    return tuple(
        sorted(
            capability.name
            for capability in RENDERER_CAPABILITIES.values()
            if capability.available
        )
    )


def known_renderer_names() -> tuple[str, ...]:
    """Return deterministic known renderer names, including unavailable ones."""
    return tuple(sorted(RENDERER_CAPABILITIES))


def select_renderer(requested_renderer: str | None) -> RendererSelection:
    """Resolve a request renderer value to an available renderer."""
    requested = _safe_value(requested_renderer)
    selected: str = (
        DEFAULT_RENDERER
        if requested is None or requested == AUTO_RENDERER
        else requested
    )

    capability = RENDERER_CAPABILITIES.get(selected)
    if capability is None:
        raise UnsupportedRendererError(selected, reason="unknown")
    if not capability.available:
        raise UnsupportedRendererError(selected, reason="unavailable")

    return RendererSelection(
        requested=requested,
        renderer=selected,
        capability=capability,
    )


def validate_renderer_capabilities(composition: Composition) -> RendererSelection:
    """Validate that the selected renderer can handle the composition."""
    selection = select_renderer(composition.renderer)
    capability = selection.capability
    issues: list[RendererFeatureIssue] = []

    _append_issue_if_unsupported(
        issues,
        capability=capability,
        feature="output.format",
        requested=composition.output.format,
        supported=capability.output_formats,
    )

    if composition.captions is not None:
        caption_modes = (
            SUPPORTED_CAPTION_MODES if capability.supports_captions else frozenset()
        )
        _append_issue_if_unsupported(
            issues,
            capability=capability,
            feature="captions.mode",
            requested=composition.captions.mode,
            supported=caption_modes,
        )
        if composition.captions.mode is CaptionMode.SIDECAR:
            caption_formats = (
                SUPPORTED_CAPTION_FORMATS
                if capability.supports_captions
                else frozenset()
            )
            _append_issue_if_unsupported(
                issues,
                capability=capability,
                feature="captions.format",
                requested=composition.captions.format,
                supported=caption_formats,
            )

    if composition.output.poster is not None:
        poster_modes = (
            SUPPORTED_POSTER_MODES
            if capability.supports_poster_options
            else frozenset()
        )
        _append_issue_if_unsupported(
            issues,
            capability=capability,
            feature="output.poster.mode",
            requested=composition.output.poster.mode,
            supported=poster_modes,
        )

    for track_index, track in enumerate(composition.timeline.tracks):
        for clip_index, clip in enumerate(track.clips):
            clip_path = f"timeline.tracks[{track_index}].clips[{clip_index}]"
            _append_issue_if_unsupported(
                issues,
                capability=capability,
                feature=f"{clip_path}.asset.type",
                requested=clip.asset.type,
                supported=capability.asset_types,
            )
            if clip.transition is not None:
                _append_issue_if_unsupported(
                    issues,
                    capability=capability,
                    feature=f"{clip_path}.transition.name",
                    requested=clip.transition.name,
                    supported=capability.transitions,
                )

    if issues:
        raise UnsupportedRendererFeatureError(selection.renderer, issues)

    return selection


def _append_issue_if_unsupported(
    issues: list[RendererFeatureIssue],
    *,
    capability: RendererCapability,
    feature: str,
    requested: object,
    supported: frozenset[Any],
) -> None:
    if requested in supported:
        return
    issues.append(
        RendererFeatureIssue(
            feature=feature,
            requested=_safe_value(requested) or "",
            supported=tuple(sorted(_safe_value(value) or "" for value in supported)),
        )
    )


def _safe_value(value: object) -> str | None:
    if value is None:
        return None
    text = value.value if isinstance(value, StrEnum) else str(value)
    text = text.replace("\r", " ").replace("\n", " ").strip()
    return text[:MAX_CONTEXT_VALUE_LENGTH]
