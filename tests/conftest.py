"""Shared test fixtures for dobotkit.

Provides:
- ``FakeWebSocket`` / ``FakeClient``: in-memory doubles for
  ``dobotkit.link.DobotLinkClient`` and a connected client, shared by the GO
  and arm/DobotLink test suites. See their docstrings below for the exact call
  shapes they mirror.
"""
import json
from typing import Any, Dict, List, Optional, Tuple

import pytest


class FakeWebSocket:
    """In-memory double for the ``websockets`` connection ``DobotLinkClient`` uses.

    The real client (see ``dobotkit/link.py``) drives the socket like this::

        ws.send(json.dumps(payload))      # JSON-RPC request, str
        raw = ws.recv(timeout=...)        # JSON-RPC response, str
        ws.close()

    so this double captures every ``send`` frame and serves queued ``recv``
    frames in order. Responses may be queued as dicts (auto JSON-encoded) or as
    raw strings, which lets a test feed malformed/out-of-order/notification
    frames to exercise the client's id-matching loop.
    """

    def __init__(self, responses: Optional[List[Any]] = None) -> None:
        # Captured outbound frames.
        self.sent: List[str] = []
        # Pending inbound frames (FIFO).
        self._rx: List[Any] = list(responses or [])
        self.closed = False

    # ---- websockets connection surface ----
    def send(self, data: str) -> None:
        self.sent.append(data)

    def recv(self, timeout: Optional[float] = None) -> str:
        if not self._rx:
            # Mirror websockets.sync: a read with nothing available times out.
            raise TimeoutError("no queued FakeWebSocket frame")
        frame = self._rx.pop(0)
        return frame if isinstance(frame, str) else json.dumps(frame)

    def close(self) -> None:
        self.closed = True

    # ---- test helpers ----
    def queue_response(self, frame: Any) -> None:
        """Append a response frame (dict -> auto JSON, str -> verbatim)."""
        self._rx.append(frame)

    def queue_result(self, result: Any, *, id: int = 1) -> None:
        """Queue a well-formed JSON-RPC success response carrying ``result``."""
        self._rx.append({"jsonrpc": "2.0", "id": id, "result": result})

    def queue_error(self, message: str = "boom", *, code: int = -32000,
                    id: int = 1) -> None:
        """Queue a JSON-RPC error response (drives ``DobotLinkError``)."""
        self._rx.append(
            {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}
        )

    def last_sent(self) -> Dict[str, Any]:
        """Decode the most recently sent frame as a JSON-RPC request dict."""
        return json.loads(self.sent[-1])


class FakeClient:
    """Double for a connected ``DobotLinkClient`` — records calls, returns canned results.

    Records ``(method, params)`` for every ``call`` and ``notify`` so a test can
    assert exactly what ``MagicianGO`` / navigation sent on the wire, with no
    socket involved.

    Programmable results, in priority order:
      1. ``results[method]`` — per-method override (most specific).
      2. ``result`` — a single default returned for any otherwise-unmatched call.
    A result entry may be a list/tuple, in which case successive calls to the
    same method pop the next value (a one-shot queue), so closed-loop reads can
    be scripted to advance.
    """

    def __init__(self, result: Any = None,
                 results: Optional[Dict[str, Any]] = None) -> None:
        self.calls: List[Tuple[str, Dict[str, Any]]] = []
        self.notifies: List[Tuple[str, Dict[str, Any]]] = []
        self._result = result
        self._results = dict(results or {})

    def call(self, method: str, *, call_timeout: Optional[float] = None, **params: Any) -> Any:
        # ``call_timeout`` mirrors ``DobotLinkClient.call``'s keyword-only
        # per-call timeout override -- it is call metadata, not an RPC param,
        # so it is deliberately excluded from the recorded ``params``.
        self.calls.append((method, params))
        if method in self._results:
            programmed = self._results[method]
            if isinstance(programmed, list):
                # One-shot queue: pop next, stick on last value when exhausted.
                # Special case: single-element lists are returned as-is (for list return values).
                if len(programmed) > 1:
                    return programmed.pop(0)
                return programmed
            return programmed
        return self._result

    def notify(self, method: str, **params: Any) -> None:
        self.notifies.append((method, params))

    # ---- test helpers ----
    def methods_called(self) -> List[str]:
        return [m for m, _ in self.calls]

    def find_call(self, method: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Return the first recorded call to ``method``, or ``None``."""
        for entry in self.calls:
            if entry[0] == method:
                return entry
        return None


@pytest.fixture
def fake_ws() -> FakeWebSocket:
    """A fresh ``FakeWebSocket`` with no queued responses."""
    return FakeWebSocket()


@pytest.fixture
def fake_client() -> FakeClient:
    """A fresh ``FakeClient`` recording calls, returning ``None`` by default."""
    return FakeClient()
