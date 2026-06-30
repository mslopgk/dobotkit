"""Serial transport for the Dobot arm.

Wraps a ``pyserial`` connection and speaks the Dobot frame protocol defined in
:mod:`dobotkit.arm.protocol`. Each :meth:`SerialTransport.send` writes one
request frame and reads exactly one response frame, guarded by an internal lock
so concurrent callers cannot interleave reads and writes on the same port.

The concrete serial class is injectable via ``_serial_factory`` so tests can
substitute an in-memory double without touching real hardware.
"""
from __future__ import annotations

import threading
from typing import Any, Callable, List, Optional

import serial
from serial.tools import list_ports

from dobotkit.arm.protocol import HEADER, Message, checksum
from dobotkit.exceptions import (
    DobotConnectionError,
    DobotProtocolError,
    DobotTimeoutError,
)

SerialFactory = Callable[..., Any]


class SerialTransport:
    """A thread-safe, frame-oriented serial link to a Dobot arm."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 1.0,
        _serial_factory: SerialFactory = serial.Serial,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._lock = threading.Lock()
        try:
            self._serial = _serial_factory(port, baudrate, timeout=timeout)
        except DobotConnectionError:
            raise
        except Exception as exc:  # serial.SerialException, OSError, ...
            raise DobotConnectionError(
                f"could not open serial port {port!r}: {exc}"
            ) from exc

    # -- lifecycle ---------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return bool(getattr(self._serial, "is_open", False))

    def close(self) -> None:
        """Close the underlying serial port (idempotent)."""
        try:
            self._serial.close()
        except Exception:  # pragma: no cover - close should not raise
            pass

    def __enter__(self) -> "SerialTransport":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- discovery ---------------------------------------------------------

    @staticmethod
    def search() -> List[str]:
        """Return the device names of all currently available serial ports."""
        return [p.device for p in list_ports.comports()]

    # -- I/O ---------------------------------------------------------------

    def send(self, message: Message) -> Message:
        """Write ``message`` as a frame and return the parsed response frame.

        Raises:
            DobotConnectionError: the port is closed or a serial error occurs.
            DobotTimeoutError: no (complete) response frame arrives in time.
            DobotProtocolError: the response frame fails checksum validation.
        """
        if not self.is_open:
            raise DobotConnectionError("serial port is not open")
        frame = message.to_bytes()
        with self._lock:
            try:
                self._serial.write(frame)
            except Exception as exc:
                raise DobotConnectionError(f"serial write failed: {exc}") from exc
            return self._read_frame()

    def _read_exact(self, n: int) -> bytes:
        """Read exactly ``n`` bytes or raise ``DobotTimeoutError``.

        ``pyserial.read`` returns fewer than ``n`` bytes when the configured
        read timeout elapses, so a short read means the device went silent.
        """
        try:
            data = self._serial.read(n)
        except Exception as exc:
            raise DobotConnectionError(f"serial read failed: {exc}") from exc
        if len(data) < n:
            raise DobotTimeoutError(
                f"timed out reading {n} bytes (got {len(data)})"
            )
        return bytes(data)

    def _read_frame(self) -> Message:
        """Read one full frame: sync to header, then length + body + checksum."""
        # Sync to the 0xAA 0xAA header, skipping any leading garbage.
        prev: Optional[int] = None
        while True:
            byte = self._read_exact(1)[0]
            if prev == HEADER[0] and byte == HEADER[1]:
                break
            prev = byte
        length = self._read_exact(1)[0]
        # length counts id + ctrl + params; body is id+ctrl+params, checksum follows.
        body = self._read_exact(length)
        chk = self._read_exact(1)[0]
        id_, ctrl = body[0], body[1]
        params = body[2:]
        expect = checksum(id_, ctrl, params)
        if chk != expect:
            raise DobotProtocolError(
                f"bad checksum: got {chk}, expected {expect}"
            )
        return Message(id=id_, ctrl=ctrl, params=params)
