from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.models.composition import (
    AudioAsset,
    Clip,
    ColorAsset,
    Composition,
    HtmlAsset,
    ImageAsset,
    TextAsset,
    VideoAsset,
)
from app.renderers.base import CompileError
from app.renderers.timeline import (
    EPSILON,
    compute_total_duration,
    iter_visual_clip_refs,
)

HYPERFRAMES_PLAN_VERSION = 1
HYPERFRAMES_SUPPORTED_ASSET_TYPES = frozenset(
    {"audio", "color", "html", "image", "text", "video"}
)
_SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")
_REMOTE_REFERENCE_PATTERN = re.compile(
    r"""(?is)(?:src|href)\s*=\s*["']([^"']*(?:https?:)?//[^"']+)["']"""
    r"""|url\(\s*["']?([^"')]*(?:https?:)?//[^"')]+)"""
)


@dataclass(frozen=True)
class HyperFramesIssue:
    """Single HyperFrames compile validation issue."""

    feature: str
    requested: str
    supported: tuple[str, ...] = ()

    def to_context(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "requested": self.requested,
            "supported": list(self.supported),
        }


class HyperFramesCompileError(CompileError):
    """Raised when a composition falls outside the HyperFrames MVP subset."""

    def __init__(self, issues: list[HyperFramesIssue]) -> None:
        if not issues:
            msg = "HyperFramesCompileError requires at least one issue"
            raise ValueError(msg)
        self.issues = tuple(issues)
        first = issues[0]
        message = (
            "HyperFrames renderer does not support requested feature "
            f"{first.feature}: {first.requested}"
        )
        super().__init__(message)

    def to_context(self) -> dict[str, Any]:
        first = self.issues[0]
        context: dict[str, Any] = first.to_context()
        context["renderer"] = "hyperframes"
        if len(self.issues) > 1:
            context["issues"] = [issue.to_context() for issue in self.issues[:10]]
            context["issue_count"] = len(self.issues)
        return context


@dataclass(frozen=True)
class HyperFramesInput:
    """Materialized input consumed by the generated HyperFrames project."""

    source: str
    path: str
    relative_path: str
    role: str

    def to_jsonable(self) -> dict[str, str]:
        return {
            "source": _redact_reference(self.source),
            "path": self.path,
            "relative_path": self.relative_path,
            "role": self.role,
        }


@dataclass(frozen=True)
class HyperFramesClip:
    """Single VidAPI clip represented in HyperFrames data-attribute form."""

    clip_id: str
    asset_type: str
    track_index: int
    clip_index: int
    start: float
    duration: float
    z_index: int
    media_path: str | None = None

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "id": self.clip_id,
            "asset_type": self.asset_type,
            "track_index": self.track_index,
            "clip_index": self.clip_index,
            "start": round(self.start, 6),
            "duration": round(self.duration, 6),
            "z_index": self.z_index,
            "media_path": self.media_path,
        }


@dataclass(frozen=True)
class HyperFramesProject:
    """Compiled HyperFrames project data and deterministic file paths."""

    renderer: str
    version: int
    width: int
    height: int
    fps: int
    duration: float
    workspace: Path
    index_path: Path
    output_path: Path
    inputs: tuple[HyperFramesInput, ...]
    clips: tuple[HyperFramesClip, ...]
    command: tuple[str, ...]
    index_html: str

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "renderer": self.renderer,
            "version": self.version,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "duration": round(self.duration, 6),
            "workspace": str(self.workspace),
            "entrypoint": str(self.index_path),
            "output_path": str(self.output_path),
            "inputs": [item.to_jsonable() for item in self.inputs],
            "clips": [clip.to_jsonable() for clip in self.clips],
            "command": list(self.command),
        }


def validate_hyperframes_project(
    composition: Composition,
    *,
    asset_path_resolver: dict[str, str] | None,
) -> list[HyperFramesIssue]:
    """Return bounded compile issues for the HyperFrames MVP subset."""
    issues: list[HyperFramesIssue] = []
    has_html_asset = False
    resolver = asset_path_resolver or {}

    if composition.captions is not None:
        issues.append(
            HyperFramesIssue(
                feature="captions.mode",
                requested=composition.captions.mode.value,
            )
        )

    if composition.output.poster is not None:
        issues.append(
            HyperFramesIssue(
                feature="output.poster.mode",
                requested=composition.output.poster.mode.value,
            )
        )

    for track_index, track in enumerate(composition.timeline.tracks):
        for clip_index, clip in enumerate(track.clips):
            asset = clip.asset
            clip_path = f"timeline.tracks[{track_index}].clips[{clip_index}]"
            if asset.type not in HYPERFRAMES_SUPPORTED_ASSET_TYPES:
                issues.append(
                    HyperFramesIssue(
                        feature=f"{clip_path}.asset.type",
                        requested=asset.type,
                        supported=tuple(sorted(HYPERFRAMES_SUPPORTED_ASSET_TYPES)),
                    )
                )

            if clip.transition is not None:
                issues.append(
                    HyperFramesIssue(
                        feature=f"{clip_path}.transition.name",
                        requested=clip.transition.name.value,
                    )
                )

            if clip.transform is not None:
                issues.append(
                    HyperFramesIssue(
                        feature=f"{clip_path}.transform",
                        requested="transform",
                    )
                )

            if isinstance(asset, HtmlAsset):
                has_html_asset = True
                issues.extend(
                    _validate_html_asset_refs(
                        asset,
                        resolver=resolver,
                        feature_prefix=f"{clip_path}.asset",
                    )
                )
            elif isinstance(asset, (AudioAsset, ImageAsset, VideoAsset)):
                _append_missing_resolved_asset(
                    issues,
                    resolver=resolver,
                    source=asset.src,
                    feature=f"{clip_path}.asset.src",
                )

    if composition.timeline.soundtrack is not None:
        _append_missing_resolved_asset(
            issues,
            resolver=resolver,
            source=composition.timeline.soundtrack.src,
            feature="timeline.soundtrack.src",
        )

    if not has_html_asset:
        issues.append(
            HyperFramesIssue(
                feature="timeline.html_asset",
                requested="absent",
                supported=("required",),
            )
        )

    return issues


def build_hyperframes_project(
    composition: Composition,
    workspace: Path,
    *,
    render_id: str,
    asset_path_resolver: dict[str, str] | None,
    hyperframes_bin: str,
    workers: int,
) -> HyperFramesProject:
    """Build and write a deterministic workspace-local HyperFrames project."""
    issues = validate_hyperframes_project(
        composition,
        asset_path_resolver=asset_path_resolver,
    )
    if issues:
        raise HyperFramesCompileError(issues)

    workspace.mkdir(parents=True, exist_ok=True)
    workspace = workspace.resolve()
    assets_dir = workspace / "hyperframes-assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    duration = compute_total_duration(composition.timeline.tracks)
    if duration <= EPSILON:
        raise HyperFramesCompileError(
            [
                HyperFramesIssue(
                    feature="timeline.duration",
                    requested="0",
                    supported=(">0",),
                )
            ]
        )

    materialized = _materialize_assets(
        composition,
        asset_path_resolver=asset_path_resolver or {},
        assets_dir=assets_dir,
    )
    clips, body = _build_body(composition, materialized=materialized)
    width = composition.output.width or 1920
    height = composition.output.height or 1080
    output_path = workspace / f"{render_id}.mp4"
    index_path = workspace / "index.html"
    command = (
        hyperframes_bin,
        "render",
        str(workspace),
        "--output",
        str(output_path),
        "--fps",
        str(composition.output.fps),
        "--quality",
        _quality_to_hyperframes(composition.output.quality.value),
        "--workers",
        str(workers),
        "--no-browser-gpu",
    )

    project = HyperFramesProject(
        renderer="hyperframes",
        version=HYPERFRAMES_PLAN_VERSION,
        width=width,
        height=height,
        fps=composition.output.fps,
        duration=duration,
        workspace=workspace,
        index_path=index_path,
        output_path=output_path,
        inputs=tuple(materialized.values()),
        clips=tuple(clips),
        command=command,
        index_html=_assemble_index_html(
            composition,
            body=body,
            duration=duration,
            width=width,
            height=height,
        ),
    )
    index_path.write_text(project.index_html, encoding="ascii")
    return project


def serialize_hyperframes_project(project: HyperFramesProject) -> str:
    """Return deterministic JSON for `compiled.hyperframes.json`."""
    return json.dumps(
        project.to_jsonable(),
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
    )


def _validate_html_asset_refs(
    asset: HtmlAsset,
    *,
    resolver: dict[str, str],
    feature_prefix: str,
) -> list[HyperFramesIssue]:
    issues: list[HyperFramesIssue] = []
    media_refs = set(asset.media_refs)
    for media_ref in asset.media_refs:
        _append_missing_resolved_asset(
            issues,
            resolver=resolver,
            source=media_ref,
            feature=f"{feature_prefix}.media_refs",
        )

    combined = "\n".join(
        part for part in (asset.html, asset.css or "", asset.script or "") if part
    )
    for reference in _iter_remote_references(combined):
        if reference not in media_refs:
            issues.append(
                HyperFramesIssue(
                    feature=f"{feature_prefix}.remote_reference",
                    requested=_redact_reference(reference),
                    supported=("media_refs",),
                )
            )
        elif reference not in resolver:
            issues.append(
                HyperFramesIssue(
                    feature=f"{feature_prefix}.media_refs",
                    requested=_redact_reference(reference),
                    supported=("resolved",),
                )
            )
    return issues


def _append_missing_resolved_asset(
    issues: list[HyperFramesIssue],
    *,
    resolver: dict[str, str],
    source: str,
    feature: str,
) -> None:
    local_path = resolver.get(source)
    if local_path and Path(local_path).is_file():
        return
    issues.append(
        HyperFramesIssue(
            feature=feature,
            requested=_redact_reference(source),
            supported=("resolved-local-file",),
        )
    )


def _iter_remote_references(value: str) -> list[str]:
    refs: list[str] = []
    for match in _REMOTE_REFERENCE_PATTERN.finditer(value):
        reference = match.group(1) or match.group(2)
        if reference:
            refs.append(reference.strip())
    return refs


def _materialize_assets(
    composition: Composition,
    *,
    asset_path_resolver: dict[str, str],
    assets_dir: Path,
) -> dict[str, HyperFramesInput]:
    materialized: dict[str, HyperFramesInput] = {}

    def add_source(source: str, role: str) -> None:
        if source in materialized:
            return
        local_path = Path(asset_path_resolver[source])
        digest = hashlib.sha256(f"{source}\0{local_path}".encode()).hexdigest()[:16]
        safe_name = _safe_asset_filename(local_path.name, fallback=f"asset-{digest}")
        destination = assets_dir / f"{digest}-{safe_name}"
        if local_path.resolve() != destination.resolve():
            shutil.copy2(local_path, destination)
        materialized[source] = HyperFramesInput(
            source=source,
            path=str(destination),
            relative_path=f"hyperframes-assets/{destination.name}",
            role=role,
        )

    for track in composition.timeline.tracks:
        for clip in track.clips:
            asset = clip.asset
            if isinstance(asset, HtmlAsset):
                for media_ref in asset.media_refs:
                    add_source(media_ref, "html-media")
            elif isinstance(asset, (AudioAsset, ImageAsset, VideoAsset)):
                add_source(asset.src, asset.type)

    if composition.timeline.soundtrack is not None:
        add_source(composition.timeline.soundtrack.src, "soundtrack")

    return materialized


def _build_body(
    composition: Composition,
    *,
    materialized: dict[str, HyperFramesInput],
) -> tuple[list[HyperFramesClip], str]:
    clips: list[HyperFramesClip] = []
    body_parts: list[str] = []
    width = composition.output.width or 1920
    height = composition.output.height or 1080

    for ref in iter_visual_clip_refs(composition.timeline.tracks):
        clip = ref.clip
        clip_id = f"clip-{ref.track_index}-{ref.clip_index}"
        z_index = ref.track_index
        html_fragment, media_path = _clip_to_html(
            clip,
            clip_id=clip_id,
            track_index=ref.track_index,
            z_index=z_index,
            width=width,
            height=height,
            materialized=materialized,
        )
        body_parts.append(html_fragment)
        clips.append(
            HyperFramesClip(
                clip_id=clip_id,
                asset_type=clip.asset.type,
                track_index=ref.track_index,
                clip_index=ref.clip_index,
                start=clip.start,
                duration=clip.length,
                z_index=z_index,
                media_path=media_path,
            )
        )

    for track_index, track in enumerate(composition.timeline.tracks):
        for clip_index, clip in enumerate(track.clips):
            if not isinstance(clip.asset, AudioAsset):
                continue
            clip_id = f"audio-{track_index}-{clip_index}"
            media = materialized[clip.asset.src]
            body_parts.append(
                _audio_tag(
                    clip,
                    clip_id=clip_id,
                    track_index=track_index,
                    src=media.relative_path,
                )
            )
            clips.append(
                HyperFramesClip(
                    clip_id=clip_id,
                    asset_type="audio",
                    track_index=track_index,
                    clip_index=clip_index,
                    start=clip.start,
                    duration=clip.length,
                    z_index=track_index,
                    media_path=media.relative_path,
                )
            )

    if composition.timeline.soundtrack is not None:
        media = materialized[composition.timeline.soundtrack.src]
        soundtrack_clip = Clip(asset=composition.timeline.soundtrack, length=0.001)
        body_parts.append(
            _audio_tag(
                soundtrack_clip,
                clip_id="soundtrack",
                track_index=-1,
                src=media.relative_path,
                duration=compute_total_duration(composition.timeline.tracks),
            )
        )

    return clips, "\n".join(body_parts)


def _clip_to_html(
    clip: Clip,
    *,
    clip_id: str,
    track_index: int,
    z_index: int,
    width: int,
    height: int,
    materialized: dict[str, HyperFramesInput],
) -> tuple[str, str | None]:
    asset = clip.asset
    attrs = _clip_attrs(
        clip,
        clip_id=clip_id,
        track_index=track_index,
        css_class="clip vidapi-clip",
        z_index=z_index,
        width=width,
        height=height,
    )

    if isinstance(asset, HtmlAsset):
        html_body = _replace_media_refs(asset.html, materialized=materialized)
        css = _replace_media_refs(asset.css or "", materialized=materialized)
        script = _replace_media_refs(asset.script or "", materialized=materialized)
        parts = [f"<div {attrs}>", html_body]
        if css:
            parts.append(f"<style>{css}</style>")
        if script:
            parts.append(f"<script>(() => {{\n{script}\n}})();</script>")
        parts.append("</div>")
        return "\n".join(parts), None

    if isinstance(asset, ImageAsset):
        media = materialized[asset.src]
        tag = (
            f'<img {attrs} src="{html.escape(media.relative_path, quote=True)}" '
            f'alt="" />'
        )
        return tag, media.relative_path

    if isinstance(asset, VideoAsset):
        media = materialized[asset.src]
        media_attrs = [
            attrs.replace('class="clip vidapi-clip"', 'class="vidapi-video"'),
            f'src="{html.escape(media.relative_path, quote=True)}"',
            "playsinline",
            'preload="auto"',
        ]
        if asset.trim is not None:
            media_attrs.append(f'data-media-start="{_format_seconds(asset.trim)}"')
        if asset.volume < 1.0:
            media_attrs.append(f'data-volume="{_format_seconds(asset.volume)}"')
        return f"<video {' '.join(media_attrs)}></video>", media.relative_path

    if isinstance(asset, TextAsset):
        style = (
            f"font-family:{_css_string(asset.font_family)};"
            f"font-size:{asset.font_size}px;"
            f"color:{html.escape(asset.color)};"
            f"text-align:{asset.align};"
            f"line-height:{asset.line_height};"
            f"padding:{asset.padding}px;"
        )
        if asset.background is not None:
            style += f"background:{html.escape(asset.background)};"
        text_attrs = _clip_attrs(
            clip,
            clip_id=clip_id,
            track_index=track_index,
            css_class="clip vidapi-clip",
            z_index=z_index,
            width=width,
            height=height,
            extra_style=style,
        )
        return (f"<div {text_attrs}>{html.escape(asset.text)}</div>"), None

    if isinstance(asset, ColorAsset):
        style = f"background:{html.escape(asset.color)};"
        color_attrs = _clip_attrs(
            clip,
            clip_id=clip_id,
            track_index=track_index,
            css_class="clip vidapi-clip",
            z_index=z_index,
            width=width,
            height=height,
            extra_style=style,
        )
        return f"<div {color_attrs}></div>", None

    msg = f"Unsupported HyperFrames asset type: {asset.type}"
    raise CompileError(msg)


def _clip_attrs(
    clip: Clip,
    *,
    clip_id: str,
    track_index: int,
    css_class: str,
    z_index: int,
    width: int,
    height: int,
    extra_style: str = "",
) -> str:
    styles = [
        "position:absolute",
        "inset:0",
        "box-sizing:border-box",
        "overflow:hidden",
        f"width:{width}px",
        f"height:{height}px",
        f"opacity:{clip.opacity}",
        f"z-index:{z_index}",
    ]
    if abs(clip.scale - 1.0) > EPSILON:
        styles.append(f"transform:scale({clip.scale})")
        styles.append("transform-origin:center center")
    if isinstance(clip.asset, (ImageAsset, VideoAsset)):
        styles.append(f"object-fit:{clip.fit.value}")
    if extra_style:
        styles.append(extra_style.rstrip(";"))
    return " ".join(
        [
            f'id="{html.escape(clip_id, quote=True)}"',
            f'class="{html.escape(css_class, quote=True)}"',
            f'data-start="{_format_seconds(clip.start)}"',
            f'data-duration="{_format_seconds(clip.length)}"',
            f'data-track-index="{track_index}"',
            f'style="{";".join(styles)}"',
        ]
    )


def _audio_tag(
    clip: Clip,
    *,
    clip_id: str,
    track_index: int,
    src: str,
    duration: float | None = None,
) -> str:
    asset = clip.asset
    if not isinstance(asset, AudioAsset):
        msg = "Audio tag requires an AudioAsset clip"
        raise CompileError(msg)
    duration_value = clip.length if duration is None else duration
    attrs = [
        f'id="{html.escape(clip_id, quote=True)}"',
        f'data-start="{_format_seconds(clip.start)}"',
        f'data-duration="{_format_seconds(duration_value)}"',
        f'data-track-index="{track_index}"',
        f'src="{html.escape(src, quote=True)}"',
        'preload="auto"',
    ]
    if asset.trim is not None:
        attrs.append(f'data-media-start="{_format_seconds(asset.trim)}"')
    if asset.volume < 1.0:
        attrs.append(f'data-volume="{_format_seconds(asset.volume)}"')
    return f"<audio {' '.join(attrs)}></audio>"


def _assemble_index_html(
    composition: Composition,
    *,
    body: str,
    duration: float,
    width: int,
    height: int,
) -> str:
    background = html.escape(composition.timeline.background)
    timeline_duration = _format_seconds(duration)
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width={width}, height={height}, initial-scale=1" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
html, body {{
  margin: 0;
  padding: 0;
  width: {width}px;
  height: {height}px;
  overflow: hidden;
  background: {background};
}}
#vidapi-root {{
  position: relative;
  width: {width}px;
  height: {height}px;
  overflow: hidden;
  background: {background};
}}
.vidapi-clip, .vidapi-video {{
  display: block;
}}
</style>
</head>
<body>
<div id="vidapi-root" data-composition-id="root" data-start="0"
     data-width="{width}" data-height="{height}">
{body}
</div>
<script>
window.__hf = window.__hf || {{}};
window.__timelines = window.__timelines || {{}};
const vidapiTimeline = gsap.timeline({{ paused: true }});
vidapiTimeline.to({{}}, {{ duration: {timeline_duration} }});
window.__timelines.root = vidapiTimeline;
window.__hf.duration = {timeline_duration};
window.__hf.seek = function(time) {{
  vidapiTimeline.seek(time);
}};
</script>
</body>
</html>
"""


def _replace_media_refs(
    value: str,
    *,
    materialized: dict[str, HyperFramesInput],
) -> str:
    result = value
    for source, item in sorted(materialized.items(), key=lambda pair: pair[0]):
        result = result.replace(source, item.relative_path)
    return result


def _safe_asset_filename(name: str, *, fallback: str) -> str:
    safe_name = _SAFE_FILENAME_PATTERN.sub("-", name).strip(".-")
    if not safe_name:
        safe_name = fallback
    return safe_name[:120]


def _format_seconds(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def _quality_to_hyperframes(value: str) -> str:
    return {
        "low": "draft",
        "medium": "standard",
        "high": "high",
    }.get(value, "standard")


def _css_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _redact_reference(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"}:
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    if value.startswith("//"):
        parsed_protocol_relative = urlsplit(f"https:{value}")
        return f"//{parsed_protocol_relative.netloc}{parsed_protocol_relative.path}"
    return value
