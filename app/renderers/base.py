from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from app.models.composition import Composition

if TYPE_CHECKING:
    from app.services.audio_mixer import AudioMixPlan


@dataclass(frozen=True)
class CompiledRender:
    """Immutable result of the compile step."""

    spec_path: Path
    replay_path: Path
    workspace: Path
    renderer_name: str
    spec_json: str
    audio_mix_plan: AudioMixPlan | None = field(default=None)


@dataclass(frozen=True)
class RenderArtifact:
    """Immutable result of the render step."""

    output_path: Path
    poster_path: Path | None
    log_path: Path
    duration_seconds: float
    exit_code: int


class CompileError(Exception):
    """Raised when composition compilation fails."""


class RenderError(Exception):
    """Raised when rendering subprocess fails."""

    def __init__(self, message: str, *, exit_code: int | None = None) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@runtime_checkable
class RendererProtocol(Protocol):
    """Contract for all renderer backends."""

    @property
    def name(self) -> str: ...

    async def compile(
        self,
        composition: Composition,
        workspace: Path,
        *,
        render_id: str,
    ) -> CompiledRender:
        """Transform a VidAPI Composition into a renderer-specific spec.

        Writes the compiled spec and replay metadata to the workspace.
        """
        ...

    async def render(
        self,
        compiled: CompiledRender,
        *,
        timeout_seconds: int = 600,
    ) -> RenderArtifact:
        """Execute the compiled spec and produce output artifacts.

        Invokes the renderer subprocess, captures logs, and verifies output.
        """
        ...
