"""Tests for arm payload (un)packing — Task 1.3 CORE motion set.

Every struct in the core set is byte-matched against the golden oracle
(``DobotDllType``). Oracle-based tests ``pytest.skip()`` (via the ``oracle``
fixture in ``tests/conftest.py``) when the oracle is not importable.
"""
import struct

from dobotkit.arm import structures as S


# --------------------------------------------------------------------------- #
# fmt_from_fields helper (ctypes -> struct char map)
# --------------------------------------------------------------------------- #
def test_fmt_from_fields_basic():
    from ctypes import c_byte, c_float, c_uint32

    fields = [("a", c_byte), ("b", c_float), ("c", c_uint32)]
    assert S.fmt_from_fields(fields) == "<bfI"


def test_fmt_from_fields_fixed_array():
    from ctypes import c_byte

    fields = [("name", c_byte * 66)]
    assert S.fmt_from_fields(fields) == "<66s"


# --------------------------------------------------------------------------- #
# PTPCmd
# --------------------------------------------------------------------------- #
def test_ptpcmd_format_and_size():
    raw = S.pack_PTPCmd(mode=2, x=200.0, y=0.0, z=50.0, r=0.0)
    assert raw == struct.pack("<Bffff", 2, 200.0, 0.0, 50.0, 0.0)
    assert len(raw) == 17


def test_ptpcmd_unpack_roundtrip():
    raw = S.pack_PTPCmd(mode=2, x=200.0, y=0.0, z=50.0, r=0.0)
    cmd = S.unpack_PTPCmd(raw)
    assert (cmd.mode, cmd.x, cmd.y, cmd.z, cmd.r) == (2, 200.0, 0.0, 50.0, 0.0)


def test_ptpcmd_matches_oracle(oracle):
    ours = S.pack_PTPCmd(mode=2, x=200.0, y=0.0, z=50.0, r=0.0)
    o = oracle.PTPCmd()
    o.ptpMode = 2
    o.x = 200.0
    o.y = 0.0
    o.z = 50.0
    o.rHead = 0.0
    assert ours == bytes(o)


# --------------------------------------------------------------------------- #
# Pose
# --------------------------------------------------------------------------- #
def test_pose_unpack():
    raw = struct.pack("<8f", 1, 2, 3, 4, 5, 6, 7, 8)
    p = S.unpack_Pose(raw)
    assert (p.x, p.y, p.z, p.r) == (1, 2, 3, 4)
    assert (p.j1, p.j2, p.j3, p.j4) == (5, 6, 7, 8)


def test_pose_pack_roundtrip():
    raw = S.pack_Pose(1, 2, 3, 4, 5, 6, 7, 8)
    assert raw == struct.pack("<8f", 1, 2, 3, 4, 5, 6, 7, 8)
    assert len(raw) == 32


def test_pose_matches_oracle(oracle):
    o = oracle.Pose()
    o.x = 1.0
    o.y = 2.0
    o.z = 3.0
    o.rHead = 4.0
    o.joint1Angle = 5.0
    o.joint2Angle = 6.0
    o.joint3Angle = 7.0
    o.joint4Angle = 8.0
    ours = S.pack_Pose(1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0)
    assert ours == bytes(o)


# --------------------------------------------------------------------------- #
# HOMEParams
# --------------------------------------------------------------------------- #
def test_homeparams_pack_and_unpack():
    raw = S.pack_HOMEParams(x=200.0, y=0.0, z=50.0, r=10.0)
    assert raw == struct.pack("<ffff", 200.0, 0.0, 50.0, 10.0)
    hp = S.unpack_HOMEParams(raw)
    assert (hp.x, hp.y, hp.z, hp.r) == (200.0, 0.0, 50.0, 10.0)


def test_homeparams_matches_oracle(oracle):
    o = oracle.HOMEParams()
    o.x = 200.0
    o.y = 0.0
    o.z = 50.0
    o.r = 10.0
    assert S.pack_HOMEParams(x=200.0, y=0.0, z=50.0, r=10.0) == bytes(o)


# --------------------------------------------------------------------------- #
# HOMECmd
# --------------------------------------------------------------------------- #
def test_homecmd_pack_and_unpack():
    raw = S.pack_HOMECmd(temp=12.5)
    assert raw == struct.pack("<f", 12.5)
    assert S.unpack_HOMECmd(raw).temp == 12.5


def test_homecmd_matches_oracle(oracle):
    o = oracle.HOMECmd()
    o.temp = 12.5
    assert S.pack_HOMECmd(temp=12.5) == bytes(o)


# --------------------------------------------------------------------------- #
# PTPCommonParams
# --------------------------------------------------------------------------- #
def test_ptpcommonparams_pack_and_unpack():
    raw = S.pack_PTPCommonParams(velocity_ratio=50.0, acceleration_ratio=80.0)
    assert raw == struct.pack("<ff", 50.0, 80.0)
    p = S.unpack_PTPCommonParams(raw)
    assert (p.velocity_ratio, p.acceleration_ratio) == (50.0, 80.0)


def test_ptpcommonparams_matches_oracle(oracle):
    o = oracle.PTPCommonParams()
    o.velocityRatio = 50.0
    o.accelerationRatio = 80.0
    assert S.pack_PTPCommonParams(velocity_ratio=50.0, acceleration_ratio=80.0) == bytes(o)


# --------------------------------------------------------------------------- #
# PTPCoordinateParams
# --------------------------------------------------------------------------- #
def test_ptpcoordinateparams_pack_and_unpack():
    raw = S.pack_PTPCoordinateParams(
        xyz_velocity=100.0, r_velocity=100.0, xyz_acceleration=80.0, r_acceleration=80.0
    )
    assert raw == struct.pack("<ffff", 100.0, 100.0, 80.0, 80.0)
    p = S.unpack_PTPCoordinateParams(raw)
    assert (p.xyz_velocity, p.r_velocity, p.xyz_acceleration, p.r_acceleration) == (
        100.0,
        100.0,
        80.0,
        80.0,
    )


def test_ptpcoordinateparams_matches_oracle(oracle):
    o = oracle.PTPCoordinateParams()
    o.xyzVelocity = 100.0
    o.rVelocity = 100.0
    o.xyzAcceleration = 80.0
    o.rAcceleration = 80.0
    ours = S.pack_PTPCoordinateParams(
        xyz_velocity=100.0, r_velocity=100.0, xyz_acceleration=80.0, r_acceleration=80.0
    )
    assert ours == bytes(o)


# --------------------------------------------------------------------------- #
# PTPJointParams
# --------------------------------------------------------------------------- #
def test_ptpjointparams_pack_and_unpack():
    vels = (1.0, 2.0, 3.0, 4.0)
    accs = (5.0, 6.0, 7.0, 8.0)
    raw = S.pack_PTPJointParams(velocities=vels, accelerations=accs)
    assert raw == struct.pack("<8f", 1, 2, 3, 4, 5, 6, 7, 8)
    p = S.unpack_PTPJointParams(raw)
    assert p.velocities == vels
    assert p.accelerations == accs


def test_ptpjointparams_matches_oracle(oracle):
    o = oracle.PTPJointParams()
    o.joint1Velocity = 1.0
    o.joint2Velocity = 2.0
    o.joint3Velocity = 3.0
    o.joint4Velocity = 4.0
    o.joint1Acceleration = 5.0
    o.joint2Acceleration = 6.0
    o.joint3Acceleration = 7.0
    o.joint4Acceleration = 8.0
    ours = S.pack_PTPJointParams(
        velocities=(1.0, 2.0, 3.0, 4.0), accelerations=(5.0, 6.0, 7.0, 8.0)
    )
    assert ours == bytes(o)


# --------------------------------------------------------------------------- #
# PTPJumpParams
# --------------------------------------------------------------------------- #
def test_ptpjumpparams_pack_and_unpack():
    raw = S.pack_PTPJumpParams(jump_height=20.0, z_limit=150.0)
    assert raw == struct.pack("<ff", 20.0, 150.0)
    p = S.unpack_PTPJumpParams(raw)
    assert (p.jump_height, p.z_limit) == (20.0, 150.0)


def test_ptpjumpparams_matches_oracle(oracle):
    o = oracle.PTPJumpParams()
    o.jumpHeight = 20.0
    o.zLimit = 150.0
    assert S.pack_PTPJumpParams(jump_height=20.0, z_limit=150.0) == bytes(o)


# --------------------------------------------------------------------------- #
# JOGCmd
# --------------------------------------------------------------------------- #
def test_jogcmd_pack_and_unpack():
    raw = S.pack_JOGCmd(is_joint=1, cmd=3)
    assert raw == struct.pack("<bb", 1, 3)
    assert len(raw) == 2
    c = S.unpack_JOGCmd(raw)
    assert (c.is_joint, c.cmd) == (1, 3)


def test_jogcmd_matches_oracle(oracle):
    o = oracle.JOGCmd()
    o.isJoint = 1
    o.cmd = 3
    assert S.pack_JOGCmd(is_joint=1, cmd=3) == bytes(o)


# --------------------------------------------------------------------------- #
# JOGCommonParams
# --------------------------------------------------------------------------- #
def test_jogcommonparams_pack_and_unpack():
    raw = S.pack_JOGCommonParams(velocity_ratio=50.0, acceleration_ratio=80.0)
    assert raw == struct.pack("<ff", 50.0, 80.0)
    p = S.unpack_JOGCommonParams(raw)
    assert (p.velocity_ratio, p.acceleration_ratio) == (50.0, 80.0)


def test_jogcommonparams_matches_oracle(oracle):
    o = oracle.JOGCommonParams()
    o.velocityRatio = 50.0
    o.accelerationRatio = 80.0
    assert S.pack_JOGCommonParams(velocity_ratio=50.0, acceleration_ratio=80.0) == bytes(o)
