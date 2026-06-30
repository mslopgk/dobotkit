"""Pack/unpack for Dobot arm payload structures.

Every wire payload mirrors a ``DobotDllType`` ``Structure``. The serial
protocol is **little-endian, packed (no alignment padding)** — equivalent to a
ctypes struct with ``_pack_ = 1``. Production code uses explicit literal
``struct`` formats (clarity over cleverness); :func:`fmt_from_fields` documents
the mechanical ctypes-to-``struct`` mapping and is exercised by the tests.

Naming mirrors the SDK: ``pack_<Name>`` / ``unpack_<Name>`` per structure, with
each ``unpack_*`` returning a typed :class:`typing.NamedTuple`.

This module implements the **core motion set** (Task 1.3):
``PTPCmd``, ``Pose``, ``HOMEParams``, ``HOMECmd``, ``PTPCommonParams``,
``PTPCoordinateParams``, ``PTPJointParams``, ``PTPJumpParams``, ``JOGCmd``,
``JOGCommonParams``. Remaining structures are added by their owning Phase-2
tasks.
"""
from __future__ import annotations

import struct
from typing import List, NamedTuple, Sequence, Tuple

__all__ = [
    "fmt_from_fields",
    "PTPCmd",
    "pack_PTPCmd",
    "unpack_PTPCmd",
    "Pose",
    "pack_Pose",
    "unpack_Pose",
    "HOMEParams",
    "pack_HOMEParams",
    "unpack_HOMEParams",
    "HOMECmd",
    "pack_HOMECmd",
    "unpack_HOMECmd",
    "PTPCommonParams",
    "pack_PTPCommonParams",
    "unpack_PTPCommonParams",
    "PTPCoordinateParams",
    "pack_PTPCoordinateParams",
    "unpack_PTPCoordinateParams",
    "PTPJointParams",
    "pack_PTPJointParams",
    "unpack_PTPJointParams",
    "PTPJumpParams",
    "pack_PTPJumpParams",
    "unpack_PTPJumpParams",
    "JOGCmd",
    "pack_JOGCmd",
    "unpack_JOGCmd",
    "JOGCommonParams",
    "pack_JOGCommonParams",
    "unpack_JOGCommonParams",
]


# --------------------------------------------------------------------------- #
# ctypes -> struct format deriver (documentation / verification helper)
# --------------------------------------------------------------------------- #
# Little-endian, packed (``_pack_ = 1``). Fixed ctypes arrays (e.g. ``c_byte *
# 66``) map to a ``Ns`` bytes field. Production pack/unpack functions below use
# explicit literal formats; this helper exists so a struct's format can be
# derived (and asserted) directly from a ``DobotDllType`` ``_fields_`` list.
#
# The mapping is keyed on each ctype's runtime ``_type_`` tag (a one-char code
# from ctypes itself) rather than on ``__name__``. This is stable across
# platforms where width aliases differ (e.g. on Win64 ``c_uint32`` is an alias
# of ``c_ulong``, so ``__name__`` would read ``"c_ulong"``). The ``_type_`` tag
# distinguishes ``i``/``I`` (int) from ``l``/``L`` (long); we normalize the
# long codes to the equivalent fixed-width struct chars (both 4 bytes LE on the
# target platforms, byte-identical).
_TYPECODE_CHAR = {
    "b": "b",  # c_byte / c_int8
    "B": "B",  # c_ubyte / c_uint8
    "?": "?",  # c_bool
    "c": "c",  # c_char
    "h": "h",  # c_short / c_int16
    "H": "H",  # c_ushort / c_uint16
    "i": "i",  # c_int / c_int32
    "I": "I",  # c_uint / c_uint32
    "l": "i",  # c_long  -> 4-byte int  (LE byte-identical to 'i')
    "L": "I",  # c_ulong -> 4-byte uint (LE byte-identical to 'I')
    "q": "q",  # c_longlong / c_int64
    "Q": "Q",  # c_ulonglong / c_uint64
    "f": "f",  # c_float
    "d": "d",  # c_double
}


def fmt_from_fields(fields: Sequence[Tuple[str, type]]) -> str:
    """Derive a little-endian packed ``struct`` format from ctypes ``_fields_``.

    ``fields`` is a sequence of ``(name, ctype)`` pairs exactly as found on a
    ``DobotDllType`` ``Structure._fields_``. Fixed-length ctypes arrays of a
    byte type (``c_byte * N`` / ``c_char * N``) map to ``Ns``. The result is
    prefixed with ``<`` and assumes no alignment padding.
    """
    parts: List[str] = []
    for _name, ctype in fields:
        length = getattr(ctype, "_length_", None)
        if length is not None:
            # Fixed array: only byte-element arrays are representable as bytes.
            elem = getattr(ctype, "_type_", None)
            elem_code = getattr(elem, "_type_", None)
            if elem_code not in ("b", "B", "c"):
                raise ValueError(f"unsupported array element type: {elem!r}")
            parts.append(f"{length}s")
            continue
        code = getattr(ctype, "_type_", None)
        if code not in _TYPECODE_CHAR:
            name = getattr(ctype, "__name__", repr(ctype))
            raise ValueError(f"unsupported ctype: {name!r} (typecode {code!r})")
        parts.append(_TYPECODE_CHAR[code])
    return "<" + "".join(parts)


# --------------------------------------------------------------------------- #
# PTPCmd  ->  <Bffff  (17 bytes)
# --------------------------------------------------------------------------- #
_PTPCMD_FMT = "<Bffff"


class PTPCmd(NamedTuple):
    mode: int
    x: float
    y: float
    z: float
    r: float


def pack_PTPCmd(mode: int, x: float, y: float, z: float, r: float) -> bytes:
    """Pack a point-to-point motion command (ptpMode, x, y, z, rHead)."""
    return struct.pack(_PTPCMD_FMT, mode, x, y, z, r)


def unpack_PTPCmd(data: bytes) -> PTPCmd:
    return PTPCmd(*struct.unpack(_PTPCMD_FMT, data))


# --------------------------------------------------------------------------- #
# Pose  ->  <8f  (32 bytes)
# --------------------------------------------------------------------------- #
_POSE_FMT = "<8f"


class Pose(NamedTuple):
    x: float
    y: float
    z: float
    r: float
    j1: float
    j2: float
    j3: float
    j4: float


def pack_Pose(
    x: float,
    y: float,
    z: float,
    r: float,
    j1: float,
    j2: float,
    j3: float,
    j4: float,
) -> bytes:
    """Pack a Cartesian + joint pose (x, y, z, rHead, joint1..4)."""
    return struct.pack(_POSE_FMT, x, y, z, r, j1, j2, j3, j4)


def unpack_Pose(data: bytes) -> Pose:
    return Pose(*struct.unpack(_POSE_FMT, data))


# --------------------------------------------------------------------------- #
# HOMEParams  ->  <ffff  (16 bytes)
# --------------------------------------------------------------------------- #
_HOMEPARAMS_FMT = "<ffff"


class HOMEParams(NamedTuple):
    x: float
    y: float
    z: float
    r: float


def pack_HOMEParams(x: float, y: float, z: float, r: float) -> bytes:
    """Pack the homing target pose."""
    return struct.pack(_HOMEPARAMS_FMT, x, y, z, r)


def unpack_HOMEParams(data: bytes) -> HOMEParams:
    return HOMEParams(*struct.unpack(_HOMEPARAMS_FMT, data))


# --------------------------------------------------------------------------- #
# HOMECmd  ->  <f  (4 bytes)
# --------------------------------------------------------------------------- #
_HOMECMD_FMT = "<f"


class HOMECmd(NamedTuple):
    temp: float


def pack_HOMECmd(temp: float = 0.0) -> bytes:
    """Pack the home command (the single ``temp`` field is reserved/unused)."""
    return struct.pack(_HOMECMD_FMT, temp)


def unpack_HOMECmd(data: bytes) -> HOMECmd:
    return HOMECmd(*struct.unpack(_HOMECMD_FMT, data))


# --------------------------------------------------------------------------- #
# PTPCommonParams  ->  <ff  (8 bytes)
# --------------------------------------------------------------------------- #
_PTPCOMMONPARAMS_FMT = "<ff"


class PTPCommonParams(NamedTuple):
    velocity_ratio: float
    acceleration_ratio: float


def pack_PTPCommonParams(velocity_ratio: float, acceleration_ratio: float) -> bytes:
    """Pack PTP common velocity/acceleration ratios."""
    return struct.pack(_PTPCOMMONPARAMS_FMT, velocity_ratio, acceleration_ratio)


def unpack_PTPCommonParams(data: bytes) -> PTPCommonParams:
    return PTPCommonParams(*struct.unpack(_PTPCOMMONPARAMS_FMT, data))


# --------------------------------------------------------------------------- #
# PTPCoordinateParams  ->  <ffff  (16 bytes)
# (oracle has no _pack_; all-float so byte layout is identical to packed)
# --------------------------------------------------------------------------- #
_PTPCOORDINATEPARAMS_FMT = "<ffff"


class PTPCoordinateParams(NamedTuple):
    xyz_velocity: float
    r_velocity: float
    xyz_acceleration: float
    r_acceleration: float


def pack_PTPCoordinateParams(
    xyz_velocity: float,
    r_velocity: float,
    xyz_acceleration: float,
    r_acceleration: float,
) -> bytes:
    """Pack PTP coordinate-mode velocity/acceleration params."""
    return struct.pack(
        _PTPCOORDINATEPARAMS_FMT,
        xyz_velocity,
        r_velocity,
        xyz_acceleration,
        r_acceleration,
    )


def unpack_PTPCoordinateParams(data: bytes) -> PTPCoordinateParams:
    return PTPCoordinateParams(*struct.unpack(_PTPCOORDINATEPARAMS_FMT, data))


# --------------------------------------------------------------------------- #
# PTPJointParams  ->  <8f  (32 bytes)
# (oracle has no _pack_; all-float so byte layout is identical to packed)
# --------------------------------------------------------------------------- #
_PTPJOINTPARAMS_FMT = "<8f"


class PTPJointParams(NamedTuple):
    velocities: Tuple[float, float, float, float]
    accelerations: Tuple[float, float, float, float]


def pack_PTPJointParams(
    velocities: Sequence[float],
    accelerations: Sequence[float],
) -> bytes:
    """Pack per-joint PTP velocities then accelerations (joint1..4)."""
    if len(velocities) != 4 or len(accelerations) != 4:
        raise ValueError("velocities and accelerations must each have 4 elements")
    return struct.pack(_PTPJOINTPARAMS_FMT, *velocities, *accelerations)


def unpack_PTPJointParams(data: bytes) -> PTPJointParams:
    vals = struct.unpack(_PTPJOINTPARAMS_FMT, data)
    return PTPJointParams(
        velocities=(vals[0], vals[1], vals[2], vals[3]),
        accelerations=(vals[4], vals[5], vals[6], vals[7]),
    )


# --------------------------------------------------------------------------- #
# PTPJumpParams  ->  <ff  (8 bytes)
# --------------------------------------------------------------------------- #
_PTPJUMPPARAMS_FMT = "<ff"


class PTPJumpParams(NamedTuple):
    jump_height: float
    z_limit: float


def pack_PTPJumpParams(jump_height: float, z_limit: float) -> bytes:
    """Pack PTP jump-mode parameters (jumpHeight, zLimit)."""
    return struct.pack(_PTPJUMPPARAMS_FMT, jump_height, z_limit)


def unpack_PTPJumpParams(data: bytes) -> PTPJumpParams:
    return PTPJumpParams(*struct.unpack(_PTPJUMPPARAMS_FMT, data))


# --------------------------------------------------------------------------- #
# JOGCmd  ->  <bb  (2 bytes)  (isJoint, cmd are signed c_byte)
# --------------------------------------------------------------------------- #
_JOGCMD_FMT = "<bb"


class JOGCmd(NamedTuple):
    is_joint: int
    cmd: int


def pack_JOGCmd(is_joint: int, cmd: int) -> bytes:
    """Pack a JOG command (isJoint flag, cmd axis/direction code)."""
    return struct.pack(_JOGCMD_FMT, is_joint, cmd)


def unpack_JOGCmd(data: bytes) -> JOGCmd:
    return JOGCmd(*struct.unpack(_JOGCMD_FMT, data))


# --------------------------------------------------------------------------- #
# JOGCommonParams  ->  <ff  (8 bytes)
# --------------------------------------------------------------------------- #
_JOGCOMMONPARAMS_FMT = "<ff"


class JOGCommonParams(NamedTuple):
    velocity_ratio: float
    acceleration_ratio: float


def pack_JOGCommonParams(velocity_ratio: float, acceleration_ratio: float) -> bytes:
    """Pack JOG common velocity/acceleration ratios."""
    return struct.pack(_JOGCOMMONPARAMS_FMT, velocity_ratio, acceleration_ratio)


def unpack_JOGCommonParams(data: bytes) -> JOGCommonParams:
    return JOGCommonParams(*struct.unpack(_JOGCOMMONPARAMS_FMT, data))
