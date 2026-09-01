"""Universal Roblox Studio MCP JSON-RPC 2.0 Bridge Server."""

import sys
import json
import signal
import threading
from typing import Dict, Any, Optional

from roblox_studio_mcp.core.protocol import (
    RequestIdDecoupler,
    make_jsonrpc_response,
    make_jsonrpc_error,
    MCP_PROTOCOL_VERSION,
    METHOD_NOT_FOUND,
    INVALID_REQUEST
)
from roblox_studio_mcp.core.resolver import RobloxStudioResolver
from roblox_studio_mcp.core.process import StudioMCPProcess
from roblox_studio_mcp.core.session import StudioSessionManager

class RobloxMCPBridge:
    """Universal MCP Bridge that multiplexes host client requests to StudioMCP.exe."""

    def __init__(self):
        # Configure UTF-8 stdio
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8")
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")

        self.decoupler = RequestIdDecoupler()
        self.resolver = RobloxStudioResolver()
        self.exe_path = self.resolver.resolve_executable()
        self.process = StudioMCPProcess(self.exe_path)
        self.session = StudioSessionManager(self.process, self.decoupler)
        self.init_result: Optional[Dict[str, Any]] = None
        self._stdout_lock = threading.Lock()

    def _write_stdout(self, payload: Dict[str, Any]):
        with self._stdout_lock:
            line = json.dumps(payload) + "\n"
            sys.stdout.write(line)
            sys.stdout.flush()

    def bootstrap_studiomcp(self):
        """Launches StudioMCP process and runs the internal initialization handshake."""
        self.process.start()
        
        # Internal initialize request
        init_id = self.decoupler.allocate_internal_id()
        init_res = self.process.send_request({
            "jsonrpc": "2.0",
            "id": init_id,
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": True}},
                "clientInfo": {"name": "universal_roblox_bridge", "version": "1.2.0"}
            }
        }, timeout=8.0)

        if init_res and "result" in init_res:
            self.init_result = init_res["result"]
        else:
            self.init_result = {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {"name": "RobloxStudio", "version": "1.2.0"},
                "instructions": "Roblox Studio MCP Bridge"
            }

        # Internal notifications/initialized
        self.process.send_notification({
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        })

    def run(self):
        """Runs the main stdio event loop."""
        self.bootstrap_studiomcp()

        # Handle process termination signals
        def _handle_exit(sig, frame):
            self.process.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, _handle_exit)
        signal.signal(signal.SIGTERM, _handle_exit)

        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                line_str = line.strip()
                if not line_str:
                    continue

                try:
                    req = json.loads(line_str)
                except Exception:
                    self._write_stdout(make_jsonrpc_error(None, -32700, "Parse error"))
                    continue

                if not isinstance(req, dict):
                    self._write_stdout(make_jsonrpc_error(None, INVALID_REQUEST, "Invalid Request"))
                    continue

                req_id = req.get("id")
                method = req.get("method")

                # Handle JSON-RPC methods
                if method == "initialize":
                    self._write_stdout(make_jsonrpc_response(req_id, self.init_result or {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {"tools": {"listChanged": True}},
                        "serverInfo": {"name": "RobloxStudio", "version": "1.2.0"}
                    }))

                elif method == "notifications/initialized":
                    pass  # Notification, no response needed

                elif method == "server/discover":
                    # Synthetic discovery probe response for modern IDEs
                    list_id = self.decoupler.allocate_internal_id()
                    list_res = self.process.send_request({
                        "jsonrpc": "2.0",
                        "id": list_id,
                        "method": "tools/list",
                        "params": {}
                    }, timeout=5.0)

                    tools_list = list_res.get("result", {}).get("tools", []) if list_res else []
                    self._write_stdout(make_jsonrpc_response(req_id, {
                        "tools": tools_list,
                        "serverInfo": {"name": "RobloxStudio", "version": "1.2.0"}
                    }))

                elif method == "ping":
                    self._write_stdout(make_jsonrpc_response(req_id, {}))

                elif method == "tools/list":
                    call_id = self.decoupler.allocate_internal_id()
                    res = self.process.send_request({
                        "jsonrpc": "2.0",
                        "id": call_id,
                        "method": "tools/list",
                        "params": req.get("params", {})
                    }, timeout=8.0)
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

                else:
                    # Forward other methods or return Method Not Found
                    call_id = self.decoupler.allocate_internal_id()
                    fwd_req = dict(req)
                    fwd_req["id"] = call_id
                    res = self.process.send_request(fwd_req, timeout=10.0)
                    if res and "result" in res:
                        self._write_stdout(make_jsonrpc_response(req_id, res["result"]))
                    elif res and "error" in res:
                        self._write_stdout(make_jsonrpc_error(req_id, res["error"].get("code", -32603), res["error"].get("message", "Internal Error")))
                    else:
                        self._write_stdout(make_jsonrpc_error(req_id, METHOD_NOT_FOUND, f"Method '{method}' not found"))

            except Exception as e:
                pass

        self.process.stop()
