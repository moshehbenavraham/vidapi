from __future__ import annotations

from typing import TypeAlias

from app.models.composition import CoordinatePosition, NamedPosition, Offset, Position

EditlyPosition: TypeAlias = dict[str, float | str]

POSITION_MARGIN = 0.05

_NAMED_POSITION_MAP: dict[NamedPosition, tuple[float, float, str, str]] = {
    NamedPosition.CENTER: (0.5, 0.5, "center", "center"),
    NamedPosition.TOP: (0.5, POSITION_MARGIN, "center", "top"),
    NamedPosition.BOTTOM: (0.5, 1.0 - POSITION_MARGIN, "center", "bottom"),
    NamedPosition.LEFT: (POSITION_MARGIN, 0.5, "left", "center"),
    NamedPosition.RIGHT: (1.0 - POSITION_MARGIN, 0.5, "right", "center"),
    NamedPosition.TOP_LEFT: (POSITION_MARGIN, POSITION_MARGIN, "left", "top"),
    NamedPosition.TOP_RIGHT: (1.0 - POSITION_MARGIN, POSITION_MARGIN, "right", "top"),
    NamedPosition.BOTTOM_LEFT: (
        POSITION_MARGIN,
        1.0 - POSITION_MARGIN,
        "left",
        "bottom",
    ),
    NamedPosition.BOTTOM_RIGHT: (
        1.0 - POSITION_MARGIN,
        1.0 - POSITION_MARGIN,
        "right",
        "bottom",
    ),
}


def _validate_output_dimensions(output_width: int, output_height: int) -> None:
    if output_width <= 0 or output_height <= 0:
        msg = "Output dimensions must be greater than zero"
        raise ValueError(msg)


def _clamp_coordinate(value: float) -> float:
    return max(0.0, min(1.0, value))


def _apply_offset(
    x: float,
    y: float,
    offset: Offset | None,
    *,
    output_width: int,
    output_height: int,
) -> tuple[float, float]:
    if offset is None:
        return x, y

    return (
        _clamp_coordinate(x + offset.x / output_width),
        _clamp_coordinate(y + offset.y / output_height),
    )


def resolve_named_position(
    position: NamedPosition,
    offset: Offset | None = None,
    *,
    output_width: int,
    output_height: int,
) -> EditlyPosition:
    """Resolve a named VidAPI position to normalized Editly coordinates."""
    _validate_output_dimensions(output_width, output_height)
    x, y, origin_x, origin_y = _NAMED_POSITION_MAP[position]
    x, y = _apply_offset(
        x,
        y,
        offset,
        output_width=output_width,
        output_height=output_height,
    )
    return {
        "x": x,
        "y": y,
        "originX": origin_x,
        "originY": origin_y,
    }


def resolve_coordinate_position(
    position: CoordinatePosition,
    offset: Offset | None = None,
    *,
    output_width: int,
    output_height: int,
) -> EditlyPosition:
    """Resolve normalized coordinates plus optional pixel offset."""
    _validate_output_dimensions(output_width, output_height)
    x, y = _apply_offset(
        position.x,
        position.y,
        offset,
        output_width=output_width,
        output_height=output_height,
    )
    return {
        "x": x,
        "y": y,
        "originX": "left",
        "originY": "top",
    }


def resolve_position(
    position: Position,
    offset: Offset | None = None,
    *,
    output_width: int,
    output_height: int,
) -> EditlyPosition:
    """Resolve any VidAPI position type to an Editly position object."""
    if isinstance(position, NamedPosition):
        return resolve_named_position(
            position,
            offset,
            output_width=output_width,
            output_height=output_height,
        )
    if isinstance(position, CoordinatePosition):
        return resolve_coordinate_position(
            position,
            offset,
            output_width=output_width,
            output_height=output_height,
        )

    msg = f"Unsupported position type: {type(position).__name__}"
    raise ValueError(msg)
