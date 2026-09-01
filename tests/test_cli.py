"""Tests for roblox_studio_mcp.cli — arg routing and install-mode-aware hints."""

import io

import pytest

from roblox_studio_mcp import cli


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
    monkeypatch.setattr(cli.MCPConfigInjector, "find_legacy_entries", classmethod(lambda cls, **kw: {}))
    monkeypatch.setattr(cli.sys, "argv", ["roblox-studio-mcp", "inject"])
    cli.main()
    out = capsys.readouterr().out
    assert "uvx roblox-studio-mcp-bridge scrub" in out
    assert "python -m roblox_studio_mcp scrub" not in out
