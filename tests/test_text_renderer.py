from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.services.text_renderer import TextRenderOptions, render_text_to_png


class TestTextRenderer:
    """Text-to-PNG rendering via Pillow."""

    def test_renders_valid_png(self) -> None:
        options = TextRenderOptions(text="Hello World")
        data = render_text_to_png(options)
        img = Image.open(BytesIO(data))
        assert img.format == "PNG"
        assert img.width > 0
        assert img.height > 0

    def test_transparent_background(self) -> None:
        options = TextRenderOptions(text="Test", background=None)
        data = render_text_to_png(options)
        img = Image.open(BytesIO(data))
        assert img.mode == "RGBA"

    def test_colored_background(self) -> None:
        options = TextRenderOptions(text="Test", background="#ff0000")
        data = render_text_to_png(options)
        img = Image.open(BytesIO(data))
        assert img.mode == "RGBA"
        r, _g, _b, _a = img.getpixel((0, 0))
        assert r == 255

    def test_empty_text_returns_1x1_png(self) -> None:
        options = TextRenderOptions(text="")
        data = render_text_to_png(options)
        img = Image.open(BytesIO(data))
        assert img.width == 1
        assert img.height == 1

    def test_multiline_text_taller_than_single_line(self) -> None:
        single = TextRenderOptions(text="Line1")
        multi = TextRenderOptions(text="Line1\nLine2\nLine3")
        data_single = render_text_to_png(single)
        data_multi = render_text_to_png(multi)
        img_single = Image.open(BytesIO(data_single))
        img_multi = Image.open(BytesIO(data_multi))
        assert img_multi.height > img_single.height

    def test_small_line_height_does_not_clip_glyph_bounds(self) -> None:
        font_dir = Path("/usr/share/fonts/truetype/dejavu")
        if not (font_dir / "DejaVuSans.ttf").is_file():
            pytest.skip("DejaVu Sans test font is not installed")

        options = TextRenderOptions(
            text="Ågjpqy",
            font_family="DejaVu Sans",
            font_size=48,
            line_height=0.1,
        )
        data = render_text_to_png(options, font_search_paths=[str(font_dir)])
        img = Image.open(BytesIO(data))

        assert img.height >= 50

    def test_padding_increases_dimensions(self) -> None:
        no_pad = TextRenderOptions(text="Test", padding=0)
        with_pad = TextRenderOptions(text="Test", padding=20)
        data_no = render_text_to_png(no_pad)
        data_pad = render_text_to_png(with_pad)
        img_no = Image.open(BytesIO(data_no))
        img_pad = Image.open(BytesIO(data_pad))
        assert img_pad.width > img_no.width
        assert img_pad.height > img_no.height

    def test_font_fallback_still_renders(self) -> None:
        options = TextRenderOptions(
            text="Fallback Test",
            font_family="NonexistentFont12345",
        )
        data = render_text_to_png(options, font_search_paths=[])
        img = Image.open(BytesIO(data))
        assert img.format == "PNG"

    @pytest.mark.parametrize("align", ["left", "center", "right"])
    def test_alignment_variants(self, align: str) -> None:
        options = TextRenderOptions(
            text="Align test",
            align=align,  # type: ignore[arg-type]
        )
        data = render_text_to_png(options)
        img = Image.open(BytesIO(data))
        assert img.format == "PNG"
