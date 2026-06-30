"""Tests for ``dobotkit.go.client.DobotLinkClient``.

The client is a thin, synchronous JSON-RPC wrapper over a ``websockets``
connection. These tests drive it entirely through the in-memory
``FakeWebSocket`` double from ``tests/go/conftest.py`` (injected via the
``_ws_factory`` hook), so no real socket is ever opened.

Behaviour under test (mirrors the proven ``magiciango/client.py`` pattern):

- ``connect()`` builds ``ws://host:port`` via the factory and returns ``self``.
- ``call(method, **params)`` emits a well-formed JSON-RPC request, auto-prefixes
  ``dobotlink.`` (and only that namespace), awaits the matching ``id``, returns
  ``result``, raises ``DobotLinkError`` on an error response, and
  ``DobotTimeoutError`` when no reply arrives.
- ``notify(method, **params)`` is fire-and-forget (no ``id``, no read).
- ``close()`` and the context manager tear the socket down.
"""
from __future__ import annotations

import json

import pytest

from dobotkit.exceptions import DobotConnectionError, DobotLinkError, DobotTimeoutError
from dobotkit.go.client import DobotLinkClient

from .conftest import FakeWebSocket


def make_client(responses=None, **kwargs) -> tuple[DobotLinkClient, FakeWebSocket]:
    """A connected client backed by a ``FakeWebSocket`` with queued ``responses``."""
    ws = FakeWebSocket(responses)
    client = DobotLinkClient(_ws_factory=lambda *a, **k: ws, **kwargs).connect()
    return client, ws


# ---- connection ------------------------------------------------------------

def test_connect_returns_self_and_uses_factory():
    ws = FakeWebSocket()
    seen = {}

    def factory(url, **kwargs):
        seen["url"] = url
        seen["kwargs"] = kwargs
        return ws

    client = DobotLinkClient(host="localhost", port=9090, _ws_factory=factory)
    assert client.connect() is client
    assert seen["url"] == "ws://localhost:9090"


def test_connect_custom_host_port():
    ws = FakeWebSocket()
    seen = {}
    client = DobotLinkClient(host="1.2.3.4", port=5000,
                             _ws_factory=lambda url, **k: seen.setdefault("url", url) or ws)
    client.connect()
    assert seen["url"] == "ws://1.2.3.4:5000"


def test_connect_failure_raises_connection_error():
    def boom(*a, **k):
        raise OSError("refused")

    client = DobotLinkClient(_ws_factory=boom)
    with pytest.raises(DobotConnectionError):
        client.connect()


# ---- call: framing ---------------------------------------------------------

def test_call_builds_jsonrpc_payload_with_prefix_and_port():
    client, ws = make_client([{"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}])
    result = client.call("MagicianGO.GetBatteryVoltage", portName="COM5")
    sent = json.loads(ws.sent[0])
    assert sent["jsonrpc"] == "2.0"
    assert sent["id"] == 1
    assert sent["method"] == "dobotlink.MagicianGO.GetBatteryVoltage"
    assert sent["params"] == {"portName": "COM5"}
    assert result == {"ok": True}


def test_call_increments_id():
    client, ws = make_client([
        {"jsonrpc": "2.0", "id": 1, "result": 1},
        {"jsonrpc": "2.0", "id": 2, "result": 2},
    ])
    client.call("MagicianGO.A")
    client.call("MagicianGO.B")
    assert json.loads(ws.sent[0])["id"] == 1
    assert json.loads(ws.sent[1])["id"] == 2


def test_call_empty_params_is_object():
    client, ws = make_client([{"jsonrpc": "2.0", "id": 1, "result": None}])
    client.call("MagicianGO.SearchDobot")
    assert json.loads(ws.sent[0])["params"] == {}


# ---- call: prefixing -------------------------------------------------------

def test_call_keeps_existing_dobotlink_prefix():
    client, ws = make_client([{"jsonrpc": "2.0", "id": 1, "result": None}])
    client.call("dobotlink.MagicianGO.X")
    assert json.loads(ws.sent[0])["method"] == "dobotlink.MagicianGO.X"


def test_call_does_not_mangle_magiciango_namespace():
    """Auto-prefix only ``dobotlink.``; ``MagicianGO.`` stays untouched (just prefixed)."""
    client, ws = make_client([{"jsonrpc": "2.0", "id": 1, "result": None}])
    client.call("MagicianGO.GetUltrasoundData", portName="COM5")
    assert json.loads(ws.sent[0])["method"] == "dobotlink.MagicianGO.GetUltrasoundData"


def test_call_does_not_mangle_magicbox_namespace():
    client, ws = make_client([{"jsonrpc": "2.0", "id": 1, "result": None}])
    client.call("MagicBox.GetStopPointState", portName="COM5")
    assert json.loads(ws.sent[0])["method"] == "dobotlink.MagicBox.GetStopPointState"


# ---- call: response handling ----------------------------------------------

def test_call_raises_on_error_response():
    client, ws = make_client([
        {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "boom"}},
    ])
    with pytest.raises(DobotLinkError):
        client.call("MagicianGO.X")


def test_call_skips_messages_with_wrong_id():
    client, ws = make_client([
        {"jsonrpc": "2.0", "method": "notify", "params": {}},   # notification, no id
        {"jsonrpc": "2.0", "id": 99, "result": "stale"},        # wrong id
        {"jsonrpc": "2.0", "id": 1, "result": "good"},          # our reply
    ])
    assert client.call("MagicianGO.X") == "good"


def test_call_timeout_when_no_reply():
    client, _ = make_client([], timeout=0.01)
    with pytest.raises(DobotTimeoutError):
        client.call("MagicianGO.X")


def test_call_without_connection_raises():
    client = DobotLinkClient(_ws_factory=lambda *a, **k: FakeWebSocket())
    with pytest.raises(DobotLinkError):
        client.call("MagicianGO.X")


# ---- notify ----------------------------------------------------------------

def test_notify_sends_no_id_and_does_not_read():
    client, ws = make_client([])  # nothing queued: a read would time out
    client.notify("MagicianGO.SetMoveSpeed", portName="COM5", x=0, y=0, r=0)
    sent = json.loads(ws.sent[0])
    assert "id" not in sent
    assert sent["method"] == "dobotlink.MagicianGO.SetMoveSpeed"
    assert sent["params"] == {"portName": "COM5", "x": 0, "y": 0, "r": 0}


def test_notify_keeps_dobotlink_prefix():
    client, ws = make_client([])
    client.notify("dobotlink.MagicianGO.SetMoveSpeed", x=0)
    assert json.loads(ws.sent[0])["method"] == "dobotlink.MagicianGO.SetMoveSpeed"


def test_notify_without_connection_raises():
    client = DobotLinkClient(_ws_factory=lambda *a, **k: FakeWebSocket())
    with pytest.raises(DobotLinkError):
        client.notify("MagicianGO.X")


# ---- teardown / lifecycle --------------------------------------------------

def test_close_closes_socket():
    client, ws = make_client([])
    client.close()
    assert ws.closed is True


def test_close_is_idempotent():
    client, ws = make_client([])
    client.close()
    client.close()  # must not raise
    assert ws.closed is True


def test_context_manager_connects_and_closes():
    ws = FakeWebSocket([{"jsonrpc": "2.0", "id": 1, "result": "ok"}])
    with DobotLinkClient(_ws_factory=lambda *a, **k: ws) as client:
        assert client.call("MagicianGO.X") == "ok"
    assert ws.closed is True


def test_context_manager_closes_on_exception():
    ws = FakeWebSocket([])
    with pytest.raises(RuntimeError):
        with DobotLinkClient(_ws_factory=lambda *a, **k: ws):
            raise RuntimeError("boom")
    assert ws.closed is True
