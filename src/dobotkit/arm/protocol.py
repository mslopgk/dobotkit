"""Dobot serial frame: [0xAA 0xAA][len][id][ctrl][params...][checksum]."""
from __future__ import annotations

from dobotkit.exceptions import DobotProtocolError

HEADER = b"\xAA\xAA"


def make_ctrl(rw: bool, queued: bool) -> int:
    return (1 if rw else 0) | (2 if queued else 0)


def checksum(id: int, ctrl: int, params: bytes) -> int:
    total = (id + ctrl + sum(params)) % 256
    return (256 - total) % 256


class Message:
    __slots__ = ("id", "ctrl", "params")

    def __init__(self, id: int, ctrl: int = 0, params: bytes = b"") -> None:
        self.id = id
        self.ctrl = ctrl
        self.params = bytes(params)

    def to_bytes(self) -> bytes:
        length = 2 + len(self.params)
        body = bytes([self.id, self.ctrl]) + self.params
        return HEADER + bytes([length]) + body + bytes([checksum(self.id, self.ctrl, self.params)])

    @classmethod
    def from_bytes(cls, raw: bytes) -> "Message":
        if len(raw) < 6 or raw[:2] != HEADER:
            raise DobotProtocolError(f"bad header: {raw[:2]!r}")
        length = raw[2]
        id_, ctrl = raw[3], raw[4]
        params = raw[5:5 + (length - 2)]
        expect = checksum(id_, ctrl, params)
        got = raw[5 + (length - 2)]
        if got != expect:
            raise DobotProtocolError(f"bad checksum: got {got}, expected {expect}")
        return cls(id=id_, ctrl=ctrl, params=params)

    def __repr__(self) -> str:
        return f"Message(id={self.id}, ctrl={self.ctrl:#04b}, params={self.params.hex()})"
