"""Asynchronous non-blocking subprocess manager and pipe drainer."""

import subprocess
import threading
import json
import collections
import time
import sys
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

class StudioMCPProcess:
    """Manages the StudioMCP.exe child process with non-blocking stdio/stderr threads."""

    def __init__(self, executable_path: Path):
        self.executable_path = executable_path
        self.proc: Optional[subprocess.Popen] = None
        self._pending_futures: Dict[Any, Tuple[threading.Event, Dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._running = False
        self.stderr_log: collections.deque = collections.deque(maxlen=250)

    def start(self):
        self.proc = subprocess.Popen(
            [str(self.executable_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1
        )
        self._running = True

        # Thread 1: Read stdout asynchronously
        self._stdout_thread = threading.Thread(target=self._stdout_reader_loop, daemon=True, name="StudioStdoutReader")
        self._stdout_thread.start()

        # Thread 2: Drain stderr asynchronously into ring buffer to prevent OS pipe deadlocks
        self._stderr_thread = threading.Thread(target=self._stderr_drainer_loop, daemon=True, name="StudioStderrDrainer")
        self._stderr_thread.start()

    def _stdout_reader_loop(self):
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
                    req_id = payload.get("id")
                    if req_id is not None:
                        with self._lock:
                            if req_id in self._pending_futures:
                                event, container = self._pending_futures[req_id]
                                container["response"] = payload
                                event.set()
                except Exception:
                    pass
            except Exception:
                break

    def _stderr_drainer_loop(self):
        while self._running and self.proc and self.proc.stderr:
            try:
                line = self.proc.stderr.readline()
                if not line:
                    break
                line_str = line.strip()
                if line_str:
                    self.stderr_log.append(line_str)
            except Exception:
                break

    def send_request(self, payload: Dict[str, Any], timeout: float = 10.0) -> Optional[Dict[str, Any]]:
        if not self.proc or self.proc.poll() is not None:
            return None

        req_id = payload.get("id")
        event = threading.Event()
        container: Dict[str, Any] = {"response": None}

        if req_id is not None:
            with self._lock:
                self._pending_futures[req_id] = (event, container)

        try:
            msg = json.dumps(payload) + "\n"
            if self.proc and self.proc.stdin:
                self.proc.stdin.write(msg)
                self.proc.stdin.flush()
        except Exception:
            with self._lock:
                self._pending_futures.pop(req_id, None)
            return None

        if req_id is None:
            return None  # Notification (no response expected)

        # Wait for asynchronous response with timeout
        signaled = event.wait(timeout)
        with self._lock:
            self._pending_futures.pop(req_id, None)

        if signaled:
            return container.get("response")
        return None

    def send_notification(self, payload: Dict[str, Any]):
        try:
            msg = json.dumps(payload) + "\n"
            if self.proc and self.proc.stdin:
                self.proc.stdin.write(msg)
                self.proc.stdin.flush()
        except Exception:
            pass

    def stop(self):
        self._running = False
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=1.5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
