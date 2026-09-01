"""Repair Roblox Studio's broken ``mcp.bat`` launcher in place.

Roblox Studio's *Model Context Protocol* beta feature writes a launcher script to
``%LOCALAPPDATA%\\Roblox\\mcp.bat`` and points every IDE config it touches at
``cmd.exe /c ...\\mcp.bat``. That script is malformed:

    @echo off
    if exist "...\\version-<hash>\\StudioMCP.exe" ( "...\\StudioMCP.exe" %* )
    else (for /f "tokens=2*" %%A in ('reg query ...ContentFolder') do (
    "%%B/..\\StudioMCP.exe" %*
    ))

The ``)`` that closes the ``if`` and the ``else`` sit on separate lines, which
``cmd.exe`` rejects - it runs ``if exist X ( ... )`` as a complete statement and
then chokes on ``else`` ("'else' is not recognized as an internal or external
command"), on the bare ``"%B/..\\StudioMCP.exe"`` (``%%B`` collapses to ``%B``
outside the ``for``), and on the trailing ``)``. It only surfaces when the first
``if exist`` path is stale - i.e. right after any Studio version update - so it
hits users seemingly at random.

The bridge's own IDE entry (``python -m roblox_studio_mcp run``) sidesteps this
completely, but users who followed Roblox's own setup docs, or whose IDE Roblox
wrote into directly, still get the broken launcher. This module rewrites that
launcher with a correct, version-independent equivalent (newest ``StudioMCP.exe``
under ``...\\Roblox\\Versions``, with the registry ``ContentFolder`` value as a
fallback) and keeps the original as ``mcp.bat.roblox-bak``. It is idempotent and
re-applies itself after a Studio update overwrites the file again.
"""

import os
import sys
from pathlib import Path
from typing import List, Optional

from roblox_studio_mcp.core._log import get_logger

logger = get_logger(__name__)

# Marker line embedded in every launcher we generate. Its presence means "this
# file is already ours" and repair() leaves it untouched.
MANAGED_MARKER = "roblox-studio-mcp-bridge managed launcher"

_SCHEMA = 1

# The corrected Windows launcher. Every control-flow token that Roblox split
# across lines is kept on one line here; resolution is version-independent.
_WINDOWS_BODY = r"""@echo off
@rem ===========================================================================
@rem  {marker} (schema {schema})
@rem
@rem  Roblox Studio's original mcp.bat had a multi-line if/else that cmd.exe
@rem  cannot parse; it broke every time the hard-coded Studio version path went
@rem  stale. roblox-studio-mcp-bridge regenerated this file with a correct,
@rem  version-independent equivalent. Your original is saved beside this file as
@rem  mcp.bat.roblox-bak - delete that backup to stop the bridge managing this
@rem  script, or run  roblox-studio-mcp eject  to restore it.
@rem ===========================================================================
setlocal enableextensions
set "RSMCP="

for /f "delims=" %%D in ('dir /b /ad /o-d "%LOCALAPPDATA%\Roblox\Versions" 2^>nul') do (
    if not defined RSMCP if exist "%LOCALAPPDATA%\Roblox\Versions\%%D\StudioMCP.exe" (
        set "RSMCP=%LOCALAPPDATA%\Roblox\Versions\%%D\StudioMCP.exe"
    )
)

if not defined RSMCP (
    for /f "tokens=2*" %%A in ('reg query "HKCU\Software\Roblox\RobloxStudio" /v ContentFolder 2^>nul') do (
        if exist "%%B\..\StudioMCP.exe" set "RSMCP=%%B\..\StudioMCP.exe"
    )
)

if not defined RSMCP (
    >&2 echo [roblox-studio-mcp-bridge] StudioMCP.exe not found. In Roblox Studio, enable
    >&2 echo [roblox-studio-mcp-bridge] File ^> Beta Features ^> Model Context Protocol, then restart Studio.
    exit /b 1
)

"%RSMCP%" %*
exit /b %errorlevel%
""".replace("{marker}", MANAGED_MARKER).replace("{schema}", str(_SCHEMA))


def _local_appdata(base: Optional[Path]) -> Optional[Path]:
    if base is not None:
        return Path(base)
    raw = os.environ.get("LOCALAPPDATA")
    return Path(raw) if raw else None


def launcher_path(base: Optional[Path] = None) -> Optional[Path]:
    """Absolute path to Roblox's ``mcp.bat``, or ``None`` when it can't be located.

    ``base`` overrides ``%LOCALAPPDATA%`` (used by the tests). Returns a path even
    when the file does not exist yet - callers check ``.exists()`` themselves.
    """
    if sys.platform != "win32" and base is None:
        # The broken launcher is a Windows-only artefact; macOS points IDE
        # configs straight at the StudioMCP binary (handled by entry scrubbing).
        return None
    root = _local_appdata(base)
    if root is None:
        return None
    return root / "Roblox" / "mcp.bat"


def is_bridge_managed(text: str) -> bool:
    """True when ``text`` is a launcher this module generated."""
    return MANAGED_MARKER in text


def is_broken_roblox_launcher(text: str) -> bool:
    """Heuristic: does ``text`` look like Roblox's un-parseable mcp.bat?

    The signature is an ``else`` that is not preceded by its ``)`` on the same
    line - exactly what makes ``cmd.exe`` reject the script.
    """
    if is_bridge_managed(text):
        return False
    for line in text.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith("else ") or stripped == "else" or stripped.startswith("else("):
            return True
    return False


def repair_roblox_launchers(
    base: Optional[Path] = None, *, force: bool = True, strict: bool = False
) -> List[str]:
    """Rewrite Roblox's ``mcp.bat`` with a correct launcher; return paths changed.

    - No file present -> ``[]`` (the bridge's own IDE entry already covers this).
    - Already bridge-managed -> ``[]`` (idempotent).
    - Otherwise the original is backed up to ``mcp.bat.roblox-bak`` (once) and the
      file is replaced. With ``force=False`` a launcher that still parses is left
      alone; the default rewrites unconditionally because Roblox's version is
      always the broken multi-line form and ours is strictly a superset.

    ``strict=False`` (the bridge's startup self-heal) swallows and logs every
    filesystem error so a failed repair can never take the stdio server down.
    ``strict=True`` (the CLI) re-raises instead, so the failure reaches the user.
    """
    path = launcher_path(base)
    if path is None:
        return []

    try:
        if not path.is_file():
            return []
        original = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.warning("mcp.bat repair: cannot read %s (%s)", path, e)
        if strict:
            raise
        return []

    if is_bridge_managed(original):
        return []
    if not force and not is_broken_roblox_launcher(original):
        logger.debug("mcp.bat repair: %s still parses and force=False; leaving it", path)
        return []

    backup = path.with_name(path.name + ".roblox-bak")
    try:
        if not backup.exists():
            backup.write_text(original, encoding="utf-8")
        tmp = path.with_name(path.name + ".bridge-tmp")
        # A .bat must be CRLF regardless of the host writing it.
        with open(tmp, "w", encoding="utf-8", newline="\r\n") as fh:
            fh.write(_WINDOWS_BODY)
        tmp.replace(path)
    except OSError as e:
        logger.warning("mcp.bat repair: failed to rewrite %s (%s)", path, e)
        if strict:
            raise
        return []

    logger.info(
        "Repaired Roblox's broken mcp.bat at %s (original saved as %s)", path, backup.name
    )
    return [str(path)]


def restore_roblox_launchers(base: Optional[Path] = None, *, strict: bool = False) -> List[str]:
    """Put Roblox's original ``mcp.bat`` back from ``mcp.bat.roblox-bak``.

    Used by ``eject``. Returns the paths restored. ``strict`` behaves as in
    :func:`repair_roblox_launchers`.
    """
    path = launcher_path(base)
    if path is None:
        return []
    backup = path.with_name(path.name + ".roblox-bak")
    try:
        if not backup.is_file():
            return []
        if path.is_file() and not is_bridge_managed(path.read_text(encoding="utf-8", errors="replace")):
            # User (or Studio) already replaced our managed copy - don't clobber it.
            return []
        path.write_text(backup.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        backup.unlink()
    except OSError as e:
        logger.warning("mcp.bat restore: failed for %s (%s)", path, e)
        if strict:
            raise
        return []
    logger.info("Restored Roblox's original mcp.bat at %s", path)
    return [str(path)]


def launcher_status(base: Optional[Path] = None) -> str:
    """One of ``"absent"``, ``"managed"``, ``"broken"``, ``"ok"`` for ``doctor``."""
    path = launcher_path(base)
    if path is None or not path.is_file():
        return "absent"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "absent"
    if is_bridge_managed(text):
        return "managed"
    if is_broken_roblox_launcher(text):
        return "broken"
    return "ok"
