"""JSON-RPC 2.0 protocol definitions, error codes, and ID virtualization."""

import threading
from typing import Dict, Any, Union, Optional

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Protocol negotiated version
MCP_PROTOCOL_VERSION = "2024-11-05"

class RequestIdDecoupler:
    """Allocates unique internal virtual IDs to prevent collision with host IDs."""
    def __init__(self, start_id: int = 100000):
        self._counter = start_id
        self._lock = threading.Lock()

    def allocate_internal_id(self) -> int:
        with self._lock:
            self._counter += 1
            return self._counter

def make_jsonrpc_response(req_id: Union[int, str, None], result: Any) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": result
    }

def make_jsonrpc_error(req_id: Union[int, str, None], code: int, message: str, data: Optional[Any] = None) -> Dict[str, Any]:
    err = {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {
            "code": code,
            "message": message
        }
    }
    if data is not None:
        err["error"]["data"] = data
    return err
