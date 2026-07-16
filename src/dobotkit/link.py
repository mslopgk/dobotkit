"""Shared DobotLink client (arm + GO): synchronous JSON-RPC over ``ws://localhost:9090``.

Neither the Magician Lite arm nor the Magician GO is driven directly; Python
talks to the **DobotLink** desktop service over a WebSocket using JSON-RPC 2.0,
and DobotLink relays commands to the device over its COM port / wireless
dongle::

    Python  --(WebSocket JSON-RPC)-->  DobotLink.exe  --(COM/wireless)-->  arm / GO

This client is a thin, blocking wrapper over the ``websockets`` *sync* API: one
request, then a read loop that returns the response whose ``id`` matches. It
depends only on ``websockets`` -- never on Dobot's DobotEDU/DobotRPC packages.

Method prefixing: only the ``dobotlink.`` namespace is added automatically.
A bare ``MagicianGO.GetBatteryVoltage`` becomes
``dobotlink.MagicianGO.GetBatteryVoltage``, but the ``MagicianGO.`` /
``MagicBox.`` / ``Magician.`` segment itself is left untouched -- callers using
the low-level ``call``/``notify`` must spell those namespaces themselves (the
high-level ``MagicianGO`` wrapper adds ``MagicianGO.`` and the arm's
``ArmCommands`` adds ``Magician.`` for you).

A ``_ws_factory`` hook lets tests inject an in-memory socket double without
opening a real connection; in production it defaults to
``websockets.sync.client.connect``.
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, Optional

from dobotkit.exceptions import DobotConnectionError, DobotLinkError, DobotTimeoutError

_PREFIX = "dobotlink."


def _default_ws_factory(url: str, *, open_timeout: float) -> Any:
    """Open a real DobotLink WebSocket. Imported lazily so importing this module
    (or ``dobotkit.go``) never pulls in ``websockets`` until a connection is made.
    """
    from websockets.sync.client import connect

    return connect(url, open_timeout=open_timeout)


class DobotLinkClient:
    """Blocking JSON-RPC 2.0 client for the DobotLink WebSocket service.

    Args:
        host: DobotLink host. Defaults to ``"localhost"``.
        port: DobotLink WebSocket port. Defaults to ``9090``.
        timeout: Seconds to wait both for the initial connection and for each
            ``call`` response before raising. Defaults to ``10.0``.
        _ws_factory: Test/advanced hook returning a connection object exposing
            ``send(str)``, ``recv(timeout=...) -> str``, and ``close()``. When
            ``None`` (default) a real ``websockets`` connection is opened.

    Use as a context manager to guarantee the socket is closed::

        with DobotLinkClient() as client:
            client.call("MagicianGO.GetBatteryVoltage", portName="COM5")
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 9090,
        timeout: float = 10.0,
        _ws_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        self._url = f"ws://{host}:{port}"
        self._timeout = timeout
        self._ws_factory = _ws_factory or _default_ws_factory
        self._ws: Optional[Any] = None
        self._id = 0

    # ---- lifecycle ---------------------------------------------------------

    def connect(self) -> "DobotLinkClient":
        """Open the WebSocket (idempotent) and return ``self`` for chaining.

        Raises:
            DobotConnectionError: if the connection cannot be established
                (most often because DobotLink.exe is not running).
        """
        if self._ws is None:
            try:
                self._ws = self._ws_factory(self._url, open_timeout=self._timeout)
            except Exception as exc:  # noqa: BLE001 - surfaced as a typed error
                raise DobotConnectionError(
                    f"cannot connect to DobotLink at {self._url}. "
                    f"Is DobotLink.exe running? ({exc})"
                ) from exc
        return self

    def close(self) -> None:
        """Close the WebSocket if open. Safe to call more than once.

        Note: this only closes the *socket* — it does **not** stop the car. A
        GO driving at its last commanded velocity keeps driving. Safety
        teardown (line-trace OFF + emergency stop) is the job of the
        ``MagicianGO`` context manager; prefer ``with MagicianGO.open(...)``.
        """
        if self._ws is not None:
            ws, self._ws = self._ws, None
            ws.close()

    def __enter__(self) -> "DobotLinkClient":
        return self.connect()

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- RPC ---------------------------------------------------------------

    def call(self, method: str, *, call_timeout: Optional[float] = None, **params: Any) -> Any:
        """Send a JSON-RPC request and block for the matching response.

        Args:
            method: RPC method name. Auto-prefixed with ``dobotlink.`` unless it
                already starts with it.
            call_timeout: Override the client's default ``timeout`` for just this
                call. Keyword-only so it never collides with an RPC param that
                happens to be named ``timeout`` (e.g. ``SetWAITCmd``). When
                ``None`` (default), the client's ``timeout`` is used.
            **params: JSON-RPC ``params`` object.

        Returns:
            The ``result`` field of the matching response.

        Raises:
            DobotLinkError: if not connected, or if the response is a JSON-RPC
                error.
            DobotTimeoutError: if no matching response arrives within the
                effective timeout (the device may be unresponsive or DobotLink
                lost the link). The timeout is a **total deadline** for the
                whole call, not a per-read budget — a stream of unrelated
                notifications cannot extend the wait indefinitely.
        """
        ws = self._require_connection()
        self._id += 1
        request_id = self._id
        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": self._full_method(method),
            "params": params,
        }
        ws.send(json.dumps(payload))

        eff = call_timeout if call_timeout is not None else self._timeout
        deadline = time.monotonic() + eff
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DobotTimeoutError(
                    f"timed out after {eff}s waiting for "
                    f"'{payload['method']}'. The device may be unresponsive or "
                    f"DobotLink lost the link."
                )
            try:
                raw = ws.recv(timeout=remaining)
            except TimeoutError as exc:
                raise DobotTimeoutError(
                    f"timed out after {eff}s waiting for "
                    f"'{payload['method']}'. The device may be unresponsive or "
                    f"DobotLink lost the link."
                ) from exc
            message = json.loads(raw)
            # Skip notifications and responses to other requests.
            if message.get("id") != request_id:
                continue
            error = message.get("error")
            if error is not None:
                raise DobotLinkError(f"DobotLink error for '{payload['method']}': {error}")
            return message.get("result")

    def notify(self, method: str, **params: Any) -> None:
        """Send a fire-and-forget JSON-RPC notification (no ``id``, no reply read).

        Used for non-blocking commands such as emergency stop, where waiting on a
        response is undesirable.

        Args:
            method: RPC method name. Auto-prefixed with ``dobotlink.`` unless it
                already starts with it.
            **params: JSON-RPC ``params`` object.

        Raises:
            DobotLinkError: if not connected.
        """
        ws = self._require_connection()
        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": self._full_method(method),
            "params": params,
        }
        ws.send(json.dumps(payload))

    # ---- internals ---------------------------------------------------------

    def _require_connection(self) -> Any:
        if self._ws is None:
            raise DobotLinkError("not connected; call connect() first")
        return self._ws

    @staticmethod
    def _full_method(method: str) -> str:
        return method if method.startswith(_PREFIX) else _PREFIX + method
