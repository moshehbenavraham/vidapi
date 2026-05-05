from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models.composition import (
    AudioAsset,
    Clip,
    ColorAsset,
    Composition,
    FitMode,
    ImageAsset,
    TextAsset,
    VideoAsset,
)
from app.renderers.base import CompileError
from app.renderers.position import resolve_position
from app.renderers.timeline import (
    EPSILON,
    VisualClipRef,
    asset_resolver_key,
    compute_total_duration,
    iter_visual_clip_refs,
)

NATIVE_PLAN_VERSION = 1
NATIVE_SUPPORTED_ASSET_TYPES = frozenset({"audio", "color", "image", "text", "video"})
NATIVE_SUPPORTED_FIT_MODES = frozenset(FitMode)
NATIVE_SUPPORTED_TRANSFORMS: tuple[str, ...] = ()
NATIVE_SUPPORTED_TRANSITIONS: tuple[str, ...] = ()
_HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


@dataclass(frozen=True)
class NativeSubsetIssue:
    """Single native-renderer subset validation issue."""

    feature: str
    requested: str
    supported: tuple[str, ...] = ()

    def to_context(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "requested": self.requested,
            "supported": list(self.supported),
        }


class NativeSubsetError(CompileError):
    """Raised when a composition falls outside the native FFmpeg subset."""

    def __init__(self, issues: list[NativeSubsetIssue]) -> None:
        if not issues:
            msg = "NativeSubsetError requires at least one issue"
            raise ValueError(msg)
        self.issues = tuple(issues)
        first = issues[0]
        message = (
            "Native FFmpeg renderer does not support requested feature "
            f"{first.feature}: {first.requested}"
        )
        super().__init__(message)

    def to_context(self) -> dict[str, Any]:
        first = self.issues[0]
        context: dict[str, Any] = first.to_context()
        context["renderer"] = "ffmpeg-native"
        if len(self.issues) > 1:
            context["issues"] = [issue.to_context() for issue in self.issues[:10]]
            context["issue_count"] = len(self.issues)
        return context


@dataclass(frozen=True)
class NativeInput:
    """Single FFmpeg input with deterministic argument ordering."""

    index: int
    kind: str
    path: str
    args: tuple[str, ...]
    track_index: int | None = None
    clip_index: int | None = None

    def to_jsonable(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "index": self.index,
            "kind": self.kind,
            "path": self.path,
            "args": list(self.args),
        }
        if self.track_index is not None:
            data["track_index"] = self.track_index
        if self.clip_index is not None:
            data["clip_index"] = self.clip_index
        return data


@dataclass(frozen=True)
class NativeVisualLayer:
    """Resolved visual layer in overlay order."""

    asset_type: str
    track_index: int
    clip_index: int
    start: float
    length: float
    fit: FitMode
    scale: float
    opacity: float
    input_index: int | None = None
    path: str | None = None
    color: str | None = None
    trim: float | None = None
    clip: Clip | None = None

    @property
    def end(self) -> float:
        return self.start + self.length

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "asset_type": self.asset_type,
            "track_index": self.track_index,
            "clip_index": self.clip_index,
            "start": round(self.start, 6),
            "length": round(self.length, 6),
            "fit": self.fit.value,
            "scale": round(self.scale, 6),
            "opacity": round(self.opacity, 6),
            "input_index": self.input_index,
            "path": self.path,
            "color": self.color,
            "trim": self.trim,
        }


@dataclass(frozen=True)
class NativeAudioLayer:
    """Resolved soundtrack or detached audio layer."""

    input_index: int
    path: str
    start: float
    length: float | None
    trim: float | None
    volume: float
    role: str
    track_index: int | None = None
    clip_index: int | None = None

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "input_index": self.input_index,
            "path": self.path,
            "start": round(self.start, 6),
            "length": round(self.length, 6) if self.length is not None else None,
            "trim": self.trim,
            "volume": round(self.volume, 6),
            "role": self.role,
            "track_index": self.track_index,
            "clip_index": self.clip_index,
        }


@dataclass(frozen=True)
class NativeRenderPlan:
    """Deterministic native FFmpeg render plan."""

    width: int
    height: int
    fps: int
    duration: float
    output_path: Path
    inputs: tuple[NativeInput, ...]
    visual_layers: tuple[NativeVisualLayer, ...]
    audio_layers: tuple[NativeAudioLayer, ...]
    filter_complex: str
    command: tuple[str, ...]

    @property
    def has_audio(self) -> bool:
        return bool(self.audio_layers)

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "renderer": "ffmpeg-native",
            "version": NATIVE_PLAN_VERSION,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "duration": round(self.duration, 6),
            "output_path": str(self.output_path),
            "inputs": [item.to_jsonable() for item in self.inputs],
            "visual_layers": [layer.to_jsonable() for layer in self.visual_layers],
            "audio_layers": [layer.to_jsonable() for layer in self.audio_layers],
            "filter_complex": self.filter_complex,
            "command": list(self.command),
        }


def build_native_render_plan(
    composition: Composition,
    output_path: Path,
    *,
    asset_path_resolver: dict[str, str] | None,
    ffmpeg_bin: str,
) -> NativeRenderPlan:
    """Validate and compile a composition into a native FFmpeg plan."""
    issues = validate_native_subset(composition, asset_path_resolver)
    if issues:
        raise NativeSubsetError(issues)

    duration = compute_total_duration(composition.timeline.tracks)
    if duration <= EPSILON:
        raise NativeSubsetError(
            [
                NativeSubsetIssue(
                    feature="timeline.duration",
                    requested="0",
                    supported=("positive visual duration",),
                )
            ]
        )

    width = composition.output.width or 1920
    height = composition.output.height or 1080
    fps = composition.output.fps

    inputs: list[NativeInput] = []
    visual_layers: list[NativeVisualLayer] = []
    audio_layers: list[NativeAudioLayer] = []
    next_input_index = 0

    for ref in iter_visual_clip_refs(composition.timeline.tracks):
        layer, next_input_index = _plan_visual_layer(
            ref,
            resolver=asset_path_resolver or {},
            next_input_index=next_input_index,
            width=width,
            height=height,
        )
        visual_layers.append(layer)
        if layer.input_index is not None and layer.path is not None:
            input_args = _visual_input_args(layer)
            inputs.append(
                NativeInput(
                    index=layer.input_index,
                    kind=layer.asset_type,
                    path=layer.path,
                    args=tuple(input_args),
                    track_index=layer.track_index,
                    clip_index=layer.clip_index,
                )
            )

    soundtrack = composition.timeline.soundtrack
    if soundtrack is not None:
        path = _resolve_asset_path(soundtrack.src, asset_path_resolver or {})
        assert path is not None
        index = next_input_index
        next_input_index += 1
        inputs.append(
            NativeInput(
                index=index,
                kind="audio",
                path=path,
                args=("-i", path),
            )
        )
        audio_layers.append(
            NativeAudioLayer(
                input_index=index,
                path=path,
                start=0.0,
                length=duration,
                trim=soundtrack.trim,
                volume=soundtrack.volume,
                role="soundtrack",
            )
        )

    for track_index, track in enumerate(composition.timeline.tracks):
        for clip_index, clip in enumerate(track.clips):
            if not isinstance(clip.asset, AudioAsset):
                continue
            path = _resolve_asset_path(clip.asset.src, asset_path_resolver or {})
            assert path is not None
            index = next_input_index
            next_input_index += 1
            inputs.append(
                NativeInput(
                    index=index,
                    kind="audio",
                    path=path,
                    args=("-i", path),
                    track_index=track_index,
                    clip_index=clip_index,
                )
            )
            audio_layers.append(
                NativeAudioLayer(
                    input_index=index,
                    path=path,
                    start=clip.start,
                    length=clip.length,
                    trim=clip.asset.trim,
                    volume=clip.asset.volume,
                    role="clip",
                    track_index=track_index,
                    clip_index=clip_index,
                )
            )

    filter_complex = build_filter_complex(
        composition,
        visual_layers=visual_layers,
        audio_layers=audio_layers,
        width=width,
        height=height,
        fps=fps,
        duration=duration,
    )
    command = build_ffmpeg_command(
        ffmpeg_bin=ffmpeg_bin,
        inputs=inputs,
        filter_complex=filter_complex,
        output_path=output_path,
        output_crf=composition.output.crf,
        output_preset=composition.output.ffmpeg_preset,
        fps=fps,
        duration=duration,
        has_audio=bool(audio_layers),
    )

    return NativeRenderPlan(
        width=width,
        height=height,
        fps=fps,
        duration=duration,
        output_path=output_path,
        inputs=tuple(inputs),
        visual_layers=tuple(visual_layers),
        audio_layers=tuple(audio_layers),
        filter_complex=filter_complex,
        command=tuple(command),
    )


def validate_native_subset(
    composition: Composition,
    asset_path_resolver: dict[str, str] | None,
) -> list[NativeSubsetIssue]:
    """Return bounded native subset validation issues without raw payload data."""
    issues: list[NativeSubsetIssue] = []
    resolver = asset_path_resolver or {}

    _append_color_issue(issues, "timeline.background", composition.timeline.background)

    if composition.captions is not None:
        issues.append(
            NativeSubsetIssue(
                feature="captions",
                requested="present",
                supported=(),
            )
        )

    if composition.output.poster is not None:
        issues.append(
            NativeSubsetIssue(
                feature="output.poster",
                requested="present",
                supported=(),
            )
        )

    for track_index, track in enumerate(composition.timeline.tracks):
        for clip_index, clip in enumerate(track.clips):
            clip_path = f"timeline.tracks[{track_index}].clips[{clip_index}]"
            asset = clip.asset
            asset_type = str(asset.type)
            if asset_type not in NATIVE_SUPPORTED_ASSET_TYPES:
                issues.append(
                    NativeSubsetIssue(
                        feature=f"{clip_path}.asset.type",
                        requested=asset_type,
                        supported=tuple(sorted(NATIVE_SUPPORTED_ASSET_TYPES)),
                    )
                )
                continue

            if clip.transition is not None:
                issues.append(
                    NativeSubsetIssue(
                        feature=f"{clip_path}.transition.name",
                        requested=clip.transition.name.value,
                        supported=NATIVE_SUPPORTED_TRANSITIONS,
                    )
                )

            if clip.transform is not None:
                issues.append(
                    NativeSubsetIssue(
                        feature=f"{clip_path}.transform",
                        requested="present",
                        supported=NATIVE_SUPPORTED_TRANSFORMS,
                    )
                )

            if clip.fit not in NATIVE_SUPPORTED_FIT_MODES:
                issues.append(
                    NativeSubsetIssue(
                        feature=f"{clip_path}.fit",
                        requested=clip.fit.value,
                        supported=tuple(sorted(mode.value for mode in FitMode)),
                    )
                )

            if isinstance(asset, ColorAsset):
                _append_color_issue(issues, f"{clip_path}.asset.color", asset.color)
                continue

            if isinstance(asset, AudioAsset):
                if asset.effect is not None:
                    issues.append(
                        NativeSubsetIssue(
                            feature=f"{clip_path}.asset.effect",
                            requested=asset.effect.value,
                            supported=(),
                        )
                    )
                if _resolve_asset_path(asset.src, resolver) is None:
                    issues.append(_missing_asset_issue(f"{clip_path}.asset.src"))
                continue

            if isinstance(asset, (ImageAsset, VideoAsset, TextAsset)):
                key = asset_resolver_key(clip)
                if key is None or _resolve_asset_path(key, resolver) is None:
                    issues.append(_missing_asset_issue(f"{clip_path}.asset.src"))

    soundtrack = composition.timeline.soundtrack
    if soundtrack is not None:
        if soundtrack.effect is not None:
            issues.append(
                NativeSubsetIssue(
                    feature="timeline.soundtrack.effect",
                    requested=soundtrack.effect.value,
                    supported=(),
                )
            )
        if _resolve_asset_path(soundtrack.src, resolver) is None:
            issues.append(_missing_asset_issue("timeline.soundtrack.src"))

    return issues


def build_filter_complex(
    composition: Composition,
    *,
    visual_layers: list[NativeVisualLayer],
    audio_layers: list[NativeAudioLayer],
    width: int,
    height: int,
    fps: int,
    duration: float,
) -> str:
    """Build a deterministic FFmpeg filter graph for the native subset."""
    filters: list[str] = [
        (
            f"color=c={_ffmpeg_color(composition.timeline.background)}:"
            f"s={width}x{height}:r={fps}:d={duration:.6f},format=rgba[base0]"
        )
    ]

    current = "base0"
    for layer_index, layer in enumerate(visual_layers):
        source_label = f"vl{layer_index}"
        output_label = f"v{layer_index}"
        filters.append(
            _visual_layer_filter(
                layer,
                label=source_label,
                width=width,
                height=height,
                fps=fps,
            )
        )
        x_expr, y_expr = _overlay_position(layer, width=width, height=height)
        filters.append(
            f"[{current}][{source_label}]overlay=x={x_expr}:y={y_expr}:"
            f"enable='between(t,{layer.start:.6f},{layer.end:.6f})':"
            f"eof_action=pass:shortest=0[{output_label}]"
        )
        current = output_label

    filters.append(f"[{current}]format=yuv420p[vout]")

    if audio_layers:
        audio_labels: list[str] = []
        for index, audio_layer in enumerate(audio_layers):
            label = f"a{index}"
            filters.append(
                _audio_layer_filter(audio_layer, label=label, duration=duration)
            )
            audio_labels.append(f"[{label}]")
        joined = "".join(audio_labels)
        filters.append(
            f"{joined}amix=inputs={len(audio_labels)}:"
            "duration=longest:dropout_transition=0,"
            f"atrim=duration={duration:.6f},asetpts=PTS-STARTPTS[aout]"
        )

    return ";".join(filters)


def build_ffmpeg_command(
    *,
    ffmpeg_bin: str,
    inputs: list[NativeInput],
    filter_complex: str,
    output_path: Path,
    output_crf: int,
    output_preset: str,
    fps: int,
    duration: float,
    has_audio: bool,
) -> list[str]:
    """Build the exact FFmpeg command line for a native render plan."""
    command: list[str] = [ffmpeg_bin, "-y", "-hide_banner"]
    for item in inputs:
        command.extend(item.args)
    command.extend(["-filter_complex", filter_complex])
    command.extend(["-map", "[vout]"])
    if has_audio:
        command.extend(["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"])
    else:
        command.append("-an")
    command.extend(
        [
            "-t",
            f"{duration:.6f}",
            "-r",
            str(fps),
            "-c:v",
            "libx264",
            "-preset",
            output_preset,
            "-crf",
            str(output_crf),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    return command


def serialize_native_plan(plan: NativeRenderPlan) -> str:
    """Serialize a native plan as deterministic ASCII JSON."""
    return json.dumps(plan.to_jsonable(), sort_keys=True, indent=2, ensure_ascii=True)


def _plan_visual_layer(
    ref: VisualClipRef,
    *,
    resolver: dict[str, str],
    next_input_index: int,
    width: int,
    height: int,
) -> tuple[NativeVisualLayer, int]:
    clip = ref.clip
    asset = clip.asset
    _validate_layer_dimensions(clip, width=width, height=height)

    if isinstance(asset, ColorAsset):
        return (
            NativeVisualLayer(
                asset_type="color",
                track_index=ref.track_index,
                clip_index=ref.clip_index,
                start=clip.start,
                length=clip.length,
                fit=clip.fit,
                scale=clip.scale,
                opacity=clip.opacity,
                color=asset.color,
                clip=clip,
            ),
            next_input_index,
        )

    key = asset_resolver_key(clip)
    path = _resolve_asset_path(key or "", resolver)
    assert path is not None
    input_index = next_input_index
    next_input_index += 1

    trim: float | None = None
    if isinstance(asset, VideoAsset):
        asset_type = "video"
        trim = asset.trim
    elif isinstance(asset, ImageAsset):
        asset_type = "image"
    else:
        asset_type = "text"

    return (
        NativeVisualLayer(
            asset_type=asset_type,
            track_index=ref.track_index,
            clip_index=ref.clip_index,
            start=clip.start,
            length=clip.length,
            fit=clip.fit,
            scale=clip.scale,
            opacity=clip.opacity,
            input_index=input_index,
            path=path,
            trim=trim,
            clip=clip,
        ),
        next_input_index,
    )


def _visual_input_args(layer: NativeVisualLayer) -> list[str]:
    assert layer.path is not None
    if layer.asset_type in {"image", "text"}:
        return ["-loop", "1", "-t", f"{layer.length:.6f}", "-i", layer.path]
    return ["-i", layer.path]


def _visual_layer_filter(
    layer: NativeVisualLayer,
    *,
    label: str,
    width: int,
    height: int,
    fps: int,
) -> str:
    chain: list[str] = []
    if layer.input_index is None:
        source = (
            f"color=c={_ffmpeg_color(layer.color or '#000000')}@{layer.opacity:.6f}:"
            f"s={_target_width(layer, width)}x{_target_height(layer, height)}:"
            f"r={fps}:d={layer.length:.6f}"
        )
        chain.extend(["format=rgba", f"trim=duration={layer.length:.6f}"])
    else:
        source = f"[{layer.input_index}:v]"
        if layer.asset_type == "video":
            trim_start = layer.trim or 0.0
            chain.append(f"trim=start={trim_start:.6f}:duration={layer.length:.6f}")
        else:
            chain.append(f"trim=duration={layer.length:.6f}")
        chain.append("setpts=PTS-STARTPTS")
        chain.extend(_fit_filters(layer, width=width, height=height))
        chain.append("format=rgba")
        if layer.opacity < 1.0 - EPSILON:
            chain.append(f"colorchannelmixer=aa={layer.opacity:.6f}")

    if layer.input_index is None:
        chain.append("setpts=PTS-STARTPTS")
    chain.append(f"setpts=PTS-STARTPTS+{layer.start:.6f}/TB")
    return f"{source},{','.join(chain)}[{label}]"


def _audio_layer_filter(
    layer: NativeAudioLayer,
    *,
    label: str,
    duration: float,
) -> str:
    chain: list[str] = []
    trim_start = layer.trim or 0.0
    trim_duration = layer.length if layer.length is not None else duration
    trim_duration = min(trim_duration, max(duration - layer.start, 0.0))
    chain.append(f"atrim=start={trim_start:.6f}:duration={trim_duration:.6f}")
    chain.append("asetpts=PTS-STARTPTS")
    if abs(layer.volume - 1.0) > EPSILON:
        chain.append(f"volume={layer.volume:.6f}")
    if layer.start > EPSILON:
        delay_ms = round(layer.start * 1000)
        chain.append(f"adelay={delay_ms}|{delay_ms}")
    chain.append("aresample=44100")
    return f"[{layer.input_index}:a]{','.join(chain)}[{label}]"


def _fit_filters(layer: NativeVisualLayer, *, width: int, height: int) -> list[str]:
    target_width = _target_width(layer, width)
    target_height = _target_height(layer, height)
    if layer.fit is FitMode.COVER:
        return [
            (
                f"scale={target_width}:{target_height}:"
                "force_original_aspect_ratio=increase"
            ),
            f"crop={target_width}:{target_height}",
        ]
    if layer.fit is FitMode.CONTAIN:
        return [
            (
                f"scale={target_width}:{target_height}:"
                "force_original_aspect_ratio=decrease"
            )
        ]
    if layer.fit is FitMode.STRETCH:
        return [f"scale={target_width}:{target_height}"]
    return []


def _overlay_position(
    layer: NativeVisualLayer,
    *,
    width: int,
    height: int,
) -> tuple[str, str]:
    if layer.clip is None:
        return "0", "0"
    position = resolve_position(
        layer.clip.position,
        layer.clip.offset,
        output_width=width,
        output_height=height,
    )
    anchor_x = float(position["x"]) * width
    anchor_y = float(position["y"]) * height
    x_expr = _axis_expression(anchor_x, str(position["originX"]), "overlay_w")
    y_expr = _axis_expression(anchor_y, str(position["originY"]), "overlay_h")
    return x_expr, y_expr


def _axis_expression(anchor: float, origin: str, size_expr: str) -> str:
    base = f"{anchor:.6f}"
    if origin in {"center", "middle"}:
        return f"({base}-{size_expr}/2)"
    if origin in {"right", "bottom"}:
        return f"({base}-{size_expr})"
    return base


def _target_width(layer: NativeVisualLayer, width: int) -> int:
    return max(1, round(width * layer.scale))


def _target_height(layer: NativeVisualLayer, height: int) -> int:
    return max(1, round(height * layer.scale))


def _validate_layer_dimensions(clip: Clip, *, width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise NativeSubsetError(
            [
                NativeSubsetIssue(
                    feature="output.dimensions",
                    requested=f"{width}x{height}",
                    supported=("positive width and height",),
                )
            ]
        )
    if clip.scale <= 0.0:
        raise NativeSubsetError(
            [
                NativeSubsetIssue(
                    feature="timeline.clip.scale",
                    requested=str(clip.scale),
                    supported=("positive scale",),
                )
            ]
        )


def _resolve_asset_path(key: str | None, resolver: dict[str, str]) -> str | None:
    if key is None:
        return None
    path = resolver.get(key)
    if path:
        return path
    return None


def _missing_asset_issue(feature: str) -> NativeSubsetIssue:
    return NativeSubsetIssue(
        feature=feature,
        requested="unresolved",
        supported=("resolved local asset path",),
    )


def _append_color_issue(
    issues: list[NativeSubsetIssue],
    feature: str,
    value: str,
) -> None:
    if _HEX_COLOR_PATTERN.fullmatch(value):
        return
    issues.append(
        NativeSubsetIssue(
            feature=feature,
            requested="invalid color",
            supported=("#RRGGBB",),
        )
    )


def _ffmpeg_color(value: str) -> str:
    if not _HEX_COLOR_PATTERN.fullmatch(value):
        return "0x000000"
    return "0x" + value[1:]
