from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.models.composition import (
    Output,
    OutputFormat,
    OutputPreset,
    OutputPresetDefaults,
    resolve_output_preset,
)
from app.models.output_artifacts import StoredOutputMetadata
from app.storage.base import validate_render_id


@dataclass(frozen=True)
class OutputFormatSpec:
    output_format: OutputFormat
    storage_suffix: str
    media_type: str
    is_sequence: bool = False
    manifest_filename: str | None = None
    manifest_media_type: str | None = None
    frame_extension: str | None = None


@dataclass(frozen=True)
class OutputFormatPlan:
    output_format: OutputFormat
    storage_suffix: str
    media_type: str
    filename: str
    is_sequence: bool
    manifest_filename: str | None = None
    manifest_media_type: str | None = None
    frame_extension: str | None = None


FORMAT_SPECS: dict[OutputFormat, OutputFormatSpec] = {
    OutputFormat.MP4: OutputFormatSpec(
        output_format=OutputFormat.MP4,
        storage_suffix=".mp4",
        media_type="video/mp4",
    ),
    OutputFormat.WEBM: OutputFormatSpec(
        output_format=OutputFormat.WEBM,
        storage_suffix=".webm",
        media_type="video/webm",
    ),
    OutputFormat.GIF: OutputFormatSpec(
        output_format=OutputFormat.GIF,
        storage_suffix=".gif",
        media_type="image/gif",
    ),
    OutputFormat.PNG_SEQUENCE: OutputFormatSpec(
        output_format=OutputFormat.PNG_SEQUENCE,
        storage_suffix=".zip",
        media_type="application/zip",
        is_sequence=True,
        manifest_filename="manifest.json",
        manifest_media_type="application/json",
        frame_extension=".png",
    ),
}


def get_output_preset_defaults(preset: OutputPreset) -> OutputPresetDefaults:
    """Return normalized defaults for a named output preset."""
    return resolve_output_preset(preset)


def supported_output_formats() -> frozenset[OutputFormat]:
    """Return the formats implemented by the shared output finishing path."""
    return frozenset(FORMAT_SPECS)


def output_format_spec(output_format: OutputFormat) -> OutputFormatSpec:
    """Return immutable artifact facts for an output format."""
    return FORMAT_SPECS[output_format]


def plan_output_format(render_id: str, output: Output) -> OutputFormatPlan:
    """Return deterministic output artifact names and media types."""
    validate_render_id(render_id)
    spec = output_format_spec(output.format)
    return OutputFormatPlan(
        output_format=spec.output_format,
        storage_suffix=spec.storage_suffix,
        media_type=spec.media_type,
        filename=f"{render_id}{spec.storage_suffix}",
        is_sequence=spec.is_sequence,
        manifest_filename=spec.manifest_filename,
        manifest_media_type=spec.manifest_media_type,
        frame_extension=spec.frame_extension,
    )


def stored_metadata_for_plan(
    plan: OutputFormatPlan,
    *,
    duration_seconds: float | None = None,
    frame_count: int | None = None,
    manifest_path: str | None = None,
) -> StoredOutputMetadata:
    """Build durable metadata from an output plan and published artifacts."""
    return StoredOutputMetadata(
        format=plan.output_format,
        media_type=plan.media_type,
        filename=plan.filename,
        duration_seconds=duration_seconds,
        frame_count=frame_count,
        manifest_path=manifest_path,
    )


def sequence_frame_name(index: int) -> str:
    """Return the deterministic one-based frame filename for a PNG sequence."""
    if index < 1:
        msg = "PNG sequence frame index must be one-based"
        raise ValueError(msg)
    return f"frame_{index:06d}.png"


def build_png_sequence_manifest(
    *,
    render_id: str,
    output: Output,
    frame_names: list[str],
) -> dict[str, Any]:
    """Build a deterministic JSON-serializable PNG sequence manifest."""
    validate_render_id(render_id)
    return {
        "render_id": render_id,
        "format": OutputFormat.PNG_SEQUENCE.value,
        "width": output.width,
        "height": output.height,
        "fps": output.fps,
        "frame_count": len(frame_names),
        "frames": frame_names,
    }


def manifest_bytes(manifest: dict[str, Any]) -> bytes:
    """Serialize a manifest as stable ASCII JSON bytes."""
    return json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=True).encode(
        "ascii"
    )
