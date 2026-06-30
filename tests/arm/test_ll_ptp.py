"""Tests for the PTP category (Task 2.3).

Covers:
- (a) byte-match of each NEW struct (``PTPWithLCmd``, ``PTPLParams``) against the
  golden oracle (``DobotDllType``); oracle tests ``pytest.skip()`` when the
  oracle is not importable.
- (b) ``FakeSerial``-backed encode/decode tests for representative ``PtpMixin``
  methods: assert the written frame's id + rw/queued ctrl bits, that queued
  setters return the queued index, and that GET methods decode correctly.
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
    """Parse the single request frame captured by the FakeSerial."""
    return Message.from_bytes(bytes(fake.written))


# --------------------------------------------------------------------------- #
# (a) NEW struct byte-match tests
# --------------------------------------------------------------------------- #
# PTPWithLCmd -> <Bfffff (21 bytes): ptpMode, x, y, z, rHead, l
def test_ptpwithlcmd_format_and_size():
    raw = S.pack_PTPWithLCmd(mode=2, x=200.0, y=0.0, z=50.0, r=0.0, l=10.0)
    assert raw == struct.pack("<Bfffff", 2, 200.0, 0.0, 50.0, 0.0, 10.0)
    assert len(raw) == 21


def test_ptpwithlcmd_unpack_roundtrip():
    raw = S.pack_PTPWithLCmd(mode=2, x=200.0, y=0.0, z=50.0, r=0.0, l=10.0)
    cmd = S.unpack_PTPWithLCmd(raw)
    assert (cmd.mode, cmd.x, cmd.y, cmd.z, cmd.r, cmd.l) == (2, 200.0, 0.0, 50.0, 0.0, 10.0)


def test_ptpwithlcmd_matches_oracle(oracle):
    o = oracle.PTPWithLCmd()
    o.ptpMode = 2
    o.x = 200.0
    o.y = 0.0
    o.z = 50.0
    o.rHead = 0.0
    o.l = 10.0
    ours = S.pack_PTPWithLCmd(mode=2, x=200.0, y=0.0, z=50.0, r=0.0, l=10.0)
    assert ours == bytes(o)


# PTPLParams -> <ff (8 bytes): velocity, acceleration
def test_ptplparams_format_and_size():
    raw = S.pack_PTPLParams(velocity=100.0, acceleration=80.0)
    assert raw == struct.pack("<ff", 100.0, 80.0)
    assert len(raw) == 8


def test_ptplparams_unpack_roundtrip():
    raw = S.pack_PTPLParams(velocity=100.0, acceleration=80.0)
    p = S.unpack_PTPLParams(raw)
    assert (p.velocity, p.acceleration) == (100.0, 80.0)


def test_ptplparams_matches_oracle(oracle):
    o = oracle.PTPLParams()
    o.velocity = 100.0
    o.acceleration = 80.0
    assert S.pack_PTPLParams(velocity=100.0, acceleration=80.0) == bytes(o)


# --------------------------------------------------------------------------- #
# (b) FakeSerial-backed encode/decode tests for representative methods
# --------------------------------------------------------------------------- #
def test_set_ptp_cmd_queued_writes_id_and_ctrl_and_returns_index():
    # Queued setter: ctrl rw=1, queued=1 -> 0b11; response carries the uint64 index.
    resp = Message(
        id=ProtocolId.SET_PTP_CMD, ctrl=0b11, params=struct.pack("<Q", 42)
    ).to_bytes()
    arm, fake = make_arm([resp])

    idx = arm.set_ptp_cmd(2, 200.0, 0.0, 50.0, 0.0, queued=True)

    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_PTP_CMD  # id == 84
    assert frame.ctrl == 0b11  # rw=1, queued=1
    assert frame.params == S.pack_PTPCmd(2, 200.0, 0.0, 50.0, 0.0)
    assert idx == 42


def test_set_ptp_cmd_immediate_sets_rw_only_and_returns_none():
    resp = Message(id=ProtocolId.SET_PTP_CMD, ctrl=0b01, params=b"").to_bytes()
    arm, fake = make_arm([resp])

    result = arm.set_ptp_cmd(1, 10.0, 20.0, 30.0, 40.0)  # queued defaults to False

    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_PTP_CMD
    assert frame.ctrl == 0b01  # rw=1, queued=0
    assert result is None


def test_set_ptp_with_l_cmd_writes_correct_id_and_payload():
    resp = Message(
        id=ProtocolId.SET_PTP_WITH_L_CMD, ctrl=0b11, params=struct.pack("<Q", 7)
    ).to_bytes()
    arm, fake = make_arm([resp])

    idx = arm.set_ptp_with_l_cmd(2, 200.0, 0.0, 50.0, 0.0, 10.0, queued=True)

    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_PTP_WITH_L_CMD  # id == 86
    assert frame.ctrl == 0b11
    assert frame.params == S.pack_PTPWithLCmd(2, 200.0, 0.0, 50.0, 0.0, 10.0)
    assert idx == 7


def test_set_ptp_joint_params_writes_rw_bit_and_payload():
    resp = Message(id=ProtocolId.SET_GET_PTP_JOINT_PARAMS, ctrl=0b01, params=b"").to_bytes()
    arm, fake = make_arm([resp])

    arm.set_ptp_joint_params((1.0, 2.0, 3.0, 4.0), (5.0, 6.0, 7.0, 8.0))

    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_PTP_JOINT_PARAMS  # id == 80
    assert frame.ctrl == 0b01  # rw=1, queued=0
    assert frame.params == S.pack_PTPJointParams(
        (1.0, 2.0, 3.0, 4.0), (5.0, 6.0, 7.0, 8.0)
    )


def test_get_ptp_joint_params_decodes_response():
    payload = S.pack_PTPJointParams((1.0, 2.0, 3.0, 4.0), (5.0, 6.0, 7.0, 8.0))
    resp = Message(
        id=ProtocolId.SET_GET_PTP_JOINT_PARAMS, ctrl=0, params=payload
    ).to_bytes()
    arm, fake = make_arm([resp])

    params = arm.get_ptp_joint_params()

    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_PTP_JOINT_PARAMS
    assert frame.ctrl == 0b00  # GET: rw=0, queued=0
    assert params.velocities == (1.0, 2.0, 3.0, 4.0)
    assert params.accelerations == (5.0, 6.0, 7.0, 8.0)


def test_get_ptp_coordinate_params_decodes_response():
    payload = S.pack_PTPCoordinateParams(
        xyz_velocity=100.0, r_velocity=90.0, xyz_acceleration=80.0, r_acceleration=70.0
    )
    resp = Message(
        id=ProtocolId.SET_GET_PTP_COORDINATE_PARAMS, ctrl=0, params=payload
    ).to_bytes()
    arm, fake = make_arm([resp])

    p = arm.get_ptp_coordinate_params()

    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_PTP_COORDINATE_PARAMS  # id == 81
    assert frame.ctrl == 0b00
    assert (p.xyz_velocity, p.r_velocity, p.xyz_acceleration, p.r_acceleration) == (
        100.0,
        90.0,
        80.0,
        70.0,
    )


def test_set_ptp_l_params_and_get_ptp_l_params():
    # SET (immediate)
    set_resp = Message(
        id=ProtocolId.SET_GET_PTP_L_PARAMS, ctrl=0b01, params=b""
    ).to_bytes()
    arm, fake = make_arm([set_resp])
    arm.set_ptp_l_params(velocity=100.0, acceleration=80.0)
    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_PTP_L_PARAMS  # id == 85
    assert frame.ctrl == 0b01
    assert frame.params == S.pack_PTPLParams(velocity=100.0, acceleration=80.0)

    # GET
    payload = S.pack_PTPLParams(velocity=100.0, acceleration=80.0)
    get_resp = Message(
        id=ProtocolId.SET_GET_PTP_L_PARAMS, ctrl=0, params=payload
    ).to_bytes()
    arm2, fake2 = make_arm([get_resp])
    p = arm2.get_ptp_l_params()
    frame2 = written_frame(fake2)
    assert frame2.ctrl == 0b00
    assert (p.velocity, p.acceleration) == (100.0, 80.0)


def test_get_ptp_jump_params_decodes_response():
    payload = S.pack_PTPJumpParams(jump_height=20.0, z_limit=150.0)
    resp = Message(
        id=ProtocolId.SET_GET_PTP_JUMP_PARAMS, ctrl=0, params=payload
    ).to_bytes()
    arm, fake = make_arm([resp])

    p = arm.get_ptp_jump_params()

    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_PTP_JUMP_PARAMS  # id == 82
    assert frame.ctrl == 0b00
    assert (p.jump_height, p.z_limit) == (20.0, 150.0)


def test_set_ptp_jump_params_queued_returns_index():
    resp = Message(
        id=ProtocolId.SET_GET_PTP_JUMP_PARAMS, ctrl=0b11, params=struct.pack("<Q", 9)
    ).to_bytes()
    arm, fake = make_arm([resp])

    idx = arm.set_ptp_jump_params(jump_height=20.0, z_limit=150.0, queued=True)

    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_PTP_JUMP_PARAMS
    assert frame.ctrl == 0b11  # rw=1, queued=1
    assert idx == 9


def test_get_ptp_common_params_decodes_response():
    payload = S.pack_PTPCommonParams(velocity_ratio=50.0, acceleration_ratio=80.0)
    resp = Message(
        id=ProtocolId.SET_GET_PTP_COMMON_PARAMS, ctrl=0, params=payload
    ).to_bytes()
    arm, fake = make_arm([resp])

    p = arm.get_ptp_common_params()

    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_PTP_COMMON_PARAMS  # id == 83
    assert frame.ctrl == 0b00
    assert (p.velocity_ratio, p.acceleration_ratio) == (50.0, 80.0)


def test_set_ptp_common_params_immediate():
    resp = Message(
        id=ProtocolId.SET_GET_PTP_COMMON_PARAMS, ctrl=0b01, params=b""
    ).to_bytes()
    arm, fake = make_arm([resp])

    result = arm.set_ptp_common_params(velocity_ratio=50.0, acceleration_ratio=80.0)

    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_PTP_COMMON_PARAMS
    assert frame.ctrl == 0b01
    assert frame.params == S.pack_PTPCommonParams(
        velocity_ratio=50.0, acceleration_ratio=80.0
    )
    assert result is None


def test_set_ptp_coordinate_params_immediate():
    resp = Message(
        id=ProtocolId.SET_GET_PTP_COORDINATE_PARAMS, ctrl=0b01, params=b""
    ).to_bytes()
    arm, fake = make_arm([resp])

    arm.set_ptp_coordinate_params(
        xyz_velocity=100.0, r_velocity=90.0, xyz_acceleration=80.0, r_acceleration=70.0
    )

    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_PTP_COORDINATE_PARAMS
    assert frame.ctrl == 0b01
    assert frame.params == S.pack_PTPCoordinateParams(
        xyz_velocity=100.0, r_velocity=90.0, xyz_acceleration=80.0, r_acceleration=70.0
    )
