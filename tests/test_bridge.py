"""Tests for roblox_studio_mcp.core.bridge.RobloxMCPBridge.

The bridge reads ``sys.stdin`` / writes ``sys.stdout`` directly. The ``drive_bridge``
fixture (see conftest.py) swaps in ``io.StringIO`` streams, installs a fake process
via a monkeypatched resolver, feeds the given JSON-RPC lines through one full
``run()`` loop and returns the parsed output objects.
"""

import json

import pytest

from roblox_studio_mcp.core.protocol import (
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
)


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
