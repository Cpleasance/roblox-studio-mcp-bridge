"""Tests for roblox_studio_mcp.core.resolver.

These build a fake Roblox ``Versions`` tree under ``tmp_path`` and point the
resolver's search roots at it via env vars. No real filesystem locations are
touched.
"""

import os
import sys

import pytest

from roblox_studio_mcp.core.resolver import RobloxStudioResolver, StudioCandidate

WIN_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only path layout")

EXE_NAME = "StudioMCP.exe" if sys.platform == "win32" else "StudioMCP"
COMPANION_NAME = "RobloxStudioBeta.exe" if sys.platform == "win32" else "RobloxStudio"


@pytest.fixture
def isolated_env(monkeypatch, tmp_path):
    """Neutralise every search root the resolver knows about, then hand back the
    ``Versions`` dir the test should populate."""
    # Drop any real override on the dev machine.
    monkeypatch.delenv("ROBLOX_STUDIO_MCP_PATH", raising=False)
    monkeypatch.delenv("STUDIO_MCP_PATH", raising=False)

    empty = tmp_path / "nonexistent"
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: home))

    # Populate versions dir matching platform and LOCALAPPDATA fallback
    if sys.platform == "darwin":
        versions = home / "Library" / "Roblox" / "Versions"
    elif sys.platform == "win32":
        versions = tmp_path / "LocalAppData" / "Roblox" / "Versions"
    else:  # linux
        versions = home / ".local" / "share" / "roblox" / "Versions"

    versions.mkdir(parents=True, exist_ok=True)

    # Set env vars for complete cross-platform test isolation
    monkeypatch.setenv("LOCALAPPDATA", str(versions.parent.parent))
    monkeypatch.setenv("ProgramFiles", str(empty / "pf"))
    monkeypatch.setenv("ProgramFiles(x86)", str(empty / "pfx86"))

    return versions


def _make_version_dir(versions, name, mtime=None, with_companion=False):
    vdir = versions / name
    vdir.mkdir(parents=True)
    exe = vdir / EXE_NAME
    exe.write_text("binary")
    if with_companion:
        (vdir / COMPANION_NAME).write_text("studio")
    if mtime is not None:
        os.utime(exe, (mtime, mtime))
    return exe


class TestGetAllCandidates:
    def test_empty_tree_returns_nothing(self, isolated_env):
        assert RobloxStudioResolver.get_all_candidates() == []

    def test_finds_version_dirs(self, isolated_env):
        _make_version_dir(isolated_env, "version-aaaaaaaaaaaa")
        cands = RobloxStudioResolver.get_all_candidates()
        assert len(cands) == 1
        assert cands[0].executable_path.name == EXE_NAME
        assert cands[0].version_dir.name == "version-aaaaaaaaaaaa"

    def test_ignores_non_version_dirs_and_dirs_without_exe(self, isolated_env):
        (isolated_env / "not-a-version").mkdir()
        (isolated_env / "version-empty").mkdir()
        _make_version_dir(isolated_env, "version-real")
        cands = RobloxStudioResolver.get_all_candidates()
        assert [c.version_dir.name for c in cands] == ["version-real"]

    def test_sorted_newest_first(self, isolated_env):
        _make_version_dir(isolated_env, "version-old", mtime=1_000_000)
        _make_version_dir(isolated_env, "version-new", mtime=2_000_000)
        _make_version_dir(isolated_env, "version-mid", mtime=1_500_000)
        cands = RobloxStudioResolver.get_all_candidates()
        assert [c.version_dir.name for c in cands] == [
            "version-new",
            "version-mid",
            "version-old",
        ]

    def test_companion_beta_wins_over_mtime(self, isolated_env):
        # Older on disk, but has the companion Studio binary -> must sort first.
        _make_version_dir(isolated_env, "version-old-beta", mtime=1_000_000, with_companion=True)
        _make_version_dir(isolated_env, "version-new-plain", mtime=9_000_000)
        cands = RobloxStudioResolver.get_all_candidates()
        assert cands[0].version_dir.name == "version-old-beta"
        assert cands[0].has_studio_beta is True
        assert cands[1].has_studio_beta is False

    @WIN_ONLY
    def test_direct_exe_in_root(self, isolated_env):
        exe = isolated_env / EXE_NAME
        exe.write_text("binary")
        cands = RobloxStudioResolver.get_all_candidates()
        assert any(c.executable_path == exe for c in cands)


class TestCandidateAtDedup:
    """The shared _candidate_at helper must skip an executable it has already
    yielded, so overlapping search roots can't produce duplicate candidates."""

    def test_same_exe_seen_twice_is_deduped(self, tmp_path):
        exe_dir = tmp_path / "Versions"
        exe_dir.mkdir()
        (exe_dir / EXE_NAME).write_text("binary")

        seen: set = set()
        first = RobloxStudioResolver._candidate_at(exe_dir, EXE_NAME, COMPANION_NAME, seen)
        assert first is not None
        assert first.executable_path == exe_dir / EXE_NAME

        second = RobloxStudioResolver._candidate_at(exe_dir, EXE_NAME, COMPANION_NAME, seen)
        assert second is None

    def test_returns_none_when_exe_absent(self, tmp_path):
        assert RobloxStudioResolver._candidate_at(tmp_path, EXE_NAME, COMPANION_NAME, set()) is None


class TestEnvOverride:
    def test_override_file_path(self, isolated_env, monkeypatch, tmp_path):
        custom = tmp_path / "custom" / EXE_NAME
        custom.parent.mkdir(parents=True)
        custom.write_text("binary")
        monkeypatch.setenv("ROBLOX_STUDIO_MCP_PATH", str(custom))
        cands = RobloxStudioResolver.get_all_candidates()
        assert len(cands) == 1
        assert cands[0].executable_path == custom
        assert cands[0].has_studio_beta is True

    def test_secondary_override_env_var(self, isolated_env, monkeypatch, tmp_path):
        custom = tmp_path / "custom2" / EXE_NAME
        custom.parent.mkdir(parents=True)
        custom.write_text("binary")
        monkeypatch.setenv("STUDIO_MCP_PATH", str(custom))
        cands = RobloxStudioResolver.get_all_candidates()
        assert cands[0].executable_path == custom

    def test_override_directory_path(self, isolated_env, monkeypatch, tmp_path):
        d = tmp_path / "customdir"
        d.mkdir()
        (d / EXE_NAME).write_text("binary")
        monkeypatch.setenv("ROBLOX_STUDIO_MCP_PATH", str(d))
        cands = RobloxStudioResolver.get_all_candidates()
        assert len(cands) == 1
        assert cands[0].executable_path == d / EXE_NAME
        assert cands[0].version_dir == d

    def test_override_pointing_nowhere_falls_through_to_search(self, isolated_env, monkeypatch, tmp_path):
        monkeypatch.setenv("ROBLOX_STUDIO_MCP_PATH", str(tmp_path / "does-not-exist"))
        _make_version_dir(isolated_env, "version-fallback")
        cands = RobloxStudioResolver.get_all_candidates()
        assert len(cands) == 1
        assert cands[0].version_dir.name == "version-fallback"


class TestResolveExecutable:
    def test_raises_filenotfound_when_nothing_found(self, isolated_env):
        with pytest.raises(FileNotFoundError):
            RobloxStudioResolver.resolve_executable()

    def test_returns_top_candidate_path(self, isolated_env):
        _make_version_dir(isolated_env, "version-old", mtime=1_000_000)
        newest = _make_version_dir(isolated_env, "version-new", mtime=5_000_000)
        assert RobloxStudioResolver.resolve_executable() == newest


def test_studio_candidate_is_a_dataclass():
    c = StudioCandidate(executable_path="a", version_dir="b", last_modified=1.0, has_studio_beta=False)
    assert c.executable_path == "a"
    assert c.has_studio_beta is False
