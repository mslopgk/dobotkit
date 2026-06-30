"""Tests for :mod:`dobotkit.arm.queue` (the ``CommandQueue`` helper).

Driven entirely by ``FakeSerial`` queuing response frames; no real hardware and
no real time delays (``time.sleep`` is monkeypatched out, ``time.monotonic`` is
patched where a deterministic clock is needed).
"""
import struct

import pytest

from dobotkit.arm.ids import ProtocolId
from dobotkit.arm.protocol import Message, make_ctrl
from dobotkit.arm.queue import CommandQueue
from dobotkit.arm.transport import SerialTransport
from dobotkit.exceptions import DobotTimeoutError
from tests.conftest import FakeSerial


def _index_frame(i: int) -> bytes:
    """A GET_QUEUED_CMD_CURRENT_INDEX response carrying ``i`` as a uint64."""
    return Message(
        id=ProtocolId.GET_QUEUED_CMD_CURRENT_INDEX,
        ctrl=0,
        params=struct.pack("<Q", i),
    ).to_bytes()


def _finish_frame(finished: bool) -> bytes:
    """A GET_QUEUED_CMD_MOTION_FINISH response carrying a single bool byte."""
    return Message(
        id=ProtocolId.GET_QUEUED_CMD_MOTION_FINISH,
        ctrl=0,
        params=struct.pack("<?", finished),
    ).to_bytes()


def _ack_frame(id_: ProtocolId) -> bytes:
    """A simple acknowledgement frame echoing the command id with no payload."""
    return Message(id=id_, ctrl=make_ctrl(rw=True, queued=False), params=b"").to_bytes()


def _make_queue(frames):
    fake = FakeSerial(frames)
    tx = SerialTransport(port="F", _serial_factory=lambda *a, **k: fake)
    return CommandQueue(tx), fake


# -- control commands ------------------------------------------------------


def test_clear_writes_clear_frame():
    q, fake = _make_queue([_ack_frame(ProtocolId.SET_QUEUED_CMD_CLEAR)])
    q.clear()
    written = Message.from_bytes(bytes(fake.written))
    assert written.id == ProtocolId.SET_QUEUED_CMD_CLEAR
    assert written.ctrl & 0b01  # rw bit set (it is a "set")
    assert written.params == b""


def test_start_writes_start_frame():
    q, fake = _make_queue([_ack_frame(ProtocolId.SET_QUEUED_CMD_START_EXEC)])
    q.start()
    written = Message.from_bytes(bytes(fake.written))
    assert written.id == ProtocolId.SET_QUEUED_CMD_START_EXEC
    assert written.ctrl & 0b01


def test_stop_writes_stop_frame():
    q, fake = _make_queue([_ack_frame(ProtocolId.SET_QUEUED_CMD_STOP_EXEC)])
    q.stop()
    written = Message.from_bytes(bytes(fake.written))
    assert written.id == ProtocolId.SET_QUEUED_CMD_STOP_EXEC
    assert written.ctrl & 0b01


def test_force_stop_writes_force_stop_frame():
    q, fake = _make_queue([_ack_frame(ProtocolId.SET_QUEUED_CMD_FORCE_STOP_EXEC)])
    q.force_stop()
    written = Message.from_bytes(bytes(fake.written))
    assert written.id == ProtocolId.SET_QUEUED_CMD_FORCE_STOP_EXEC
    assert written.ctrl & 0b01


# -- queries ---------------------------------------------------------------


def test_current_index_decodes_uint64():
    q, fake = _make_queue([_index_frame(42)])
    assert q.current_index() == 42
    written = Message.from_bytes(bytes(fake.written))
    assert written.id == ProtocolId.GET_QUEUED_CMD_CURRENT_INDEX
    assert not (written.ctrl & 0b01)  # rw=0 (a "get")


def test_motion_finished_true():
    q, _ = _make_queue([_finish_frame(True)])
    assert q.motion_finished() is True


def test_motion_finished_false():
    q, fake = _make_queue([_finish_frame(False)])
    assert q.motion_finished() is False
    written = Message.from_bytes(bytes(fake.written))
    assert written.id == ProtocolId.GET_QUEUED_CMD_MOTION_FINISH
    assert not (written.ctrl & 0b01)


# -- wait_for --------------------------------------------------------------


def test_wait_for_returns_when_index_reached(monkeypatch):
    frames = [_index_frame(i) for i in (1, 3, 5)]
    fake = FakeSerial(frames)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    q = CommandQueue(SerialTransport(port="F", _serial_factory=lambda *a, **k: fake))
    q.wait_for(5, poll=0)  # should not raise


def test_wait_for_returns_immediately_when_already_past(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    q, _ = _make_queue([_index_frame(10)])
    q.wait_for(5, poll=0)  # index already >= 5 on the first poll


def test_wait_for_times_out(monkeypatch):
    # Always report index 0 so the target (99) is never reached.
    monkeypatch.setattr("time.sleep", lambda *_: None)
    # Advance the monotonic clock past the timeout on the second reading.
    clock = {"t": 0.0}

    def fake_monotonic():
        clock["t"] += 0.1
        return clock["t"]

    monkeypatch.setattr("time.monotonic", fake_monotonic)

    fake = FakeSerial()
    # Refill the queue on every read so the transport never starves.
    original_read = fake.read

    def refill_read(n=1):
        if not fake._rx:
            fake._rx += _index_frame(0)
        return original_read(n)

    fake.read = refill_read
    q = CommandQueue(SerialTransport(port="F", _serial_factory=lambda *a, **k: fake))
    with pytest.raises(DobotTimeoutError):
        q.wait_for(99, poll=0.01, timeout=0.2)
