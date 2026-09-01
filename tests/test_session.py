"""Tests for roblox_studio_mcp.core.session.StudioSessionManager."""

import json

import pytest

from roblox_studio_mcp.core.protocol import RequestIdDecoupler
from roblox_studio_mcp.core.session import StudioSessionManager

NOT_CONNECTED_SNIPPET = "Roblox Studio is not connected"


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("roblox_studio_mcp.core.session.time.sleep", lambda *_a, **_k: None)


class ScriptedProcess:
    """Process double whose ``send_request`` is dispatched by (method, tool name)."""

    def __init__(self):
        self.requests = []
        self._handlers = {}

    def on(self, key, handler):
        self._handlers[key] = handler
        return self

    def send_request(self, payload, timeout=10.0):
        self.requests.append(payload)
        method = payload.get("method")
        if method == "tools/call":
            key = ("tools/call", payload["params"]["name"])
        else:
            key = (method,)
        handler = self._handlers.get(key)
        if handler is None:
            return None
        return handler(payload) if callable(handler) else handler

    def tool_calls(self, name):
        return [r for r in self.requests if r.get("method") == "tools/call" and r["params"]["name"] == name]


def _text_result(payload_obj, is_error=False):
    return {
        "result": {
            "isError": is_error,
            "content": [{"type": "text", "text": json.dumps(payload_obj)}],
        }
    }


def _list_studios_ok(studios):
    return lambda _p: _text_result({"studios": studios})


def _bind_ok(_p):
    return {"result": {"isError": False}}


def make_manager(proc):
    return StudioSessionManager(proc, RequestIdDecoupler())


class TestGetActiveStudioId:
    def test_resolves_id_via_list_no_set_active(self):
        proc = ScriptedProcess()
        proc.on(("tools/call", "list_roblox_studios"), _list_studios_ok([{"id": "studio-1"}]))
        mgr = make_manager(proc)

        sid = mgr.get_active_studio_id()

        assert sid == "studio-1"
        assert mgr.active_studio_id == "studio-1"
        assert len(proc.tool_calls("list_roblox_studios")) == 1
        # set_active_studio was removed from the protocol; it must never be called.
        assert proc.tool_calls("set_active_studio") == []

    def test_picks_first_studio_that_has_an_id(self):
        proc = ScriptedProcess()
        proc.on(
            ("tools/call", "list_roblox_studios"),
            _list_studios_ok([{"name": "no-id"}, {"id": "studio-2", "name": "Place2"}]),
        )
        mgr = make_manager(proc)
        assert mgr.get_active_studio_id() == "studio-2"

    def test_caches_active_id_no_second_roundtrip(self):
        proc = ScriptedProcess()
        proc.on(("tools/call", "list_roblox_studios"), _list_studios_ok([{"id": "studio-1"}]))
        proc.on(("tools/call", "set_active_studio"), _bind_ok)
        mgr = make_manager(proc)

        assert mgr.get_active_studio_id() == "studio-1"
        proc.requests.clear()
        assert mgr.get_active_studio_id() == "studio-1"
        assert proc.requests == []  # served from cache

    def test_force_refresh_rebinds(self):
        proc = ScriptedProcess()
        proc.on(("tools/call", "list_roblox_studios"), _list_studios_ok([{"id": "studio-1"}]))
        proc.on(("tools/call", "set_active_studio"), _bind_ok)
        mgr = make_manager(proc)
        mgr.get_active_studio_id()
        proc.requests.clear()

        mgr.get_active_studio_id(force_refresh=True)
        assert len(proc.tool_calls("list_roblox_studios")) == 1

    def test_no_studios_returns_none(self):
        proc = ScriptedProcess()
        proc.on(("tools/call", "list_roblox_studios"), _list_studios_ok([]))
        mgr = make_manager(proc)
        assert mgr.get_active_studio_id() is None
        assert mgr.active_studio_id is None

    def test_no_response_returns_none(self):
        proc = ScriptedProcess()  # no handlers -> send_request returns None
        mgr = make_manager(proc)
        assert mgr.get_active_studio_id() is None

    def test_error_response_returns_none(self):
        proc = ScriptedProcess()
        proc.on(("tools/call", "list_roblox_studios"), {"error": {"code": -1, "message": "x"}})
        mgr = make_manager(proc)
        assert mgr.get_active_studio_id() is None

    def test_iserror_result_returns_none(self):
        proc = ScriptedProcess()
        proc.on(
            ("tools/call", "list_roblox_studios"),
            _text_result({"studios": [{"id": "s"}]}, is_error=True),
        )
        mgr = make_manager(proc)
        assert mgr.get_active_studio_id() is None

    def test_studios_without_ids_return_none(self):
        proc = ScriptedProcess()
        proc.on(("tools/call", "list_roblox_studios"), _list_studios_ok([{"name": "x"}, {"name": "y"}]))
        mgr = make_manager(proc)
        assert mgr.get_active_studio_id() is None
        assert mgr.active_studio_id is None

    def test_malformed_content_json_returns_none(self):
        proc = ScriptedProcess()
        proc.on(
            ("tools/call", "list_roblox_studios"),
            {"result": {"content": [{"type": "text", "text": "not json{"}]}},
        )
        mgr = make_manager(proc)
        assert mgr.get_active_studio_id() is None


class TestExecuteWithSessionPassthrough:
    @pytest.mark.parametrize("tool", ["list_roblox_studios", "set_active_studio"])
    def test_session_tools_pass_straight_through(self, tool):
        proc = ScriptedProcess()
        proc.on(("tools/call", tool), {"result": {"content": [{"type": "text", "text": "ok"}]}})
        mgr = make_manager(proc)

        out = mgr.execute_with_session(tool, {"foo": "bar"})

        assert out == {"content": [{"type": "text", "text": "ok"}]}
        assert len(proc.tool_calls(tool)) == 1
        # no pre-binding round trips
        assert len(proc.requests) == 1

    def test_passthrough_no_response_returns_friendly_stub(self):
        proc = ScriptedProcess()
        mgr = make_manager(proc)
        out = mgr.execute_with_session("list_roblox_studios", {})
        assert out["isError"] is True
        assert "No response from StudioMCP" in out["content"][0]["text"]


class TestExecuteWithSessionRetry:
    def _bound_proc(self):
        proc = ScriptedProcess()
        proc.on(("tools/call", "list_roblox_studios"), _list_studios_ok([{"id": "studio-1"}]))
        proc.on(("tools/call", "set_active_studio"), _bind_ok)
        return proc

    def test_happy_path_returns_result(self):
        proc = self._bound_proc()
        proc.on(
            ("tools/call", "do_thing"),
            {"result": {"isError": False, "content": [{"type": "text", "text": "done"}]}},
        )
        mgr = make_manager(proc)

        out = mgr.execute_with_session("do_thing", {"x": 1})
        assert out == {"isError": False, "content": [{"type": "text", "text": "done"}]}
        assert len(proc.tool_calls("do_thing")) == 1

    @pytest.mark.parametrize(
        "marker",
        ["Not connected", "No active studio", "Connection lost", "Studio disconnected"],
    )
    def test_retries_on_disconnect_markers_then_friendly_error(self, marker):
        proc = self._bound_proc()
        proc.on(
            ("tools/call", "do_thing"),
            lambda _p: {"result": {"isError": True, "content": [{"type": "text", "text": marker}]}},
        )
        mgr = make_manager(proc)

        out = mgr.execute_with_session("do_thing", {}, max_retries=3)

        assert out["isError"] is True
        assert NOT_CONNECTED_SNIPPET in out["content"][0]["text"]
        assert len(proc.tool_calls("do_thing")) == 3
        assert mgr.active_studio_id is None  # cache cleared on disconnect

    def test_recovers_on_second_attempt(self):
        proc = self._bound_proc()
        state = {"n": 0}

        def flaky(_p):
            state["n"] += 1
            if state["n"] == 1:
                return {
                    "result": {
                        "isError": True,
                        "content": [{"type": "text", "text": "Connection lost"}],
                    }
                }
            return {"result": {"isError": False, "content": [{"type": "text", "text": "recovered"}]}}

        proc.on(("tools/call", "do_thing"), flaky)
        mgr = make_manager(proc)

        out = mgr.execute_with_session("do_thing", {})
        assert out["content"][0]["text"] == "recovered"
        assert len(proc.tool_calls("do_thing")) == 2

    def test_non_disconnect_error_returned_as_is_no_retry(self):
        proc = self._bound_proc()
        proc.on(
            ("tools/call", "do_thing"),
            {
                "result": {
                    "isError": True,
                    "content": [{"type": "text", "text": "Some other failure"}],
                }
            },
        )
        mgr = make_manager(proc)

        out = mgr.execute_with_session("do_thing", {})
        assert out["content"][0]["text"] == "Some other failure"
        assert len(proc.tool_calls("do_thing")) == 1

    def test_friendly_error_when_never_binds(self):
        proc = ScriptedProcess()
        proc.on(("tools/call", "list_roblox_studios"), _list_studios_ok([]))  # never any studios
        mgr = make_manager(proc)

        out = mgr.execute_with_session("do_thing", {}, max_retries=3)
        assert out["isError"] is True
        assert NOT_CONNECTED_SNIPPET in out["content"][0]["text"]
        # last attempt still fires the tool call even without a session id
        assert len(proc.tool_calls("do_thing")) == 1


class TestStudioIdInjection:
    def _proc_with_studio(self, sid="studio-1"):
        proc = ScriptedProcess()
        proc.on(("tools/call", "list_roblox_studios"), _list_studios_ok([{"id": sid}]))
        proc.on(
            ("tools/call", "execute_luau"),
            {"result": {"isError": False, "content": [{"type": "text", "text": "42"}]}},
        )
        return proc

    def test_resolved_studio_id_is_injected_into_arguments(self):
        proc = self._proc_with_studio("studio-1")
        mgr = make_manager(proc)

        mgr.execute_with_session("execute_luau", {"code": "return 6*7"})

        call = proc.tool_calls("execute_luau")[0]
        assert call["params"]["arguments"] == {"code": "return 6*7", "studio_id": "studio-1"}

    def test_caller_supplied_studio_id_is_not_overridden(self):
        proc = self._proc_with_studio("resolved")
        mgr = make_manager(proc)

        mgr.execute_with_session("execute_luau", {"code": "x", "studio_id": "explicit"})

        call = proc.tool_calls("execute_luau")[0]
        assert call["params"]["arguments"]["studio_id"] == "explicit"
        # no discovery round-trip when the caller already chose an instance
        assert proc.tool_calls("list_roblox_studios") == []

    def test_caller_supplied_id_error_is_returned_not_retried(self):
        proc = ScriptedProcess()
        proc.on(
            ("tools/call", "execute_luau"),
            lambda _p: {"result": {"isError": True, "content": [{"type": "text", "text": "Not connected"}]}},
        )
        mgr = make_manager(proc)

        out = mgr.execute_with_session("execute_luau", {"studio_id": "explicit"}, max_retries=3)
        # caller owns the id; we surface the error rather than looping / re-resolving
        assert out["content"][0]["text"] == "Not connected"
        assert len(proc.tool_calls("execute_luau")) == 1

    def test_stale_id_marker_triggers_reresolve(self):
        proc = ScriptedProcess()
        proc.on(("tools/call", "list_roblox_studios"), _list_studios_ok([{"id": "studio-1"}]))
        state = {"n": 0}

        def handler(_p):
            state["n"] += 1
            if state["n"] == 1:
                return {"result": {"isError": True, "content": [{"type": "text", "text": "studio_id is required"}]}}
            return {"result": {"isError": False, "content": [{"type": "text", "text": "ok"}]}}

        proc.on(("tools/call", "execute_luau"), handler)
        mgr = make_manager(proc)

        out = mgr.execute_with_session("execute_luau", {})
        assert out["content"][0]["text"] == "ok"
        assert len(proc.tool_calls("execute_luau")) == 2
