"""Tests for the CP / ARC / Circle low-level command set (Task 2.5).

Two layers:

* **Struct byte-match** — every NEW structure is packed and compared against
  ``bytes(oracle.StructX(...))`` (the golden ``DobotDllType``). These skip via
  the ``oracle`` fixture when the oracle is not importable.
* **Method encode/decode** — a ``FakeSerial``-backed ``LowLevelArm`` exercises
  representative methods, asserting the written frame's id + rw/queued ctrl
  bits and that GET methods decode their response correctly.
"""
import struct


from dobotkit.arm import structures as S
from dobotkit.arm.ids import ProtocolId
from dobotkit.arm.lowlevel import LowLevelArm
from dobotkit.arm.protocol import Message, make_ctrl
from dobotkit.arm.transport import SerialTransport


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def make_arm(responses=None):
    """A LowLevelArm over a FakeSerial-backed transport (injectable factory)."""
    from tests.conftest import FakeSerial

    fake = FakeSerial(responses or [])
    tx = SerialTransport(port="FAKE", _serial_factory=lambda *a, **k: fake)
    return LowLevelArm(tx), fake


def queued_frame(id_):
    """A queued-setter response frame carrying a uint64 queue index (=7)."""
    return Message(id=id_, ctrl=make_ctrl(True, True), params=struct.pack("<Q", 7)).to_bytes()


def ack_frame(id_):
    """An immediate-setter ack frame (no payload)."""
    return Message(id=id_, ctrl=make_ctrl(True, False)).to_bytes()


def get_frame(id_, params):
    """A GET response frame carrying decoded struct bytes."""
    return Message(id=id_, ctrl=make_ctrl(False, False), params=params).to_bytes()


def written_msg(fake):
    return Message.from_bytes(bytes(fake.written))


# --------------------------------------------------------------------------- #
# Struct byte-match vs oracle
# --------------------------------------------------------------------------- #
def test_cpcmd_format_and_size():
    raw = S.pack_CPCmd(cp_mode=1, x=200.0, y=0.0, z=50.0, velocity=100.0)
    assert raw == struct.pack("<bffff", 1, 200.0, 0.0, 50.0, 100.0)
    assert len(raw) == 17


def test_cpcmd_matches_oracle(oracle):
    o = oracle.CPCmd()
    o.cpMode = 1
    o.x = 200.0
    o.y = 0.0
    o.z = 50.0
    o.velocity = 100.0
    assert S.pack_CPCmd(cp_mode=1, x=200.0, y=0.0, z=50.0, velocity=100.0) == bytes(o)


def test_cp2cmd_matches_oracle(oracle):
    o = oracle.CP2Cmd()
    o.cpMode = 0
    o.x = 10.0
    o.y = 20.0
    o.z = 30.0
    o.velocity = 100.0
    assert S.pack_CP2Cmd(cp_mode=0, x=10.0, y=20.0, z=30.0, velocity=100.0) == bytes(o)


def test_cpparams_format_and_size():
    raw = S.pack_CPParams(plan_acc=100.0, junction_vel=50.0, acc=80.0, real_time_track=1)
    assert raw == struct.pack("<fffb", 100.0, 50.0, 80.0, 1)
    assert len(raw) == 13


def test_cpparams_matches_oracle(oracle):
    o = oracle.CPParams()
    o.planAcc = 100.0
    o.juncitionVel = 50.0
    o.acc = 80.0
    o.realTimeTrack = 1
    assert (
        S.pack_CPParams(plan_acc=100.0, junction_vel=50.0, acc=80.0, real_time_track=1)
        == bytes(o)
    )


def test_cpparams_unpack_roundtrip():
    raw = S.pack_CPParams(plan_acc=100.0, junction_vel=50.0, acc=80.0, real_time_track=1)
    p = S.unpack_CPParams(raw)
    assert (p.plan_acc, p.junction_vel, p.acc, p.real_time_track) == (100.0, 50.0, 80.0, 1)


def test_cpcommonparams_matches_oracle(oracle):
    o = oracle.CPCommonParams()
    o.velocityRatio = 50.0
    o.accelerationRatio = 80.0
    assert S.pack_CPCommonParams(velocity_ratio=50.0, acceleration_ratio=80.0) == bytes(o)


def test_arcparams_matches_oracle(oracle):
    o = oracle.ARCParams()
    o.xyzVelocity = 100.0
    o.rVelocity = 90.0
    o.xyzAcceleration = 80.0
    o.rAcceleration = 70.0
    ours = S.pack_ARCParams(
        xyz_velocity=100.0, r_velocity=90.0, xyz_acceleration=80.0, r_acceleration=70.0
    )
    assert ours == bytes(o)


def test_arcpoint_matches_oracle(oracle):
    o = oracle.ARCPoint()
    o.x = 1.0
    o.y = 2.0
    o.z = 3.0
    o.rHead = 4.0
    assert S.pack_ARCPoint(1.0, 2.0, 3.0, 4.0) == bytes(o)


def test_arccmd_format_and_matches_oracle(oracle):
    raw = S.pack_ARCCmd(S.ARCPoint(1, 2, 3, 4), S.ARCPoint(5, 6, 7, 8))
    assert raw == struct.pack("<8f", 1, 2, 3, 4, 5, 6, 7, 8)
    assert len(raw) == 32
    o = oracle.ARCCmd()
    o.cirPoint.x, o.cirPoint.y, o.cirPoint.z, o.cirPoint.rHead = 1, 2, 3, 4
    o.toPoint.x, o.toPoint.y, o.toPoint.z, o.toPoint.rHead = 5, 6, 7, 8
    assert raw == bytes(o)


def test_arccmd_unpack_roundtrip():
    raw = S.pack_ARCCmd(S.ARCPoint(1, 2, 3, 4), S.ARCPoint(5, 6, 7, 8))
    cmd = S.unpack_ARCCmd(raw)
    assert cmd.cir_point == S.ARCPoint(1, 2, 3, 4)
    assert cmd.to_point == S.ARCPoint(5, 6, 7, 8)


def test_circlecmd_matches_oracle(oracle):
    raw = S.pack_CircleCmd(S.ARCPoint(1, 2, 3, 4), S.ARCPoint(5, 6, 7, 8))
    o = oracle.CircleCmd()
    o.cirPoint.x, o.cirPoint.y, o.cirPoint.z, o.cirPoint.rHead = 1, 2, 3, 4
    o.toPoint.x, o.toPoint.y, o.toPoint.z, o.toPoint.rHead = 5, 6, 7, 8
    assert raw == bytes(o)


def test_arccommonparams_matches_oracle(oracle):
    o = oracle.ARCCommonParams()
    o.velocityRatio = 60.0
    o.accelerationRatio = 40.0
    assert S.pack_ARCCommonParams(velocity_ratio=60.0, acceleration_ratio=40.0) == bytes(o)


def test_waitparams_matches_oracle(oracle):
    o = oracle.WAITParams()
    o.unitType = 2
    assert S.pack_WAITParams(unit_type=2) == bytes(o)
    assert len(S.pack_WAITParams(unit_type=2)) == 1


# --------------------------------------------------------------------------- #
# Method encode/decode (FakeSerial)
# --------------------------------------------------------------------------- #
def test_set_cp_cmd_immediate_frame():
    arm, fake = make_arm([ack_frame(ProtocolId.SET_CP_CMD)])
    out = arm.set_cp_cmd(1, 200.0, 0.0, 50.0, 100.0)
    assert out is None
    msg = written_msg(fake)
    assert msg.id == ProtocolId.SET_CP_CMD
    assert msg.ctrl == make_ctrl(rw=True, queued=False)
    assert msg.params == S.pack_CPCmd(1, 200.0, 0.0, 50.0, 100.0)


def test_set_cp_cmd_queued_returns_index():
    arm, fake = make_arm([queued_frame(ProtocolId.SET_CP_CMD)])
    idx = arm.set_cp_cmd(1, 200.0, 0.0, 50.0, 100.0, queued=True)
    assert idx == 7
    msg = written_msg(fake)
    assert msg.id == ProtocolId.SET_CP_CMD
    assert msg.ctrl == make_ctrl(rw=True, queued=True)


def test_set_cp2_cmd_frame():
    arm, fake = make_arm([queued_frame(ProtocolId.SET_CP2_CMD)])
    idx = arm.set_cp2_cmd(0, 10.0, 20.0, 30.0, queued=True)
    assert idx == 7
    msg = written_msg(fake)
    assert msg.id == ProtocolId.SET_CP2_CMD
    assert msg.ctrl == make_ctrl(rw=True, queued=True)
    assert msg.params == S.pack_CP2Cmd(0, 10.0, 20.0, 30.0, 100.0)


def test_set_cp_le_cmd_frame():
    arm, fake = make_arm([ack_frame(ProtocolId.SET_CP_LE_CMD)])
    arm.set_cp_le_cmd(1, 5.0, 6.0, 7.0, power=80.0)
    msg = written_msg(fake)
    assert msg.id == ProtocolId.SET_CP_LE_CMD
    assert msg.ctrl == make_ctrl(rw=True, queued=False)
    # power rides in the velocity field
    assert msg.params == S.pack_CPCmd(1, 5.0, 6.0, 7.0, 80.0)


def test_set_cp_params_immediate():
    arm, fake = make_arm([ack_frame(ProtocolId.SET_GET_CP_PARAMS)])
    arm.set_cp_params(100.0, 50.0, 80.0, real_time_track=0)
    msg = written_msg(fake)
    assert msg.id == ProtocolId.SET_GET_CP_PARAMS
    assert msg.ctrl == make_ctrl(rw=True, queued=False)
    assert msg.params == S.pack_CPParams(100.0, 50.0, 80.0, 0)


def test_get_cp_params_decodes_and_uses_read_bit():
    payload = S.pack_CPParams(100.0, 50.0, 80.0, 1)
    arm, fake = make_arm([get_frame(ProtocolId.SET_GET_CP_PARAMS, payload)])
    result = arm.get_cp_params()
    assert result == S.CPParams(100.0, 50.0, 80.0, 1)
    msg = written_msg(fake)
    assert msg.id == ProtocolId.SET_GET_CP_PARAMS
    assert msg.ctrl == make_ctrl(rw=False, queued=False)  # GET uses rw=0


def test_get_cp_common_params_decodes():
    payload = S.pack_CPCommonParams(50.0, 80.0)
    arm, fake = make_arm([get_frame(ProtocolId.SET_GET_CP_COMMON_PARAMS, payload)])
    result = arm.get_cp_common_params()
    assert result == S.CPCommonParams(50.0, 80.0)
    assert written_msg(fake).ctrl == make_ctrl(rw=False, queued=False)


def test_set_cp_common_params_shares_id_with_get():
    arm, fake = make_arm([ack_frame(ProtocolId.SET_GET_CP_COMMON_PARAMS)])
    arm.set_cp_common_params(50.0, 80.0)
    msg = written_msg(fake)
    assert msg.id == ProtocolId.SET_GET_CP_COMMON_PARAMS
    assert msg.ctrl == make_ctrl(rw=True, queued=False)  # SET uses rw=1


def test_set_and_get_cpr_hold_enable():
    arm, fake = make_arm([ack_frame(ProtocolId.SET_GET_CP_PARAMS)])
    arm.set_cpr_hold_enable(True)
    msg = written_msg(fake)
    assert msg.ctrl == make_ctrl(rw=True, queued=False)
    assert msg.params == struct.pack("<?", True)

    arm2, _ = make_arm([get_frame(ProtocolId.SET_GET_CP_PARAMS, struct.pack("<?", True))])
    assert arm2.get_cpr_hold_enable() is True


def test_set_arc_cmd_frame():
    arm, fake = make_arm([queued_frame(ProtocolId.SET_ARC_CMD)])
    idx = arm.set_arc_cmd((1, 2, 3, 4), (5, 6, 7, 8), queued=True)
    assert idx == 7
    msg = written_msg(fake)
    assert msg.id == ProtocolId.SET_ARC_CMD
    assert msg.ctrl == make_ctrl(rw=True, queued=True)
    assert msg.params == S.pack_ARCCmd(S.ARCPoint(1, 2, 3, 4), S.ARCPoint(5, 6, 7, 8))


def test_set_circle_cmd_frame():
    arm, fake = make_arm([ack_frame(ProtocolId.SET_CIRCLE_CMD)])
    arm.set_circle_cmd((1, 2, 3, 4), (5, 6, 7, 8))
    msg = written_msg(fake)
    assert msg.id == ProtocolId.SET_CIRCLE_CMD
    assert msg.params == S.pack_CircleCmd(S.ARCPoint(1, 2, 3, 4), S.ARCPoint(5, 6, 7, 8))


def test_set_arc_params_and_get_decodes():
    arm, fake = make_arm([ack_frame(ProtocolId.SET_GET_ARC_PARAMS)])
    arm.set_arc_params(100.0, 90.0, 80.0, 70.0)
    msg = written_msg(fake)
    assert msg.id == ProtocolId.SET_GET_ARC_PARAMS
    assert msg.ctrl == make_ctrl(rw=True, queued=False)

    payload = S.pack_ARCParams(100.0, 90.0, 80.0, 70.0)
    arm2, fake2 = make_arm([get_frame(ProtocolId.SET_GET_ARC_PARAMS, payload)])
    result = arm2.get_arc_params()
    assert result == S.ARCParams(100.0, 90.0, 80.0, 70.0)
    assert written_msg(fake2).ctrl == make_ctrl(rw=False, queued=False)


def test_get_arc_common_params_decodes():
    payload = S.pack_ARCCommonParams(60.0, 40.0)
    arm, fake = make_arm([get_frame(ProtocolId.SET_GET_ARC_COMMON_PARAMS, payload)])
    result = arm.get_arc_common_params()
    assert result == S.ARCCommonParams(60.0, 40.0)
    assert written_msg(fake).ctrl == make_ctrl(rw=False, queued=False)


def test_set_arc_common_params_queued_index():
    arm, fake = make_arm([queued_frame(ProtocolId.SET_GET_ARC_COMMON_PARAMS)])
    idx = arm.set_arc_common_params(60.0, 40.0, queued=True)
    assert idx == 7
    assert written_msg(fake).ctrl == make_ctrl(rw=True, queued=True)
