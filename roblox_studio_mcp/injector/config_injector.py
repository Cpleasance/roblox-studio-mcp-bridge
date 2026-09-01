"""Multi-IDE configuration detector and one-click injector."""

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional

from roblox_studio_mcp.core._log import get_logger

logger = get_logger(__name__)


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

        # Antigravity's config location isn't documented, and the two forks it
        # descends from disagree: Windsurf-lineage tools read a dotfile in the
        # home directory, while plain VS Code / Code-OSS forks read a per-user
        # profile file under the app's own data directory. We write to both
        # candidates so `inject` works regardless of which one Antigravity
        # actually reads; `doctor` lists both paths with their existence status.
        if sys.platform == "win32":
            appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
            targets["claude"].append(appdata / "Claude" / "claude_desktop_config.json")
            targets["cursor"].append(home / ".cursor" / "mcp.json")
            targets["cursor"].append(appdata / "Cursor" / "User" / "globalStorage" / "roam.cursor-mcp" / "mcp.json")
            targets["opencode"].append(home / ".opencode" / "mcp.json")
            targets["antigravity"].append(home / ".antigravity" / "mcp_config.json")
            targets["antigravity"].append(appdata / "Antigravity" / "User" / "mcp.json")
        elif sys.platform == "darwin":
            app_support = home / "Library" / "Application Support"
            targets["claude"].append(app_support / "Claude" / "claude_desktop_config.json")
            targets["cursor"].append(home / ".cursor" / "mcp.json")
            targets["cursor"].append(app_support / "Cursor" / "User" / "globalStorage" / "roam.cursor-mcp" / "mcp.json")
            targets["opencode"].append(home / ".opencode" / "mcp.json")
            targets["antigravity"].append(home / ".antigravity" / "mcp_config.json")
            targets["antigravity"].append(app_support / "Antigravity" / "User" / "mcp.json")
        else:
            targets["cursor"].append(home / ".cursor" / "mcp.json")
            targets["opencode"].append(home / ".opencode" / "mcp.json")
            targets["antigravity"].append(home / ".antigravity" / "mcp_config.json")
            targets["antigravity"].append(home / ".config" / "Antigravity" / "User" / "mcp.json")

        return targets

    @classmethod
    def inject(cls, target_name: str = "all", python_path: Optional[str] = None) -> List[str]:
        py_exec = python_path or sys.executable
        repo_root = str(Path(__file__).resolve().parent.parent.parent)

        bridge_entry = {
            "command": py_exec,
            "args": ["-m", "roblox_studio_mcp", "run"],
            "cwd": repo_root,
            "env": {"PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1", "PYTHONPATH": repo_root},
        }

        targets = cls.get_target_paths()
        selected = targets if target_name == "all" else {target_name: targets.get(target_name, [])}
        modified_files = []

        for _client_name, path_list in selected.items():
            for config_path in path_list:
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

                data["mcpServers"]["roblox_studio"] = bridge_entry

                # Atomic write
                temp_file = config_path.with_suffix(".tmp")
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                temp_file.replace(config_path)

                modified_files.append(str(config_path))

        return modified_files

    @classmethod
    def eject(cls, target_name: str = "all") -> List[str]:
        targets = cls.get_target_paths()
        selected = targets if target_name == "all" else {target_name: targets.get(target_name, [])}
        modified_files = []

        for _client_name, path_list in selected.items():
            for config_path in path_list:
                if not config_path.exists():
                    continue

                try:
                    with open(config_path, encoding="utf-8") as f:
                        data = json.load(f)
                except (ValueError, OSError) as e:
                    logger.warning("Skipping unreadable config %s: %s", config_path, e)
                    continue

                if "mcpServers" in data and "roblox_studio" in data["mcpServers"]:
                    del data["mcpServers"]["roblox_studio"]
                    with open(config_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    modified_files.append(str(config_path))

        return modified_files
