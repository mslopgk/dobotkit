"""Tests for the JOG category — structures (Task 2.4) + LowLevelArm JogMixin.

Struct tests byte-match each NEW JOG struct against the golden oracle
(``DobotDllType``); oracle-based tests ``pytest.skip()`` (via the ``oracle``
fixture in ``tests/conftest.py``) when the oracle is not importable.

Method tests drive a real :class:`SerialTransport` over the in-memory
``FakeSerial`` double, asserting the frame written by each method (id + rw /
queued ctrl bits) and that GET methods decode their response payloads.
"""
import struct


from dobotkit.arm import structures as S
from dobotkit.arm.ids import ProtocolId
from dobotkit.arm.lowlevel import LowLevelArm
from dobotkit.arm.protocol import Message
from dobotkit.arm.transport import SerialTransport
from tests.conftest import FakeSerial


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def make_arm(responses):
    """Build a LowLevelArm over a FakeSerial preloaded with response frames."""
    fake = FakeSerial(responses)
    tx = SerialTransport(port="FAKE", _serial_factory=lambda *a, **k: fake)
    return LowLevelArm(tx), fake


def written_frame(fake):
    """Parse the single frame the arm wrote to the fake serial port."""
    return Message.from_bytes(bytes(fake.written))


# --------------------------------------------------------------------------- #
# Structures: JOGJointParams  ->  <8f  (32 bytes)
# --------------------------------------------------------------------------- #
def test_jogjointparams_pack_and_unpack():
    vels = (1.0, 2.0, 3.0, 4.0)
    accs = (5.0, 6.0, 7.0, 8.0)
    raw = S.pack_JOGJointParams(velocities=vels, accelerations=accs)
    assert raw == struct.pack("<8f", 1, 2, 3, 4, 5, 6, 7, 8)
    assert len(raw) == 32
    p = S.unpack_JOGJointParams(raw)
    assert p.velocities == vels
    assert p.accelerations == accs


def test_jogjointparams_matches_oracle(oracle):
    o = oracle.JOGJointParams()
    o.joint1Velocity = 1.0
    o.joint2Velocity = 2.0
    o.joint3Velocity = 3.0
    o.joint4Velocity = 4.0
    o.joint1Acceleration = 5.0
    o.joint2Acceleration = 6.0
    o.joint3Acceleration = 7.0
    o.joint4Acceleration = 8.0
    ours = S.pack_JOGJointParams(
        velocities=(1.0, 2.0, 3.0, 4.0), accelerations=(5.0, 6.0, 7.0, 8.0)
    )
    assert ours == bytes(o)


# --------------------------------------------------------------------------- #
# Structures: JOGCoordinateParams  ->  <8f  (32 bytes)
# --------------------------------------------------------------------------- #
def test_jogcoordinateparams_pack_and_unpack():
    vels = (10.0, 20.0, 30.0, 40.0)
    accs = (50.0, 60.0, 70.0, 80.0)
    raw = S.pack_JOGCoordinateParams(velocities=vels, accelerations=accs)
    assert raw == struct.pack("<8f", 10, 20, 30, 40, 50, 60, 70, 80)
    assert len(raw) == 32
    p = S.unpack_JOGCoordinateParams(raw)
    assert p.velocities == vels
    assert p.accelerations == accs


def test_jogcoordinateparams_matches_oracle(oracle):
    o = oracle.JOGCoordinateParams()
    o.xVelocity = 10.0
    o.yVelocity = 20.0
    o.zVelocity = 30.0
    o.rVelocity = 40.0
    o.xAcceleration = 50.0
    o.yAcceleration = 60.0
    o.zAcceleration = 70.0
    o.rAcceleration = 80.0
    ours = S.pack_JOGCoordinateParams(
        velocities=(10.0, 20.0, 30.0, 40.0), accelerations=(50.0, 60.0, 70.0, 80.0)
    )
    assert ours == bytes(o)


# --------------------------------------------------------------------------- #
# Structures: JOGLParams  ->  <ff  (8 bytes)
# --------------------------------------------------------------------------- #
def test_joglparams_pack_and_unpack():
    raw = S.pack_JOGLParams(velocity=55.0, acceleration=66.0)
    assert raw == struct.pack("<ff", 55.0, 66.0)
    assert len(raw) == 8
    p = S.unpack_JOGLParams(raw)
    assert (p.velocity, p.acceleration) == (55.0, 66.0)


def test_joglparams_matches_oracle(oracle):
    o = oracle.JOGLParams()
    o.velocity = 55.0
    o.acceleration = 66.0
    assert S.pack_JOGLParams(velocity=55.0, acceleration=66.0) == bytes(o)


# --------------------------------------------------------------------------- #
# set_jog_cmd  ->  SET_JOG_CMD (73), rw=1
# --------------------------------------------------------------------------- #
def test_set_jog_cmd_immediate_writes_frame():
    resp = Message(id=ProtocolId.SET_JOG_CMD, ctrl=0b01, params=b"").to_bytes()
    arm, fake = make_arm([resp])
    out = arm.set_jog_cmd(is_joint=1, cmd=3)
    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_JOG_CMD
    # rw bit set (write), queued bit clear.
    assert frame.ctrl & 0b01 == 0b01
    assert frame.ctrl & 0b10 == 0
    assert frame.params == S.pack_JOGCmd(is_joint=1, cmd=3)
    assert out is None


def test_set_jog_cmd_queued_returns_index():
    resp = Message(
        id=ProtocolId.SET_JOG_CMD, ctrl=0b11, params=struct.pack("<Q", 42)
    ).to_bytes()
    arm, fake = make_arm([resp])
    idx = arm.set_jog_cmd(is_joint=0, cmd=1, queued=True)
    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_JOG_CMD
    assert frame.ctrl & 0b11 == 0b11  # rw + queued
    assert idx == 42


# --------------------------------------------------------------------------- #
# set/get jog_joint_params  ->  SET_GET_JOG_JOINT_PARAMS (70)
# --------------------------------------------------------------------------- #
def test_set_jog_joint_params_immediate():
    resp = Message(
        id=ProtocolId.SET_GET_JOG_JOINT_PARAMS, ctrl=0b01, params=b""
    ).to_bytes()
    arm, fake = make_arm([resp])
    out = arm.set_jog_joint_params(
        velocities=(1.0, 2.0, 3.0, 4.0), accelerations=(5.0, 6.0, 7.0, 8.0)
    )
    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_JOG_JOINT_PARAMS
    assert frame.ctrl & 0b01 == 0b01  # write
    assert frame.ctrl & 0b10 == 0  # not queued
    assert frame.params == S.pack_JOGJointParams(
        velocities=(1.0, 2.0, 3.0, 4.0), accelerations=(5.0, 6.0, 7.0, 8.0)
    )
    assert out is None


def test_set_jog_joint_params_queued_returns_index():
    resp = Message(
        id=ProtocolId.SET_GET_JOG_JOINT_PARAMS,
        ctrl=0b11,
        params=struct.pack("<Q", 7),
    ).to_bytes()
    arm, fake = make_arm([resp])
    idx = arm.set_jog_joint_params(
        velocities=(1.0, 2.0, 3.0, 4.0),
        accelerations=(5.0, 6.0, 7.0, 8.0),
        queued=True,
    )
    frame = written_frame(fake)
    assert frame.ctrl & 0b11 == 0b11
    assert idx == 7


def test_get_jog_joint_params_decodes():
    payload = struct.pack("<8f", 1, 2, 3, 4, 5, 6, 7, 8)
    resp = Message(
        id=ProtocolId.SET_GET_JOG_JOINT_PARAMS, ctrl=0, params=payload
    ).to_bytes()
    arm, fake = make_arm([resp])
    p = arm.get_jog_joint_params()
    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_JOG_JOINT_PARAMS
    assert frame.ctrl & 0b01 == 0  # read
    assert p.velocities == (1.0, 2.0, 3.0, 4.0)
    assert p.accelerations == (5.0, 6.0, 7.0, 8.0)


# --------------------------------------------------------------------------- #
# set/get jog_coordinate_params  ->  SET_GET_JOG_COORDINATE_PARAMS (71)
# --------------------------------------------------------------------------- #
def test_set_jog_coordinate_params_immediate():
    resp = Message(
        id=ProtocolId.SET_GET_JOG_COORDINATE_PARAMS, ctrl=0b01, params=b""
    ).to_bytes()
    arm, fake = make_arm([resp])
    arm.set_jog_coordinate_params(
        velocities=(10.0, 20.0, 30.0, 40.0), accelerations=(50.0, 60.0, 70.0, 80.0)
    )
    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_JOG_COORDINATE_PARAMS
    assert frame.ctrl & 0b01 == 0b01
    assert frame.params == S.pack_JOGCoordinateParams(
        velocities=(10.0, 20.0, 30.0, 40.0), accelerations=(50.0, 60.0, 70.0, 80.0)
    )


def test_get_jog_coordinate_params_decodes():
    payload = struct.pack("<8f", 10, 20, 30, 40, 50, 60, 70, 80)
    resp = Message(
        id=ProtocolId.SET_GET_JOG_COORDINATE_PARAMS, ctrl=0, params=payload
    ).to_bytes()
    arm, fake = make_arm([resp])
    p = arm.get_jog_coordinate_params()
    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_JOG_COORDINATE_PARAMS
    assert frame.ctrl & 0b01 == 0  # read
    assert p.velocities == (10.0, 20.0, 30.0, 40.0)
    assert p.accelerations == (50.0, 60.0, 70.0, 80.0)


# --------------------------------------------------------------------------- #
# set/get jog_l_params  ->  SET_GET_JOG_L_PARAMS (74)
# --------------------------------------------------------------------------- #
def test_set_jog_l_params_immediate():
    resp = Message(
        id=ProtocolId.SET_GET_JOG_L_PARAMS, ctrl=0b01, params=b""
    ).to_bytes()
    arm, fake = make_arm([resp])
    arm.set_jog_l_params(velocity=55.0, acceleration=66.0)
    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_JOG_L_PARAMS
    assert frame.ctrl & 0b01 == 0b01
    assert frame.params == S.pack_JOGLParams(velocity=55.0, acceleration=66.0)


def test_get_jog_l_params_decodes():
    payload = struct.pack("<ff", 55.0, 66.0)
    resp = Message(
        id=ProtocolId.SET_GET_JOG_L_PARAMS, ctrl=0, params=payload
    ).to_bytes()
    arm, fake = make_arm([resp])
    p = arm.get_jog_l_params()
    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_JOG_L_PARAMS
    assert frame.ctrl & 0b01 == 0  # read
    assert (p.velocity, p.acceleration) == (55.0, 66.0)


# --------------------------------------------------------------------------- #
# set/get jog_common_params  ->  SET_GET_JOG_COMMON_PARAMS (72)
# --------------------------------------------------------------------------- #
def test_set_jog_common_params_queued_returns_index():
    resp = Message(
        id=ProtocolId.SET_GET_JOG_COMMON_PARAMS,
        ctrl=0b11,
        params=struct.pack("<Q", 99),
    ).to_bytes()
    arm, fake = make_arm([resp])
    idx = arm.set_jog_common_params(
        velocity_ratio=50.0, acceleration_ratio=80.0, queued=True
    )
    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_JOG_COMMON_PARAMS
    assert frame.ctrl & 0b11 == 0b11
    assert frame.params == S.pack_JOGCommonParams(
        velocity_ratio=50.0, acceleration_ratio=80.0
    )
    assert idx == 99


def test_get_jog_common_params_decodes():
    payload = struct.pack("<ff", 50.0, 80.0)
    resp = Message(
        id=ProtocolId.SET_GET_JOG_COMMON_PARAMS, ctrl=0, params=payload
    ).to_bytes()
    arm, fake = make_arm([resp])
    p = arm.get_jog_common_params()
    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_JOG_COMMON_PARAMS
    assert frame.ctrl & 0b01 == 0  # read
    assert (p.velocity_ratio, p.acceleration_ratio) == (50.0, 80.0)
