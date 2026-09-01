"""Roblox Studio session resolution with self-healing reconnection.

The current ``StudioMCP`` protocol identifies the target Studio instance with a
``studio_id`` argument passed to every tool call (discovered via the
``list_roblox_studios`` tool). Older builds instead had a stateful
``set_active_studio`` binding step; that tool no longer exists, so this manager
discovers an id once, caches it, and injects it into outgoing tool-call
arguments. On a disconnect it drops the cache and re-discovers.
"""

import json
import threading
import time
from typing import Any, Dict, List, Optional

from roblox_studio_mcp.core._log import get_logger

logger = get_logger(__name__)

# Substring signatures (matched against the stringified tool result) that mean
# the bound Studio id is stale / gone and we should re-discover before retrying.
DISCONNECT_MARKERS = (
    "Not connected",
    "No active studio",
    "No Roblox Studio instances",
    "Connection lost",
    "Studio disconnected",
    "studio_id is required",
    "Studio not found",
    "Unknown studio",
    "Invalid studio",
)

# Tools that operate on the daemon itself, not on a specific Studio instance -
# they must not have a studio_id injected and do not need pre-resolution.
_SESSION_FREE_TOOLS = ("list_roblox_studios", "set_active_studio")


class StudioSessionManager:
    """Resolves and caches the target Studio id and injects it into tool calls."""

    def __init__(self, process_manager, id_decoupler):
        self.proc = process_manager
        self.id_decoupler = id_decoupler
        self.active_studio_id: Optional[str] = None
        self._lock = threading.Lock()

    def get_active_studio_id(self, force_refresh: bool = False) -> Optional[str]:
        """Return a usable Studio id, discovering one via ``list_roblox_studios``.

        Holds ``self._lock`` across the discovery round-trip so two threads do not
        race to pick different instances. ``execute_with_session`` intentionally
        does not take this lock, so there is no lock-ordering cycle; the worst
        case is a caller briefly waiting on an in-flight discovery.
        """
        with self._lock:
            if self.active_studio_id and not force_refresh:
                return self.active_studio_id

            call_id = self.id_decoupler.allocate_internal_id()
            res = self.proc.send_request(
                {
                    "jsonrpc": "2.0",
                    "id": call_id,
                    "method": "tools/call",
                    "params": {"name": "list_roblox_studios", "arguments": {}},
                },
                timeout=3.5,
            )

            if not res or res.get("error"):
                return None

            result_obj = res.get("result", {})
            if result_obj.get("isError"):
                return None

            content_text = ""
            for item in result_obj.get("content", []):
                if isinstance(item, dict) and item.get("type") == "text":
                    content_text = item.get("text", "{}")
                    break

            try:
                data = json.loads(content_text)
            except (ValueError, TypeError) as e:
                logger.debug("Failed to parse list_roblox_studios payload: %s", e)
                return None

            studios: List[Dict[str, Any]] = data.get("studios", []) if isinstance(data, dict) else []
            if not studios:
                return None

            # Prefer the first instance that reports an id (usually the only one).
            studio_id = next((s.get("id") for s in studios if isinstance(s, dict) and s.get("id")), None)
            if studio_id:
                self.active_studio_id = studio_id
                logger.debug("Resolved Studio id %s (%s)", studio_id, studios[0].get("name"))
            return studio_id

    def execute_with_session(self, tool_name: str, arguments: Dict[str, Any], max_retries: int = 3) -> Dict[str, Any]:
        """Forward a tool call, injecting the resolved ``studio_id`` and retrying on disconnect."""
        if tool_name in _SESSION_FREE_TOOLS:
            call_id = self.id_decoupler.allocate_internal_id()
            res = self.proc.send_request(
                {
                    "jsonrpc": "2.0",
                    "id": call_id,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments},
                }
            )
            return (
                res.get("result", {})
                if res
                else {
                    "isError": True,
                    "content": [{"type": "text", "text": "No response from StudioMCP"}],
                }
            )

        # The caller (host/model) may already have supplied a studio_id; only fill
        # it in when absent so we never override an explicit choice.
        caller_supplied_id = bool(isinstance(arguments, dict) and arguments.get("studio_id"))

        for attempt in range(max_retries):
            call_args = dict(arguments) if isinstance(arguments, dict) else {}

            if not caller_supplied_id:
                session_id = self.get_active_studio_id(force_refresh=(attempt > 0))
                if not session_id:
                    if attempt < max_retries - 1:
                        time.sleep(0.3 * (attempt + 1))
                        continue
                    # Last attempt: fall through and let StudioMCP return its own
                    # (informative) "no instances connected" error.
                else:
                    call_args["studio_id"] = session_id

            call_id = self.id_decoupler.allocate_internal_id()
            res = self.proc.send_request(
                {
                    "jsonrpc": "2.0",
                    "id": call_id,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": call_args},
                },
                timeout=15.0,
            )

            if not res:
                time.sleep(0.3)
                continue

            result = res.get("result", {})
            content_str = str(result.get("content", ""))

            if (
                not caller_supplied_id
                and result.get("isError")
                and any(marker in content_str for marker in DISCONNECT_MARKERS)
            ):
                logger.warning(
                    "Studio disconnect/stale-id for %r; re-resolving (attempt %d)",
                    tool_name,
                    attempt + 1,
                )
                self.active_studio_id = None
                time.sleep(0.4 * (attempt + 1))
                continue

            return result

        return {
            "isError": True,
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Error: Roblox Studio is not connected. Please ensure Roblox Studio "
                        "is open with a place loaded and the MCP server is enabled in "
                        "Studio's Assistant settings."
                    ),
                }
            ],
        }
