"""JOG motion structures (Task 2.4).

JOG params for the three motion frames the SDK exposes:

* ``JOGJointParams`` — per-joint velocities then accelerations (joint1..4).
* ``JOGCoordinateParams`` — Cartesian x/y/z/r velocities then accelerations.
* ``JOGLParams`` — sliding-rail (L axis) velocity / acceleration.

``JOGCmd`` and ``JOGCommonParams`` live in :mod:`._core` (core motion set) and
are reused by the JOG command layer.

All formats are little-endian and packed (``_pack_ = 1`` in the oracle); the
two 8-float params are all-float so the byte layout is identical with or
without explicit packing. See :mod:`._core` for the wire-format conventions.
"""
from __future__ import annotations

import struct
from typing import NamedTuple, Sequence, Tuple

__all__ = [
    "JOGJointParams",
    "pack_JOGJointParams",
    "unpack_JOGJointParams",
    "JOGCoordinateParams",
    "pack_JOGCoordinateParams",
    "unpack_JOGCoordinateParams",
    "JOGLParams",
    "pack_JOGLParams",
    "unpack_JOGLParams",
]


# --------------------------------------------------------------------------- #
# JOGJointParams  ->  <8f  (32 bytes)
# joint1..4 Velocity, then joint1..4 Acceleration.
# --------------------------------------------------------------------------- #
_JOGJOINTPARAMS_FMT = "<8f"


class JOGJointParams(NamedTuple):
    velocities: Tuple[float, float, float, float]
    accelerations: Tuple[float, float, float, float]


def pack_JOGJointParams(
    velocities: Sequence[float],
    accelerations: Sequence[float],
) -> bytes:
    """Pack per-joint JOG velocities then accelerations (joint1..4)."""
    if len(velocities) != 4 or len(accelerations) != 4:
        raise ValueError("velocities and accelerations must each have 4 elements")
    return struct.pack(_JOGJOINTPARAMS_FMT, *velocities, *accelerations)


def unpack_JOGJointParams(data: bytes) -> JOGJointParams:
    vals = struct.unpack(_JOGJOINTPARAMS_FMT, data)
    return JOGJointParams(
        velocities=(vals[0], vals[1], vals[2], vals[3]),
        accelerations=(vals[4], vals[5], vals[6], vals[7]),
    )


# --------------------------------------------------------------------------- #
# JOGCoordinateParams  ->  <8f  (32 bytes)
# x/y/z/r Velocity, then x/y/z/r Acceleration.
# --------------------------------------------------------------------------- #
_JOGCOORDINATEPARAMS_FMT = "<8f"


class JOGCoordinateParams(NamedTuple):
    velocities: Tuple[float, float, float, float]
    accelerations: Tuple[float, float, float, float]


def pack_JOGCoordinateParams(
    velocities: Sequence[float],
    accelerations: Sequence[float],
) -> bytes:
    """Pack Cartesian JOG velocities then accelerations (x, y, z, r)."""
    if len(velocities) != 4 or len(accelerations) != 4:
        raise ValueError("velocities and accelerations must each have 4 elements")
    return struct.pack(_JOGCOORDINATEPARAMS_FMT, *velocities, *accelerations)


def unpack_JOGCoordinateParams(data: bytes) -> JOGCoordinateParams:
    vals = struct.unpack(_JOGCOORDINATEPARAMS_FMT, data)
    return JOGCoordinateParams(
        velocities=(vals[0], vals[1], vals[2], vals[3]),
        accelerations=(vals[4], vals[5], vals[6], vals[7]),
    )


# --------------------------------------------------------------------------- #
# JOGLParams  ->  <ff  (8 bytes)  (velocity, acceleration)
# --------------------------------------------------------------------------- #
_JOGLPARAMS_FMT = "<ff"


class JOGLParams(NamedTuple):
    velocity: float
    acceleration: float


def pack_JOGLParams(velocity: float, acceleration: float) -> bytes:
    """Pack sliding-rail (L axis) JOG velocity / acceleration."""
    return struct.pack(_JOGLPARAMS_FMT, velocity, acceleration)


def unpack_JOGLParams(data: bytes) -> JOGLParams:
    return JOGLParams(*struct.unpack(_JOGLPARAMS_FMT, data))
