"""Shared diagnostic logging channel.

``stdout`` is reserved exclusively for the line-delimited JSON-RPC message
stream that the MCP host reads, so every diagnostic message emitted by this
package MUST go to ``stderr``.  Modules should call :func:`get_logger` instead
of ``print`` or bare ``logging.getLogger``.

Verbosity is controlled by the ``ROBLOX_STUDIO_MCP_LOG_LEVEL`` environment
variable (e.g. ``DEBUG``, ``INFO``, ``WARNING``); the default is ``WARNING`` so
a normal run stays quiet.
"""

import logging
import os
import sys
from typing import Optional

_ROOT_NAME = "roblox_studio_mcp"
_configured = False


def _configure() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger(_ROOT_NAME)
    level_name = os.environ.get("ROBLOX_STUDIO_MCP_LOG_LEVEL", "WARNING").upper()
    root.setLevel(getattr(logging, level_name, logging.WARNING))

    # Never attach to stdout: that is the JSON-RPC transport.
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.propagate = False


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a stderr-backed logger namespaced under ``roblox_studio_mcp``."""
    _configure()
    child = name.split(".")[-1] if name else None
    logger = logging.getLogger(_ROOT_NAME)
    return logger.getChild(child) if child else logger
