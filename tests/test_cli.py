"""Tests for roblox_studio_mcp.cli — arg routing and install-mode-aware hints."""

import io

import pytest

from roblox_studio_mcp import cli


@pytest.fixture(autouse=True)
def _no_real_batfix(monkeypatch):
    """Keep every CLI test off the real ``%LOCALAPPDATA%\\Roblox\\mcp.bat``."""
    monkeypatch.setattr(cli.batfix, "repair_roblox_launchers", lambda *a, **k: [])
    monkeypatch.setattr(cli.batfix, "restore_roblox_launchers", lambda *a, **k: [])
    monkeypatch.setattr(cli.batfix, "launcher_status", lambda *a, **k: "absent")
    monkeypatch.setattr(cli.batfix, "launcher_path", lambda *a, **k: None)


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("uvx", "uvx roblox-studio-mcp-bridge"),
        ("repo", "python -m roblox_studio_mcp"),
        ("pip", "roblox-studio-mcp"),
        ("anything-else", "roblox-studio-mcp"),
    ],
)
def test_self_command(mode, expected):
    assert cli._self_command(mode) == expected


def test_force_utf8_stdio_is_safe_on_stringio(monkeypatch):
    # io.StringIO has no reconfigure(); the helper must swallow that.
    monkeypatch.setattr(cli.sys, "stdout", io.StringIO())
    monkeypatch.setattr(cli.sys, "stderr", io.StringIO())
    cli._force_utf8_stdio()  # must not raise


def test_no_subcommand_routes_to_run(monkeypatch):
    called = {}
    monkeypatch.setattr(cli, "cmd_run", lambda args: called.setdefault("run", True))
    monkeypatch.setattr(cli.sys, "argv", ["roblox-studio-mcp"])
    cli.main()
    assert called == {"run": True}


@pytest.mark.parametrize("sub", ["doctor", "inject", "scrub", "eject"])
def test_subcommands_route_to_their_handler(monkeypatch, sub):
    called = {}
    monkeypatch.setattr(cli, f"cmd_{sub}", lambda args: called.setdefault(sub, args))
    monkeypatch.setattr(cli.sys, "argv", ["roblox-studio-mcp", sub])
    cli.main()
    assert sub in called


def test_inject_hint_uses_uvx_command_in_uvx_mode(monkeypatch, capsys):
    monkeypatch.setattr(cli.MCPConfigInjector, "detect_mode", classmethod(lambda cls: "uvx"))
    monkeypatch.setattr(
        cli.MCPConfigInjector, "inject", classmethod(lambda cls, **kw: ["/tmp/some/config.json"])
    )
    monkeypatch.setattr(cli.sys, "argv", ["roblox-studio-mcp", "inject"])
    cli.main()
    out = capsys.readouterr().out
    assert "uvx roblox-studio-mcp-bridge scrub" in out
    assert "python -m roblox_studio_mcp scrub" not in out


def test_inject_reports_launcher_repair(monkeypatch, capsys):
    monkeypatch.setattr(cli.MCPConfigInjector, "detect_mode", classmethod(lambda cls: "pip"))
    monkeypatch.setattr(cli.MCPConfigInjector, "inject", classmethod(lambda cls, **kw: []))
    monkeypatch.setattr(
        cli.batfix, "repair_roblox_launchers", lambda *a, **k: [r"C:\X\Roblox\mcp.bat"]
    )
    monkeypatch.setattr(cli.sys, "argv", ["roblox-studio-mcp", "inject"])
    cli.main()
    out = capsys.readouterr().out
    assert "Repaired Roblox's broken launcher" in out
    assert "restart" in out.lower()


def test_scrub_reports_nothing_to_do(monkeypatch, capsys):
    monkeypatch.setattr(cli.MCPConfigInjector, "scrub", classmethod(lambda cls, **kw: []))
    monkeypatch.setattr(cli.sys, "argv", ["roblox-studio-mcp", "scrub"])
    cli.main()
    assert "Nothing to clean up" in capsys.readouterr().out


def test_scrub_reports_launcher_repair(monkeypatch, capsys):
    monkeypatch.setattr(cli.MCPConfigInjector, "scrub", classmethod(lambda cls, **kw: []))
    monkeypatch.setattr(
        cli.batfix, "repair_roblox_launchers", lambda *a, **k: [r"C:\X\Roblox\mcp.bat"]
    )
    monkeypatch.setattr(cli.sys, "argv", ["roblox-studio-mcp", "scrub"])
    cli.main()
    out = capsys.readouterr().out
    assert "Repaired Roblox's broken launcher" in out
    assert "Healed 1 file(s)" in out


def test_command_exception_is_surfaced_and_exits_1(monkeypatch, capsys):
    def _boom(_args):
        raise RuntimeError("disk exploded")

    monkeypatch.setattr(cli, "cmd_scrub", _boom)
    monkeypatch.setattr(cli.sys, "argv", ["roblox-studio-mcp", "scrub"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "'scrub' failed" in err
    assert "disk exploded" in err


def test_inject_launcher_repair_failure_is_surfaced(monkeypatch, capsys):
    monkeypatch.setattr(cli.MCPConfigInjector, "detect_mode", classmethod(lambda cls: "pip"))
    monkeypatch.setattr(cli.MCPConfigInjector, "inject", classmethod(lambda cls, **kw: []))
    monkeypatch.setattr(
        cli.batfix,
        "repair_roblox_launchers",
        lambda *a, **k: (_ for _ in ()).throw(PermissionError("mcp.bat is locked")),
    )
    monkeypatch.setattr(cli.sys, "argv", ["roblox-studio-mcp", "inject"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    assert "mcp.bat is locked" in capsys.readouterr().err


def test_doctor_reports_broken_launcher(monkeypatch, capsys):
    monkeypatch.setattr(cli.RobloxStudioResolver, "get_all_candidates", staticmethod(lambda: []))
    monkeypatch.setattr(cli.MCPConfigInjector, "get_target_paths", staticmethod(lambda: {"claude": []}))
    monkeypatch.setattr(cli.MCPConfigInjector, "find_legacy_entries", classmethod(lambda cls, **kw: {}))
    monkeypatch.setattr(cli.batfix, "launcher_status", lambda *a, **k: "broken")
    monkeypatch.setattr(cli.batfix, "launcher_path", lambda *a, **k: r"C:\X\Roblox\mcp.bat")
    monkeypatch.setattr(cli.sys, "argv", ["roblox-studio-mcp", "doctor"])
    cli.main()
    out = capsys.readouterr().out
    assert "BROKEN" in out
    assert "scrub" in out
