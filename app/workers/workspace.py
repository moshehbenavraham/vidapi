from __future__ import annotations

import asyncio
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

PRESERVE_ON_FAILURE = {
    "input.json",
    "expanded.json",
    "logs.txt",
    "compiled.editly.json",
}


@dataclass(frozen=True)
class OrphanCleanupResult:
    scanned: int = 0
    removed: int = 0
    skipped_active: int = 0
    skipped_young: int = 0
    skipped_unsafe: int = 0
    bytes_removed: int = 0


@dataclass(frozen=True)
class _WorkspaceCandidate:
    path: Path
    mtime: float
    bytes_used: int


class WorkspaceManager:
    """Manages per-render workspace lifecycle with guaranteed cleanup.

    Each render gets an isolated directory under the configured workspace root.
    After artifacts are persisted, temp files are removed. On failure, diagnostic
    files (input, logs, compiled spec) are preserved for debugging.
    """

    def __init__(self, workspace_root: Path) -> None:
        self._root = workspace_root.resolve()

    async def create(self, render_id: str) -> Path:
        """Create an isolated workspace directory for a render job.

        If the directory already exists (e.g. from a previous attempt),
        it is removed and recreated to ensure a clean state.
        """
        ws = self._root / render_id
        if ws.exists():
            await asyncio.to_thread(shutil.rmtree, ws, ignore_errors=True)
        await asyncio.to_thread(ws.mkdir, parents=True, exist_ok=True)
        await logger.ainfo("workspace_created", render_id=render_id, path=str(ws))
        return ws

    async def cleanup_success(self, workspace: Path) -> None:
        """Remove the entire workspace after successful artifact persistence."""
        settings = get_settings()
        if not settings.workspace_cleanup_enabled:
            await logger.ainfo(
                "workspace_cleanup_skipped_disabled", path=str(workspace)
            )
            return

        try:
            await asyncio.to_thread(shutil.rmtree, workspace, ignore_errors=True)
            await logger.ainfo("workspace_cleanup_success", path=str(workspace))
        except Exception as exc:
            await logger.awarning(
                "workspace_cleanup_error",
                path=str(workspace),
                error=str(exc),
            )

    async def cleanup_failure(self, workspace: Path) -> None:
        """Partial cleanup on failure: remove temp files, keep diagnostics."""
        settings = get_settings()
        if not settings.workspace_cleanup_enabled:
            await logger.ainfo(
                "workspace_cleanup_skipped_disabled", path=str(workspace)
            )
            return

        if not settings.workspace_cleanup_keep_on_failure:
            await self.cleanup_success(workspace)
            return

        if not workspace.exists():
            return

        try:
            entries = await asyncio.to_thread(list, workspace.iterdir())
            for entry in entries:
                if entry.name not in PRESERVE_ON_FAILURE:
                    if entry.is_dir():
                        await asyncio.to_thread(
                            shutil.rmtree, entry, ignore_errors=True
                        )
                    else:
                        await asyncio.to_thread(entry.unlink, missing_ok=True)
            await logger.ainfo(
                "workspace_cleanup_failure_partial",
                path=str(workspace),
                preserved=[e.name for e in workspace.iterdir() if e.exists()],
            )
        except Exception as exc:
            await logger.awarning(
                "workspace_cleanup_error",
                path=str(workspace),
                error=str(exc),
            )

    async def cleanup_orphans(
        self,
        active_render_ids: set[str],
        *,
        now: float | None = None,
    ) -> OrphanCleanupResult:
        """Remove stale inactive workspaces under the configured root."""
        settings = get_settings()
        if not settings.workspace_cleanup_enabled:
            await logger.ainfo("workspace_orphan_cleanup_skipped_disabled")
            return OrphanCleanupResult()

        if now is None:
            now = time.time()

        await asyncio.to_thread(self._root.mkdir, parents=True, exist_ok=True)
        root = self._root.resolve()
        ttl = settings.workspace_orphan_ttl_seconds

        scanned = 0
        skipped_active = 0
        skipped_young = 0
        skipped_unsafe = 0
        candidates: list[_WorkspaceCandidate] = []

        entries = await asyncio.to_thread(list, root.iterdir())
        for entry in entries:
            scanned += 1
            if entry.name in active_render_ids:
                skipped_active += 1
                continue
            if entry.is_symlink() or not entry.is_dir():
                skipped_unsafe += 1
                continue

            resolved = entry.resolve()
            if not _is_subpath(resolved, root):
                skipped_unsafe += 1
                continue

            try:
                stat_result = await asyncio.to_thread(entry.stat, follow_symlinks=False)
            except OSError:
                skipped_unsafe += 1
                continue

            age_seconds = now - stat_result.st_mtime
            if age_seconds < ttl:
                skipped_young += 1
                continue

            bytes_used = await asyncio.to_thread(_directory_size, entry)
            candidates.append(
                _WorkspaceCandidate(
                    path=entry,
                    mtime=stat_result.st_mtime,
                    bytes_used=bytes_used,
                )
            )

        candidates.sort(key=lambda candidate: candidate.mtime)
        removed = 0
        bytes_removed = 0
        for candidate in candidates:
            await asyncio.to_thread(shutil.rmtree, candidate.path, ignore_errors=True)
            removed += 1
            bytes_removed += candidate.bytes_used

        result = OrphanCleanupResult(
            scanned=scanned,
            removed=removed,
            skipped_active=skipped_active,
            skipped_young=skipped_young,
            skipped_unsafe=skipped_unsafe,
            bytes_removed=bytes_removed,
        )
        await logger.ainfo(
            "workspace_orphan_cleanup_complete",
            scanned=result.scanned,
            removed=result.removed,
            skipped_active=result.skipped_active,
            skipped_young=result.skipped_young,
            skipped_unsafe=result.skipped_unsafe,
            bytes_removed=result.bytes_removed,
            disk_budget_bytes=settings.workspace_disk_budget_bytes,
        )
        return result


def _is_subpath(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _directory_size(path: Path) -> int:
    total = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            for entry in current.iterdir():
                if entry.is_symlink():
                    continue
                if entry.is_dir():
                    stack.append(entry)
                    continue
                if entry.is_file():
                    total += entry.stat(follow_symlinks=False).st_size
        except OSError:
            continue
    return total
