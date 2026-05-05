from __future__ import annotations

import pytest

from app.models.composition import CoordinatePosition, NamedPosition, Offset
from app.renderers.position import (
    resolve_coordinate_position,
    resolve_named_position,
    resolve_position,
)


@pytest.mark.parametrize(
    ("position", "expected"),
    [
        (
            NamedPosition.CENTER,
            {"x": 0.5, "y": 0.5, "originX": "center", "originY": "center"},
        ),
        (
            NamedPosition.TOP,
            {"x": 0.5, "y": 0.05, "originX": "center", "originY": "top"},
        ),
        (
            NamedPosition.BOTTOM,
            {"x": 0.5, "y": 0.95, "originX": "center", "originY": "bottom"},
        ),
        (
            NamedPosition.LEFT,
            {"x": 0.05, "y": 0.5, "originX": "left", "originY": "center"},
        ),
        (
            NamedPosition.RIGHT,
            {"x": 0.95, "y": 0.5, "originX": "right", "originY": "center"},
        ),
        (
            NamedPosition.TOP_LEFT,
            {"x": 0.05, "y": 0.05, "originX": "left", "originY": "top"},
        ),
        (
            NamedPosition.TOP_RIGHT,
            {"x": 0.95, "y": 0.05, "originX": "right", "originY": "top"},
        ),
        (
            NamedPosition.BOTTOM_LEFT,
            {"x": 0.05, "y": 0.95, "originX": "left", "originY": "bottom"},
        ),
        (
            NamedPosition.BOTTOM_RIGHT,
            {"x": 0.95, "y": 0.95, "originX": "right", "originY": "bottom"},
        ),
    ],
)
@pytest.mark.parametrize(
    ("output_width", "output_height"),
    [(1920, 1080), (1080, 1920)],
)
def test_resolve_named_position_all_values(
    position: NamedPosition,
    expected: dict[str, float | str],
    output_width: int,
    output_height: int,
) -> None:
    assert (
        resolve_named_position(
            position,
            output_width=output_width,
            output_height=output_height,
        )
        == expected
    )


def test_resolve_named_position_applies_pixel_offset() -> None:
    result = resolve_named_position(
        NamedPosition.CENTER,
        Offset(x=192.0, y=-108.0),
        output_width=1920,
        output_height=1080,
    )

    assert result == {
        "x": 0.6,
        "y": 0.4,
        "originX": "center",
        "originY": "center",
    }


def test_resolve_coordinate_position_without_offset() -> None:
    result = resolve_coordinate_position(
        CoordinatePosition(x=0.25, y=0.75),
        output_width=1920,
        output_height=1080,
    )

    assert result == {
        "x": 0.25,
        "y": 0.75,
        "originX": "left",
        "originY": "top",
    }


def test_resolve_coordinate_position_applies_pixel_offset() -> None:
    result = resolve_coordinate_position(
        CoordinatePosition(x=0.25, y=0.75),
        Offset(x=192.0, y=-108.0),
        output_width=1920,
        output_height=1080,
    )

    assert result == {
        "x": 0.35,
        "y": 0.65,
        "originX": "left",
        "originY": "top",
    }


@pytest.mark.parametrize(
    ("position", "offset", "expected_x", "expected_y"),
    [
        (CoordinatePosition(x=0.0, y=0.0), Offset(x=-1.0, y=-1.0), 0.0, 0.0),
        (CoordinatePosition(x=1.0, y=1.0), Offset(x=1.0, y=1.0), 1.0, 1.0),
    ],
)
def test_resolve_coordinate_position_clamps_boundaries(
    position: CoordinatePosition,
    offset: Offset,
    expected_x: float,
    expected_y: float,
) -> None:
    result = resolve_coordinate_position(
        position,
        offset,
        output_width=1920,
        output_height=1080,
    )

    assert result["x"] == expected_x
    assert result["y"] == expected_y


def test_resolve_position_dispatches_named_position() -> None:
    result = resolve_position(
        NamedPosition.BOTTOM_RIGHT,
        output_width=1920,
        output_height=1080,
    )

    assert result["originX"] == "right"
    assert result["originY"] == "bottom"


def test_resolve_position_dispatches_coordinate_position() -> None:
    result = resolve_position(
        CoordinatePosition(x=1.0, y=0.0),
        output_width=1920,
        output_height=1080,
    )

    assert result == {
        "x": 1.0,
        "y": 0.0,
        "originX": "left",
        "originY": "top",
    }


def test_invalid_output_dimensions_raise() -> None:
    with pytest.raises(ValueError, match="Output dimensions"):
        resolve_position(
            NamedPosition.CENTER,
            output_width=0,
            output_height=1080,
        )
