from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import structlog
from PIL import Image, ImageDraw, ImageFont

logger = structlog.get_logger(__name__)

_FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}
_CSS_RGB_PATTERN = re.compile(
    r"(?i)^rgba?\(\s*"
    r"(?P<r>\d{1,3})\s*,\s*"
    r"(?P<g>\d{1,3})\s*,\s*"
    r"(?P<b>\d{1,3})"
    r"(?:\s*,\s*(?P<a>[0-9]*\.?[0-9]+%?))?"
    r"\s*\)$"
)

_FONT_FAMILY_MAP: dict[str, list[str]] = {
    "inter": [
        "Inter-Regular.otf",
        "Inter-Bold.otf",
    ],
    "noto sans": [
        "NotoSans-Regular.ttf",
        "NotoSans-Bold.ttf",
    ],
    "roboto": [
        "Roboto-Regular.ttf",
        "Roboto-Bold.ttf",
    ],
    "dejavu sans": [
        "DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf",
    ],
}


@dataclass(frozen=True)
class TextRenderOptions:
    text: str
    font_family: str = "Inter"
    font_size: int = 48
    color: str = "#ffffff"
    background: str | None = None
    padding: int = 0
    line_height: float = 1.2
    align: Literal["left", "center", "right"] = "center"
    max_width: int | None = None


def render_text_to_png(
    options: TextRenderOptions,
    font_search_paths: list[str] | None = None,
) -> bytes:
    """Render text to a transparent PNG image.

    Returns raw PNG bytes suitable for writing to disk or cache.
    """
    if not options.text:
        return _empty_png()

    font = _resolve_font(
        options.font_family,
        options.font_size,
        font_search_paths or [],
    )

    dummy_img = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy_img)

    max_text_width: int | None = None
    padding = options.padding
    if options.max_width is not None:
        max_width = max(1, options.max_width)
        padding = min(padding, max((max_width - 1) // 2, 0))
        max_text_width = max(1, max_width - padding * 2)

    line_spacing = max(1, round(options.font_size * options.line_height))
    lines = _wrap_lines(options.text.split("\n"), draw, font, max_text_width)

    line_bboxes: list[tuple[int, int, int, int]] = []
    line_widths: list[int] = []
    line_heights: list[int] = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_bboxes.append((int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])))
        line_widths.append(max(0, int(bbox[2] - bbox[0])))
        bbox_height = max(0, int(bbox[3] - bbox[1]))
        line_heights.append(max(line_spacing, bbox_height, 1))

    text_width = max(line_widths) if line_widths else 0
    text_height = sum(line_heights)

    img_width = text_width + padding * 2
    img_height = text_height + padding * 2

    img_width = max(img_width, 1)
    img_height = max(img_height, 1)

    if options.background:
        img = Image.new(
            "RGBA",
            (img_width, img_height),
            _parse_color(options.background),
        )
    else:
        img = Image.new("RGBA", (img_width, img_height), (0, 0, 0, 0))

    draw = ImageDraw.Draw(img)

    text_color = _parse_color(options.color)
    y = padding
    for i, (line, bbox) in enumerate(zip(lines, line_bboxes, strict=True)):
        bbox_left, bbox_top, _bbox_right, _bbox_bottom = bbox
        line_left = padding
        if options.align == "center":
            line_left = padding + (text_width - line_widths[i]) // 2
        elif options.align == "right":
            line_left = padding + text_width - line_widths[i]

        x = line_left - bbox_left
        draw_y = y - bbox_top
        draw.text((x, draw_y), line, fill=text_color, font=font)
        y += line_heights[i]

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _wrap_lines(
    raw_lines: list[str],
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int | None,
) -> list[str]:
    if max_width is None:
        return raw_lines

    wrapped: list[str] = []
    for raw_line in raw_lines:
        if not raw_line:
            wrapped.append(raw_line)
            continue

        current = ""
        for word in raw_line.split():
            candidate = word if not current else f"{current} {word}"
            if _text_width(draw, candidate, font) <= max_width:
                current = candidate
                continue

            if current:
                wrapped.append(current)
                current = ""

            if _text_width(draw, word, font) <= max_width:
                current = word
                continue

            chunks = _break_long_word(word, draw, font, max_width)
            wrapped.extend(chunks[:-1])
            current = chunks[-1] if chunks else ""

        wrapped.append(current)

    return wrapped


def _break_long_word(
    word: str,
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    chunks: list[str] = []
    current = ""
    for char in word:
        candidate = current + char
        if not current or _text_width(draw, candidate, font) <= max_width:
            current = candidate
            continue
        chunks.append(current)
        current = char
    if current:
        chunks.append(current)
    return chunks


def _text_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return max(0, int(bbox[2] - bbox[0]))


def _parse_color(value: str) -> str | tuple[int, int, int, int]:
    match = _CSS_RGB_PATTERN.fullmatch(value.strip())
    if match is None:
        return value

    red = _clamp_channel(match.group("r"))
    green = _clamp_channel(match.group("g"))
    blue = _clamp_channel(match.group("b"))
    alpha_raw = match.group("a")
    if alpha_raw is None:
        alpha = 255
    elif alpha_raw.endswith("%"):
        alpha = round(float(alpha_raw[:-1]) * 2.55)
    else:
        alpha_value = float(alpha_raw)
        alpha = round(alpha_value * 255) if alpha_value <= 1.0 else round(alpha_value)

    return red, green, blue, max(0, min(255, alpha))


def _clamp_channel(value: str) -> int:
    return max(0, min(255, int(value)))


def _empty_png() -> bytes:
    """Return a 1x1 transparent PNG for empty text input."""
    img = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _resolve_font(
    family: str,
    size: int,
    search_paths: list[str],
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    cache_key = (family.lower(), size)
    if cache_key in _FONT_CACHE:
        return _FONT_CACHE[cache_key]

    font_path = _find_font_file(family, search_paths)
    if font_path is not None:
        try:
            font = ImageFont.truetype(str(font_path), size)
            _FONT_CACHE[cache_key] = font
            return font
        except OSError:
            logger.warning(
                "font_load_failed",
                family=family,
                path=str(font_path),
            )

    logger.info("font_fallback", requested=family)
    return ImageFont.load_default()


def _find_font_file(
    family: str,
    search_paths: list[str],
) -> Path | None:
    """Search for a font file matching the requested family."""
    family_lower = family.lower()
    candidates = _FONT_FAMILY_MAP.get(family_lower, [])

    if not candidates:
        candidates = [f"{family}.ttf", f"{family}.otf"]

    for search_dir in search_paths:
        base = Path(search_dir)
        if not base.is_dir():
            continue
        for candidate in candidates:
            match = _recursive_find(base, candidate)
            if match is not None:
                return match

    return None


def _recursive_find(base: Path, filename: str) -> Path | None:
    """Find a file by name under a directory tree."""
    lower = filename.lower()
    try:
        for path in base.rglob("*"):
            if path.is_file() and path.name.lower() == lower:
                return path
    except OSError:
        pass
    return None
