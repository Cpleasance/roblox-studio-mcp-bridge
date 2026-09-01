"""Roblox Studio session auto-binding with self-healing reconnection."""

import json
import threading
import time
from typing import Any, Dict, List, Optional

from roblox_studio_mcp.core._log import get_logger

logger = get_logger(__name__)

# Substring signatures that StudioMCP uses to report a dropped Studio connection.
# Matching is deliberately loose (substring on the stringified content) - brittle
# but adequate, and centralized here so it is easy to extend.
DISCONNECT_MARKERS = (
    "Not connected",
    "No active studio",
    "Connection lost",
    "Studio disconnected",
)


class StudioSessionManager:
    """Manages active Studio session binding and automatic reconnection recovery."""

    def __init__(self, process_manager, id_decoupler):
        self.proc = process_manager
        self.id_decoupler = id_decoupler
        self.active_studio_id: Optional[str] = None
        self._lock = threading.Lock()

    def get_active_studio_id(self, force_refresh: bool = False) -> Optional[str]:
        """Return the bound Studio id, discovering and binding one if needed.

        Holds ``self._lock`` across the discovery round-trips so two threads do
        not race to bind different Studio instances. ``execute_with_session``
        intentionally does not take this lock, so there is no lock-ordering
        cycle and no deadlock; the worst case is a caller waiting on the
        in-flight discovery, bounded by the ``send_request`` timeouts.
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
                studios: List[Dict[str, Any]] = data.get("studios", [])
                if not studios:
                    return None

                # Select active studio (prefer first available instance)
                target_studio = studios[0]
                studio_id = target_studio.get("id")

                if studio_id:
                    bind_id = self.id_decoupler.allocate_internal_id()
                    bind_res = self.proc.send_request(
                        {
                            "jsonrpc": "2.0",
                            "id": bind_id,
                            "method": "tools/call",
                            "params": {
                                "name": "set_active_studio",
                                "arguments": {"studio_id": studio_id},
                            },
                        },
                        timeout=3.5,
                    )

                    if bind_res and not bind_res.get("result", {}).get("isError", False):
                        self.active_studio_id = studio_id
                        return studio_id
            except (ValueError, TypeError) as e:
                logger.debug("Failed to parse list_roblox_studios payload: %s", e)

            return None

    def execute_with_session(self, tool_name: str, arguments: Dict[str, Any], max_retries: int = 3) -> Dict[str, Any]:
        """Executes a tool with automatic session verification and transparent retry upon disconnect."""
        # Session query tools do not need pre-binding
        if tool_name in ("list_roblox_studios", "set_active_studio"):
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

        for attempt in range(max_retries):
            session_id = self.get_active_studio_id(force_refresh=(attempt > 0))
            if not session_id and attempt < max_retries - 1:
                time.sleep(0.3 * (attempt + 1))
                continue

            call_id = self.id_decoupler.allocate_internal_id()
            res = self.proc.send_request(
                {
                    "jsonrpc": "2.0",
                    "id": call_id,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments},
                },
                timeout=15.0,
            )

            if not res:
                time.sleep(0.3)
                continue

            result = res.get("result", {})
            content_str = str(result.get("content", ""))

            # Detect disconnection signatures and retry after clearing the binding.
            if result.get("isError") and any(marker in content_str for marker in DISCONNECT_MARKERS):
                logger.warning(
                    "Studio disconnect detected for %r; rebinding (attempt %d)",
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
                        "is open with a Place loaded and Beta Features -> Model Context Protocol "
                        "is enabled."
                    ),
                }
            ],
        }
