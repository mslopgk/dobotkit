"""Shared base for the low-level Dobot arm API.

:class:`_LowLevelBase` owns the transport, the on-device command queue, and the
two primitives every category mixin builds on: :meth:`_send` (frame out, frame
back) and :meth:`_queued_index` (decode the uint64 queue index returned by a
queued setter). Category command sets are layered on as mixins; see
:class:`dobotkit.arm.lowlevel.LowLevelArm`.
"""
from __future__ import annotations

import struct
from typing import List

from dobotkit.arm.protocol import Message, make_ctrl
from dobotkit.arm.queue import CommandQueue
from dobotkit.arm.transport import SerialTransport


class _LowLevelProtocol:
    """Typed view of the shared state and primitives every category mixin uses.

    The category mixins (``DeviceMixin``, ``PoseMixin``, ...) live in disjoint
    modules and never inherit :class:`_LowLevelBase` directly, yet they call
    ``self._send`` / ``self._queued_index`` and read ``self.transport`` /
    ``self.queue``. Each mixin inherits this class so the type-checker knows
    those members exist; at runtime :class:`LowLevelArm`'s MRO always resolves
    them to :class:`_LowLevelBase`'s concrete implementations, so the
    ``NotImplementedError`` bodies below are never executed.
    """

    transport: SerialTransport
    queue: CommandQueue

    def _send(
        self,
        id: int,
        params: bytes = b"",
        *,
        rw: bool = False,
        queued: bool = False,
    ) -> Message:
        raise NotImplementedError

    def _queued_index(self, resp: Message) -> int:
        raise NotImplementedError


class _LowLevelBase(_LowLevelProtocol):
    """Transport, queue, and the ``_send`` / ``_queued_index`` primitives."""

    def __init__(self, transport: SerialTransport) -> None:
        self.transport = transport
        self.queue = CommandQueue(transport)

    # -- primitives --------------------------------------------------------

    def _send(
        self,
        id: int,
        params: bytes = b"",
        *,
        rw: bool = False,
        queued: bool = False,
    ) -> Message:
        """Build a frame, send it over the transport, and return the response."""
        return self.transport.send(
            Message(id=id, ctrl=make_ctrl(rw, queued), params=params)
        )

    def _queued_index(self, resp: Message) -> int:
        """Decode the 64-bit queued-command index from a queued setter response."""
        if not resp.params:
            return 0
        return int(struct.unpack("<Q", resp.params[:8])[0])

    # -- discovery ---------------------------------------------------------

    @staticmethod
    def search_dobot() -> List[str]:
        """Enumerate serial ports that look like a connected Dobot.

        Pure-Python replacement for the SDK's DLL ``SearchDobot``: it scans the
        host's serial ports via :mod:`pyserial` and returns the device names
        (e.g. ``"COM3"``, ``"/dev/ttyUSB0"``) of likely candidates. The DLL
        filtered by USB VID/PID; here every available serial port is reported so
        callers can pass one to :class:`~dobotkit.arm.transport.SerialTransport`.

        Returns an empty list when ``pyserial`` is unavailable.
        """
        try:
            from serial.tools import list_ports
        except Exception:
            return []
        return [port.device for port in list_ports.comports()]

    # -- lifecycle ---------------------------------------------------------

    def connect(self) -> None:
        """Open the underlying transport.

        The :class:`~dobotkit.arm.transport.SerialTransport` opens its port in
        its constructor, so this delegates to ``transport.open()`` only when the
        transport exposes one (a no-op for the already-open serial transport).
        """
        opener = getattr(self.transport, "open", None)
        if callable(opener):
            opener()

    def disconnect(self) -> None:
        """Close the underlying transport."""
        self.transport.close()
