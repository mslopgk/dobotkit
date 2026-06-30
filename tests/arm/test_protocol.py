import pytest
from dobotkit.arm.protocol import Message, make_ctrl, checksum
from dobotkit.exceptions import DobotProtocolError


def test_make_ctrl():
    assert make_ctrl(rw=False, queued=False) == 0b00
    assert make_ctrl(rw=True, queued=False) == 0b01
    assert make_ctrl(rw=True, queued=True) == 0b11


def test_checksum_known_vector():
    # GetPose: id=10, ctrl=0, no params -> checksum = (256 - 10) % 256 = 246
    assert checksum(10, 0, b"") == 246


def test_roundtrip_no_params():
    m = Message(id=10, ctrl=0, params=b"")
    raw = m.to_bytes()
    assert raw[:2] == b"\xAA\xAA"
    assert raw[2] == 2          # len = 2 + 0
    assert raw[3] == 10         # id
    assert raw[4] == 0          # ctrl
    assert raw[5] == 246        # checksum
    back = Message.from_bytes(raw)
    assert back.id == 10 and back.ctrl == 0 and back.params == b""


def test_roundtrip_with_params():
    m = Message(id=84, ctrl=0b11, params=b"\x02\x00\x01")
    raw = m.to_bytes()
    back = Message.from_bytes(raw)
    assert back.id == 84 and back.ctrl == 0b11 and back.params == b"\x02\x00\x01"


def test_bad_header_raises():
    with pytest.raises(DobotProtocolError):
        Message.from_bytes(b"\x00\x00\x02\x0a\x00\xf6")


def test_bad_checksum_raises():
    with pytest.raises(DobotProtocolError):
        Message.from_bytes(b"\xAA\xAA\x02\x0a\x00\x00")
