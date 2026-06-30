"""Exception hierarchy shared across all dobotkit devices."""
from __future__ import annotations
from typing import Sequence


class DobotError(Exception):
    """Base class for all dobotkit errors."""


class DobotConnectionError(DobotError):
    """Connection failed: device not found, port occupied, or disconnected."""


class DobotTimeoutError(DobotError):
    """A response or motion-completion wait exceeded its timeout."""


class DobotProtocolError(DobotError):
    """Malformed frame, bad checksum, or undecodable payload."""


class DobotValueError(DobotError):
    """An argument was out of range or otherwise invalid."""


class DobotLinkError(DobotError):
    """GO only: DobotLink not running, or an RPC returned an error response."""


class DobotAlarmError(DobotError):
    """The arm reported one or more active alarms."""

    def __init__(self, codes: Sequence[int], message: str = "") -> None:
        self.codes = list(codes)
        text = message or f"active alarms: {self.codes}"
        super().__init__(text)
