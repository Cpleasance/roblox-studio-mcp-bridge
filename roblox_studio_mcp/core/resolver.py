"""Multi-path LastWriteTime StudioMCP executable resolver."""

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class StudioCandidate:
    executable_path: Path
    version_dir: Path
    last_modified: float
    has_studio_beta: bool


class RobloxStudioResolver:
    """Discovers all StudioMCP binaries across user, system, and custom paths."""

    @classmethod
    def get_all_candidates(cls) -> List[StudioCandidate]:
        """Return every discoverable StudioMCP binary, best match first.

        Honors ``ROBLOX_STUDIO_MCP_PATH`` / ``STUDIO_MCP_PATH`` overrides, then
        scans the known Roblox install roots. Results are sorted so a candidate
        that ships alongside the Studio Beta binary and has the newest mtime
        wins.
        """
        candidates: List[StudioCandidate] = []

        # 1. Environment variable override
        env_override = os.getenv("ROBLOX_STUDIO_MCP_PATH") or os.getenv("STUDIO_MCP_PATH")
        if env_override:
            p = Path(env_override)
            if p.is_file() and os.access(p, os.X_OK):
                return [
                    StudioCandidate(
                        executable_path=p,
                        version_dir=p.parent,
                        last_modified=p.stat().st_mtime,
                        has_studio_beta=True,
                    )
                ]
            elif p.is_dir():
                cand = p / ("StudioMCP.exe" if sys.platform == "win32" else "StudioMCP")
                if cand.is_file():
                    return [
                        StudioCandidate(
                            executable_path=cand,
                            version_dir=p,
                            last_modified=cand.stat().st_mtime,
                            has_studio_beta=True,
                        )
                    ]

        search_roots = []
        exe_name = "StudioMCP.exe" if sys.platform == "win32" else "StudioMCP"
        companion_name = "RobloxStudioBeta.exe" if sys.platform == "win32" else "RobloxStudio"

        home = Path.home()

        # Check LOCALAPPDATA if available in environment (Windows standard, Wine / test harnesses on Linux/macOS)
        local_appdata = os.getenv("LOCALAPPDATA")
        if local_appdata:
            search_roots.append(Path(local_appdata) / "Roblox" / "Versions")

        if sys.platform == "win32":
            prog_files = os.getenv("ProgramFiles", r"C:\Program Files")
            prog_files_x86 = os.getenv("ProgramFiles(x86)", r"C:\Program Files (x86)")

            search_roots.extend(
                [
                    Path(prog_files) / "Roblox" / "Versions",
                    Path(prog_files_x86) / "Roblox" / "Versions",
                ]
            )
        elif sys.platform == "darwin":
            search_roots.extend(
                [
                    Path("/Applications/RobloxStudio.app/Contents/MacOS"),
                    home / "Applications" / "RobloxStudio.app" / "Contents" / "MacOS",
                    home / "Library" / "Roblox" / "Versions",
                ]
            )
        else:
            search_roots.extend(
                [
                    home / ".local" / "share" / "roblox" / "Versions",
                    home / ".var" / "app" / "com.roblox.RobloxStudio" / "data" / "Roblox" / "Versions",
                    home / "Library" / "Roblox" / "Versions",
                ]
            )

        for root_path in search_roots:
            if not root_path.exists():
                continue

            # Check root directory
            direct_exe = root_path / exe_name
            if direct_exe.is_file():
                candidates.append(
                    StudioCandidate(
                        executable_path=direct_exe,
                        version_dir=root_path,
                        last_modified=direct_exe.stat().st_mtime,
                        has_studio_beta=(root_path / companion_name).is_file(),
                    )
                )

            # Check version subdirectories (e.g. version-xxxxxxxxxxxx)
            for version_folder in root_path.glob("version-*"):
                if version_folder.is_dir():
                    sub_exe = version_folder / exe_name
                    if sub_exe.is_file():
                        candidates.append(
                            StudioCandidate(
                                executable_path=sub_exe,
                                version_dir=version_folder,
                                last_modified=sub_exe.stat().st_mtime,
                                has_studio_beta=(version_folder / companion_name).is_file(),
                            )
                        )

        # Sort primarily by presence of companion Studio binary, secondarily by LastWriteTime (newest first)
        candidates.sort(key=lambda c: (c.has_studio_beta, c.last_modified), reverse=True)
        return candidates

    @classmethod
    def resolve_executable(cls) -> Path:
        """Return the best StudioMCP executable path, or raise ``FileNotFoundError``."""
        candidates = cls.get_all_candidates()
        if not candidates:
            raise FileNotFoundError(
                "Could not locate StudioMCP binary. Please verify Roblox Studio is installed "
                "with Beta Features -> Model Context Protocol enabled."
            )
        return candidates[0].executable_path
