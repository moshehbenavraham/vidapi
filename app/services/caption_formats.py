from __future__ import annotations

import html
from dataclasses import dataclass

from app.models.composition import (
    CaptionFormat,
    CaptionMode,
    Captions,
    CaptionStyle,
)
from app.storage.base import validate_render_id

SRT_MEDIA_TYPE = "application/x-subrip"
WEBVTT_MEDIA_TYPE = "text/vtt; charset=utf-8"
ASS_MEDIA_TYPE = "text/x-ssa; charset=utf-8"


@dataclass(frozen=True)
class CaptionSidecarSpec:
    caption_format: CaptionFormat
    suffix: str
    media_type: str
    filename: str


@dataclass(frozen=True)
class CaptionCuePlan:
    index: int
    start: float
    end: float
    text: str


def caption_sidecar_spec(render_id: str, captions: Captions) -> CaptionSidecarSpec:
    """Return deterministic sidecar filename and media type facts."""
    validate_render_id(render_id)
    if captions.format is CaptionFormat.SRT:
        suffix = ".srt"
        media_type = SRT_MEDIA_TYPE
    else:
        suffix = ".vtt"
        media_type = WEBVTT_MEDIA_TYPE
    return CaptionSidecarSpec(
        caption_format=captions.format,
        suffix=suffix,
        media_type=media_type,
        filename=f"{render_id}-captions{suffix}",
    )


def plan_caption_cues(captions: Captions) -> tuple[CaptionCuePlan, ...]:
    """Return cues in deterministic playback order."""
    ordered = sorted(
        captions.cues,
        key=lambda cue: (cue.start, cue.end or cue.start, cue.text),
    )
    return tuple(
        CaptionCuePlan(
            index=index,
            start=cue.start,
            end=cue.end or cue.start,
            text=cue.text,
        )
        for index, cue in enumerate(ordered, start=1)
    )


def caption_sidecar_bytes(captions: Captions) -> bytes:
    """Serialize a public caption sidecar as UTF-8 bytes."""
    if captions.mode is not CaptionMode.SIDECAR:
        msg = "Only sidecar caption mode can be serialized as a public sidecar"
        raise ValueError(msg)
    if captions.format is CaptionFormat.SRT:
        text = srt_text(captions)
    else:
        text = webvtt_text(captions)
    return text.encode("utf-8")


def srt_text(captions: Captions) -> str:
    """Serialize cues to deterministic SubRip text."""
    blocks: list[str] = []
    for cue in plan_caption_cues(captions):
        cue_lines = "\n".join(_escape_plain_caption_line(line) for line in _lines(cue))
        blocks.append(
            "\n".join(
                [
                    str(cue.index),
                    (
                        f"{_format_srt_timestamp(cue.start)} --> "
                        f"{_format_srt_timestamp(cue.end)}"
                    ),
                    cue_lines,
                ]
            )
        )
    return "\n\n".join(blocks) + "\n"


def webvtt_text(captions: Captions) -> str:
    """Serialize cues to deterministic WebVTT text."""
    blocks = ["WEBVTT", ""]
    for cue in plan_caption_cues(captions):
        cue_lines = "\n".join(_escape_webvtt_line(line) for line in _lines(cue))
        blocks.append(
            "\n".join(
                [
                    (
                        f"{_format_webvtt_timestamp(cue.start)} --> "
                        f"{_format_webvtt_timestamp(cue.end)}"
                    ),
                    cue_lines,
                ]
            )
        )
        blocks.append("")
    return "\n".join(blocks)


def ass_text(captions: Captions) -> str:
    """Serialize cues to deterministic ASS subtitles for FFmpeg burn-in."""
    style = captions.style
    events = [
        (
            "Dialogue: 0,"
            f"{_format_ass_timestamp(cue.start)},"
            f"{_format_ass_timestamp(cue.end)},"
            "Default,,0,0,0,,"
            f"{_escape_ass_text(cue.text)}"
        )
        for cue in plan_caption_cues(captions)
    ]
    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "WrapStyle: 0",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            (
                "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
                "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,"
                "ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
                "Alignment,MarginL,MarginR,MarginV,Encoding"
            ),
            _ass_style_line(style),
            "",
            "[Events]",
            "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
            *events,
            "",
        ]
    )


def ass_bytes(captions: Captions) -> bytes:
    """Serialize burn-in captions as UTF-8 ASS bytes."""
    return ass_text(captions).encode("utf-8")


def _lines(cue: CaptionCuePlan) -> list[str]:
    normalized = cue.text.replace("\r\n", "\n").replace("\r", "\n")
    return [line if line.strip() else " " for line in normalized.split("\n")]


def _escape_plain_caption_line(line: str) -> str:
    return html.escape(line, quote=False).replace("-->", "-- >")


def _escape_webvtt_line(line: str) -> str:
    return _escape_plain_caption_line(line).replace("&lrm;", "")


def _escape_ass_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    escaped = (
        normalized.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\n", r"\N")
    )
    return escaped


def _format_srt_timestamp(seconds: float) -> str:
    return _format_timestamp(seconds, separator=",", precision=3)


def _format_webvtt_timestamp(seconds: float) -> str:
    return _format_timestamp(seconds, separator=".", precision=3)


def _format_ass_timestamp(seconds: float) -> str:
    total_centiseconds = max(0, round(seconds * 100))
    centiseconds = total_centiseconds % 100
    total_seconds = total_centiseconds // 100
    secs = total_seconds % 60
    minutes = (total_seconds // 60) % 60
    hours = total_seconds // 3600
    return f"{hours:d}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def _format_timestamp(seconds: float, *, separator: str, precision: int) -> str:
    scale = 10**precision
    total_units = max(0, round(seconds * scale))
    units = total_units % scale
    total_seconds = total_units // scale
    secs = total_seconds % 60
    minutes = (total_seconds // 60) % 60
    hours = total_seconds // 3600
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{units:0{precision}d}"


def _ass_style_line(style: CaptionStyle) -> str:
    border_style = 3 if style.background_color else 1
    back_color = _ass_color(style.background_color or "#000000", opacity=0.6)
    return (
        "Style: Default,"
        f"{style.font_family},"
        f"{style.font_size},"
        f"{_ass_color(style.color, opacity=style.opacity)},"
        f"{_ass_color(style.color, opacity=style.opacity)},"
        f"{_ass_color(style.outline_color)},"
        f"{back_color},"
        "0,0,0,0,"
        "100,100,0,0,"
        f"{border_style},"
        "2,0,"
        f"{_ass_alignment(style)},"
        "24,24,"
        f"{style.margin_v},"
        "1"
    )


def _ass_color(hex_color: str, *, opacity: float = 1.0) -> str:
    red = int(hex_color[1:3], 16)
    green = int(hex_color[3:5], 16)
    blue = int(hex_color[5:7], 16)
    alpha = round((1.0 - max(0.0, min(1.0, opacity))) * 255)
    return f"&H{alpha:02X}{blue:02X}{green:02X}{red:02X}"


def _ass_alignment(style: CaptionStyle) -> int:
    horizontal = {"left": 0, "center": 1, "right": 2}[style.align]
    vertical = {"bottom": 1, "middle": 4, "top": 7}[style.position.value]
    return vertical + horizontal
