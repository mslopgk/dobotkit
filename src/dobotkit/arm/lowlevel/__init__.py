"""Low-level Dobot arm API (1:1 with the SDK), assembled from category mixins.

Each command category lives in its own module as a ``*Mixin`` so the nine
Phase-2 category tasks can fill DISJOINT files in parallel. :class:`LowLevelArm`
composes them all onto :class:`._base._LowLevelBase`, which provides the
transport, command queue, and the ``_send`` / ``_queued_index`` primitives.
"""
from __future__ import annotations

from ._base import _LowLevelBase
from .device import DeviceMixin
from .pose import PoseMixin
from .ptp import PtpMixin
from .jog import JogMixin
from .cp_arc import CpArcMixin
from .effector import EffectorMixin
from .io import IoMixin
from .sensor import SensorMixin
from .system import SystemMixin


class LowLevelArm(
    DeviceMixin,
    PoseMixin,
    PtpMixin,
    JogMixin,
    CpArcMixin,
    EffectorMixin,
    IoMixin,
    SensorMixin,
    SystemMixin,
    _LowLevelBase,
):
    """Complete 1:1 low-level Dobot arm API."""


__all__ = ["LowLevelArm"]
