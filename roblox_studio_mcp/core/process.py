"""Asynchronous non-blocking subprocess manager and pipe drainer.

Wraps ``StudioMCP`` in a child process and services its stdio pipes from
dedicated daemon threads so the bridge never blocks on a full OS pipe buffer
(the historical cause of stderr deadlocks).  Responses are matched back to
callers by JSON-RPC id through per-request futures.
"""

import collections
import json
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from roblox_studio_mcp.core._log import get_logger

logger = get_logger(__name__)


class StudioMCPProcess:
    """Manages the StudioMCP child process with non-blocking stdio/stderr threads."""

    def __init__(self, executable_path: Path):
        self.executable_path = executable_path
        self.proc: Optional[subprocess.Popen] = None
        self._pending_futures: Dict[Any, Tuple[threading.Event, Dict[str, Any]]] = {}
        self._lock = threading.Lock()
        # Serializes writes to the child's stdin: session-manager retries and the
        # main loop can call send_request/send_notification from several threads,
        # and interleaved writes would corrupt the line-delimited JSON stream.
        self._stdin_lock = threading.Lock()
        self._running = False
        self.stderr_log: collections.deque = collections.deque(maxlen=250)

    def start(self) -> None:
        """Spawn the child process and start the stdout/stderr service threads."""
        self.proc = subprocess.Popen(
            [str(self.executable_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self._running = True

        # Thread 1: Read stdout asynchronously and resolve pending futures.
        self._stdout_thread = threading.Thread(target=self._stdout_reader_loop, daemon=True, name="StudioStdoutReader")
        self._stdout_thread.start()

        # Thread 2: Drain stderr into a ring buffer to prevent OS pipe deadlocks.
        self._stderr_thread = threading.Thread(
            target=self._stderr_drainer_loop, daemon=True, name="StudioStderrDrainer"
        )
        self._stderr_thread.start()

    def _stdout_reader_loop(self) -> None:
        while self._running and self.proc and self.proc.stdout:
            try:
                line = self.proc.stdout.readline()
                if not line:
                    break
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    payload = json.loads(line_str)
                except ValueError as e:
                    # StudioMCP occasionally emits non-JSON banner lines on stdout.
                    logger.debug("Ignoring non-JSON stdout line: %s (%s)", line_str[:200], e)
                    continue
                req_id = payload.get("id") if isinstance(payload, dict) else None
                if req_id is not None:
                    with self._lock:
                        fut = self._pending_futures.get(req_id)
                        if fut is not None:
                            event, container = fut
                            container["response"] = payload
                            event.set()
            except Exception as e:
                logger.debug("stdout reader loop terminating: %s", e)
                break
        self._release_pending()

    def _stderr_drainer_loop(self) -> None:
        while self._running and self.proc and self.proc.stderr:
            try:
                line = self.proc.stderr.readline()
                if not line:
                    break
                line_str = line.strip()
                if line_str:
                    self.stderr_log.append(line_str)
                    logger.debug("StudioMCP stderr: %s", line_str)
            except Exception as e:
                logger.debug("stderr drainer loop terminating: %s", e)
                break

    def _release_pending(self) -> None:
        """Wake every waiting caller so they fail fast instead of hitting the timeout."""
        with self._lock:
            pending = list(self._pending_futures.values())
        for event, _container in pending:
            event.set()

    def send_request(self, payload: Dict[str, Any], timeout: float = 10.0) -> Optional[Dict[str, Any]]:
        """Send a request and block until the matching response arrives or ``timeout`` elapses."""
        if not self.proc or self.proc.poll() is not None:
            logger.warning("send_request: StudioMCP process is not running")
            return None

        req_id = payload.get("id")
        event = threading.Event()
        container: Dict[str, Any] = {"response": None}

        if req_id is not None:
            with self._lock:
                self._pending_futures[req_id] = (event, container)

        try:
            msg = json.dumps(payload) + "\n"
            with self._stdin_lock:
                if self.proc and self.proc.stdin:
                    self.proc.stdin.write(msg)
                    self.proc.stdin.flush()
                else:
                    raise RuntimeError("StudioMCP stdin is closed")
        except Exception as e:
            logger.warning("send_request: failed to write to StudioMCP stdin: %s", e)
            if req_id is not None:
                with self._lock:
                    self._pending_futures.pop(req_id, None)
            return None

        if req_id is None:
            return None  # Notification (no response expected)

        signaled = event.wait(timeout)
        with self._lock:
            self._pending_futures.pop(req_id, None)

        if signaled and container.get("response") is not None:
            return container.get("response")
        if not signaled:
            logger.warning("send_request: timed out after %.1fs waiting for id=%s", timeout, req_id)
        return None

    def send_notification(self, payload: Dict[str, Any]) -> None:
        """Fire-and-forget a JSON-RPC notification to the child process."""
        try:
            msg = json.dumps(payload) + "\n"
            with self._stdin_lock:
                if self.proc and self.proc.stdin:
                    self.proc.stdin.write(msg)
                    self.proc.stdin.flush()
        except Exception as e:
            logger.warning("send_notification failed: %s", e)

    def stop(self) -> None:
        """Stop reader threads, terminate the child, and close all pipes."""
        # Signal the reader/drainer loops to exit *before* tearing down the process
        # so they observe _running == False and don't treat the closed pipe as an error.
        self._running = False

        proc = self.proc
        if not proc:
            return

        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    logger.debug("StudioMCP did not terminate; killing")
                    proc.kill()
                    try:
                        proc.wait(timeout=1.5)
                    except subprocess.TimeoutExpired:
                        logger.warning("StudioMCP did not exit after kill()")
        except Exception as e:
            logger.debug("Error terminating StudioMCP: %s", e)

        for pipe in (proc.stdin, proc.stdout, proc.stderr):
            try:
                if pipe:
                    pipe.close()
            except Exception as e:
                logger.debug("Error closing StudioMCP pipe: %s", e)

        self._release_pending()
