"""Pose / home / kinematics structures (Task 2.2).

Wire format is little-endian, packed (``_pack_ = 1``); see :mod:`._core` for the
conventions and the :func:`fmt_from_fields` ctypes-to-``struct`` mapping helper.

``Pose``, ``HOMEParams`` and ``HOMECmd`` live in :mod:`._core` (the core motion
set) and are reused as-is; this module adds the remaining pose-category
structures:

- ``Kinematics``      -> ``<ff``  (velocity, acceleration)
- ``AutoLevelingCmd`` -> ``<Bf``  (controlFlag, precision) -- packed, 5 bytes
- ``UserParams``      -> ``<8f``  (params1..params8)
"""
from __future__ import annotations

import struct
from typing import NamedTuple

__all__ = [
    "Kinematics",
    "pack_Kinematics",
    "unpack_Kinematics",
    "AutoLevelingCmd",
    "pack_AutoLevelingCmd",
    "unpack_AutoLevelingCmd",
    "UserParams",
    "pack_UserParams",
    "unpack_UserParams",
]


# --------------------------------------------------------------------------- #
# Kinematics  ->  <ff  (8 bytes)   (velocity, acceleration)
# --------------------------------------------------------------------------- #
_KINEMATICS_FMT = "<ff"


class Kinematics(NamedTuple):
    velocity: float
    acceleration: float


def pack_Kinematics(velocity: float, acceleration: float) -> bytes:
    """Pack real-time kinematics (velocity, acceleration)."""
    return struct.pack(_KINEMATICS_FMT, velocity, acceleration)


def unpack_Kinematics(data: bytes) -> Kinematics:
    return Kinematics(*struct.unpack(_KINEMATICS_FMT, data))


# --------------------------------------------------------------------------- #
# AutoLevelingCmd  ->  <Bf  (5 bytes, packed)   (controlFlag, precision)
# c_ubyte followed by c_float with _pack_=1 -> no alignment padding.
# --------------------------------------------------------------------------- #
_AUTOLEVELINGCMD_FMT = "<Bf"


class AutoLevelingCmd(NamedTuple):
    control_flag: int
    precision: float


def pack_AutoLevelingCmd(control_flag: int, precision: float) -> bytes:
    """Pack an auto-leveling command (controlFlag, precision)."""
    return struct.pack(_AUTOLEVELINGCMD_FMT, control_flag, precision)


def unpack_AutoLevelingCmd(data: bytes) -> AutoLevelingCmd:
    return AutoLevelingCmd(*struct.unpack(_AUTOLEVELINGCMD_FMT, data))


# --------------------------------------------------------------------------- #
# UserParams  ->  <8f  (32 bytes)   (params1..params8)
# --------------------------------------------------------------------------- #
_USERPARAMS_FMT = "<8f"


class UserParams(NamedTuple):
    params1: float
    params2: float
    params3: float
    params4: float
    params5: float
    params6: float
    params7: float
    params8: float


def pack_UserParams(
    params1: float,
    params2: float,
    params3: float,
    params4: float,
    params5: float,
    params6: float,
    params7: float,
    params8: float,
) -> bytes:
    """Pack the eight user parameters (params1..params8)."""
    return struct.pack(
        _USERPARAMS_FMT,
        params1,
        params2,
        params3,
        params4,
        params5,
        params6,
        params7,
        params8,
    )


def unpack_UserParams(data: bytes) -> UserParams:
    return UserParams(*struct.unpack(_USERPARAMS_FMT, data))
