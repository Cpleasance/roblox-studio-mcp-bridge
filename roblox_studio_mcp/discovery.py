"""Multi-platform discovery and resolution of the latest Roblox StudioMCP executable."""

import os
import sys
import glob
from pathlib import Path
from typing import Optional, Dict, Any, List


def find_roblox_studio_mcp() -> Optional[Dict[str, Any]]:
    """
    Auto-discovers the latest active StudioMCP binary across Windows and macOS.
    Sorts all candidate version folders by modification time to ensure we always
    bind to the most recently updated Studio build.
    """
    # 1. Check environment variable override
    env_override = os.environ.get("ROBLOX_STUDIO_MCP_PATH")
    if env_override and os.path.exists(env_override):
        return {
            "path": str(Path(env_override).resolve()),
            "version_folder": Path(env_override).parent.name,
            "modified_time": os.path.getmtime(env_override),
            "source": "environment_variable"
        }

    candidates: List[Dict[str, Any]] = []

    # 2. Windows Discovery
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            versions_root = Path(local_app_data) / "Roblox" / "Versions"
            if versions_root.exists():
                for version_dir in versions_root.iterdir():
                    if version_dir.is_dir():
                        mcp_exe = version_dir / "StudioMCP.exe"
                        if mcp_exe.exists():
                            candidates.append({
                                "path": str(mcp_exe),
                                "version_folder": version_dir.name,
                                "modified_time": mcp_exe.stat().st_mtime,
                                "source": "roblox_versions_dir"
                            })

    # 3. macOS Discovery
    elif sys.platform == "darwin":
        home = Path.home()
        mac_paths = [
            Path("/Applications/RobloxStudio.app/Contents/MacOS/StudioMCP"),
            home / "Library" / "Roblox" / "Versions",
            home / "Applications" / "RobloxStudio.app" / "Contents" / "MacOS" / "StudioMCP"
        ]
        for p in mac_paths:
            if p.is_file() and os.access(p, os.X_OK):
                candidates.append({
                    "path": str(p),
                    "version_folder": p.parent.name,
                    "modified_time": p.stat().st_mtime,
                    "source": "macos_app"
                })
            elif p.is_dir():
                for version_dir in p.iterdir():
                    mcp_bin = version_dir / "StudioMCP"
                    if mcp_bin.exists():
                        candidates.append({
                            "path": str(mcp_bin),
                            "version_folder": version_dir.name,
                            "modified_time": mcp_bin.stat().st_mtime,
                            "source": "macos_versions_dir"
                        })

    if not candidates:
        return None

    # Sort descending by modification timestamp: newest build first
    candidates.sort(key=lambda x: x["modified_time"], reverse=True)
    return candidates[0]
