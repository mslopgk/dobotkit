"""Tests for the pose category: structures (vs golden oracle) + lowlevel methods.

Covers Task 2.2:
- byte-match each NEW struct (Kinematics, AutoLevelingCmd, UserParams) against
  ``bytes(oracle.StructX(...))``;
- FakeSerial-backed encode/decode tests for representative ``PoseMixin`` methods
  (assert the written frame's id + rw/queued ctrl bits, and that GET methods
  decode correctly).
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
# Struct format / size sanity (no oracle needed)
# --------------------------------------------------------------------------- #
def test_kinematics_format_and_size():
    raw = S.pack_Kinematics(velocity=100.0, acceleration=50.0)
    assert raw == struct.pack("<ff", 100.0, 50.0)
    assert len(raw) == 8
    assert S.unpack_Kinematics(raw) == S.Kinematics(100.0, 50.0)


def test_auto_leveling_cmd_format_and_size():
    raw = S.pack_AutoLevelingCmd(control_flag=1, precision=0.2)
    assert raw == struct.pack("<Bf", 1, 0.2)
    assert len(raw) == 5  # packed: ubyte + float, no padding
    cmd = S.unpack_AutoLevelingCmd(raw)
    assert cmd.control_flag == 1
    assert cmd.precision == pytest.approx(0.2)


def test_user_params_format_and_size():
    raw = S.pack_UserParams(1, 2, 3, 4, 5, 6, 7, 8)
    assert raw == struct.pack("<8f", 1, 2, 3, 4, 5, 6, 7, 8)
    assert len(raw) == 32
    p = S.unpack_UserParams(raw)
    assert (p.params1, p.params8) == (1, 8)


# --------------------------------------------------------------------------- #
# Golden-oracle byte-match for each NEW struct
# --------------------------------------------------------------------------- #
def test_kinematics_matches_oracle(oracle):
    ours = S.pack_Kinematics(velocity=123.5, acceleration=42.25)
    o = oracle.Kinematics()
    o.velocity = 123.5
    o.acceleration = 42.25
    assert ours == bytes(o)


def test_auto_leveling_cmd_matches_oracle(oracle):
    ours = S.pack_AutoLevelingCmd(control_flag=1, precision=0.5)
    o = oracle.AutoLevelingCmd()
    o.controlFlag = 1
    o.precision = 0.5
    assert ours == bytes(o)


def test_user_params_matches_oracle(oracle):
    ours = S.pack_UserParams(1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5)
    o = oracle.UserParams()
    o.params1 = 1.5
    o.params2 = 2.5
    o.params3 = 3.5
    o.params4 = 4.5
    o.params5 = 5.5
    o.params6 = 6.5
    o.params7 = 7.5
    o.params8 = 8.5
    assert ours == bytes(o)


# --------------------------------------------------------------------------- #
# FakeSerial-backed lowlevel tests
# --------------------------------------------------------------------------- #
def _make_arm(responses):
    """Build a LowLevelArm over a FakeSerial preloaded with `responses`."""
    fake = FakeSerial(responses)
    tx = SerialTransport(port="FAKE", _serial_factory=lambda *a, **k: fake)
    return LowLevelArm(tx), fake


def _written_message(fake):
    """Parse the single frame the arm wrote out."""
    return Message.from_bytes(bytes(fake.written))


def test_get_pose_decodes_and_reads():
    payload = struct.pack("<8f", 200.0, 0.0, 50.0, 10.0, 1.0, 2.0, 3.0, 4.0)
    resp = Message(id=ProtocolId.GET_POSE, ctrl=0, params=payload).to_bytes()
    arm, fake = _make_arm([resp])

    pose = arm.get_pose()

    # decoded correctly
    assert isinstance(pose, S.Pose)
    assert (pose.x, pose.y, pose.z, pose.r) == (200.0, 0.0, 50.0, 10.0)
    assert (pose.j1, pose.j2, pose.j3, pose.j4) == (1.0, 2.0, 3.0, 4.0)
    # frame: GET_POSE, rw=0 (read), not queued
    sent = _written_message(fake)
    assert sent.id == ProtocolId.GET_POSE
    assert sent.ctrl & 0b01 == 0  # rw bit clear
    assert sent.ctrl & 0b10 == 0  # queued bit clear


def test_get_pose_l_decodes_float():
    resp = Message(id=ProtocolId.GET_POSE_L, ctrl=0, params=struct.pack("<f", 137.5)).to_bytes()
    arm, fake = _make_arm([resp])

    val = arm.get_pose_l()

    assert val == pytest.approx(137.5)
    sent = _written_message(fake)
    assert sent.id == ProtocolId.GET_POSE_L
    assert sent.ctrl == 0


def test_get_kinematics_decodes():
    resp = Message(
        id=ProtocolId.GET_KINEMATICS, ctrl=0, params=struct.pack("<ff", 99.0, 11.0)
    ).to_bytes()
    arm, fake = _make_arm([resp])

    kin = arm.get_kinematics()

    assert isinstance(kin, S.Kinematics)
    assert (kin.velocity, kin.acceleration) == (99.0, 11.0)
    assert _written_message(fake).id == ProtocolId.GET_KINEMATICS


def test_get_home_params_decodes():
    resp = Message(
        id=ProtocolId.SET_GET_HOME_PARAMS, ctrl=0, params=struct.pack("<ffff", 200, 0, 0, 0)
    ).to_bytes()
    arm, fake = _make_arm([resp])

    hp = arm.get_home_params()

    assert isinstance(hp, S.HOMEParams)
    assert (hp.x, hp.y, hp.z, hp.r) == (200, 0, 0, 0)
    sent = _written_message(fake)
    assert sent.id == ProtocolId.SET_GET_HOME_PARAMS
    assert sent.ctrl & 0b01 == 0  # GET => rw clear


def test_set_home_params_queued_writes_set_bits_and_returns_index():
    resp = Message(
        id=ProtocolId.SET_GET_HOME_PARAMS, ctrl=0b11, params=struct.pack("<Q", 42)
    ).to_bytes()
    arm, fake = _make_arm([resp])

    idx = arm.set_home_params(200.0, 0.0, 0.0, 0.0, queued=True)

    assert idx == 42
    sent = _written_message(fake)
    assert sent.id == ProtocolId.SET_GET_HOME_PARAMS
    assert sent.ctrl & 0b01 == 0b01  # rw set
    assert sent.ctrl & 0b10 == 0b10  # queued set
    assert sent.params == struct.pack("<ffff", 200.0, 0.0, 0.0, 0.0)


def test_set_home_cmd_queued_returns_index():
    resp = Message(
        id=ProtocolId.SET_HOME_CMD, ctrl=0b11, params=struct.pack("<Q", 7)
    ).to_bytes()
    arm, fake = _make_arm([resp])

    idx = arm.set_home_cmd(queued=True)

    assert idx == 7
    sent = _written_message(fake)
    assert sent.id == ProtocolId.SET_HOME_CMD
    assert sent.ctrl == 0b11  # rw + queued
    assert sent.params == struct.pack("<f", 0.0)


def test_set_home_cmd_immediate_returns_none():
    resp = Message(id=ProtocolId.SET_HOME_CMD, ctrl=0b01, params=b"").to_bytes()
    arm, fake = _make_arm([resp])

    assert arm.set_home_cmd() is None
    sent = _written_message(fake)
    assert sent.ctrl & 0b10 == 0  # not queued


def test_reset_pose_writes_set_bit():
    resp = Message(id=ProtocolId.RESET_POSE, ctrl=0b01, params=b"").to_bytes()
    arm, fake = _make_arm([resp])

    arm.reset_pose(manual=1, rear_arm_angle=10.0, front_arm_angle=20.0)

    sent = _written_message(fake)
    assert sent.id == ProtocolId.RESET_POSE
    assert sent.ctrl & 0b01 == 0b01  # rw set
    assert sent.params == struct.pack("<Bff", 1, 10.0, 20.0)


def test_set_auto_leveling_queued_returns_index():
    resp = Message(
        id=ProtocolId.SET_AUTO_LEVELING, ctrl=0b11, params=struct.pack("<Q", 9)
    ).to_bytes()
    arm, fake = _make_arm([resp])

    idx = arm.set_auto_leveling(control_flag=1, precision=0.3, queued=True)

    assert idx == 9
    sent = _written_message(fake)
    assert sent.id == ProtocolId.SET_AUTO_LEVELING
    assert sent.ctrl == 0b11
    assert sent.params == struct.pack("<Bf", 1, 0.3)


def test_get_auto_leveling_result_decodes_float():
    resp = Message(
        id=ProtocolId.GET_AUTO_LEVELING, ctrl=0, params=struct.pack("<f", 0.05)
    ).to_bytes()
    arm, fake = _make_arm([resp])

    precision = arm.get_auto_leveling_result()

    assert precision == pytest.approx(0.05)
    assert _written_message(fake).id == ProtocolId.GET_AUTO_LEVELING


def test_arm_orientation_set_and_get():
    # SET (queued)
    set_resp = Message(
        id=ProtocolId.SET_GET_ARM_ORIENTATION, ctrl=0b11, params=struct.pack("<Q", 3)
    ).to_bytes()
    arm, fake = _make_arm([set_resp])
    idx = arm.set_arm_orientation(1, queued=True)
    assert idx == 3
    sent = _written_message(fake)
    assert sent.id == ProtocolId.SET_GET_ARM_ORIENTATION
    assert sent.ctrl == 0b11
    assert sent.params == struct.pack("<B", 1)

    # GET
    get_resp = Message(
        id=ProtocolId.SET_GET_ARM_ORIENTATION, ctrl=0, params=struct.pack("<i", 1)
    ).to_bytes()
    arm2, fake2 = _make_arm([get_resp])
    orientation = arm2.get_arm_orientation()
    assert orientation == 1
    sent2 = _written_message(fake2)
    assert sent2.id == ProtocolId.SET_GET_ARM_ORIENTATION
    assert sent2.ctrl & 0b01 == 0  # GET => rw clear


def test_get_user_params_decodes():
    payload = struct.pack("<8f", 1, 2, 3, 4, 5, 6, 7, 8)
    # id whatever the mixin uses; decode is what matters here
    arm, fake = _make_arm([
        Message(id=arm_user_params_id(), ctrl=0, params=payload).to_bytes()
    ])
    p = arm.get_user_params()
    assert isinstance(p, S.UserParams)
    assert (p.params1, p.params8) == (1, 8)
    # GET => rw clear
    assert _written_message(fake).ctrl & 0b01 == 0


def arm_user_params_id():
    """The ProtocolId the get_user_params method sends (kept in one place)."""
    return ProtocolId.GET_USER_PARAMS
