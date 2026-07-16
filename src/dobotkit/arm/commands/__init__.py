"""Thin dobotlink.Magician.* RPC wrappers for the Magician Lite arm.

:class:`ArmCommands` assembles the arm's RPC surface from category mixins so
independent command groups (connection, motion, effector/IO, sensors) can be
filled in in parallel. Each mixin inherits :class:`~._base._Base`, which owns
the DobotLink client, the port name, and the shared ``_call`` /
``_queued_index`` primitives; the MRO resolves ``_Base`` once.
"""
from __future__ import annotations

from .connection import ConnectionMixin
from .motion import MotionMixin
from .effector_io import EffectorIoMixin
from .sensors import SensorMixin


class ArmCommands(ConnectionMixin, MotionMixin, EffectorIoMixin, SensorMixin):
    """1:1 wrappers over the arm's DobotLink RPC surface."""


__all__ = ["ArmCommands"]
