"""Tests for the device category: structures + lowlevel DeviceMixin (Task 2.1).

Two kinds of test:

(a) golden-oracle byte-match for each NEW device struct (skips if the oracle
    ``DobotDllType.py`` is not importable);
(b) FakeSerial-backed encode/decode tests for representative DeviceMixin
    methods — asserting the *written* frame's id + rw/queued ctrl bits and that
    GET methods decode their response correctly.
"""
import struct

import pytest

from dobotkit.arm import structures as S
from dobotkit.arm.ids import ProtocolId
from dobotkit.arm.lowlevel import LowLevelArm
from dobotkit.arm.protocol import Message
from dobotkit.arm.transport import SerialTransport
from tests.conftest import FakeSerial


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def make_arm(responses=None):
    """Build a LowLevelArm over a FakeSerial-backed SerialTransport."""
    fake = FakeSerial(responses or [])
    tx = SerialTransport(port="FAKE", _serial_factory=lambda *a, **k: fake)
    return LowLevelArm(tx), fake


def resp_frame(id_: int, params: bytes = b"") -> bytes:
    """Build a device response frame (rw=0)."""
    return Message(id=id_, ctrl=0, params=params).to_bytes()


def written_msg(fake: FakeSerial) -> Message:
    """Parse the single frame the arm wrote to the fake serial."""
    return Message.from_bytes(bytes(fake.written))


# --------------------------------------------------------------------------- #
# (a) struct byte-match vs oracle
# --------------------------------------------------------------------------- #
def test_device_version_matches_oracle(oracle):
    ours = S.pack_DeviceVersion(1, 2, 3, 4, 5, 6, 7, 8)
    o = oracle.DeviceVersion()
    o.fw_majorVersion = 1
    o.fw_minorVersion = 2
    o.fw_revision = 3
    o.fw_alphaVersion = 4
    o.hw_majorVersion = 5
    o.hw_minorVersion = 6
    o.hw_revision = 7
    o.hw_alphaVersion = 8
    assert ours == bytes(o)
    assert len(ours) == 8


def test_device_id_matches_oracle(oracle):
    ours = S.pack_DeviceID(0x11111111, 0x22222222, 0x33333333)
    o = oracle.DeviceID()
    o.deviceID1 = 0x11111111
    o.deviceID2 = 0x22222222
    o.deviceID3 = 0x33333333
    assert ours == bytes(o)
    assert len(ours) == 12


def test_devinfo_matches_oracle(oracle):
    ours = S.pack_DevInfo(
        dev_id=7,
        type=2,
        firmware_name=b"fw-name",
        firmware_version=b"1.2.3",
        run_time=12.5,
    )
    o = oracle.DevInfo()
    o.devId = 7
    o.type = 2
    o.firmwareName = (oracle.c_byte * 50)(*b"fw-name")
    o.firwareVersion = (oracle.c_byte * 50)(*b"1.2.3")
    o.runTime = 12.5
    assert ours == bytes(o)
    assert len(ours) == struct.calcsize("<ii50s50sf")


def test_device_count_info_matches_oracle(oracle):
    ours = S.pack_DeviceCountInfo(
        device_run_time=0x0102030405060708,
        device_power_on=0x0A0B0C0D,
        device_power_off=0x11223344,
    )
    o = oracle.DeviceCountInfo()
    o.deviceRunTime = 0x0102030405060708
    o.devicePowerOn = 0x0A0B0C0D
    o.devicePowerOff = 0x11223344
    assert ours == bytes(o)
    assert len(ours) == 16


# --------------------------------------------------------------------------- #
# (a') struct round-trips (no oracle required)
# --------------------------------------------------------------------------- #
def test_device_version_roundtrip():
    raw = S.pack_DeviceVersion(1, 2, 3, 4, 5, 6, 7, 8)
    v = S.unpack_DeviceVersion(raw)
    assert v == S.DeviceVersion(1, 2, 3, 4, 5, 6, 7, 8)
    assert v.fw_major == 1 and v.hw_alpha == 8


def test_device_id_roundtrip():
    raw = S.pack_DeviceID(10, 20, 30)
    assert S.unpack_DeviceID(raw) == S.DeviceID(10, 20, 30)


def test_devinfo_roundtrip():
    raw = S.pack_DevInfo(dev_id=3, type=1, firmware_name="fw", firmware_version="v1", run_time=2.0)
    info = S.unpack_DevInfo(raw)
    assert info.dev_id == 3 and info.type == 1 and info.run_time == 2.0
    assert info.firmware_name.split(b"\x00", 1)[0] == b"fw"
    assert info.firmware_version.split(b"\x00", 1)[0] == b"v1"


def test_device_count_info_roundtrip():
    raw = S.pack_DeviceCountInfo(123456789, 42, 7)
    assert S.unpack_DeviceCountInfo(raw) == S.DeviceCountInfo(123456789, 42, 7)


# --------------------------------------------------------------------------- #
# (b) FakeSerial-backed method tests — GET decode + frame id/ctrl assertions
# --------------------------------------------------------------------------- #
def test_get_device_version_decodes_and_frames():
    payload = bytes([1, 2, 3, 4, 5, 6, 7, 8])
    arm, fake = make_arm([resp_frame(ProtocolId.GET_DEVICE_VERSION, payload)])
    got = arm.get_device_version()
    assert got == S.DeviceVersion(1, 2, 3, 4, 5, 6, 7, 8)
    m = written_msg(fake)
    assert m.id == ProtocolId.GET_DEVICE_VERSION
    assert m.ctrl & 0b01 == 0  # rw=0 (read)
    assert m.ctrl & 0b10 == 0  # not queued
    assert m.params == b""


def test_get_device_id_decodes():
    payload = struct.pack("<3I", 100, 200, 300)
    arm, fake = make_arm([resp_frame(ProtocolId.GET_DEVICE_ID, payload)])
    assert arm.get_device_id() == S.DeviceID(100, 200, 300)
    assert written_msg(fake).id == ProtocolId.GET_DEVICE_ID


def test_get_device_time_decodes_uint32():
    payload = struct.pack("<I", 0xDEADBEEF)
    arm, fake = make_arm([resp_frame(ProtocolId.GET_DEVICE_TIME, payload)])
    assert arm.get_device_time() == 0xDEADBEEF
    assert written_msg(fake).id == ProtocolId.GET_DEVICE_TIME


def test_get_device_info_decodes():
    payload = struct.pack("<QII", 999, 11, 3)
    arm, fake = make_arm([resp_frame(ProtocolId.GET_DEVICE_INFO, payload)])
    assert arm.get_device_info() == S.DeviceCountInfo(999, 11, 3)


def test_get_device_sn_decodes_cstring():
    payload = b"SN12345\x00garbage"
    arm, fake = make_arm([resp_frame(ProtocolId.GET_SET_DEVICE_SN, payload)])
    assert arm.get_device_sn() == "SN12345"
    m = written_msg(fake)
    assert m.id == ProtocolId.GET_SET_DEVICE_SN and m.ctrl & 0b01 == 0


def test_get_device_name_decodes_cstring():
    payload = b"Dobot-1\x00\x00\x00"
    arm, fake = make_arm([resp_frame(ProtocolId.GET_SET_DEVICE_NAME, payload)])
    assert arm.get_device_name() == "Dobot-1"


# -- SET encode tests --------------------------------------------------------
def test_set_device_sn_writes_write_frame():
    arm, fake = make_arm([resp_frame(ProtocolId.GET_SET_DEVICE_SN)])
    arm.set_device_sn("ABC")
    m = written_msg(fake)
    assert m.id == ProtocolId.GET_SET_DEVICE_SN
    assert m.ctrl & 0b01 == 1  # rw=1 (write)
    assert m.params == b"ABC\x00"


def test_set_device_name_writes_write_frame():
    arm, fake = make_arm([resp_frame(ProtocolId.GET_SET_DEVICE_NAME)])
    arm.set_device_name("arm")
    m = written_msg(fake)
    assert m.id == ProtocolId.GET_SET_DEVICE_NAME
    assert m.ctrl & 0b01 == 1
    assert m.params == b"arm\x00"


# -- with-L (GET/SET pair sharing one id, differing by rw) -------------------
def test_set_device_with_l_immediate():
    arm, fake = make_arm([resp_frame(ProtocolId.SET_GET_PTP_L_PARAMS)])
    assert arm.set_device_with_l(True, version=2) is None
    m = written_msg(fake)
    assert m.ctrl & 0b01 == 1  # write
    assert m.ctrl & 0b10 == 0  # immediate
    assert m.params == struct.pack("<?B", True, 2)


def test_set_device_with_l_queued_returns_index():
    qidx = struct.pack("<Q", 77)
    arm, fake = make_arm([resp_frame(ProtocolId.SET_GET_PTP_L_PARAMS, qidx)])
    assert arm.set_device_with_l(True, queued=True) == 77
    m = written_msg(fake)
    assert m.ctrl & 0b01 == 1  # write
    assert m.ctrl & 0b10 == 0b10  # queued


def test_get_device_with_l_decodes_bool():
    arm, fake = make_arm([resp_frame(ProtocolId.SET_GET_PTP_L_PARAMS, b"\x01")])
    assert arm.get_device_with_l() is True
    assert written_msg(fake).ctrl & 0b01 == 0  # read


def test_get_uart4_peripherals_type_decodes():
    arm, fake = make_arm([resp_frame(ProtocolId.GET_DEVICE_INFO, b"\x05")])
    assert arm.get_uart4_peripherals_type() == 5


# -- non-wire / local-state methods -----------------------------------------
def test_set_cmd_timeout_adjusts_transport_timeout():
    arm, _ = make_arm([])
    arm.set_cmd_timeout(2500)
    assert arm.transport.timeout == pytest.approx(2.5)


def test_restart_magic_box_writes_write_frame():
    arm, fake = make_arm([resp_frame(ProtocolId.GET_DEVICE_INFO)])
    arm.restart_magic_box()
    assert written_msg(fake).ctrl & 0b01 == 1  # write bit set
