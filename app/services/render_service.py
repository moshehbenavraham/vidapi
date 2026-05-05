from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import StorageError
from app.db import render_crud
from app.db.models import Render
from app.models.composition import (
    AudioAsset,
    Clip,
    Composition,
    ImageAsset,
    TextAsset,
    VideoAsset,
)
from app.models.output_artifacts import StoredOutputMetadata
from app.models.render import RenderStatus
from app.renderers import get_renderer
from app.renderers.base import (
    CompiledRender,
    CompileError,
    RendererProtocol,
    RendererResolver,
    RenderError,
)
from app.renderers.capabilities import (
    RendererCapabilityError,
    validate_renderer_capabilities,
)
from app.renderers.poster import PosterError, generate_poster
from app.services.asset_service import AssetService
from app.services.merge import MergeError, expand_merge_variables
from app.services.output_postprocess import OutputPostprocessor
from app.storage.base import ArtifactStorageProtocol, ArtifactType

logger = structlog.get_logger(__name__)


class RenderServiceError(Exception):
    """Top-level error from the render pipeline."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "RENDER_PIPELINE_ERROR",
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.cause = cause


class RenderService:
    """Orchestrates the render pipeline.

    Exposes public stage methods that accept render_id so the async worker
    can drive status transitions externally. Also provides execute_render()
    as a convenience method for the sync render path.
    """

    def __init__(
        self,
        storage: ArtifactStorageProtocol,
        asset_service: AssetService,
        renderer: RendererProtocol,
        renderer_resolver: RendererResolver | None = None,
        output_postprocessor: OutputPostprocessor | None = None,
    ) -> None:
        self._storage = storage
        self._asset_service = asset_service
        self._renderer = renderer
        self._renderer_resolver = renderer_resolver or get_renderer
        self._output_postprocessor = output_postprocessor or OutputPostprocessor()

    def _resolve_renderer(self, renderer_name: str) -> RendererProtocol:
        if self._renderer.name == renderer_name:
            return self._renderer
        renderer = self._renderer_resolver(renderer_name)
        if renderer.name != renderer_name:
            msg = "Renderer resolver returned a mismatched renderer"
            raise RenderServiceError(msg, error_code="UNSUPPORTED_RENDERER")
        return renderer

    # ------------------------------------------------------------------
    # Convenience: full pipeline (sync path)
    # ------------------------------------------------------------------

    async def execute_render(
        self,
        composition: Composition,
        session: AsyncSession,
    ) -> Render:
        """Run the full render pipeline for a composition (sync path).

        Creates its own render record and workspace, runs all stages, and
        handles failure internally. Used by the sync API route.
        """
        render = await render_crud.create_render(session)
        render_id = render.id

        structlog.contextvars.bind_contextvars(render_id=render_id)
        await logger.ainfo("render_pipeline_start", render_id=render_id)

        workspace: Path | None = None

        try:
            workspace = await self._storage.create_workspace(render_id)

            expanded_composition = await self.stage_validate_and_expand(
                composition, render_id, workspace, session
            )

            compiled = await self.stage_resolve_and_compile(
                expanded_composition, render_id, workspace, session
            )

            await self.stage_render_and_store(
                expanded_composition, compiled, render_id, workspace, session
            )

            updated = await render_crud.update_render_status(
                session,
                render_id,
                RenderStatus.SUCCEEDED,
                stage="complete",
                progress=100,
            )
            if updated is not None:
                render = updated
            await logger.ainfo("render_pipeline_succeeded", render_id=render_id)

        except Exception as exc:
            await self._handle_failure(render_id, session, workspace, exc)
            failed = await render_crud.get_render_by_id(session, render_id)
            if failed is not None:
                render = failed

        return render

    # ------------------------------------------------------------------
    # Public stage methods (called by worker or execute_render)
    # ------------------------------------------------------------------

    async def read_artifact_uri(self, uri: str) -> bytes:
        """Read a previously persisted artifact URI through configured storage."""
        return await self._storage.read_uri(uri)

    async def publish_artifact_file(
        self,
        render_id: str,
        artifact_type: ArtifactType,
        source_path: Path,
        session: AsyncSession,
        *,
        suffix: str = "",
        media_type: str | None = None,
    ) -> str:
        """Publish a file and update the matching render artifact path."""
        artifact_uri = await self._publish_file(
            render_id,
            artifact_type,
            source_path,
            suffix=suffix,
            media_type=media_type,
        )
        await self._update_artifact_path(
            session,
            render_id,
            artifact_type,
            artifact_uri,
        )
        return artifact_uri

    async def stage_validate_and_expand(
        self,
        composition: Composition,
        render_id: str,
        workspace: Path,
        session: AsyncSession,
    ) -> Composition:
        """Stage 1: Validate composition, expand merge variables, persist input.

        Raises RenderServiceError on merge failures.
        """
        input_json = composition.model_dump_json(indent=2)
        input_path = workspace / "input.json"
        input_path.write_text(input_json, encoding="utf-8")
        input_uri = await self._publish_bytes(
            render_id,
            ArtifactType.INPUT,
            input_json.encode("utf-8"),
        )
        await render_crud.update_render_paths(
            session,
            render_id,
            input_path=input_uri,
        )

        try:
            expanded_json = expand_merge_variables(input_json, composition.merge)
        except MergeError as exc:
            raise RenderServiceError(
                str(exc), error_code="MERGE_ERROR", cause=exc
            ) from exc

        if expanded_json != input_json:
            expanded_composition = Composition.model_validate_json(expanded_json)
        else:
            expanded_composition = composition

        expanded_path = workspace / "expanded.json"
        expanded_path.write_text(
            expanded_composition.model_dump_json(indent=2), encoding="utf-8"
        )
        expanded_uri = await self._publish_file(
            render_id,
            ArtifactType.EXPANDED,
            expanded_path,
        )
        await render_crud.update_render_paths(
            session,
            render_id,
            expanded_path=expanded_uri,
        )

        await logger.ainfo("stage_validate_complete", render_id=render_id, progress=10)
        return expanded_composition

    async def stage_resolve_and_compile(
        self,
        composition: Composition,
        render_id: str,
        workspace: Path,
        session: AsyncSession,
    ) -> CompiledRender:
        """Stage 2: Resolve assets to local paths and compile renderer spec.

        Raises RenderServiceError on compile failures.
        """
        try:
            renderer_selection = validate_renderer_capabilities(composition)
        except RendererCapabilityError as exc:
            raise RenderServiceError(
                str(exc),
                error_code=exc.code,
                cause=exc,
            ) from exc

        renderer = self._resolve_renderer(renderer_selection.renderer)
        await render_crud.update_render_renderer(
            session,
            render_id,
            renderer_selection.renderer,
        )
        await logger.ainfo(
            "renderer_selected",
            render_id=render_id,
            renderer=renderer_selection.renderer,
        )

        asset_map = await self._resolve_all_assets(composition, workspace)

        try:
            compiled = await renderer.compile(
                composition,
                workspace,
                render_id=render_id,
                asset_path_resolver=asset_map,
            )
        except CompileError as exc:
            raise RenderServiceError(
                str(exc), error_code="COMPILE_ERROR", cause=exc
            ) from exc

        compiled_uri = await self._publish_file(
            render_id,
            ArtifactType.COMPILED,
            compiled.spec_path,
        )
        replay_uri = await self._publish_file(
            render_id,
            ArtifactType.REPLAY,
            compiled.replay_path,
        )

        await render_crud.update_render_paths(
            session,
            render_id,
            compiled_path=compiled_uri,
            replay_path=replay_uri,
            renderer=compiled.renderer_name,
        )

        await logger.ainfo(
            "stage_compile_complete",
            render_id=render_id,
            progress=40,
            renderer=compiled.renderer_name,
        )
        return compiled

    async def stage_render_and_store(
        self,
        composition: Composition,
        compiled: CompiledRender,
        render_id: str,
        workspace: Path,
        session: AsyncSession,
        *,
        progress_callback: Any | None = None,
        cancel_check: Any | None = None,
    ) -> None:
        """Stage 3: Execute renderer, generate poster, store artifacts.

        Raises RenderServiceError on render failures.
        """
        renderer = self._resolve_renderer(compiled.renderer_name)
        try:
            artifact = await renderer.render(
                compiled,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )
        except RenderError as exc:
            raise RenderServiceError(
                str(exc), error_code="RENDER_ERROR", cause=exc
            ) from exc

        try:
            finished = await self._output_postprocessor.finish(
                composition=composition,
                artifact=artifact,
                render_id=render_id,
                workspace=workspace,
            )
        except RenderError as exc:
            await render_crud.clear_render_output_metadata(session, render_id)
            raise RenderServiceError(
                str(exc), error_code="RENDER_ERROR", cause=exc
            ) from exc

        output_uri = await self._publish_file(
            render_id,
            ArtifactType.OUTPUT,
            finished.output_path,
            suffix=finished.suffix,
            media_type=finished.media_type,
        )

        manifest_uri: str | None = None
        if finished.manifest_path is not None:
            manifest_uri = await self._publish_file(
                render_id,
                ArtifactType.MANIFEST,
                finished.manifest_path,
                media_type="application/json",
            )

        await render_crud.update_render_output_metadata(
            session,
            render_id,
            metadata=StoredOutputMetadata(
                format=composition.output.format,
                media_type=finished.media_type,
                filename=finished.filename,
                frame_count=finished.frame_count,
                manifest_path=manifest_uri,
            ),
            output_path=output_uri,
        )

        poster_path: Path | None = None
        try:
            poster_path = await generate_poster(
                artifact.output_path,
                workspace / "poster.jpg",
                video_duration=artifact.duration_seconds,
            )
        except PosterError:
            await logger.awarning(
                "poster_generation_failed_nonfatal", render_id=render_id
            )

        if poster_path is not None:
            poster_uri = await self._publish_file(
                render_id,
                ArtifactType.POSTER,
                poster_path,
            )
            await render_crud.update_render_paths(
                session,
                render_id,
                poster_path=poster_uri,
            )

        log_path = workspace / "logs.txt"
        log_parts: list[str] = []
        if artifact.log_path.exists():
            log_parts.append(
                artifact.log_path.read_text(encoding="utf-8", errors="replace")
            )
        if (
            finished.log_path is not None
            and finished.log_path != artifact.log_path
            and finished.log_path.exists()
        ):
            log_parts.append(
                finished.log_path.read_text(encoding="utf-8", errors="replace")
            )
        if log_parts:
            log_path.write_text("\n".join(log_parts), encoding="utf-8")
            durable_log_uri = await self._publish_file(
                render_id,
                ArtifactType.LOG,
                log_path,
            )
            await render_crud.update_render_paths(
                session,
                render_id,
                log_path=durable_log_uri,
            )

        await logger.ainfo(
            "stage_render_complete",
            render_id=render_id,
            progress=95,
            renderer=compiled.renderer_name,
        )

    # ------------------------------------------------------------------
    # Asset resolution
    # ------------------------------------------------------------------

    async def _resolve_all_assets(
        self,
        composition: Composition,
        workspace: Path,
    ) -> dict[str, str]:
        """Walk all clips and resolve asset sources to local paths."""
        asset_map: dict[str, str] = {}

        for track in composition.timeline.tracks:
            for clip in track.clips:
                resolved = await self._resolve_clip_asset(clip, workspace)
                if resolved is not None:
                    src, local_path = resolved
                    asset_map[src] = local_path

        if composition.timeline.soundtrack is not None:
            src = composition.timeline.soundtrack.src
            resolved_asset = await self._asset_service.resolve_asset(
                src, workspace=workspace
            )
            asset_map[src] = str(resolved_asset.local_path)

        return asset_map

    async def _resolve_clip_asset(
        self,
        clip: Clip,
        workspace: Path,
    ) -> tuple[str, str] | None:
        """Resolve a single clip's asset, returning (src, local_path) or None."""
        asset = clip.asset

        if isinstance(asset, (VideoAsset, ImageAsset, AudioAsset)):
            resolved = await self._asset_service.resolve_asset(
                asset.src, workspace=workspace
            )
            return asset.src, str(resolved.local_path)

        if isinstance(asset, TextAsset):
            resolved = await self._asset_service.resolve_asset(
                "", text_asset=asset, workspace=workspace
            )
            return "", str(resolved.local_path)

        return None

    # ------------------------------------------------------------------
    # Failure handling
    # ------------------------------------------------------------------

    async def _handle_failure(
        self,
        render_id: str,
        session: AsyncSession,
        workspace: Path | None,
        exc: Exception,
    ) -> None:
        """Persist partial artifacts and transition to failed status."""
        error_code = "RENDER_PIPELINE_ERROR"
        error_message = str(exc)

        if isinstance(exc, RenderServiceError):
            error_code = exc.error_code
            if exc.cause is not None:
                error_message = str(exc.cause)

        renderer_name: str | None = None
        if isinstance(exc, RenderServiceError) and isinstance(
            exc.cause,
            RendererCapabilityError,
        ):
            renderer_name = exc.cause.renderer

        await logger.aerror(
            "render_pipeline_failed",
            render_id=render_id,
            renderer=renderer_name,
            error_code=error_code,
            error_message=error_message,
        )

        if renderer_name is not None:
            await render_crud.update_render_renderer(
                session,
                render_id,
                renderer_name,
            )

        if workspace is not None and workspace.exists():
            log_path = workspace / "logs.txt"
            log_path.write_text(
                f"ERROR ({error_code}): {error_message}\n", encoding="utf-8"
            )
            try:
                log_uri = await self._publish_file(
                    render_id,
                    ArtifactType.LOG,
                    log_path,
                )
                await render_crud.update_render_paths(
                    session,
                    render_id,
                    log_path=log_uri,
                )
            except Exception:
                await logger.aerror(
                    "failed_to_publish_failure_log",
                    render_id=render_id,
                )

        try:
            render = await render_crud.get_render_by_id(session, render_id)
            if render is not None and not RenderStatus(render.status).is_terminal:
                await render_crud.update_render_status(
                    session,
                    render_id,
                    RenderStatus.FAILED,
                    error_code=error_code,
                    error_message=error_message[:500],
                    stage="failed",
                )
        except Exception:
            await logger.aerror("failed_to_mark_render_as_failed", render_id=render_id)

    async def _publish_bytes(
        self,
        render_id: str,
        artifact_type: ArtifactType,
        data: bytes,
        *,
        suffix: str = "",
        media_type: str | None = None,
    ) -> str:
        try:
            return await self._storage.publish_bytes(
                render_id,
                artifact_type,
                data,
                suffix=suffix,
                media_type=media_type,
            )
        except (OSError, StorageError, ValueError) as exc:
            raise RenderServiceError(
                f"Failed to publish {artifact_type.value}",
                error_code="STORAGE_ERROR",
                cause=exc,
            ) from exc

    async def _publish_file(
        self,
        render_id: str,
        artifact_type: ArtifactType,
        source_path: Path,
        *,
        suffix: str = "",
        media_type: str | None = None,
    ) -> str:
        try:
            return await self._storage.publish_file(
                render_id,
                artifact_type,
                source_path,
                suffix=suffix,
                media_type=media_type,
            )
        except (OSError, StorageError, ValueError) as exc:
            raise RenderServiceError(
                f"Failed to publish {artifact_type.value}",
                error_code="STORAGE_ERROR",
                cause=exc,
            ) from exc

    async def _update_artifact_path(
        self,
        session: AsyncSession,
        render_id: str,
        artifact_type: ArtifactType,
        artifact_uri: str,
    ) -> None:
        kwargs: dict[str, str] = {}
        if artifact_type is ArtifactType.INPUT:
            kwargs["input_path"] = artifact_uri
        elif artifact_type is ArtifactType.EXPANDED:
            kwargs["expanded_path"] = artifact_uri
        elif artifact_type is ArtifactType.COMPILED:
            kwargs["compiled_path"] = artifact_uri
        elif artifact_type is ArtifactType.OUTPUT:
            kwargs["output_path"] = artifact_uri
        elif artifact_type is ArtifactType.POSTER:
            kwargs["poster_path"] = artifact_uri
        elif artifact_type is ArtifactType.REPLAY:
            kwargs["replay_path"] = artifact_uri
        elif artifact_type is ArtifactType.LOG:
            kwargs["log_path"] = artifact_uri

        if kwargs:
            await render_crud.update_render_paths(session, render_id, **kwargs)
