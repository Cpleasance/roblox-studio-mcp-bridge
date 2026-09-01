"""Multi-path LastWriteTime StudioMCP executable resolver."""

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class StudioCandidate:
    executable_path: Path
    version_dir: Path
    last_modified: float
    has_studio_beta: bool


class RobloxStudioResolver:
    """Discovers all StudioMCP binaries across user, system, and custom paths."""

    @staticmethod
    def _resolve(path: Path) -> Path:
        """Best-effort ``Path.resolve`` that never raises."""
        try:
            return path.resolve()
        except (OSError, RuntimeError):
            return path

    @classmethod
    def _candidate_at(
        cls, exe_dir: Path, exe_name: str, companion_name: str, seen_exes: set
    ) -> Optional[StudioCandidate]:
        """Return a candidate for ``exe_dir/exe_name`` if it exists and is new."""
        exe = exe_dir / exe_name
        if not exe.is_file():
            return None
        resolved = cls._resolve(exe)
        if resolved in seen_exes:
            return None
        seen_exes.add(resolved)
        return StudioCandidate(
            executable_path=exe,
            version_dir=exe_dir,
            last_modified=exe.stat().st_mtime,
            has_studio_beta=(exe_dir / companion_name).is_file(),
        )

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
            if p.is_file():
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

        # Deduplicate search roots while preserving priority order
        deduped_roots: List[Path] = []
        seen_roots = set()
        for root in search_roots:
            resolved_root = cls._resolve(root)
            if resolved_root not in seen_roots:
                seen_roots.add(resolved_root)
                deduped_roots.append(root)

        seen_exes: set = set()
        for root_path in deduped_roots:
            if not root_path.exists():
                continue

            # Check the root directory itself, then each version-* subdirectory.
            search_dirs = [root_path]
            search_dirs.extend(d for d in root_path.glob("version-*") if d.is_dir())
            for exe_dir in search_dirs:
                cand = cls._candidate_at(exe_dir, exe_name, companion_name, seen_exes)
                if cand is not None:
                    candidates.append(cand)

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
