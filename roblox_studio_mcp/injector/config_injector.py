"""Multi-IDE configuration detector and one-click injector."""

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from roblox_studio_mcp.core._log import get_logger

logger = get_logger(__name__)


_COMMON_ENV = {"PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
_INJECT_MODES = ("auto", "repo", "pip", "uvx")


def _is_legacy_roblox_mcp_bat_entry(entry: object) -> bool:
    """True if ``entry`` is an MCP server config that shells out to Roblox's own
    ``mcp.bat`` launcher.

    Roblox Studio itself (or its installer) writes an entry like this straight
    into detected IDE configs when the MCP beta feature is enabled - independent
    of this bridge, and usually under a different key such as ``Roblox_Studio``.
    That launcher has two well-known bugs this bridge exists to work around (a
    ``server/discover``-before-``initialize`` crash, and a broken multi-line
    ``if/else`` in the generated batch file), so if it is still present alongside
    our own entry it will intermittently win the race and produce exactly those
    errors. We only match on the ``mcp.bat`` fingerprint - nothing else uses
    that filename - so this can't misfire on an unrelated server.
    """
    if not isinstance(entry, dict):
        return False
    haystack = " ".join(str(v).lower() for v in (entry.get("command"), *(entry.get("args") or [])) if v is not None)
    return "mcp.bat" in haystack


class MCPConfigInjector:
    """Detects installed AI IDEs and safely injects roblox_studio MCP server config."""

    @staticmethod
    def get_target_paths() -> Dict[str, List[Path]]:
        home = Path.home()
        targets: Dict[str, List[Path]] = {
            "claude": [],
            "cursor": [],
            "opencode": [],
            "antigravity": [],
        }

        # Antigravity stores its MCP config under ~/.gemini/antigravity/mcp_config.json
        # on all platforms. We also include the old ~/.antigravity dotfile and the
        # VSCode-lineage per-user profile path as fallbacks so users on forks
        # (Windsurf, Code-OSS, etc.) are still covered; inject() writes to every path
        # that already exists, or creates the primary one when none exist.
        if sys.platform == "win32":
            appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
            targets["claude"].append(appdata / "Claude" / "claude_desktop_config.json")
            targets["cursor"].append(home / ".cursor" / "mcp.json")
            targets["cursor"].append(appdata / "Cursor" / "User" / "globalStorage" / "roam.cursor-mcp" / "mcp.json")
            targets["opencode"].append(home / ".opencode" / "mcp.json")
            # Primary: actual Antigravity path (confirmed on Windows)
            targets["antigravity"].append(home / ".gemini" / "antigravity" / "mcp_config.json")
            # Legacy fallbacks for Windsurf-lineage forks and VSCode-lineage builds
            targets["antigravity"].append(home / ".antigravity" / "mcp_config.json")
            targets["antigravity"].append(appdata / "Antigravity" / "User" / "mcp.json")
        elif sys.platform == "darwin":
            app_support = home / "Library" / "Application Support"
            targets["claude"].append(app_support / "Claude" / "claude_desktop_config.json")
            targets["cursor"].append(home / ".cursor" / "mcp.json")
            targets["cursor"].append(app_support / "Cursor" / "User" / "globalStorage" / "roam.cursor-mcp" / "mcp.json")
            targets["opencode"].append(home / ".opencode" / "mcp.json")
            targets["antigravity"].append(home / ".gemini" / "antigravity" / "mcp_config.json")
            targets["antigravity"].append(home / ".antigravity" / "mcp_config.json")
            targets["antigravity"].append(app_support / "Antigravity" / "User" / "mcp.json")
        else:
            targets["cursor"].append(home / ".cursor" / "mcp.json")
            targets["opencode"].append(home / ".opencode" / "mcp.json")
            targets["antigravity"].append(home / ".gemini" / "antigravity" / "mcp_config.json")
            targets["antigravity"].append(home / ".antigravity" / "mcp_config.json")
            targets["antigravity"].append(home / ".config" / "Antigravity" / "User" / "mcp.json")

        return targets

    @classmethod
    def _select_targets(cls, target_name: str) -> Dict[str, List[Path]]:
        targets = cls.get_target_paths()
        return targets if target_name == "all" else {target_name: targets.get(target_name, [])}

    @classmethod
    def _iter_config_servers(
        cls, target_name: str
    ) -> Iterator[Tuple[Path, Dict, Dict]]:
        """Yield ``(config_path, data, servers)`` for every existing, readable config.

        Files that are missing, unreadable, or whose ``mcpServers`` is not a dict
        are skipped. ``servers`` is ``data["mcpServers"]`` and can be mutated in
        place; the caller is responsible for writing ``data`` back.
        """
        for path_list in cls._select_targets(target_name).values():
            for config_path in path_list:
                if not config_path.exists():
                    continue
                try:
                    with open(config_path, encoding="utf-8") as f:
                        data = json.load(f)
                except (ValueError, OSError) as e:
                    logger.warning("Skipping unreadable config %s: %s", config_path, e)
                    continue
                servers = data.get("mcpServers") if isinstance(data, dict) else None
                if not isinstance(servers, dict):
                    continue
                yield config_path, data, servers

    @staticmethod
    def _legacy_keys(servers: Dict) -> List[str]:
        """Return the keys of every legacy Roblox ``mcp.bat`` entry (never ours)."""
        return [
            k for k, v in servers.items()
            if k != "roblox_studio" and _is_legacy_roblox_mcp_bat_entry(v)
        ]

    @staticmethod
    def _package_root() -> Path:
        """The directory that contains the ``roblox_studio_mcp`` package."""
        return Path(__file__).resolve().parent.parent.parent

    @classmethod
    def detect_mode(cls) -> str:
        """``"repo"`` when running from a source checkout, otherwise ``"pip"``.

        A checkout has ``pyproject.toml`` next to the package and a ``.git`` dir;
        a ``pip``/``uvx`` install lives in ``site-packages`` with neither.
        """
        root = cls._package_root()
        if (root / "pyproject.toml").is_file() and (root / ".git").exists():
            return "repo"
        return "pip"

    @classmethod
    def build_bridge_entry(cls, mode: str = "auto", python_path: Optional[str] = None) -> Dict:
        """Return the ``mcpServers.roblox_studio`` entry for the given install mode.

        - ``repo`` — bind ``cwd`` + ``PYTHONPATH`` to the checkout so ``python -m``
          resolves without an install (the original, move-sensitive behaviour).
        - ``pip`` — plain ``<python> -m roblox_studio_mcp run``; needs the package
          installed but has no path dependency.
        - ``uvx`` — ``uvx roblox-studio-mcp run``; no install step at all.
        - ``auto`` — ``repo`` from a checkout, else ``pip``.
        """
        if mode == "auto":
            mode = cls.detect_mode()
        if mode not in _INJECT_MODES or mode == "auto":
            raise ValueError(f"unknown inject mode {mode!r}; expected one of {_INJECT_MODES}")

        if mode == "uvx":
            return {"command": "uvx", "args": ["roblox-studio-mcp", "run"], "env": dict(_COMMON_ENV)}

        py_exec = python_path or sys.executable
        if mode == "pip":
            return {"command": py_exec, "args": ["-m", "roblox_studio_mcp", "run"], "env": dict(_COMMON_ENV)}

        repo_root = str(cls._package_root())
        return {
            "command": py_exec,
            "args": ["-m", "roblox_studio_mcp", "run"],
            "cwd": repo_root,
            "env": {**_COMMON_ENV, "PYTHONPATH": repo_root},
        }

    @classmethod
    def inject(
        cls, target_name: str = "all", python_path: Optional[str] = None, mode: str = "auto"
    ) -> List[str]:
        bridge_entry = cls.build_bridge_entry(mode, python_path)

        selected = cls._select_targets(target_name)
        modified_files = []

        for _client_name, path_list in selected.items():
            # For each IDE, only write to paths that already exist, EXCEPT we always
            # create the first (primary) path when none of the candidates exist yet.
            existing_paths = [p for p in path_list if p.exists()]
            paths_to_write = existing_paths if existing_paths else path_list[:1]

            for config_path in paths_to_write:
                config_path.parent.mkdir(parents=True, exist_ok=True)
                data = {"mcpServers": {}}

                if config_path.exists():
                    try:
                        with open(config_path, encoding="utf-8") as f:
                            data = json.load(f)
                    except (ValueError, OSError) as e:
                        logger.warning(
                            "Existing config %s is unreadable (%s); backing up to .corrupt.bak",
                            config_path,
                            e,
                        )
                        shutil.copyfile(config_path, config_path.with_suffix(".corrupt.bak"))
                        data = {"mcpServers": {}}

                if config_path.exists():
                    shutil.copyfile(config_path, config_path.with_suffix(".backup.json"))

                if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
                    data["mcpServers"] = {}

                servers = data["mcpServers"]
                for key in cls._legacy_keys(servers):
                    logger.warning(
                        "Removing conflicting legacy entry %r from %s (it shells out to Roblox's "
                        "broken mcp.bat and will intermittently crash the connection)",
                        key,
                        config_path,
                    )
                    del servers[key]

                servers["roblox_studio"] = bridge_entry

                # Atomic write
                temp_file = config_path.with_suffix(".tmp")
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                temp_file.replace(config_path)

                modified_files.append(str(config_path))

        return modified_files

    @classmethod
    def scrub(cls, target_name: str = "all") -> List[str]:
        """Remove any legacy Roblox ``mcp.bat`` entries from all IDE configs.

        Roblox Studio re-injects its own broken ``cmd.exe``/``mcp.bat`` entry into
        IDE config files on every weekly auto-update, which causes a race that
        intermittently crashes the bridge connection. This method strips those entries
        from every config it can find without touching any other servers (including
        the bridge's own ``roblox_studio`` entry).

        Returns a list of config file paths that were modified.
        """
        modified_files = []
        for config_path, data, servers in cls._iter_config_servers(target_name):
            legacy_keys = cls._legacy_keys(servers)
            if not legacy_keys:
                continue
            for key in legacy_keys:
                logger.warning("scrub: removing legacy mcp.bat entry %r from %s", key, config_path)
                del servers[key]
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            modified_files.append(str(config_path))

        return modified_files

    @classmethod
    def find_legacy_entries(cls, target_name: str = "all") -> Dict[str, List[str]]:
        """Return a mapping of config path -> list of legacy mcp.bat key names found.

        Used by ``doctor`` to warn users about active broken entries without
        modifying any files.
        """
        found: Dict[str, List[str]] = {}
        for config_path, _data, servers in cls._iter_config_servers(target_name):
            legacy_keys = cls._legacy_keys(servers)
            if legacy_keys:
                found[str(config_path)] = legacy_keys

        return found

    @classmethod
    def eject(cls, target_name: str = "all") -> List[str]:
        modified_files = []
        for config_path, data, servers in cls._iter_config_servers(target_name):
            if servers.pop("roblox_studio", None) is None:
                continue
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            modified_files.append(str(config_path))

        return modified_files
