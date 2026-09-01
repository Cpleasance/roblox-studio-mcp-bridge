"""Tests for roblox_studio_mcp.core.protocol."""

import threading

import pytest

from roblox_studio_mcp.core.protocol import (
    INVALID_REQUEST,
    MCP_PROTOCOL_VERSION,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    RequestIdDecoupler,
    make_jsonrpc_error,
    make_jsonrpc_response,
)


class TestRequestIdDecoupler:
    def test_allocates_monotonically_from_start(self):
        d = RequestIdDecoupler(start_id=100000)
        first = d.allocate_internal_id()
        second = d.allocate_internal_id()
        assert first == 100001
        assert second == 100002
        assert second > first

    def test_custom_start_id(self):
        d = RequestIdDecoupler(start_id=5)
        assert d.allocate_internal_id() == 6

    def test_ids_never_collide_with_low_host_ids(self):
        d = RequestIdDecoupler()
        assert d.allocate_internal_id() > 100000

    def test_thread_safe_no_duplicates_under_hammering(self):
        d = RequestIdDecoupler()
        threads_count = 16
        per_thread = 2000
        results = []
        results_lock = threading.Lock()
        barrier = threading.Barrier(threads_count)

        def worker():
            barrier.wait()
            local = [d.allocate_internal_id() for _ in range(per_thread)]
            with results_lock:
                results.extend(local)

        threads = [threading.Thread(target=worker) for _ in range(threads_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == threads_count * per_thread
        assert len(set(results)) == len(results)  # all unique
        # contiguous + monotonic overall
        assert sorted(results) == list(range(100001, 100001 + len(results)))


class TestMakeJsonRpcResponse:
    def test_response_shape(self):
        resp = make_jsonrpc_response(7, {"ok": True})
        assert resp == {"jsonrpc": "2.0", "id": 7, "result": {"ok": True}}

    @pytest.mark.parametrize("req_id", [1, "abc", None])
    def test_response_preserves_id_type(self, req_id):
        resp = make_jsonrpc_response(req_id, [])
        assert resp["id"] == req_id
        assert resp["jsonrpc"] == "2.0"
        assert resp["result"] == []


class TestMakeJsonRpcError:
    def test_error_shape_without_data(self):
        err = make_jsonrpc_error(3, METHOD_NOT_FOUND, "nope")
        assert err == {
            "jsonrpc": "2.0",
            "id": 3,
            "error": {"code": METHOD_NOT_FOUND, "message": "nope"},
        }
        assert "data" not in err["error"]

    def test_data_omitted_when_none_explicitly(self):
        err = make_jsonrpc_error(None, PARSE_ERROR, "Parse error", data=None)
        assert "data" not in err["error"]
        assert err["id"] is None

    @pytest.mark.parametrize(
        "data",
        [0, "", [], {}, False],
        ids=["zero", "empty-str", "empty-list", "empty-dict", "false"],
    )
    def test_falsy_but_not_none_data_is_included(self, data):
        err = make_jsonrpc_error(1, INVALID_REQUEST, "bad", data=data)
        assert "data" in err["error"]
        assert err["error"]["data"] == data

    def test_truthy_data_included(self):
        err = make_jsonrpc_error(1, INVALID_REQUEST, "bad", data={"detail": "x"})
        assert err["error"]["data"] == {"detail": "x"}


def test_protocol_version_constant():
    assert MCP_PROTOCOL_VERSION == "2024-11-05"
