"""Tests for roblox_studio_mcp.core.bridge.RobloxMCPBridge.

The bridge reads ``sys.stdin`` / writes ``sys.stdout`` directly. The ``drive_bridge``
fixture (see conftest.py) swaps in ``io.StringIO`` streams, installs a fake process
via a monkeypatched resolver, feeds the given JSON-RPC lines through one full
``run()`` loop and returns the parsed output objects.
"""

import io
import json
import sys
from pathlib import Path

import pytest

from roblox_studio_mcp.core.protocol import (
    INTERNAL_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
)


@pytest.fixture(autouse=True)
def mcp_bat_repair_calls(monkeypatch):
    """Record (and neutralise) the bridge's mcp.bat self-heal so no test touches
    the real ``%LOCALAPPDATA%\\Roblox\\mcp.bat``. Yields the call list."""
    from roblox_studio_mcp.core import batfix

    calls = []
    monkeypatch.setattr(
        batfix, "repair_roblox_launchers", lambda *a, **k: calls.append(True) or []
    )
    return calls


def _line(obj):
    return json.dumps(obj)


def default_responder(payload):
    """A permissive StudioMCP stand-in."""
    method = payload.get("method")
    if method == "initialize":
        return {"result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "StudioMCP"}}}
    if method == "tools/list":
        return {"result": {"tools": [{"name": "insert_model"}, {"name": "run_code"}]}}
    return None


class TestInitialize:
    def test_initialize_uses_bootstrapped_result(self, drive_bridge):
        out, proc, _ = drive_bridge(
            [_line({"jsonrpc": "2.0", "id": 1, "method": "initialize"})],
            responder=default_responder,
        )
        assert len(out) == 1
        assert out[0]["jsonrpc"] == "2.0"
        assert out[0]["id"] == 1
        assert out[0]["result"]["protocolVersion"] == "2024-11-05"
        assert proc.started is True
        assert proc.stopped is True

    def test_initialize_falls_back_to_default_when_studio_silent(self, drive_bridge):
        out, _, _ = drive_bridge(
            [_line({"jsonrpc": "2.0", "id": "a", "method": "initialize"})],
            responder=lambda p: None,
        )
        assert out[0]["id"] == "a"
        assert out[0]["result"]["protocolVersion"] == "2024-11-05"
        assert "serverInfo" in out[0]["result"]


class TestNotificationsAndPing:
    def test_notifications_initialized_produces_no_response(self, drive_bridge):
        out, _, _ = drive_bridge(
            [_line({"jsonrpc": "2.0", "method": "notifications/initialized"})],
            responder=default_responder,
        )
        assert out == []

    def test_ping_returns_empty_result(self, drive_bridge):
        out, _, _ = drive_bridge(
            [_line({"jsonrpc": "2.0", "id": 42, "method": "ping"})],
            responder=default_responder,
        )
        assert out == [{"jsonrpc": "2.0", "id": 42, "result": {}}]

    def test_blank_lines_are_skipped(self, drive_bridge):
        out, _, _ = drive_bridge(
            ["", "   ", _line({"jsonrpc": "2.0", "id": 1, "method": "ping"})],
            responder=default_responder,
        )
        assert out == [{"jsonrpc": "2.0", "id": 1, "result": {}}]

    def test_unknown_notification_is_dropped_not_forwarded(self, drive_bridge):
        # An id-less request for a method not in the dispatch table must be
        # silently dropped - never answered and never relayed to StudioMCP.
        out, proc, _ = drive_bridge(
            [_line({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 7}})],
            responder=default_responder,
        )
        assert out == []
        assert proc.requests_for("notifications/cancelled") == []


class TestToolsList:
    def test_tools_list_proxied_from_studio(self, drive_bridge):
        out, proc, _ = drive_bridge(
            [_line({"jsonrpc": "2.0", "id": 5, "method": "tools/list", "params": {}})],
            responder=default_responder,
        )
        assert out[0]["id"] == 5
        assert [t["name"] for t in out[0]["result"]["tools"]] == ["insert_model", "run_code"]
        # internal request used a decoupled id, not the host id
        internal = proc.requests_for("tools/list")[-1]
        assert internal["id"] != 5
        assert internal["id"] >= 100001

    def test_tools_list_empty_when_studio_silent(self, drive_bridge):
        out, _, _ = drive_bridge(
            [_line({"jsonrpc": "2.0", "id": 6, "method": "tools/list"})],
            responder=lambda p: None,
        )
        assert out[0]["result"] == {"tools": []}


class TestToolsCall:
    def test_tools_call_routed_through_session_manager(self, drive_bridge):
        # Exercises the _HANDLERS "tools/call" entry: the bridge must hand the
        # call to the session manager and return its result under the host id.
        def responder(p):
            if p.get("method") == "tools/call" and p.get("params", {}).get("name") == "list_roblox_studios":
                return {"result": {"content": [{"type": "text", "text": "{}"}]}}
            return default_responder(p)

        out, proc, _ = drive_bridge(
            [
                _line(
                    {
                        "jsonrpc": "2.0",
                        "id": 11,
                        "method": "tools/call",
                        "params": {"name": "list_roblox_studios", "arguments": {}},
                    }
                )
            ],
            responder=responder,
        )
        assert out[0]["id"] == 11
        assert out[0]["result"] == {"content": [{"type": "text", "text": "{}"}]}
        assert proc.tool_calls_for("list_roblox_studios")


class TestServerDiscover:
    def test_server_discover_synthesises_probe_response(self, drive_bridge):
        out, _, _ = drive_bridge(
            [_line({"jsonrpc": "2.0", "id": 9, "method": "server/discover"})],
            responder=default_responder,
        )
        assert out[0]["id"] == 9
        assert [t["name"] for t in out[0]["result"]["tools"]] == ["insert_model", "run_code"]
        assert out[0]["result"]["serverInfo"]["name"] == "RobloxStudio"

    def test_server_discover_tolerates_silent_studio(self, drive_bridge):
        out, _, _ = drive_bridge(
            [_line({"jsonrpc": "2.0", "id": 9, "method": "server/discover"})],
            responder=lambda p: None if p.get("method") == "tools/list" else default_responder(p),
        )
        assert out[0]["result"]["tools"] == []


class TestListEndpoints:
    @pytest.mark.parametrize(
        "method,key",
        [("resources/list", "resources"), ("prompts/list", "prompts")],
    )
    def test_empty_list_endpoints(self, drive_bridge, method, key):
        out, _, _ = drive_bridge(
            [_line({"jsonrpc": "2.0", "id": 3, "method": method})],
            responder=default_responder,
        )
        assert out[0]["result"] == {key: []}


class TestErrorHandling:
    def test_malformed_json_line_returns_parse_error(self, drive_bridge):
        out, _, _ = drive_bridge(["{not valid json"], responder=default_responder)
        assert out[0]["error"]["code"] == PARSE_ERROR
        assert out[0]["id"] is None
        assert "data" not in out[0]["error"]

    @pytest.mark.parametrize("payload", ["123", '"a string"', "[1, 2, 3]", "true", "null"])
    def test_non_dict_payload_returns_invalid_request(self, drive_bridge, payload):
        out, _, _ = drive_bridge([payload], responder=default_responder)
        assert out[0]["error"]["code"] == INVALID_REQUEST
        assert out[0]["id"] is None

    def test_unknown_method_forwarded_then_method_not_found(self, drive_bridge):
        out, proc, _ = drive_bridge(
            [_line({"jsonrpc": "2.0", "id": 77, "method": "totally/unknown"})],
            responder=lambda p: None,
        )
        assert out[0]["id"] == 77
        assert out[0]["error"]["code"] == METHOD_NOT_FOUND
        assert "totally/unknown" in out[0]["error"]["message"]
        # was forwarded with a decoupled id
        fwd = proc.requests_for("totally/unknown")
        assert len(fwd) == 1 and fwd[0]["id"] >= 100001

    def test_non_string_method_is_forwarded_not_crashed(self, drive_bridge):
        # A spec-violating non-string `method` must not blow up the _HANDLERS
        # lookup; with an id it falls through to the forward/METHOD_NOT_FOUND path.
        out, proc, _ = drive_bridge(
            [_line({"jsonrpc": "2.0", "id": 12, "method": ["not", "a", "string"]})],
            responder=lambda p: None,
        )
        assert out[0]["id"] == 12
        assert out[0]["error"]["code"] == METHOD_NOT_FOUND

    def test_non_string_method_notification_is_dropped(self, drive_bridge):
        out, _, _ = drive_bridge(
            [_line({"jsonrpc": "2.0", "method": {"weird": True}})],
            responder=default_responder,
        )
        assert out == []

    def test_unknown_method_returns_studio_result_when_available(self, drive_bridge):
        out, _, _ = drive_bridge(
            [_line({"jsonrpc": "2.0", "id": 8, "method": "custom/thing"})],
            responder=lambda p: {"result": {"ok": True}} if p.get("method") == "custom/thing" else default_responder(p),
        )
        assert out[0] == {"jsonrpc": "2.0", "id": 8, "result": {"ok": True}}

    def test_unknown_method_propagates_studio_error(self, drive_bridge):
        out, _, _ = drive_bridge(
            [_line({"jsonrpc": "2.0", "id": 8, "method": "custom/thing"})],
            responder=lambda p: (
                {"error": {"code": -32050, "message": "boom"}}
                if p.get("method") == "custom/thing"
                else default_responder(p)
            ),
        )
        assert out[0]["error"] == {"code": -32050, "message": "boom"}


class TestServeForeverHandlerException:
    """A handler that raises mid-request must not desync the stream: a request
    with an id still gets a -32603, an id-less notification stays silent."""

    @staticmethod
    def _responder_ok_init_then_boom(p):
        if p.get("method") == "initialize":
            return {"result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "StudioMCP"}}}
        raise RuntimeError("handler exploded")

    def test_request_with_id_still_gets_internal_error(self, drive_bridge):
        out, _, _ = drive_bridge(
            [_line({"jsonrpc": "2.0", "id": 5, "method": "tools/list"})],
            responder=self._responder_ok_init_then_boom,
        )
        assert len(out) == 1
        assert out[0]["id"] == 5
        assert out[0]["error"]["code"] == INTERNAL_ERROR
        assert "handler exploded" in out[0]["error"]["message"]

    def test_idless_notification_failure_is_swallowed(self, drive_bridge):
        # tools/list with no id routes to the same handler; when it raises there
        # is no id to answer, so nothing must be written.
        out, _, _ = drive_bridge(
            [_line({"jsonrpc": "2.0", "method": "tools/list"})],
            responder=self._responder_ok_init_then_boom,
        )
        assert out == []

    def test_stream_stays_in_sync_after_a_failed_request(self, drive_bridge):
        def responder(p):
            if p.get("method") == "initialize":
                return {"result": {"protocolVersion": "2024-11-05"}}
            if p.get("method") == "tools/list":
                raise RuntimeError("boom")
            return None

        out, _, _ = drive_bridge(
            [
                _line({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
                _line({"jsonrpc": "2.0", "id": 2, "method": "ping"}),
            ],
            responder=responder,
        )
        assert [m["id"] for m in out] == [1, 2]
        assert out[0]["error"]["code"] == INTERNAL_ERROR
        assert out[1]["result"] == {}


class TestBootstrapFailureExit:
    """``run()`` must turn a failed StudioMCP bootstrap into a clean stderr
    message + ``exit(1)`` rather than a traceback."""

    @staticmethod
    def _prep(monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))
        out, err = io.StringIO(), io.StringIO()
        monkeypatch.setattr(sys, "stdout", out)
        monkeypatch.setattr(sys, "stderr", err)
        return err

    def test_missing_executable_prints_beta_hint_and_exits_1(self, monkeypatch):
        from roblox_studio_mcp.core import bridge as bridge_mod

        monkeypatch.setattr(
            bridge_mod.MCPConfigInjector, "scrub", staticmethod(lambda: [])
        )
        monkeypatch.setattr(
            bridge_mod.RobloxStudioResolver,
            "resolve_executable",
            classmethod(lambda cls: (_ for _ in ()).throw(FileNotFoundError("Could not locate StudioMCP binary"))),
        )
        err = self._prep(monkeypatch)

        b = bridge_mod.RobloxMCPBridge()
        with pytest.raises(SystemExit) as exc:
            b.run()

        assert exc.value.code == 1
        text = err.getvalue()
        assert "Could not locate StudioMCP binary" in text
        assert "Beta Features" in text
        assert "ROBLOX_STUDIO_MCP_PATH" in text

    def test_generic_startup_failure_prints_reason_and_exits_1(self, monkeypatch):
        from roblox_studio_mcp.core import bridge as bridge_mod

        monkeypatch.setattr(
            bridge_mod.MCPConfigInjector, "scrub", staticmethod(lambda: [])
        )
        monkeypatch.setattr(
            bridge_mod.RobloxStudioResolver,
            "resolve_executable",
            classmethod(lambda cls: Path("fake") / "StudioMCP.exe"),
        )

        def _boom_ctor(*_a, **_kw):
            raise RuntimeError("spawn failed: EACCES")

        monkeypatch.setattr(bridge_mod, "StudioMCPProcess", _boom_ctor)
        err = self._prep(monkeypatch)

        b = bridge_mod.RobloxMCPBridge()
        with pytest.raises(SystemExit) as exc:
            b.run()

        assert exc.value.code == 1
        text = err.getvalue()
        assert "Failed to start" in text
        assert "spawn failed: EACCES" in text


class TestStudioNotificationRelay:
    """StudioMCP pushes id-less notifications (e.g. tools/list_changed when a
    Studio instance connects); the bridge must relay the useful ones to the host."""

    def _bridge(self):
        from roblox_studio_mcp.core import bridge as bridge_mod

        b = bridge_mod.RobloxMCPBridge()
        sent = []
        b._write_stdout = lambda payload: sent.append(payload)
        return b, sent

    def test_forwards_tools_list_changed(self):
        b, sent = self._bridge()
        b._on_studio_notification({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"})
        assert sent == [{"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}]

    def test_forwards_params_when_present(self):
        b, sent = self._bridge()
        b._on_studio_notification(
            {"jsonrpc": "2.0", "method": "notifications/resources/updated", "params": {"uri": "x"}}
        )
        assert sent == [{"jsonrpc": "2.0", "method": "notifications/resources/updated", "params": {"uri": "x"}}]

    def test_drops_unlisted_notification(self):
        b, sent = self._bridge()
        b._on_studio_notification({"jsonrpc": "2.0", "method": "notifications/message", "params": {"x": 1}})
        assert sent == []

    def test_process_manager_dispatches_notifications_to_callback(self):
        import io

        from roblox_studio_mcp.core import process as process_mod

        seen = []
        pm = process_mod.StudioMCPProcess("fake", on_notification=seen.append)
        pm._running = True

        class _Proc:
            stdout = io.StringIO(
                '{"jsonrpc":"2.0","method":"notifications/tools/list_changed"}\n'
                '{"jsonrpc":"2.0","id":5,"result":{"ok":true}}\n'
            )
            stderr = io.StringIO("")

        pm.proc = _Proc()
        pm._stdout_reader_loop()
        assert seen == [{"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}]


class TestMultipleMessages:
    def test_sequential_messages_each_answered(self, drive_bridge):
        out, _, _ = drive_bridge(
            [
                _line({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
                _line({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                _line({"jsonrpc": "2.0", "id": 2, "method": "ping"}),
                _line({"jsonrpc": "2.0", "id": 3, "method": "tools/list"}),
            ],
            responder=default_responder,
        )
        assert [m["id"] for m in out] == [1, 2, 3]


class TestAutoScrub:
    """run() must call MCPConfigInjector.scrub() before bootstrapping so that
    mcp.bat entries re-added by a Studio update are removed automatically."""

    def test_scrub_called_on_run(self, drive_bridge, monkeypatch):
        from roblox_studio_mcp.core import bridge as bridge_mod

        scrub_calls = []
        monkeypatch.setattr(
            bridge_mod.MCPConfigInjector,
            "scrub",
            staticmethod(lambda: scrub_calls.append(True) or []),
        )
        drive_bridge([_line({"jsonrpc": "2.0", "id": 1, "method": "ping"})], responder=default_responder)
        assert scrub_calls, "scrub() was not called during run()"

    def test_scrub_failure_does_not_crash_bridge(self, drive_bridge, monkeypatch):
        """A broken scrub must never prevent the bridge from starting."""
        from roblox_studio_mcp.core import bridge as bridge_mod

        monkeypatch.setattr(
            bridge_mod.MCPConfigInjector,
            "scrub",
            staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("disk full"))),
        )
        # Bridge should still start and answer requests normally.
        out, _, _ = drive_bridge(
            [_line({"jsonrpc": "2.0", "id": 99, "method": "ping"})],
            responder=default_responder,
        )
        assert out == [{"jsonrpc": "2.0", "id": 99, "result": {}}]


class TestAutoRepairLauncher:
    """run() also repairs Roblox's broken mcp.bat launcher on startup."""

    def test_repair_called_on_run(self, drive_bridge, mcp_bat_repair_calls):
        drive_bridge(
            [_line({"jsonrpc": "2.0", "id": 1, "method": "ping"})], responder=default_responder
        )
        assert mcp_bat_repair_calls, "repair_roblox_launchers() was not called during run()"

    def test_repair_failure_does_not_crash_bridge(self, drive_bridge, monkeypatch):
        from roblox_studio_mcp.core import batfix

        monkeypatch.setattr(
            batfix,
            "repair_roblox_launchers",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("read-only fs")),
        )
        out, _, _ = drive_bridge(
            [_line({"jsonrpc": "2.0", "id": 7, "method": "ping"})], responder=default_responder
        )
        assert out == [{"jsonrpc": "2.0", "id": 7, "result": {}}]
