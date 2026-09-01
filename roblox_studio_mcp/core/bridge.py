"""Universal Roblox Studio MCP JSON-RPC 2.0 bridge server.

Runs the stdio event loop that a host client (Claude Desktop, Cursor, ...) talks
to, and multiplexes those requests onto a single StudioMCP child process while
handling handshake quirks, id virtualization, and session rebinding.
"""

import json
import signal
import sys
import threading
from typing import Any, Dict, Optional

from roblox_studio_mcp.core._log import get_logger
from roblox_studio_mcp.core.process import StudioMCPProcess
from roblox_studio_mcp.core.protocol import (
    INTERNAL_ERROR,
    INVALID_REQUEST,
    MCP_PROTOCOL_VERSION,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    RequestIdDecoupler,
    make_jsonrpc_error,
    make_jsonrpc_response,
)
from roblox_studio_mcp.core.resolver import RobloxStudioResolver
from roblox_studio_mcp.core.session import StudioSessionManager

logger = get_logger(__name__)

_DEFAULT_INIT_RESULT = {
    "protocolVersion": MCP_PROTOCOL_VERSION,
    "capabilities": {"tools": {"listChanged": True}},
    "serverInfo": {"name": "RobloxStudio", "version": "1.2.0"},
}

# Server->client notifications that are safe and useful to relay from StudioMCP
# straight through to the host (they carry no id and no sensitive payload).
_FORWARDED_NOTIFICATIONS = frozenset(
    {
        "notifications/tools/list_changed",
        "notifications/resources/list_changed",
        "notifications/prompts/list_changed",
        "notifications/resources/updated",
    }
)

# StudioMCP holds tools/list open until a Studio instance registers its tools (or
# an internal timeout, ~8-10s, elapses). Wait longer than that so we capture the
# daemon's real answer instead of racing it.
_TOOLS_LIST_TIMEOUT = 12.0


class RobloxMCPBridge:
    """Universal MCP bridge that multiplexes host client requests to StudioMCP."""

    def __init__(self):
        # Configure UTF-8 stdio.
        for stream in (sys.stdin, sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                try:
                    stream.reconfigure(encoding="utf-8")
                except Exception as e:  # pragma: no cover - platform dependent
                    logger.debug("Could not reconfigure %r to utf-8: %s", stream, e)

        self.decoupler = RequestIdDecoupler()
        self.resolver = RobloxStudioResolver()
        # Executable resolution and process creation are deferred to bootstrap so
        # a "StudioMCP not found" condition can be reported cleanly rather than
        # crashing the constructor with a traceback.
        self.process: Optional[StudioMCPProcess] = None
        self.session: Optional[StudioSessionManager] = None
        self.init_result: Optional[Dict[str, Any]] = None
        self._stdout_lock = threading.Lock()

    def _write_stdout(self, payload: Dict[str, Any]) -> None:
        with self._stdout_lock:
            line = json.dumps(payload) + "\n"
            sys.stdout.write(line)
            sys.stdout.flush()

    def bootstrap_studiomcp(self) -> None:
        """Resolve StudioMCP, launch it, and run the internal initialize handshake."""
        exe_path = self.resolver.resolve_executable()  # may raise FileNotFoundError
        logger.info("Using StudioMCP executable: %s", exe_path)
        self.process = StudioMCPProcess(exe_path, on_notification=self._on_studio_notification)
        self.session = StudioSessionManager(self.process, self.decoupler)

        self.process.start()

        # Internal initialize request.
        init_id = self.decoupler.allocate_internal_id()
        init_res = self.process.send_request(
            {
                "jsonrpc": "2.0",
                "id": init_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": True}},
                    "clientInfo": {"name": "universal_roblox_bridge", "version": "1.2.0"},
                },
            },
            timeout=8.0,
        )

        if init_res and "result" in init_res:
            self.init_result = init_res["result"]
        else:
            logger.warning("StudioMCP initialize handshake returned no result; using defaults")
            self.init_result = dict(_DEFAULT_INIT_RESULT)
            self.init_result["instructions"] = "Roblox Studio MCP Bridge"

        # Internal notifications/initialized.
        self.process.send_notification({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _on_studio_notification(self, payload: Dict[str, Any]) -> None:
        """Relay selected server-initiated notifications from StudioMCP to the host.

        Most importantly ``notifications/tools/list_changed``: StudioMCP fires it
        when a Studio instance connects and registers its tools, which is how the
        host learns to re-request ``tools/list`` after starting up before Studio.
        """
        method = payload.get("method")
        if method in _FORWARDED_NOTIFICATIONS:
            logger.debug("Relaying StudioMCP notification: %s", method)
            self._write_stdout(
                {"jsonrpc": "2.0", "method": method, **({"params": payload["params"]} if "params" in payload else {})}
            )
        else:
            logger.debug("Dropping non-forwarded StudioMCP notification: %s", method)

    def _handle_exit(self, sig, frame):
        logger.info("Received signal %s; shutting down", sig)
        if self.process:
            self.process.stop()
        sys.exit(0)

    def _install_signal_handlers(self) -> None:
        """Best-effort signal handlers.

        ``signal.signal`` only works on the main thread and not every signal
        exists on every platform (notably ``SIGTERM`` handling under some Windows
        contexts, and ``SIGBREAK`` being Windows-only), so each install is guarded.
        """
        if threading.current_thread() is not threading.main_thread():
            logger.debug("Not on main thread; skipping signal handler installation")
            return
        for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
            sig = getattr(signal, name, None)
            if sig is None:
                continue
            try:
                signal.signal(sig, self._handle_exit)
            except (ValueError, OSError, RuntimeError) as e:
                logger.debug("Could not install %s handler: %s", name, e)

    def run(self) -> None:
        """Run the main stdio event loop until stdin closes or a signal arrives."""
        try:
            self.bootstrap_studiomcp()
        except FileNotFoundError as e:
            sys.stderr.write(f"[roblox-studio-mcp] {e}\n")
            sys.stderr.write(
                "[roblox-studio-mcp] Open Roblox Studio, enable File > Beta Features > "
                "Model Context Protocol, then retry. You can also set "
                "ROBLOX_STUDIO_MCP_PATH to the StudioMCP executable.\n"
            )
            sys.stderr.flush()
            sys.exit(1)
        except Exception as e:
            logger.error("Failed to start StudioMCP bridge: %s", e, exc_info=True)
            sys.stderr.write(f"[roblox-studio-mcp] Failed to start: {e}\n")
            sys.stderr.flush()
            sys.exit(1)

        self._install_signal_handlers()

        try:
            self._serve_forever()
        finally:
            if self.process:
                self.process.stop()

    def _serve_forever(self) -> None:
        while True:
            req_id: Any = None
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                line_str = line.strip()
                if not line_str:
                    continue

                try:
                    req = json.loads(line_str)
                except ValueError:
                    self._write_stdout(make_jsonrpc_error(None, PARSE_ERROR, "Parse error"))
                    continue

                if not isinstance(req, dict):
                    self._write_stdout(make_jsonrpc_error(None, INVALID_REQUEST, "Invalid Request"))
                    continue

                req_id = req.get("id")
                method = req.get("method")

                self._dispatch(req, req_id, method)

            except Exception as e:
                # A failed request must still produce a response, otherwise the
                # host blocks forever waiting on an id it will never see.
                logger.warning("Error handling request id=%r: %s", req_id, e, exc_info=True)
                if req_id is not None:
                    try:
                        self._write_stdout(make_jsonrpc_error(req_id, INTERNAL_ERROR, f"Internal error: {e}"))
                    except Exception:
                        logger.error("Failed to send error response for id=%r", req_id, exc_info=True)

    def _dispatch(self, req: Dict[str, Any], req_id: Any, method: Optional[str]) -> None:
        assert self.process is not None and self.session is not None

        if method == "initialize":
            self._write_stdout(make_jsonrpc_response(req_id, self.init_result or dict(_DEFAULT_INIT_RESULT)))

        elif method == "notifications/initialized":
            pass  # Notification, no response needed.

        elif method == "server/discover":
            list_id = self.decoupler.allocate_internal_id()
            list_res = self.process.send_request(
                {"jsonrpc": "2.0", "id": list_id, "method": "tools/list", "params": {}},
                timeout=_TOOLS_LIST_TIMEOUT,
            )
            tools_list = list_res.get("result", {}).get("tools", []) if list_res else []
            self._write_stdout(
                make_jsonrpc_response(
                    req_id,
                    {
                        "tools": tools_list,
                        "serverInfo": {"name": "RobloxStudio", "version": "1.2.0"},
                    },
                )
            )

        elif method == "ping":
            self._write_stdout(make_jsonrpc_response(req_id, {}))

        elif method == "tools/list":
            call_id = self.decoupler.allocate_internal_id()
            res = self.process.send_request(
                {
                    "jsonrpc": "2.0",
                    "id": call_id,
                    "method": "tools/list",
                    "params": req.get("params", {}),
                },
                timeout=_TOOLS_LIST_TIMEOUT,
            )
            result_payload = res.get("result", {"tools": []}) if res else {"tools": []}
            self._write_stdout(make_jsonrpc_response(req_id, result_payload))

        elif method == "tools/call":
            params = req.get("params", {})
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = self.session.execute_with_session(tool_name, arguments)
            self._write_stdout(make_jsonrpc_response(req_id, result))

        elif method in ("resources/list", "prompts/list"):
            self._write_stdout(make_jsonrpc_response(req_id, {method.split("/")[0]: []}))

        elif req_id is None:
            # Unknown notification: nothing to answer.
            logger.debug("Ignoring unknown notification: %s", method)

        else:
            # Forward other methods, or return Method Not Found.
            call_id = self.decoupler.allocate_internal_id()
            fwd_req = dict(req)
            fwd_req["id"] = call_id
            res = self.process.send_request(fwd_req, timeout=10.0)
            if res and "result" in res:
                self._write_stdout(make_jsonrpc_response(req_id, res["result"]))
            elif res and "error" in res:
                self._write_stdout(
                    make_jsonrpc_error(
                        req_id,
                        res["error"].get("code", INTERNAL_ERROR),
                        res["error"].get("message", "Internal Error"),
                    )
                )
            else:
                self._write_stdout(make_jsonrpc_error(req_id, METHOD_NOT_FOUND, f"Method '{method}' not found"))
