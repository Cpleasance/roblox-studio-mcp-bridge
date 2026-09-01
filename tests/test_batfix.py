"""Tests for roblox_studio_mcp.core.batfix — repairing Roblox's broken mcp.bat."""

import sys

import pytest

from roblox_studio_mcp.core import batfix

# The real thing, as Roblox Studio writes it: the ``)`` closing the ``if`` and the
# ``else`` are on separate lines, which cmd.exe cannot parse.
BROKEN_ROBLOX_BAT = (
    '@echo off\n'
    'if exist "C:\\Users\\x\\AppData\\Local\\Roblox\\Versions\\version-abc\\StudioMCP.exe" '
    '( "C:\\Users\\x\\AppData\\Local\\Roblox\\Versions\\version-abc\\StudioMCP.exe" %* )\n'
    'else (for /f "tokens=2*" %%A in '
    "('reg query HKEY_CURRENT_USER\\Software\\Roblox\\RobloxStudio /v ContentFolder') do (\n"
    '"%%B/..\\StudioMCP.exe" %*\n'
    '))'
)

# A hypothetical single-line launcher that at least parses.
PARSING_ROBLOX_BAT = '@echo off\n"C:\\Roblox\\StudioMCP.exe" %*\n'


@pytest.fixture
def bat(tmp_path):
    """Return the mcp.bat path under a fake %LOCALAPPDATA% and its base dir."""
    p = batfix.launcher_path(base=tmp_path)
    assert p == tmp_path / "Roblox" / "mcp.bat"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


class TestDetection:
    def test_is_broken_detects_split_else(self):
        assert batfix.is_broken_roblox_launcher(BROKEN_ROBLOX_BAT)

    def test_parsing_launcher_is_not_broken(self):
        assert not batfix.is_broken_roblox_launcher(PARSING_ROBLOX_BAT)

    def test_managed_launcher_is_never_broken(self):
        assert batfix.is_bridge_managed(batfix._WINDOWS_BODY)
        assert not batfix.is_broken_roblox_launcher(batfix._WINDOWS_BODY)


class TestRepair:
    def test_noop_when_file_absent(self, tmp_path):
        assert batfix.repair_roblox_launchers(base=tmp_path) == []

    def test_rewrites_broken_launcher_and_backs_it_up(self, bat):
        bat.write_text(BROKEN_ROBLOX_BAT, encoding="utf-8")

        changed = batfix.repair_roblox_launchers(base=bat.parent.parent)

        assert changed == [str(bat)]
        assert batfix.is_bridge_managed(bat.read_text(encoding="utf-8"))
        backup = bat.with_name("mcp.bat.roblox-bak")
        assert backup.read_text(encoding="utf-8") == BROKEN_ROBLOX_BAT
        # The corrected script keeps every control-flow token on one line.
        for line in bat.read_text(encoding="utf-8").splitlines():
            assert not line.strip().lower().startswith("else")

    def test_idempotent(self, bat):
        bat.write_text(BROKEN_ROBLOX_BAT, encoding="utf-8")
        base = bat.parent.parent
        first = batfix.repair_roblox_launchers(base=base)
        second = batfix.repair_roblox_launchers(base=base)
        assert first == [str(bat)]
        assert second == []

    def test_backup_not_overwritten_if_studio_rewrites_then_we_reheal(self, bat):
        base = bat.parent.parent
        bat.write_text(BROKEN_ROBLOX_BAT, encoding="utf-8")
        batfix.repair_roblox_launchers(base=base)
        # Studio update clobbers our managed copy with a fresh broken one.
        bat.write_text(BROKEN_ROBLOX_BAT.replace("version-abc", "version-def"), encoding="utf-8")

        changed = batfix.repair_roblox_launchers(base=base)

        assert changed == [str(bat)]
        # Original backup (first-seen) is preserved, not replaced by the v-def one.
        assert "version-abc" in bat.with_name("mcp.bat.roblox-bak").read_text(encoding="utf-8")

    def test_force_false_leaves_a_parsing_launcher_alone(self, bat):
        bat.write_text(PARSING_ROBLOX_BAT, encoding="utf-8")
        changed = batfix.repair_roblox_launchers(base=bat.parent.parent, force=False)
        assert changed == []
        assert bat.read_text(encoding="utf-8") == PARSING_ROBLOX_BAT

    def test_force_true_rewrites_even_a_parsing_launcher(self, bat):
        bat.write_text(PARSING_ROBLOX_BAT, encoding="utf-8")
        changed = batfix.repair_roblox_launchers(base=bat.parent.parent, force=True)
        assert changed == [str(bat)]
        assert batfix.is_bridge_managed(bat.read_text(encoding="utf-8"))

    def test_strict_reraises_write_failure(self, bat, monkeypatch):
        bat.write_text(BROKEN_ROBLOX_BAT, encoding="utf-8")

        def _boom(*_a, **_k):
            raise OSError("read-only file system")

        monkeypatch.setattr(batfix.Path, "write_text", _boom)
        with pytest.raises(OSError, match="read-only"):
            batfix.repair_roblox_launchers(base=bat.parent.parent, strict=True)

    def test_non_strict_swallows_write_failure(self, bat, monkeypatch):
        bat.write_text(BROKEN_ROBLOX_BAT, encoding="utf-8")
        monkeypatch.setattr(
            batfix.Path, "write_text", lambda *a, **k: (_ for _ in ()).throw(OSError("nope"))
        )
        assert batfix.repair_roblox_launchers(base=bat.parent.parent, strict=False) == []


class TestRestore:
    def test_restore_puts_original_back_and_drops_backup(self, bat):
        base = bat.parent.parent
        bat.write_text(BROKEN_ROBLOX_BAT, encoding="utf-8")
        batfix.repair_roblox_launchers(base=base)

        restored = batfix.restore_roblox_launchers(base=base)

        assert restored == [str(bat)]
        assert bat.read_text(encoding="utf-8") == BROKEN_ROBLOX_BAT
        assert not bat.with_name("mcp.bat.roblox-bak").exists()

    def test_restore_noop_without_backup(self, bat):
        bat.write_text(PARSING_ROBLOX_BAT, encoding="utf-8")
        assert batfix.restore_roblox_launchers(base=bat.parent.parent) == []

    def test_restore_wont_clobber_a_non_managed_replacement(self, bat):
        base = bat.parent.parent
        bat.write_text(BROKEN_ROBLOX_BAT, encoding="utf-8")
        batfix.repair_roblox_launchers(base=base)
        # Something replaced our managed file with its own content.
        bat.write_text("@echo off\nREM hand-rolled\n", encoding="utf-8")

        assert batfix.restore_roblox_launchers(base=base) == []
        assert "hand-rolled" in bat.read_text(encoding="utf-8")


class TestLauncherStatus:
    def test_absent(self, tmp_path):
        assert batfix.launcher_status(base=tmp_path) == "absent"

    def test_broken(self, bat):
        bat.write_text(BROKEN_ROBLOX_BAT, encoding="utf-8")
        assert batfix.launcher_status(base=bat.parent.parent) == "broken"

    def test_ok(self, bat):
        bat.write_text(PARSING_ROBLOX_BAT, encoding="utf-8")
        assert batfix.launcher_status(base=bat.parent.parent) == "ok"

    def test_managed(self, bat):
        bat.write_text(batfix._WINDOWS_BODY, encoding="utf-8")
        assert batfix.launcher_status(base=bat.parent.parent) == "managed"


@pytest.mark.skipif(sys.platform == "win32", reason="non-Windows behaviour")
def test_launcher_path_is_none_off_windows_without_base():
    assert batfix.launcher_path() is None
    assert batfix.repair_roblox_launchers() == []
