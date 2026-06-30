"""Tests for end-effector structures + low-level commands (Task 2.6).

Two layers:
- struct byte-match: ``pack_EndTypeParams`` vs ``bytes(oracle.EndTypeParams(...))``;
- FakeSerial-backed encode/decode of representative ``EffectorMixin`` methods:
  the written frame's id + rw/queued ctrl bits are asserted, and GET methods are
  checked to decode their response payloads correctly.

Oracle-based tests ``pytest.skip()`` (via the ``oracle`` fixture in
``tests/conftest.py``) when the golden ``DobotDllType`` is not importable.
"""
import struct

from dobotkit.arm import structures as S
from dobotkit.arm.ids import ProtocolId
from dobotkit.arm.lowlevel import LowLevelArm
from dobotkit.arm.protocol import Message, make_ctrl
from dobotkit.arm.transport import SerialTransport


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def make_arm(responses):
    """Build a LowLevelArm over a FakeSerial-backed SerialTransport."""
    from tests.conftest import FakeSerial

    fake = FakeSerial(responses)
    tx = SerialTransport(port="FAKE", _serial_factory=lambda *a, **k: fake)
    return LowLevelArm(tx), fake


def written_frames(fake):
    """Parse every frame the arm wrote back into Message objects."""
    raw = bytes(fake.written)
    frames = []
    i = 0
    while i < len(raw):
        length = raw[i + 2]
        end = i + 4 + length  # header(2)+len(1)+body(len)+checksum(1) == 3+length+1
        frames.append(Message.from_bytes(raw[i:end]))
        i = end
    return frames


# --------------------------------------------------------------------------- #
# Struct: EndTypeParams  ->  <fff  (12 bytes)
# --------------------------------------------------------------------------- #
def test_endtypeparams_pack_and_unpack():
    raw = S.pack_EndTypeParams(x_bias=1.0, y_bias=2.0, z_bias=3.0)
    assert raw == struct.pack("<fff", 1.0, 2.0, 3.0)
    assert len(raw) == 12
    p = S.unpack_EndTypeParams(raw)
    assert (p.x_bias, p.y_bias, p.z_bias) == (1.0, 2.0, 3.0)


def test_endtypeparams_matches_oracle(oracle):
    o = oracle.EndTypeParams()
    o.xBias = 1.0
    o.yBias = 2.0
    o.zBias = 3.0
    assert S.pack_EndTypeParams(x_bias=1.0, y_bias=2.0, z_bias=3.0) == bytes(o)


# --------------------------------------------------------------------------- #
# set/get end_effector_params
# --------------------------------------------------------------------------- #
def test_set_end_effector_params_immediate():
    # Non-queued setter: device echoes an empty-params response.
    resp = Message(id=ProtocolId.SET_GET_END_EFFECTOR_PARAMS, ctrl=make_ctrl(True, False))
    arm, fake = make_arm([resp.to_bytes()])
    assert arm.set_end_effector_params(1.0, 2.0, 3.0) is None
    (frame,) = written_frames(fake)
    assert frame.id == ProtocolId.SET_GET_END_EFFECTOR_PARAMS
    assert frame.ctrl == make_ctrl(rw=True, queued=False)  # rw=1, queued=0
    assert frame.params == struct.pack("<fff", 1.0, 2.0, 3.0)


def test_set_end_effector_params_queued_returns_index():
    idx = 42
    resp = Message(
        id=ProtocolId.SET_GET_END_EFFECTOR_PARAMS,
        ctrl=make_ctrl(True, True),
        params=struct.pack("<Q", idx),
    )
    arm, fake = make_arm([resp.to_bytes()])
    assert arm.set_end_effector_params(1.0, 2.0, 3.0, queued=True) == idx
    (frame,) = written_frames(fake)
    assert frame.id == ProtocolId.SET_GET_END_EFFECTOR_PARAMS
    assert frame.ctrl == make_ctrl(rw=True, queued=True)  # rw=1, queued=1


def test_get_end_effector_params_decodes():
    resp = Message(
        id=ProtocolId.SET_GET_END_EFFECTOR_PARAMS,
        ctrl=make_ctrl(False, False),
        params=struct.pack("<fff", 4.0, 5.0, 6.0),
    )
    arm, fake = make_arm([resp.to_bytes()])
    out = arm.get_end_effector_params()
    assert out == S.EndTypeParams(4.0, 5.0, 6.0)
    (frame,) = written_frames(fake)
    assert frame.id == ProtocolId.SET_GET_END_EFFECTOR_PARAMS
    assert frame.ctrl == make_ctrl(rw=False, queued=False)  # GET: rw=0
    assert frame.params == b""


# --------------------------------------------------------------------------- #
# suction cup (representative on/off pair)
# --------------------------------------------------------------------------- #
def test_set_suction_cup_encodes_on_off_pair_queued():
    idx = 7
    resp = Message(
        id=ProtocolId.SET_GET_END_EFFECTOR_SUCTION_CUP,
        ctrl=make_ctrl(True, True),
        params=struct.pack("<Q", idx),
    )
    arm, fake = make_arm([resp.to_bytes()])
    assert arm.set_end_effector_suction_cup(True, True, queued=True) == idx
    (frame,) = written_frames(fake)
    assert frame.id == ProtocolId.SET_GET_END_EFFECTOR_SUCTION_CUP
    assert frame.ctrl == make_ctrl(rw=True, queued=True)
    assert frame.params == struct.pack("<BB", 1, 1)


def test_get_suction_cup_decodes_pair():
    resp = Message(
        id=ProtocolId.SET_GET_END_EFFECTOR_SUCTION_CUP,
        ctrl=make_ctrl(False, False),
        params=struct.pack("<BB", 1, 0),
    )
    arm, fake = make_arm([resp.to_bytes()])
    assert arm.get_end_effector_suction_cup() == (True, False)
    (frame,) = written_frames(fake)
    assert frame.id == ProtocolId.SET_GET_END_EFFECTOR_SUCTION_CUP
    assert frame.ctrl == make_ctrl(rw=False, queued=False)


def test_set_laser_off_immediate():
    resp = Message(id=ProtocolId.SET_GET_END_EFFECTOR_LASER, ctrl=make_ctrl(True, False))
    arm, fake = make_arm([resp.to_bytes()])
    assert arm.set_end_effector_laser(False, False) is None
    (frame,) = written_frames(fake)
    assert frame.id == ProtocolId.SET_GET_END_EFFECTOR_LASER
    assert frame.ctrl == make_ctrl(rw=True, queued=False)
    assert frame.params == struct.pack("<BB", 0, 0)


def test_get_gripper_decodes_pair():
    resp = Message(
        id=ProtocolId.SET_GET_END_EFFECTOR_GRIPPER,
        ctrl=make_ctrl(False, False),
        params=struct.pack("<BB", 1, 1),
    )
    arm, fake = make_arm([resp.to_bytes()])
    assert arm.get_end_effector_gripper() == (True, True)


# --------------------------------------------------------------------------- #
# end-effector type  ->  <B
# --------------------------------------------------------------------------- #
def test_set_end_effector_type_encodes_uint8_queued():
    idx = 3
    resp = Message(
        id=ProtocolId.SET_GET_END_EFFECTOR_TYPE,
        ctrl=make_ctrl(True, True),
        params=struct.pack("<Q", idx),
    )
    arm, fake = make_arm([resp.to_bytes()])
    assert arm.set_end_effector_type(2, queued=True) == idx
    (frame,) = written_frames(fake)
    assert frame.id == ProtocolId.SET_GET_END_EFFECTOR_TYPE
    assert frame.ctrl == make_ctrl(rw=True, queued=True)
    assert frame.params == struct.pack("<B", 2)


def test_get_end_effector_type_decodes():
    resp = Message(
        id=ProtocolId.SET_GET_END_EFFECTOR_TYPE,
        ctrl=make_ctrl(False, False),
        params=struct.pack("<B", 1),
    )
    arm, fake = make_arm([resp.to_bytes()])
    assert arm.get_end_effector_type() == 1
    (frame,) = written_frames(fake)
    assert frame.id == ProtocolId.SET_GET_END_EFFECTOR_TYPE
    assert frame.ctrl == make_ctrl(rw=False, queued=False)


# --------------------------------------------------------------------------- #
# servo angle  ->  SET <Bf, GET request <B / response <f
# --------------------------------------------------------------------------- #
def test_set_servo_angle_encodes_id_and_angle_queued():
    idx = 11
    resp = Message(
        id=ProtocolId.SET_GET_SERVO_ANGLE,
        ctrl=make_ctrl(True, True),
        params=struct.pack("<Q", idx),
    )
    arm, fake = make_arm([resp.to_bytes()])
    assert arm.set_servo_angle(1, 45.0, queued=True) == idx
    (frame,) = written_frames(fake)
    assert frame.id == ProtocolId.SET_GET_SERVO_ANGLE
    assert frame.ctrl == make_ctrl(rw=True, queued=True)
    assert frame.params == struct.pack("<Bf", 1, 45.0)


def test_get_servo_angle_encodes_id_and_decodes_angle():
    resp = Message(
        id=ProtocolId.SET_GET_SERVO_ANGLE,
        ctrl=make_ctrl(False, False),
        params=struct.pack("<f", 90.5),
    )
    arm, fake = make_arm([resp.to_bytes()])
    assert arm.get_servo_angle(2) == 90.5
    (frame,) = written_frames(fake)
    assert frame.id == ProtocolId.SET_GET_SERVO_ANGLE
    assert frame.ctrl == make_ctrl(rw=False, queued=False)
    assert frame.params == struct.pack("<B", 2)
