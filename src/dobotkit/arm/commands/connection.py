"""Connection and on-device command-queue RPC wrappers."""
from __future__ import annotations
from typing import Any, List, cast
from dobotkit.arm.commands._base import _Base


class ConnectionMixin(_Base):
    """Connect/disconnect the arm and control its queued-command queue."""

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
        return self._queued_index(resp)
