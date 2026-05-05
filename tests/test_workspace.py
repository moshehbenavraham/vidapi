from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.models.error_codes import ErrorCode, error_code_for_exception
from app.workers.workspace import PRESERVE_ON_FAILURE, WorkspaceManager

# ---------------------------------------------------------------------------
# Workspace lifecycle tests
# ---------------------------------------------------------------------------


class TestWorkspaceCreate:
    @pytest.mark.asyncio
    async def test_create_workspace(self, tmp_path: Path):
        """create() produces an isolated directory."""
        mgr = WorkspaceManager(workspace_root=tmp_path)
        ws = await mgr.create("render_001")
        assert ws.exists()
        assert ws.is_dir()
        assert ws.name == "render_001"

    @pytest.mark.asyncio
    async def test_create_workspace_recreates_existing(self, tmp_path: Path):
        """If workspace already exists, it is cleared and recreated."""
        mgr = WorkspaceManager(workspace_root=tmp_path)
        ws = await mgr.create("render_002")
        (ws / "stale.txt").write_text("old data", encoding="utf-8")

        ws2 = await mgr.create("render_002")
        assert ws2 == ws
        assert not (ws2 / "stale.txt").exists()

    @pytest.mark.asyncio
    async def test_create_workspace_nested_path(self, tmp_path: Path):
        """Workspace root doesn't need to pre-exist."""
        root = tmp_path / "deep" / "nested"
        mgr = WorkspaceManager(workspace_root=root)
        ws = await mgr.create("render_003")
        assert ws.exists()


class TestWorkspaceCleanupSuccess:
    @pytest.mark.asyncio
    async def test_cleanup_removes_directory(self, tmp_path: Path):
        """cleanup_success removes entire workspace."""
        mgr = WorkspaceManager(workspace_root=tmp_path)
        ws = await mgr.create("render_010")
        (ws / "output.mp4").write_bytes(b"\x00" * 50)

        await mgr.cleanup_success(ws)
        assert not ws.exists()

    @pytest.mark.asyncio
    async def test_cleanup_disabled_keeps_workspace(self, tmp_path: Path):
        """When cleanup is disabled, workspace is preserved."""
        mgr = WorkspaceManager(workspace_root=tmp_path)
        ws = await mgr.create("render_011")
        (ws / "output.mp4").write_bytes(b"\x00" * 50)

        with patch("app.workers.workspace.get_settings") as mock_settings:
            settings = MagicMock()
            settings.workspace_cleanup_enabled = False
            mock_settings.return_value = settings
            await mgr.cleanup_success(ws)

        assert ws.exists()


class TestWorkspaceCleanupFailure:
    @pytest.mark.asyncio
    async def test_partial_cleanup_preserves_diagnostics(self, tmp_path: Path):
        """cleanup_failure preserves input.json, logs.txt, compiled spec."""
        mgr = WorkspaceManager(workspace_root=tmp_path)
        ws = await mgr.create("render_020")

        (ws / "input.json").write_text("{}", encoding="utf-8")
        (ws / "logs.txt").write_text("error log", encoding="utf-8")
        (ws / "compiled.editly.json").write_text("{}", encoding="utf-8")
        (ws / "output.mp4").write_bytes(b"\x00" * 50)
        (ws / "temp_chunk.ts").write_bytes(b"\x00" * 20)

        with patch("app.workers.workspace.get_settings") as mock_settings:
            settings = MagicMock()
            settings.workspace_cleanup_enabled = True
            settings.workspace_cleanup_keep_on_failure = True
            mock_settings.return_value = settings
            await mgr.cleanup_failure(ws)

        assert (ws / "input.json").exists()
        assert (ws / "logs.txt").exists()
        assert (ws / "compiled.editly.json").exists()
        assert not (ws / "output.mp4").exists()
        assert not (ws / "temp_chunk.ts").exists()

    @pytest.mark.asyncio
    async def test_full_cleanup_on_failure_when_keep_disabled(self, tmp_path: Path):
        """When keep_on_failure is False, everything is removed."""
        mgr = WorkspaceManager(workspace_root=tmp_path)
        ws = await mgr.create("render_021")
        (ws / "input.json").write_text("{}", encoding="utf-8")

        with patch("app.workers.workspace.get_settings") as mock_settings:
            settings = MagicMock()
            settings.workspace_cleanup_enabled = True
            settings.workspace_cleanup_keep_on_failure = False
            mock_settings.return_value = settings
            await mgr.cleanup_failure(ws)

        assert not ws.exists()

    @pytest.mark.asyncio
    async def test_cleanup_failure_nonexistent_workspace(self, tmp_path: Path):
        """cleanup_failure on missing workspace does not raise."""
        mgr = WorkspaceManager(workspace_root=tmp_path)
        ws = tmp_path / "nonexistent"
        await mgr.cleanup_failure(ws)


class TestWorkspaceOrphanCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_orphans_removes_stale_inactive_only(self, tmp_path: Path):
        """cleanup_orphans removes stale inactive workspaces only."""
        mgr = WorkspaceManager(workspace_root=tmp_path)
        stale = tmp_path / "render_stale"
        active = tmp_path / "render_active"
        young = tmp_path / "render_young"
        stale.mkdir()
        active.mkdir()
        young.mkdir()
        (stale / "chunk.bin").write_bytes(b"x" * 10)

        now = time.time()
        old_mtime = now - 3600
        os.utime(stale, (old_mtime, old_mtime))
        os.utime(active, (old_mtime, old_mtime))

        with patch("app.workers.workspace.get_settings") as mock_settings:
            settings = MagicMock()
            settings.workspace_cleanup_enabled = True
            settings.workspace_orphan_ttl_seconds = 60
            settings.workspace_disk_budget_bytes = None
            mock_settings.return_value = settings

            result = await mgr.cleanup_orphans({"render_active"}, now=now)

        assert result.removed == 1
        assert result.skipped_active == 1
        assert result.skipped_young == 1
        assert result.bytes_removed == 10
        assert not stale.exists()
        assert active.exists()
        assert young.exists()

    @pytest.mark.asyncio
    async def test_cleanup_orphans_skips_symlinks(self, tmp_path: Path):
        """cleanup_orphans never follows symlinks under the workspace root."""
        root = tmp_path / "root"
        root.mkdir()
        mgr = WorkspaceManager(workspace_root=root)
        outside = tmp_path / "outside"
        outside.mkdir()
        link = root / "render_link"
        link.symlink_to(outside, target_is_directory=True)

        with patch("app.workers.workspace.get_settings") as mock_settings:
            settings = MagicMock()
            settings.workspace_cleanup_enabled = True
            settings.workspace_orphan_ttl_seconds = 0
            settings.workspace_disk_budget_bytes = None
            mock_settings.return_value = settings

            result = await mgr.cleanup_orphans(set(), now=time.time())

        assert result.removed == 0
        assert result.skipped_unsafe == 1
        assert link.exists()
        assert outside.exists()


# ---------------------------------------------------------------------------
# Error codes registry tests
# ---------------------------------------------------------------------------


class TestErrorCodes:
    def test_all_codes_are_strings(self):
        """All ErrorCode members are plain strings."""
        for code in ErrorCode:
            assert isinstance(code.value, str)
            assert code.value == code.value.upper()

    def test_error_code_for_timeout(self):
        """TimeoutError maps to RENDER_TIMEOUT."""
        exc = TimeoutError("timed out")
        assert error_code_for_exception(exc) == ErrorCode.RENDER_TIMEOUT

    def test_error_code_for_os_error(self):
        """OSError maps to STORAGE_ERROR."""
        exc = OSError("disk full")
        assert error_code_for_exception(exc) == ErrorCode.STORAGE_ERROR

    def test_error_code_for_unknown(self):
        """Unknown exception maps to WORKER_UNEXPECTED_ERROR."""
        exc = ValueError("something")
        assert error_code_for_exception(exc) == ErrorCode.WORKER_UNEXPECTED_ERROR

    def test_preserve_on_failure_set(self):
        """PRESERVE_ON_FAILURE contains expected diagnostic files."""
        assert "input.json" in PRESERVE_ON_FAILURE
        assert "logs.txt" in PRESERVE_ON_FAILURE
        assert "compiled.editly.json" in PRESERVE_ON_FAILURE
