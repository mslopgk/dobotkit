"""The Dobot arm command queue.

Motion commands sent with the *queued* control bit set are appended to an
on-device FIFO and executed in order once :meth:`CommandQueue.start` is called.
Each queued command is assigned a monotonically increasing 64-bit index; the
host tracks progress by polling :meth:`current_index` and can block until a
given index has executed with :meth:`wait_for`.

This module owns only the queue-control protocol IDs (clear / start / stop /
force-stop / current-index / motion-finish). It speaks through a
:class:`~dobotkit.arm.transport.SerialTransport`, so it is fully exercised in
tests with the in-memory ``FakeSerial`` double.
"""
from __future__ import annotations

import struct
import time

from dobotkit.arm.ids import ProtocolId
from dobotkit.arm.protocol import Message, make_ctrl
from dobotkit.arm.transport import SerialTransport
from dobotkit.exceptions import DobotTimeoutError


class CommandQueue:
    """High-level control over the arm's on-device command queue."""

    def __init__(self, transport: SerialTransport) -> None:
        self.transport = transport

    # -- internal ----------------------------------------------------------

    def _send(
        self,
        id: ProtocolId,
        params: bytes = b"",
        *,
        rw: bool = False,
        queued: bool = False,
    ) -> Message:
        """Build a frame, send it, and return the parsed response frame."""
        return self.transport.send(
            Message(id=id, ctrl=make_ctrl(rw, queued), params=params)
        )

    # -- control commands --------------------------------------------------

    def clear(self) -> None:
        """Empty the command queue, discarding all pending commands."""
        self._send(ProtocolId.SET_QUEUED_CMD_CLEAR, rw=True)

    def start(self) -> None:
        """Begin executing queued commands in FIFO order."""
        self._send(ProtocolId.SET_QUEUED_CMD_START_EXEC, rw=True)

    def stop(self) -> None:
        """Stop executing queued commands after the current one finishes."""
        self._send(ProtocolId.SET_QUEUED_CMD_STOP_EXEC, rw=True)

    def force_stop(self) -> None:
        """Immediately abort the running queue (does not wait for completion)."""
        self._send(ProtocolId.SET_QUEUED_CMD_FORCE_STOP_EXEC, rw=True)

    # -- queries -----------------------------------------------------------

    def current_index(self) -> int:
        """Return the index of the most recently executed queued command."""
        resp = self._send(ProtocolId.GET_QUEUED_CMD_CURRENT_INDEX)
        (index,) = struct.unpack("<Q", resp.params)
        return int(index)

    def motion_finished(self) -> bool:
        """Return ``True`` when all queued motion commands have completed."""
        resp = self._send(ProtocolId.GET_QUEUED_CMD_MOTION_FINISH)
        (finished,) = struct.unpack("<?", resp.params)
        return bool(finished)

    # -- blocking helper ---------------------------------------------------

    def wait_for(
        self,
        index: int,
        poll: float = 0.05,
        timeout: float = 30.0,
    ) -> None:
        """Block until the queue has executed command ``index``.

        Polls :meth:`current_index` every ``poll`` seconds, returning as soon as
        the executed index is greater than or equal to ``index``.

        Args:
            index: The queued-command index to wait for.
            poll: Seconds to sleep between polls. ``0`` polls as fast as the
                transport allows.
            timeout: Maximum seconds to wait before giving up.

        Raises:
            DobotTimeoutError: ``timeout`` elapsed before ``index`` was reached.
        """
        deadline = time.monotonic() + timeout
        while True:
            if self.current_index() >= index:
                return
            if time.monotonic() >= deadline:
                raise DobotTimeoutError(
                    f"queue index {index} not reached within {timeout}s"
                )
            time.sleep(poll)
