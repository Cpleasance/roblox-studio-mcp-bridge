"""Shared pytest fixtures and path setup for the Roblox Studio MCP Bridge test suite.

The project uses a flat layout (package ``roblox_studio_mcp`` sits directly in the
repo root), so we make sure the repo root is importable regardless of how pytest
was invoked.
"""

import io
import json
import signal
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Generic doubles
# ---------------------------------------------------------------------------
class FakeProcess:
    """Stand-in for :class:`roblox_studio_mcp.core.process.StudioMCPProcess`.

    ``responder`` is an optional ``callable(payload) -> Optional[dict]`` used to
    synthesise JSON-RPC responses without ever spawning a real subprocess.
    """

    def __init__(self, responder=None, on_notification=None):
        self.responder = responder
        self.on_notification = on_notification
        self.started = False
        self.stopped = False
        self.requests = []
        self.notifications = []

    def emit_notification(self, payload):
        """Simulate StudioMCP pushing a server->client notification."""
        if self.on_notification is not None:
            self.on_notification(payload)

    # -- lifecycle -----------------------------------------------------------
    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    # -- io ----------------------------------------------------------------
    def send_request(self, payload, timeout=10.0):
        self.requests.append(payload)
        if self.responder is None:
            return None
        return self.responder(payload)

    def send_notification(self, payload):
        self.notifications.append(payload)

    # -- helpers ---------------------------------------------------------
    def requests_for(self, method):
        return [r for r in self.requests if r.get("method") == method]

    def tool_calls_for(self, name):
        calls = []
        for r in self.requests:
            if r.get("method") == "tools/call" and r.get("params", {}).get("name") == name:
                calls.append(r)
        return calls


@pytest.fixture
def fake_process_factory():
    def _make(responder=None):
        return FakeProcess(responder)

    return _make


@pytest.fixture(autouse=True)
def _restore_signal_handlers():
    """``RobloxMCPBridge.run`` installs SIGINT/SIGTERM handlers; keep the test
    runner's handlers intact by restoring them afterwards."""
    saved = {}
    for sig in (signal.SIGINT, getattr(signal, "SIGTERM", None)):
        if sig is not None:
            try:
                saved[sig] = signal.getsignal(sig)
            except (ValueError, OSError):
                pass
    yield
    for sig, handler in saved.items():
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError, TypeError):
            pass


@pytest.fixture
def drive_bridge(monkeypatch):
    """Return a helper that runs one full ``RobloxMCPBridge.run`` loop against an
    in-memory stdin/stdout pair and returns the parsed JSON-RPC output lines.

    The bridge reads ``sys.stdin``/writes ``sys.stdout`` directly, so we swap in
    ``io.StringIO`` objects. See the accompanying report note about an injectable
    stream seam that would make this cleaner.
    """
    from roblox_studio_mcp.core import bridge as bridge_mod

    holder = {}

    def _run(lines, responder=None):
        fake_proc = FakeProcess(responder)
        holder["proc"] = fake_proc

        # Resolver + process creation happen inside bootstrap_studiomcp; stub both
        # so no real executable is resolved and no real subprocess is spawned.
        monkeypatch.setattr(
            bridge_mod.RobloxStudioResolver,
            "resolve_executable",
            classmethod(lambda cls: Path("fake") / "StudioMCP.exe"),
        )

        def _fake_ctor(*_a, **kw):
            fake_proc.on_notification = kw.get("on_notification")
            return fake_proc

        monkeypatch.setattr(bridge_mod, "StudioMCPProcess", _fake_ctor)

        stdin_text = "".join(ln if ln.endswith("\n") else ln + "\n" for ln in lines)
        monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_text))
        fake_stdout = io.StringIO()
        monkeypatch.setattr(sys, "stdout", fake_stdout)

        b = bridge_mod.RobloxMCPBridge()
        b.run()

        raw = fake_stdout.getvalue()
        out = [json.loads(x) for x in raw.splitlines() if x.strip()]
        return out, fake_proc, b

    return _run
