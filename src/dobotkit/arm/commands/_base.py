"""Shared base for the arm's DobotLink RPC command mixins."""
from __future__ import annotations
from typing import Any, Optional
from dobotkit.link import DobotLinkClient


class _Base:
    """Connection state and the shared ``_call`` / ``_queued_index`` primitives."""

    def __init__(self, client: DobotLinkClient, port_name: str) -> None:
        self._client = client
        self.port_name = port_name

    def _call(self, func: str, *, call_timeout: Optional[float] = None, **params: Any) -> Any:
        params["portName"] = self.port_name
        return self._client.call(f"Magician.{func}", call_timeout=call_timeout, **params)

    def _queued_index(self, resp: Any) -> int:
        return int(resp.get("queuedCmdIndex", 0)) if isinstance(resp, dict) else int(resp or 0)
