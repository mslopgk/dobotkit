"""End-effector structures (Task 2.6).

Mirrors the ``DobotDllType`` end-effector payloads. The only structured payload
is :class:`EndTypeParams` (``EndTypeParams`` in the SDK, ``_pack_ = 1``); the
laser / suction-cup / gripper enable+on pairs travel as an inline ``<BB``
(``enableCtrl``, ``on``) payload and need no struct here. End-effector *type* is
a single ``<B`` (``c_uint8``) and servo angle is ``<Bf`` (``servoId``,
``angle``) on the wire — both handled inline by :class:`EffectorMixin`.

Wire format is little-endian, packed; see :mod:`dobotkit.arm.structures._core`.
"""
from __future__ import annotations

import struct
from typing import NamedTuple

__all__: list[str] = [
    "EndTypeParams",
    "pack_EndTypeParams",
    "unpack_EndTypeParams",
]


# --------------------------------------------------------------------------- #
# EndTypeParams  ->  <fff  (12 bytes)
# oracle EndTypeParams._fields_ = [xBias c_float, yBias c_float, zBias c_float],
# _pack_ = 1.
# --------------------------------------------------------------------------- #
_ENDTYPEPARAMS_FMT = "<fff"


class EndTypeParams(NamedTuple):
    x_bias: float
    y_bias: float
    z_bias: float


def pack_EndTypeParams(x_bias: float, y_bias: float, z_bias: float) -> bytes:
    """Pack the end-effector tool-center-point bias (xBias, yBias, zBias)."""
    return struct.pack(_ENDTYPEPARAMS_FMT, x_bias, y_bias, z_bias)


def unpack_EndTypeParams(data: bytes) -> EndTypeParams:
    return EndTypeParams(*struct.unpack(_ENDTYPEPARAMS_FMT, data))
