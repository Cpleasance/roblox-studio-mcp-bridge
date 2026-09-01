"""Tests for roblox_studio_mcp.core.process.StudioMCPProcess.

These exercise the request/response bookkeeping without spawning a real
subprocess: ``proc`` is a hand-rolled double with in-memory pipes, mirroring the
``_Proc`` pattern already used in test_bridge.py's
``test_process_manager_dispatches_notifications_to_callback``.
"""

import io
import threading
import time

from roblox_studio_mcp.core.process import StudioMCPProcess


def _wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


class _DeadProc:
    """A child whose stdout is already at EOF (i.e. the process has exited)."""

    def __init__(self):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("")  # readline() -> "" -> reader loop exits
        self.stderr = io.StringIO("")

    def poll(self):
        return None  # not yet reaped at the moment send_request is first called


class TestSendRequestProcessNotRunning:
    def test_returns_none_when_process_never_started(self):
        pm = StudioMCPProcess("fake")
        assert pm.proc is None
        assert pm.send_request({"jsonrpc": "2.0", "id": 1, "method": "ping"}) is None

    def test_returns_none_when_child_already_exited(self):
        pm = StudioMCPProcess("fake")

        class _Exited:
            def poll(self):
                return 1

        pm.proc = _Exited()
        assert pm.send_request({"jsonrpc": "2.0", "id": 1, "method": "ping"}) is None

    def test_no_future_registered_for_dead_process(self):
        pm = StudioMCPProcess("fake")
        pm.send_request({"jsonrpc": "2.0", "id": 99, "method": "ping"})
        assert pm._pending_futures == {}


class TestReleasePending:
    def test_sets_every_waiting_event(self):
        pm = StudioMCPProcess("fake")
        e1, e2 = threading.Event(), threading.Event()
        pm._pending_futures[1] = (e1, {"response": None})
        pm._pending_futures[2] = (e2, {"response": None})

        pm._release_pending()

        assert e1.is_set() and e2.is_set()

    def test_noop_when_nothing_pending(self):
        pm = StudioMCPProcess("fake")
        pm._release_pending()  # must not raise

    def test_child_death_unblocks_a_waiting_send_request(self):
        pm = StudioMCPProcess("fake")
        pm._running = True
        pm.proc = _DeadProc()

        result = {}

        def _call():
            result["value"] = pm.send_request(
                {"jsonrpc": "2.0", "id": 7, "method": "tools/list"}, timeout=5.0
            )

        caller = threading.Thread(target=_call, name="blocked-caller")
        caller.start()
        try:
            assert _wait_until(lambda: 7 in pm._pending_futures), "caller never registered its future"

            # The stdout reader observes EOF (child gone) and releases waiters.
            pm._stdout_reader_loop()

            assert _wait_until(lambda: not caller.is_alive()), "caller stayed blocked after child death"
            assert result["value"] is None
        finally:
            caller.join(timeout=2.0)
            assert not caller.is_alive()
