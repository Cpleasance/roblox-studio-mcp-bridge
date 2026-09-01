"""Tests for roblox_studio_mcp.injector.config_injector.MCPConfigInjector."""

import json
import sys

import pytest

from roblox_studio_mcp.injector.config_injector import MCPConfigInjector

EXPECTED_KEYS = {"claude", "cursor", "opencode", "antigravity"}


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


@pytest.fixture
def cfg(tmp_path):
    return tmp_path / "ide" / "mcp.json"


@pytest.fixture
def single_target(monkeypatch, cfg):
    """Point ``get_target_paths`` at exactly one file under tmp_path."""
    monkeypatch.setattr(MCPConfigInjector, "get_target_paths", staticmethod(lambda: {"claude": [cfg]}))
    return cfg


class TestGetTargetPaths:
    def test_returns_all_expected_keys(self):
        targets = MCPConfigInjector.get_target_paths()
        assert set(targets) == EXPECTED_KEYS
        assert all(isinstance(v, list) for v in targets.values())

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows path layout")
    def test_windows_paths(self, monkeypatch, tmp_path):
        monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
        targets = MCPConfigInjector.get_target_paths()
        claude = targets["claude"][0]
        assert claude.name == "claude_desktop_config.json"
        assert "Claude" in claude.parts
        assert any(p.name == "mcp.json" for p in targets["cursor"])
        assert targets["antigravity"][0].name == "mcp_config.json"

    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS path layout")
    def test_macos_paths(self):  # pragma: no cover - platform specific
        targets = MCPConfigInjector.get_target_paths()
        assert targets["claude"][0].name == "claude_desktop_config.json"
        assert "Application Support" in targets["claude"][0].parts

    @pytest.mark.skipif(sys.platform in ("win32", "darwin"), reason="Linux fallback layout")
    def test_linux_has_no_claude_target(self):  # pragma: no cover - platform specific
        targets = MCPConfigInjector.get_target_paths()
        assert targets["claude"] == []
        assert targets["cursor"]


class TestInject:
    def test_creates_file_with_roblox_studio_server(self, single_target):
        result = MCPConfigInjector.inject()
        assert result == [str(single_target)]
        assert single_target.exists()

        data = _read(single_target)
        entry = data["mcpServers"]["roblox_studio"]
        assert entry["args"] == ["-m", "roblox_studio_mcp", "run"]
        assert entry["command"] == sys.executable
        assert entry["env"]["PYTHONIOENCODING"] == "utf-8"

    def test_custom_python_path_is_used(self, single_target):
        MCPConfigInjector.inject(python_path="/opt/py/bin/python")
        data = _read(single_target)
        assert data["mcpServers"]["roblox_studio"]["command"] == "/opt/py/bin/python"

    def test_preserves_unrelated_servers(self, single_target):
        _write(single_target, {"mcpServers": {"other": {"command": "foo"}}, "misc": 1})
        MCPConfigInjector.inject()

        data = _read(single_target)
        assert data["mcpServers"]["other"] == {"command": "foo"}
        assert "roblox_studio" in data["mcpServers"]
        assert data["misc"] == 1

    def test_backs_up_existing_file(self, single_target):
        _write(single_target, {"mcpServers": {"other": {"command": "foo"}}})
        MCPConfigInjector.inject()

        backup = single_target.with_suffix(".backup.json")
        assert backup.exists()
        assert _read(backup) == {"mcpServers": {"other": {"command": "foo"}}}

    def test_no_backup_when_file_absent(self, single_target):
        MCPConfigInjector.inject()
        assert not single_target.with_suffix(".backup.json").exists()

    def test_handles_preexisting_corrupt_json(self, single_target):
        single_target.parent.mkdir(parents=True, exist_ok=True)
        single_target.write_text("{ this is not json", encoding="utf-8")

        MCPConfigInjector.inject()

        corrupt_bak = single_target.with_suffix(".corrupt.bak")
        assert corrupt_bak.exists()
        assert corrupt_bak.read_text(encoding="utf-8") == "{ this is not json"
        # File is now valid and contains our server.
        data = _read(single_target)
        assert list(data["mcpServers"]) == ["roblox_studio"]

    def test_repairs_non_dict_mcpservers(self, single_target):
        _write(single_target, {"mcpServers": "garbage"})
        MCPConfigInjector.inject()
        data = _read(single_target)
        assert isinstance(data["mcpServers"], dict)
        assert "roblox_studio" in data["mcpServers"]

    def test_idempotent(self, single_target):
        first = MCPConfigInjector.inject()
        data_first = _read(single_target)
        second = MCPConfigInjector.inject()
        data_second = _read(single_target)

        assert first == second
        assert data_first == data_second
        assert list(data_second["mcpServers"]).count("roblox_studio") == 1

    def test_target_name_filters_selection(self, monkeypatch, tmp_path):
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        monkeypatch.setattr(
            MCPConfigInjector,
            "get_target_paths",
            staticmethod(lambda: {"claude": [a], "cursor": [b]}),
        )
        result = MCPConfigInjector.inject(target_name="cursor")
        assert result == [str(b)]
        assert b.exists() and not a.exists()


class TestEject:
    def test_removes_only_roblox_studio_key(self, single_target):
        _write(
            single_target,
            {"mcpServers": {"other": {"command": "foo"}, "roblox_studio": {"command": "x"}}},
        )
        result = MCPConfigInjector.eject()

        assert result == [str(single_target)]
        data = _read(single_target)
        assert "roblox_studio" not in data["mcpServers"]
        assert data["mcpServers"]["other"] == {"command": "foo"}

    def test_noop_when_file_missing(self, single_target):
        assert MCPConfigInjector.eject() == []

    def test_noop_when_key_absent(self, single_target):
        _write(single_target, {"mcpServers": {"other": {}}})
        assert MCPConfigInjector.eject() == []
        assert _read(single_target) == {"mcpServers": {"other": {}}}

    def test_skips_corrupt_file(self, single_target):
        single_target.parent.mkdir(parents=True, exist_ok=True)
        single_target.write_text("nonsense{", encoding="utf-8")
        assert MCPConfigInjector.eject() == []
        assert single_target.read_text(encoding="utf-8") == "nonsense{"

    def test_inject_then_eject_roundtrip(self, single_target):
        _write(single_target, {"mcpServers": {"keep": {"command": "k"}}})
        MCPConfigInjector.inject()
        MCPConfigInjector.eject()
        data = _read(single_target)
        assert data["mcpServers"] == {"keep": {"command": "k"}}
