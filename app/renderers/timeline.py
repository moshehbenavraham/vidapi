from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app.models.composition import AudioAsset, Clip, TextAsset, Track

EPSILON = 1e-6


@dataclass(frozen=True)
class VisualClipRef:
    """Renderer-neutral reference to a non-audio timeline clip."""

    clip: Clip
    track_index: int
    clip_index: int

    @property
    def start(self) -> float:
        return self.clip.start

    @property
    def end(self) -> float:
        return self.clip.start + self.clip.length


def compute_total_duration(tracks: list[Track]) -> float:
    """Compute total visual timeline duration from non-audio clips."""
    max_end = 0.0
    for ref in iter_visual_clip_refs(tracks):
        if ref.end > max_end:
            max_end = ref.end
    return max_end


def iter_visual_clip_refs(tracks: list[Track]) -> list[VisualClipRef]:
    """Return visual clips in deterministic z-order and timeline order."""
    refs: list[VisualClipRef] = []
    for track_index, track in enumerate(tracks):
        for clip_index, clip in enumerate(track.clips):
            if isinstance(clip.asset, AudioAsset):
                continue
            refs.append(
                VisualClipRef(
                    clip=clip,
                    track_index=track_index,
                    clip_index=clip_index,
                )
            )
    return sorted(
        refs,
        key=lambda ref: (
            ref.track_index,
            round(ref.clip.start, 6),
            ref.clip_index,
        ),
    )


def asset_resolver_key(clip: Clip) -> str | None:
    """Return the deterministic key used for resolved local asset paths."""
    asset = clip.asset
    if isinstance(asset, AudioAsset):
        return asset.src
    if hasattr(asset, "src"):
        return str(asset.src)
    if isinstance(asset, TextAsset):
        payload = json.dumps(
            asset.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        digest = hashlib.sha256(payload.encode("ascii")).hexdigest()
        return f"text:{digest}"
    return None
