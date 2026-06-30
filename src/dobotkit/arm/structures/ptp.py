"""PTP motion structures (Task 2.3).

The core PTP structures (``PTPCmd``, ``PTPJointParams``, ``PTPCoordinateParams``,
``PTPJumpParams``, ``PTPCommonParams``) already live in :mod:`._core` and are
re-exported by the structures package, so they are reused as-is. This module
adds the two PTP structures not in the core set:

- ``PTPWithLCmd`` -> ``<Bfffff`` (21 bytes): ptpMode, x, y, z, rHead, l
- ``PTPLParams``  -> ``<ff``     (8 bytes):  velocity, acceleration

Formats are derived from the ``DobotDllType`` ``Structure._fields_`` (see the
golden-oracle byte-match tests); the wire format is little-endian, packed.
"""
from __future__ import annotations

import struct
from typing import NamedTuple

__all__ = [
    "PTPWithLCmd",
    "pack_PTPWithLCmd",
    "unpack_PTPWithLCmd",
    "PTPLParams",
    "pack_PTPLParams",
    "unpack_PTPLParams",
]


# --------------------------------------------------------------------------- #
# PTPWithLCmd  ->  <Bfffff  (21 bytes)
# oracle _fields_: ptpMode (c_byte), x, y, z, rHead, l (c_float), _pack_ = 1
# --------------------------------------------------------------------------- #
_PTPWITHLCMD_FMT = "<Bfffff"


class PTPWithLCmd(NamedTuple):
    mode: int
    x: float
    y: float
    z: float
    r: float
    l: float  # noqa: E741  L-axis (sliding-rail) — protocol field name


def pack_PTPWithLCmd(
    mode: int, x: float, y: float, z: float, r: float, l: float  # noqa: E741
) -> bytes:
    """Pack a PTP-with-sliding-rail command (ptpMode, x, y, z, rHead, l)."""
    return struct.pack(_PTPWITHLCMD_FMT, mode, x, y, z, r, l)


def unpack_PTPWithLCmd(data: bytes) -> PTPWithLCmd:
    return PTPWithLCmd(*struct.unpack(_PTPWITHLCMD_FMT, data))


# --------------------------------------------------------------------------- #
# PTPLParams  ->  <ff  (8 bytes)
# oracle _fields_: velocity, acceleration (c_float), _pack_ = 1
# --------------------------------------------------------------------------- #
_PTPLPARAMS_FMT = "<ff"


class PTPLParams(NamedTuple):
    velocity: float
    acceleration: float


def pack_PTPLParams(velocity: float, acceleration: float) -> bytes:
    """Pack PTP sliding-rail (L-axis) velocity/acceleration params."""
    return struct.pack(_PTPLPARAMS_FMT, velocity, acceleration)


def unpack_PTPLParams(data: bytes) -> PTPLParams:
    return PTPLParams(*struct.unpack(_PTPLPARAMS_FMT, data))
