"""Thin dobotlink.Magician.* RPC wrappers for the Magician Lite arm."""
from __future__ import annotations
from typing import Any, List, cast
from dobotkit.link import DobotLinkClient


class ArmCommands:
    """1:1 wrappers over the arm's DobotLink RPC surface."""

    def __init__(self, client: DobotLinkClient, port_name: str) -> None:
        self._client = client
        self.port_name = port_name

    def _call(self, func: str, **params: Any) -> Any:
        params["portName"] = self.port_name
        return self._client.call(f"Magician.{func}", **params)

    # -- connection --
    def search(self) -> List[Any]:
        return cast(List[Any], self._client.call("Magician.SearchDobot"))

    def connect(self) -> Any:
        return self._call("ConnectDobot")

    def disconnect(self) -> Any:
        return self._call("DisconnectDobot")

    # -- queue --
    def queue_clear(self) -> Any:
        return self._call("QueuedCmdClear")

    def queue_start(self) -> Any:
        return self._call("QueuedCmdStart")

    def queue_stop(self) -> Any:
        return self._call("QueuedCmdStop")

    def current_index(self) -> int:
        resp = self._call("GetQueuedCmdCurrentIndex")
        return int(resp.get("queuedCmdIndex", 0)) if isinstance(resp, dict) else int(resp or 0)
