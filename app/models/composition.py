from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, NamedTuple

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class FitMode(StrEnum):
    COVER = "cover"
    CONTAIN = "contain"
    STRETCH = "stretch"
    NONE = "none"


class OutputFormat(StrEnum):
    MP4 = "mp4"
    GIF = "gif"
    WEBM = "webm"
    PNG_SEQUENCE = "png-sequence"


class OutputPreset(StrEnum):
    TIKTOK = "tiktok"
    REELS = "reels"
    SHORTS = "shorts"
    YOUTUBE = "youtube"
    SQUARE_AD = "square-ad"
    PREVIEW_LOW = "preview-low"


class ResolutionPreset(StrEnum):
    R360 = "360"
    R480 = "480"
    R720 = "720"
    R1080 = "1080"
    R4K = "4k"


class AspectRatio(StrEnum):
    AR_16_9 = "16:9"
    AR_9_16 = "9:16"
    AR_1_1 = "1:1"
    AR_4_5 = "4:5"


class QualityPreset(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class NamedPosition(StrEnum):
    CENTER = "center"
    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"
    TOP_LEFT = "top-left"
    TOP_RIGHT = "top-right"
    BOTTOM_LEFT = "bottom-left"
    BOTTOM_RIGHT = "bottom-right"


class AudioEffect(StrEnum):
    FADE_IN = "fadeIn"
    FADE_OUT = "fadeOut"
    FADE_IN_FADE_OUT = "fadeInFadeOut"


class TransitionType(StrEnum):
    FADE_IN = "fade_in"
    FADE_OUT = "fade_out"
    CROSSFADE = "crossfade"


class TransitionPlacement(StrEnum):
    IN = "in"
    OUT = "out"
    BETWEEN = "between"


TRANSITION_PLACEMENTS: dict[TransitionType, TransitionPlacement] = {
    TransitionType.FADE_IN: TransitionPlacement.IN,
    TransitionType.FADE_OUT: TransitionPlacement.OUT,
    TransitionType.CROSSFADE: TransitionPlacement.BETWEEN,
}


# ---------------------------------------------------------------------------
# Resolution preset lookup
# ---------------------------------------------------------------------------

RESOLUTION_TABLE: dict[tuple[ResolutionPreset, AspectRatio], tuple[int, int]] = {
    (ResolutionPreset.R360, AspectRatio.AR_16_9): (640, 360),
    (ResolutionPreset.R360, AspectRatio.AR_9_16): (360, 640),
    (ResolutionPreset.R360, AspectRatio.AR_1_1): (360, 360),
    (ResolutionPreset.R360, AspectRatio.AR_4_5): (360, 450),
    (ResolutionPreset.R480, AspectRatio.AR_16_9): (854, 480),
    (ResolutionPreset.R480, AspectRatio.AR_9_16): (480, 854),
    (ResolutionPreset.R480, AspectRatio.AR_1_1): (480, 480),
    (ResolutionPreset.R480, AspectRatio.AR_4_5): (480, 600),
    (ResolutionPreset.R720, AspectRatio.AR_16_9): (1280, 720),
    (ResolutionPreset.R720, AspectRatio.AR_9_16): (720, 1280),
    (ResolutionPreset.R720, AspectRatio.AR_1_1): (720, 720),
    (ResolutionPreset.R720, AspectRatio.AR_4_5): (720, 900),
    (ResolutionPreset.R1080, AspectRatio.AR_16_9): (1920, 1080),
    (ResolutionPreset.R1080, AspectRatio.AR_9_16): (1080, 1920),
    (ResolutionPreset.R1080, AspectRatio.AR_1_1): (1080, 1080),
    (ResolutionPreset.R1080, AspectRatio.AR_4_5): (1080, 1350),
    (ResolutionPreset.R4K, AspectRatio.AR_16_9): (3840, 2160),
    (ResolutionPreset.R4K, AspectRatio.AR_9_16): (2160, 3840),
    (ResolutionPreset.R4K, AspectRatio.AR_1_1): (2160, 2160),
    (ResolutionPreset.R4K, AspectRatio.AR_4_5): (2160, 2700),
}


# ---------------------------------------------------------------------------
# Quality preset lookup
# ---------------------------------------------------------------------------

QUALITY_TABLE: dict[QualityPreset, tuple[int, str]] = {
    QualityPreset.LOW: (28, "veryfast"),
    QualityPreset.MEDIUM: (23, "medium"),
    QualityPreset.HIGH: (18, "slow"),
}


class OutputPresetDefaults(NamedTuple):
    width: int
    height: int
    aspect_ratio: AspectRatio
    fps: int
    quality: QualityPreset


OUTPUT_PRESET_TABLE: dict[OutputPreset, OutputPresetDefaults] = {
    OutputPreset.TIKTOK: OutputPresetDefaults(
        width=1080,
        height=1920,
        aspect_ratio=AspectRatio.AR_9_16,
        fps=30,
        quality=QualityPreset.HIGH,
    ),
    OutputPreset.REELS: OutputPresetDefaults(
        width=1080,
        height=1920,
        aspect_ratio=AspectRatio.AR_9_16,
        fps=30,
        quality=QualityPreset.HIGH,
    ),
    OutputPreset.SHORTS: OutputPresetDefaults(
        width=1080,
        height=1920,
        aspect_ratio=AspectRatio.AR_9_16,
        fps=30,
        quality=QualityPreset.HIGH,
    ),
    OutputPreset.YOUTUBE: OutputPresetDefaults(
        width=1920,
        height=1080,
        aspect_ratio=AspectRatio.AR_16_9,
        fps=30,
        quality=QualityPreset.HIGH,
    ),
    OutputPreset.SQUARE_AD: OutputPresetDefaults(
        width=1080,
        height=1080,
        aspect_ratio=AspectRatio.AR_1_1,
        fps=30,
        quality=QualityPreset.MEDIUM,
    ),
    OutputPreset.PREVIEW_LOW: OutputPresetDefaults(
        width=640,
        height=360,
        aspect_ratio=AspectRatio.AR_16_9,
        fps=24,
        quality=QualityPreset.LOW,
    ),
}


def resolve_quality(quality: QualityPreset) -> tuple[int, str]:
    """Return (crf, ffmpeg_preset) for a quality preset."""
    return QUALITY_TABLE[quality]


def resolve_output_preset(preset: OutputPreset) -> OutputPresetDefaults:
    """Return output defaults for a named publishing preset."""
    return OUTPUT_PRESET_TABLE[preset]


def resolve_resolution(
    resolution: ResolutionPreset,
    aspect_ratio: AspectRatio,
) -> tuple[int, int]:
    """Return (width, height) for a resolution + aspect ratio pair."""
    key = (resolution, aspect_ratio)
    if key not in RESOLUTION_TABLE:
        msg = f"No resolution mapping for {resolution.value} at {aspect_ratio.value}"
        raise ValueError(msg)
    return RESOLUTION_TABLE[key]


# ---------------------------------------------------------------------------
# Value Objects (frozen / immutable)
# ---------------------------------------------------------------------------


class CoordinatePosition(BaseModel):
    """Normalized (0.0-1.0) coordinate pair."""

    model_config = ConfigDict(frozen=True)

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


Position = NamedPosition | CoordinatePosition


class Offset(BaseModel):
    model_config = ConfigDict(frozen=True)

    x: float = 0.0
    y: float = 0.0


class Transition(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: TransitionType = TransitionType.FADE_IN
    duration: float = Field(default=1.0, gt=0.0)
    placement: TransitionPlacement | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _parse_transition_type(cls, v: object) -> object:
        if isinstance(v, str):
            aliases = {
                "fadeIn": TransitionType.FADE_IN,
                "fade-in": TransitionType.FADE_IN,
                "fadeOut": TransitionType.FADE_OUT,
                "fade-out": TransitionType.FADE_OUT,
            }
            return aliases.get(v, v)
        return v

    @model_validator(mode="after")
    def _validate_placement(self) -> Transition:
        expected = TRANSITION_PLACEMENTS[self.name]
        if self.placement is None:
            object.__setattr__(self, "placement", expected)
            return self
        if self.placement != expected:
            msg = f"Transition {self.name.value} must use placement {expected.value}"
            raise ValueError(msg)
        return self


class Transform(BaseModel):
    """Placeholder for rotation/skew/keyframe support."""

    model_config = ConfigDict(frozen=True)

    rotation: float = 0.0
    skew_x: float = 0.0
    skew_y: float = 0.0


# ---------------------------------------------------------------------------
# Asset types (discriminated union on `type`)
# ---------------------------------------------------------------------------


class VideoAsset(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["video"]
    src: str
    trim: float | None = None
    volume: float = Field(default=1.0, ge=0.0, le=1.0)


class ImageAsset(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["image"]
    src: str


class TextAsset(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["text"]
    text: str
    font_family: str = "Inter"
    font_size: int = Field(default=48, gt=0)
    color: str = "#ffffff"
    background: str | None = None
    padding: int = Field(default=0, ge=0)
    line_height: float = Field(default=1.2, gt=0.0)
    align: Literal["left", "center", "right"] = "center"


class AudioAsset(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["audio"]
    src: str
    trim: float | None = None
    volume: float = Field(default=1.0, ge=0.0, le=1.0)
    effect: AudioEffect | None = None


class ColorAsset(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["color"]
    color: str = "#000000"


Asset = Annotated[
    VideoAsset | ImageAsset | TextAsset | AudioAsset | ColorAsset,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Clip
# ---------------------------------------------------------------------------


class Clip(BaseModel):
    model_config = ConfigDict(frozen=True)

    asset: Asset
    start: float = Field(default=0.0, ge=0.0)
    length: float = Field(gt=0.0)
    fit: FitMode = FitMode.COVER
    position: Position = NamedPosition.CENTER
    offset: Offset | None = None
    scale: float = Field(default=1.0, gt=0.0)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    transition: Transition | None = None
    transform: Transform | None = None

    @field_validator("position", mode="before")
    @classmethod
    def _parse_position(cls, v: object) -> object:
        if isinstance(v, str):
            return NamedPosition(v)
        return v

    @model_validator(mode="after")
    def _validate_transition_duration(self) -> Clip:
        if self.transition is None:
            return self
        if self.transition.duration > self.length:
            msg = "Transition duration must be less than or equal to clip length"
            raise ValueError(msg)
        return self


# ---------------------------------------------------------------------------
# Track / Timeline
# ---------------------------------------------------------------------------


class Track(BaseModel):
    clips: list[Clip] = Field(min_length=1)


class Timeline(BaseModel):
    background: str = "#000000"
    tracks: list[Track] = Field(min_length=1)
    soundtrack: AudioAsset | None = None


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


class Output(BaseModel):
    format: OutputFormat = OutputFormat.MP4
    preset: OutputPreset | None = None
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    resolution: ResolutionPreset | None = None
    aspect_ratio: AspectRatio | None = None
    fps: int = Field(default=30, gt=0, le=60)
    quality: QualityPreset = QualityPreset.MEDIUM

    @model_validator(mode="after")
    def _resolve_dimensions(self) -> Output:
        self._apply_preset_defaults()
        if self.width is not None and self.height is not None:
            return self
        if self.resolution is not None and self.aspect_ratio is not None:
            w, h = resolve_resolution(self.resolution, self.aspect_ratio)
            if self.width is None:
                object.__setattr__(self, "width", w)
            if self.height is None:
                object.__setattr__(self, "height", h)
            return self
        if self.resolution is not None and self.aspect_ratio is None:
            ar = AspectRatio.AR_16_9
            w, h = resolve_resolution(self.resolution, ar)
            if self.width is None:
                object.__setattr__(self, "width", w)
            if self.height is None:
                object.__setattr__(self, "height", h)
            return self
        if self.preset is not None:
            preset_defaults = resolve_output_preset(self.preset)
            if self.width is None:
                object.__setattr__(self, "width", preset_defaults.width)
            if self.height is None:
                object.__setattr__(self, "height", preset_defaults.height)
            return self
        if self.width is None and self.height is None:
            object.__setattr__(self, "width", 1920)
            object.__setattr__(self, "height", 1080)
        return self

    def _apply_preset_defaults(self) -> None:
        if self.preset is None:
            return

        preset_defaults = resolve_output_preset(self.preset)
        fields_set = self.model_fields_set
        if self.aspect_ratio is None:
            object.__setattr__(self, "aspect_ratio", preset_defaults.aspect_ratio)
        if "fps" not in fields_set:
            object.__setattr__(self, "fps", preset_defaults.fps)
        if "quality" not in fields_set:
            object.__setattr__(self, "quality", preset_defaults.quality)

    @property
    def crf(self) -> int:
        return resolve_quality(self.quality)[0]

    @property
    def ffmpeg_preset(self) -> str:
        return resolve_quality(self.quality)[1]


# ---------------------------------------------------------------------------
# Renderer selector
# ---------------------------------------------------------------------------

RendererChoice = str


# ---------------------------------------------------------------------------
# Composition (top-level)
# ---------------------------------------------------------------------------


class Composition(BaseModel):
    timeline: Timeline
    output: Output = Field(default_factory=Output)
    merge: dict[str, str | int | float | bool] | None = None
    callback: HttpUrl | None = None
    renderer: RendererChoice | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _validate_timeline_has_content(self) -> Composition:
        for track in self.timeline.tracks:
            if track.clips:
                return self
        msg = "Timeline must contain at least one track with at least one clip"
        raise ValueError(msg)
