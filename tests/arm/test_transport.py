"""Tests for the pyserial-backed SerialTransport (with injectable factory)."""
import pytest

from dobotkit.arm.protocol import Message
from dobotkit.arm.transport import SerialTransport
from dobotkit.exceptions import DobotConnectionError, DobotTimeoutError


def make_tx(responses):
    from tests.conftest import FakeSerial

    fake = FakeSerial(responses)
    tx = SerialTransport(port="FAKE", _serial_factory=lambda *a, **k: fake)
    return tx, fake


def test_send_writes_frame_and_parses_response():
    resp = Message(id=10, ctrl=0, params=b"\x01\x02").to_bytes()
    tx, fake = make_tx([resp])
    reply = tx.send(Message(id=10, ctrl=0))
    assert fake.written == Message(id=10, ctrl=0).to_bytes()
    assert reply.id == 10 and reply.params == b"\x01\x02"


def test_timeout_on_empty():
    tx, _ = make_tx([])
    with pytest.raises(DobotTimeoutError):
        tx.send(Message(id=10, ctrl=0))


def test_send_with_params_roundtrip():
    resp = Message(id=84, ctrl=0b11, params=b"\xaa\xbb\xcc").to_bytes()
    tx, fake = make_tx([resp])
    sent = Message(id=84, ctrl=0b11, params=b"\x01\x02\x03")
    reply = tx.send(sent)
    assert fake.written == sent.to_bytes()
    assert reply.id == 84 and reply.ctrl == 0b11 and reply.params == b"\xaa\xbb\xcc"


def test_skips_garbage_before_header():
    # Leading noise bytes before the 0xAA 0xAA header must be skipped.
    resp = Message(id=10, ctrl=0, params=b"\x07").to_bytes()
    tx, _ = make_tx([b"\x00\x13\x42" + resp])
    reply = tx.send(Message(id=10, ctrl=0))
    assert reply.id == 10 and reply.params == b"\x07"


def test_timeout_on_truncated_response():
    # A header but a short/truncated body must raise a timeout, not hang.
    full = Message(id=10, ctrl=0, params=b"\x01\x02\x03").to_bytes()
    tx, _ = make_tx([full[:-2]])  # drop checksum + last param byte
    with pytest.raises(DobotTimeoutError):
        tx.send(Message(id=10, ctrl=0))


def test_close_marks_serial_closed():
    tx, fake = make_tx([])
    tx.close()
    assert fake.is_open is False


def test_send_after_close_raises_connection_error():
    tx, _ = make_tx([])
    tx.close()
    with pytest.raises(DobotConnectionError):
        tx.send(Message(id=10, ctrl=0))


def test_context_manager_closes():
    from tests.conftest import FakeSerial

    fake = FakeSerial([])
    with SerialTransport(port="FAKE", _serial_factory=lambda *a, **k: fake) as tx:
        assert tx.is_open is True
    assert fake.is_open is False


def test_connection_error_when_factory_fails():
    def boom(*a, **k):
        raise OSError("port occupied")

    with pytest.raises(DobotConnectionError):
        SerialTransport(port="FAKE", _serial_factory=boom)


def test_search_returns_port_names(monkeypatch):
    class _Port:
        def __init__(self, device):
            self.device = device

    import dobotkit.arm.transport as transport_mod

    monkeypatch.setattr(
        transport_mod.list_ports,
        "comports",
        lambda: [_Port("COM3"), _Port("COM7")],
    )
    assert SerialTransport.search() == ["COM3", "COM7"]


def test_factory_receives_port_and_baudrate():
    captured = {}

    def factory(*args, **kwargs):
        from tests.conftest import FakeSerial

        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeSerial([])

    SerialTransport(port="COM9", baudrate=9600, timeout=2.0, _serial_factory=factory)
    # port/baudrate/timeout must reach the underlying serial factory.
    flat = list(captured["args"]) + list(captured["kwargs"].values())
    assert "COM9" in flat
    assert 9600 in flat
