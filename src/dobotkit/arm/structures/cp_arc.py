"""CP / ARC / Circle structures (Task 2.5).

Mirrors the ``DobotDllType`` ``Structure`` definitions for continuous-path (CP),
arc, and circle motion. The serial protocol is **little-endian, packed (no
alignment padding)** — equivalent to a ctypes struct with ``_pack_ = 1``; each
format is derived directly from the oracle ``_fields_`` list.

Naming mirrors the SDK: ``pack_<Name>`` / ``unpack_<Name>`` per structure, with
each ``unpack_*`` returning a typed :class:`typing.NamedTuple`.
"""
from __future__ import annotations

import struct
from typing import NamedTuple

__all__ = [
    "CPCmd",
    "pack_CPCmd",
    "unpack_CPCmd",
    "CP2Cmd",
    "pack_CP2Cmd",
    "unpack_CP2Cmd",
    "CPParams",
    "pack_CPParams",
    "unpack_CPParams",
    "CPCommonParams",
    "pack_CPCommonParams",
    "unpack_CPCommonParams",
    "ARCParams",
    "pack_ARCParams",
    "unpack_ARCParams",
    "ARCPoint",
    "pack_ARCPoint",
    "unpack_ARCPoint",
    "ARCCmd",
    "pack_ARCCmd",
    "unpack_ARCCmd",
    "CircleCmd",
    "pack_CircleCmd",
    "unpack_CircleCmd",
    "ARCCommonParams",
    "pack_ARCCommonParams",
    "unpack_ARCCommonParams",
    "WAITParams",
    "pack_WAITParams",
    "unpack_WAITParams",
]


# --------------------------------------------------------------------------- #
# CPCmd  ->  <bffff  (17 bytes)
#   cpMode (c_byte), x, y, z, velocity
# --------------------------------------------------------------------------- #
_CPCMD_FMT = "<bffff"


class CPCmd(NamedTuple):
    cp_mode: int
    x: float
    y: float
    z: float
    velocity: float


def pack_CPCmd(cp_mode: int, x: float, y: float, z: float, velocity: float) -> bytes:
    """Pack a continuous-path motion command (cpMode, x, y, z, velocity)."""
    return struct.pack(_CPCMD_FMT, cp_mode, x, y, z, velocity)


def unpack_CPCmd(data: bytes) -> CPCmd:
    return CPCmd(*struct.unpack(_CPCMD_FMT, data))


# --------------------------------------------------------------------------- #
# CP2Cmd  ->  <bffff  (17 bytes)  (identical layout to CPCmd)
#   cpMode (c_byte), x, y, z, velocity
# --------------------------------------------------------------------------- #
_CP2CMD_FMT = "<bffff"


class CP2Cmd(NamedTuple):
    cp_mode: int
    x: float
    y: float
    z: float
    velocity: float


def pack_CP2Cmd(cp_mode: int, x: float, y: float, z: float, velocity: float) -> bytes:
    """Pack a CP2 motion command (cpMode, x, y, z, velocity)."""
    return struct.pack(_CP2CMD_FMT, cp_mode, x, y, z, velocity)


def unpack_CP2Cmd(data: bytes) -> CP2Cmd:
    return CP2Cmd(*struct.unpack(_CP2CMD_FMT, data))


# --------------------------------------------------------------------------- #
# CPParams  ->  <fffb  (13 bytes)
#   planAcc, juncitionVel, acc (c_float), realTimeTrack (c_byte)
# --------------------------------------------------------------------------- #
_CPPARAMS_FMT = "<fffb"


class CPParams(NamedTuple):
    plan_acc: float
    junction_vel: float
    acc: float
    real_time_track: int


def pack_CPParams(
    plan_acc: float,
    junction_vel: float,
    acc: float,
    real_time_track: int = 0,
) -> bytes:
    """Pack CP planning params (planAcc, junctionVel, acc, realTimeTrack)."""
    return struct.pack(_CPPARAMS_FMT, plan_acc, junction_vel, acc, real_time_track)


def unpack_CPParams(data: bytes) -> CPParams:
    return CPParams(*struct.unpack(_CPPARAMS_FMT, data))


# --------------------------------------------------------------------------- #
# CPCommonParams  ->  <ff  (8 bytes)
#   velocityRatio, accelerationRatio
# --------------------------------------------------------------------------- #
_CPCOMMONPARAMS_FMT = "<ff"


class CPCommonParams(NamedTuple):
    velocity_ratio: float
    acceleration_ratio: float


def pack_CPCommonParams(velocity_ratio: float, acceleration_ratio: float) -> bytes:
    """Pack CP common velocity/acceleration ratios."""
    return struct.pack(_CPCOMMONPARAMS_FMT, velocity_ratio, acceleration_ratio)


def unpack_CPCommonParams(data: bytes) -> CPCommonParams:
    return CPCommonParams(*struct.unpack(_CPCOMMONPARAMS_FMT, data))


# --------------------------------------------------------------------------- #
# ARCParams  ->  <ffff  (16 bytes)
#   xyzVelocity, rVelocity, xyzAcceleration, rAcceleration
# --------------------------------------------------------------------------- #
_ARCPARAMS_FMT = "<ffff"


class ARCParams(NamedTuple):
    xyz_velocity: float
    r_velocity: float
    xyz_acceleration: float
    r_acceleration: float


def pack_ARCParams(
    xyz_velocity: float,
    r_velocity: float,
    xyz_acceleration: float,
    r_acceleration: float,
) -> bytes:
    """Pack ARC velocity/acceleration params."""
    return struct.pack(
        _ARCPARAMS_FMT,
        xyz_velocity,
        r_velocity,
        xyz_acceleration,
        r_acceleration,
    )


def unpack_ARCParams(data: bytes) -> ARCParams:
    return ARCParams(*struct.unpack(_ARCPARAMS_FMT, data))


# --------------------------------------------------------------------------- #
# ARCPoint  ->  <ffff  (16 bytes)
#   x, y, z, rHead
# --------------------------------------------------------------------------- #
_ARCPOINT_FMT = "<ffff"


class ARCPoint(NamedTuple):
    x: float
    y: float
    z: float
    r: float


def pack_ARCPoint(x: float, y: float, z: float, r: float) -> bytes:
    """Pack a single ARC waypoint (x, y, z, rHead)."""
    return struct.pack(_ARCPOINT_FMT, x, y, z, r)


def unpack_ARCPoint(data: bytes) -> ARCPoint:
    return ARCPoint(*struct.unpack(_ARCPOINT_FMT, data))


# --------------------------------------------------------------------------- #
# ARCCmd  ->  <8f  (32 bytes)
#   cirPoint (ARCPoint), toPoint (ARCPoint)
# --------------------------------------------------------------------------- #
_ARCCMD_FMT = "<8f"


class ARCCmd(NamedTuple):
    cir_point: ARCPoint
    to_point: ARCPoint


def pack_ARCCmd(cir_point: ARCPoint, to_point: ARCPoint) -> bytes:
    """Pack an ARC command (intermediate cirPoint then destination toPoint)."""
    return struct.pack(_ARCCMD_FMT, *cir_point, *to_point)


def unpack_ARCCmd(data: bytes) -> ARCCmd:
    vals = struct.unpack(_ARCCMD_FMT, data)
    return ARCCmd(
        cir_point=ARCPoint(vals[0], vals[1], vals[2], vals[3]),
        to_point=ARCPoint(vals[4], vals[5], vals[6], vals[7]),
    )


# --------------------------------------------------------------------------- #
# CircleCmd  ->  <8f  (32 bytes)  (identical layout to ARCCmd)
#   cirPoint (ARCPoint), toPoint (ARCPoint)
# --------------------------------------------------------------------------- #
_CIRCLECMD_FMT = "<8f"


class CircleCmd(NamedTuple):
    cir_point: ARCPoint
    to_point: ARCPoint


def pack_CircleCmd(cir_point: ARCPoint, to_point: ARCPoint) -> bytes:
    """Pack a Circle command (point on circle cirPoint then end toPoint)."""
    return struct.pack(_CIRCLECMD_FMT, *cir_point, *to_point)


def unpack_CircleCmd(data: bytes) -> CircleCmd:
    vals = struct.unpack(_CIRCLECMD_FMT, data)
    return CircleCmd(
        cir_point=ARCPoint(vals[0], vals[1], vals[2], vals[3]),
        to_point=ARCPoint(vals[4], vals[5], vals[6], vals[7]),
    )


# --------------------------------------------------------------------------- #
# ARCCommonParams  ->  <ff  (8 bytes)
#   velocityRatio, accelerationRatio
# --------------------------------------------------------------------------- #
_ARCCOMMONPARAMS_FMT = "<ff"


class ARCCommonParams(NamedTuple):
    velocity_ratio: float
    acceleration_ratio: float


def pack_ARCCommonParams(velocity_ratio: float, acceleration_ratio: float) -> bytes:
    """Pack ARC common velocity/acceleration ratios."""
    return struct.pack(_ARCCOMMONPARAMS_FMT, velocity_ratio, acceleration_ratio)


def unpack_ARCCommonParams(data: bytes) -> ARCCommonParams:
    return ARCCommonParams(*struct.unpack(_ARCCOMMONPARAMS_FMT, data))


# --------------------------------------------------------------------------- #
# WAITParams  ->  <b  (1 byte)
#   unitType (c_byte)
# --------------------------------------------------------------------------- #
_WAITPARAMS_FMT = "<b"


class WAITParams(NamedTuple):
    unit_type: int


def pack_WAITParams(unit_type: int) -> bytes:
    """Pack WAIT params (unitType time-unit selector)."""
    return struct.pack(_WAITPARAMS_FMT, unit_type)


def unpack_WAITParams(data: bytes) -> WAITParams:
    return WAITParams(*struct.unpack(_WAITPARAMS_FMT, data))
