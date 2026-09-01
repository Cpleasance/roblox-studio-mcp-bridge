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
        # Primary Antigravity path is ~/.gemini/antigravity/mcp_config.json
        primary_ag = targets["antigravity"][0]
        assert primary_ag.name == "mcp_config.json"
        assert ".gemini" in primary_ag.parts
        assert "antigravity" in primary_ag.parts
        # Legacy fallbacks are still present for Windsurf/Code-OSS forks
        assert any(p.name == "mcp_config.json" and ".antigravity" in p.parts for p in targets["antigravity"])
        assert any(p.name == "mcp.json" and "Antigravity" in p.parts for p in targets["antigravity"])

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

    def test_removes_legacy_mcp_bat_entry_regardless_of_key_name(self, single_target):
        # This is Roblox's own auto-generated (and broken) entry, seen in the
        # wild under the key "Roblox_Studio" - it must be stripped so it can't
        # race our entry and intermittently crash the connection.
        _write(
            single_target,
            {
                "mcpServers": {
                    "Roblox_Studio": {
                        "transport": "stdio",
                        "command": "cmd.exe",
                        "args": ["/c", "cd /d %LOCALAPPDATA%\\Roblox && .\\mcp.bat"],
                    },
                    "unrelated": {"command": "foo", "args": ["bar"]},
                }
            },
        )

        MCPConfigInjector.inject()

        data = _read(single_target)
        assert "Roblox_Studio" not in data["mcpServers"]
        assert "roblox_studio" in data["mcpServers"]
        assert data["mcpServers"]["unrelated"] == {"command": "foo", "args": ["bar"]}

    def test_does_not_remove_our_own_entry_on_reinject(self, single_target):
        MCPConfigInjector.inject()
        MCPConfigInjector.inject()  # idempotent: must not treat our own entry as legacy
        data = _read(single_target)
        assert "roblox_studio" in data["mcpServers"]


class TestLegacyMcpBatDetection:
    """Unit coverage for the ``mcp.bat`` fingerprint used to strip Roblox's own
    broken auto-generated entry (see TestInject.test_removes_legacy_mcp_bat_entry_regardless_of_key_name)."""

    def _detect(self, entry):
        from roblox_studio_mcp.injector.config_injector import _is_legacy_roblox_mcp_bat_entry

        return _is_legacy_roblox_mcp_bat_entry(entry)

    def test_matches_mcp_bat_in_args(self):
        assert self._detect({"command": "cmd.exe", "args": ["/c", "...\\Roblox\\mcp.bat"]})

    def test_matches_mcp_bat_case_insensitively(self):
        assert self._detect({"command": "CMD.EXE", "args": ["/c", "...\\MCP.BAT"]})

    def test_does_not_match_unrelated_entry(self):
        assert not self._detect({"command": "python", "args": ["-m", "roblox_studio_mcp", "run"]})

    def test_does_not_match_non_dict(self):
        assert not self._detect("not a dict")
        assert not self._detect(None)

    def test_tolerates_missing_args(self):
        assert not self._detect({"command": "python"})


class TestInjectMisc:
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


class TestScrub:
    """scrub() removes Roblox's broken mcp.bat entries without touching anything else."""

    @pytest.fixture
    def cfg(self, tmp_path):
        return tmp_path / "ide" / "mcp.json"

    @pytest.fixture
    def single_target(self, monkeypatch, cfg):
        monkeypatch.setattr(MCPConfigInjector, "get_target_paths", staticmethod(lambda: {"claude": [cfg]}))
        return cfg

    def _legacy_entry(self):
        return {"command": "cmd.exe", "args": ["/c", "cd /d %LOCALAPPDATA%\\Roblox && .\\mcp.bat"]}

    def test_scrub_removes_legacy_entry(self, single_target):
        _write(single_target, {"mcpServers": {"Roblox_Studio": self._legacy_entry(), "other": {"command": "x"}}})
        result = MCPConfigInjector.scrub()
        assert result == [str(single_target)]
        data = _read(single_target)
        assert "Roblox_Studio" not in data["mcpServers"]
        assert data["mcpServers"]["other"] == {"command": "x"}

    def test_scrub_leaves_bridge_entry_intact(self, single_target):
        _write(
            single_target,
            {
                "mcpServers": {
                    "Roblox_Studio": self._legacy_entry(),
                    "roblox_studio": {"command": "python", "args": ["-m", "roblox_studio_mcp", "run"]},
                }
            },
        )
        MCPConfigInjector.scrub()
        data = _read(single_target)
        assert "Roblox_Studio" not in data["mcpServers"]
        assert "roblox_studio" in data["mcpServers"]

    def test_scrub_noop_when_no_legacy_entries(self, single_target):
        _write(single_target, {"mcpServers": {"roblox_studio": {"command": "python"}}})
        result = MCPConfigInjector.scrub()
        assert result == []

    def test_scrub_noop_when_file_missing(self, single_target):
        assert MCPConfigInjector.scrub() == []

    def test_scrub_skips_corrupt_file(self, single_target):
        single_target.parent.mkdir(parents=True, exist_ok=True)
        single_target.write_text("{ bad json", encoding="utf-8")
        assert MCPConfigInjector.scrub() == []
        assert single_target.read_text(encoding="utf-8") == "{ bad json"

    def test_scrub_idempotent(self, single_target):
        _write(single_target, {"mcpServers": {"Roblox_Studio": self._legacy_entry()}})
        MCPConfigInjector.scrub()
        result2 = MCPConfigInjector.scrub()
        assert result2 == []

    def test_scrub_case_insensitive_filename_match(self, single_target):
        _write(single_target, {"mcpServers": {"rs": {"command": "CMD.EXE", "args": ["/c", "...\\MCP.BAT"]}}})
        result = MCPConfigInjector.scrub()
        assert result == [str(single_target)]
        assert _read(single_target)["mcpServers"] == {}


class TestFindLegacyEntries:
    """find_legacy_entries() returns a report without modifying anything."""

    @pytest.fixture
    def cfg(self, tmp_path):
        return tmp_path / "ide" / "mcp.json"

    @pytest.fixture
    def single_target(self, monkeypatch, cfg):
        monkeypatch.setattr(MCPConfigInjector, "get_target_paths", staticmethod(lambda: {"claude": [cfg]}))
        return cfg

    def _legacy_entry(self):
        return {"command": "cmd.exe", "args": ["/c", ".\\mcp.bat"]}

    def test_finds_legacy_key(self, single_target):
        _write(single_target, {"mcpServers": {"Roblox_Studio": self._legacy_entry()}})
        found = MCPConfigInjector.find_legacy_entries()
        assert str(single_target) in found
        assert found[str(single_target)] == ["Roblox_Studio"]

    def test_empty_when_no_legacy(self, single_target):
        _write(single_target, {"mcpServers": {"roblox_studio": {"command": "python"}}})
        assert MCPConfigInjector.find_legacy_entries() == {}

    def test_empty_when_file_missing(self, single_target):
        assert MCPConfigInjector.find_legacy_entries() == {}

    def test_does_not_modify_file(self, single_target):
        original = {"mcpServers": {"Roblox_Studio": self._legacy_entry()}}
        _write(single_target, original)
        MCPConfigInjector.find_legacy_entries()
        assert _read(single_target) == original
