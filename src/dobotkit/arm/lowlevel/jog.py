"""JOG (jogging) commands for the low-level Dobot arm API (Task 2.4).

Covers ``SetJOGCmd`` and the set/get parameter pairs for the joint,
coordinate, L-axis, and common JOG frames. Each method follows the canonical
pattern from :class:`dobotkit.arm.lowlevel._base._LowLevelBase`: build a frame
(``ProtocolId`` + ``rw``/``queued`` ctrl bits + packed params via
``structures.pack_*``), send it, and decode any response with
``structures.unpack_*``. Queued setters return the queued-command index;
immediate setters return ``None``.

A GET/SET pair shares one ``ProtocolId`` and is distinguished only by the
``rw`` ctrl bit (0 = read, 1 = write).
"""
from __future__ import annotations

from typing import Optional, Sequence

from dobotkit.arm import structures as S
from dobotkit.arm.ids import ProtocolId
from dobotkit.arm.lowlevel._base import _LowLevelProtocol


class JogMixin(_LowLevelProtocol):
    """JOG command set (jog command + joint/coordinate/L/common params)."""

    # -- JOG command -------------------------------------------------------

    def set_jog_cmd(
        self, is_joint: int, cmd: int, *, queued: bool = False
    ) -> Optional[int]:
        """Start/stop a JOG motion (``isJoint`` frame flag, ``cmd`` axis code)."""
        resp = self._send(
            ProtocolId.SET_JOG_CMD,
            S.pack_JOGCmd(is_joint, cmd),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    # -- joint params (set/get) -------------------------------------------

    def set_jog_joint_params(
        self,
        velocities: Sequence[float],
        accelerations: Sequence[float],
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Set per-joint JOG velocities/accelerations (joint1..4)."""
        resp = self._send(
            ProtocolId.SET_GET_JOG_JOINT_PARAMS,
            S.pack_JOGJointParams(velocities, accelerations),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_jog_joint_params(self) -> "S.JOGJointParams":
        """Read the per-joint JOG velocity/acceleration params."""
        resp = self._send(ProtocolId.SET_GET_JOG_JOINT_PARAMS)
        return S.unpack_JOGJointParams(resp.params)

    # -- coordinate params (set/get) --------------------------------------

    def set_jog_coordinate_params(
        self,
        velocities: Sequence[float],
        accelerations: Sequence[float],
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Set Cartesian JOG velocities/accelerations (x, y, z, r)."""
        resp = self._send(
            ProtocolId.SET_GET_JOG_COORDINATE_PARAMS,
            S.pack_JOGCoordinateParams(velocities, accelerations),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_jog_coordinate_params(self) -> "S.JOGCoordinateParams":
        """Read the Cartesian JOG velocity/acceleration params."""
        resp = self._send(ProtocolId.SET_GET_JOG_COORDINATE_PARAMS)
        return S.unpack_JOGCoordinateParams(resp.params)

    # -- L-axis params (set/get) ------------------------------------------

    def set_jog_l_params(
        self, velocity: float, acceleration: float, *, queued: bool = False
    ) -> Optional[int]:
        """Set the sliding-rail (L axis) JOG velocity/acceleration."""
        resp = self._send(
            ProtocolId.SET_GET_JOG_L_PARAMS,
            S.pack_JOGLParams(velocity, acceleration),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_jog_l_params(self) -> "S.JOGLParams":
        """Read the sliding-rail (L axis) JOG velocity/acceleration."""
        resp = self._send(ProtocolId.SET_GET_JOG_L_PARAMS)
        return S.unpack_JOGLParams(resp.params)

    # -- common params (set/get) ------------------------------------------

    def set_jog_common_params(
        self,
        velocity_ratio: float,
        acceleration_ratio: float,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Set the global JOG velocity/acceleration ratios (percent)."""
        resp = self._send(
            ProtocolId.SET_GET_JOG_COMMON_PARAMS,
            S.pack_JOGCommonParams(velocity_ratio, acceleration_ratio),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_jog_common_params(self) -> "S.JOGCommonParams":
        """Read the global JOG velocity/acceleration ratios."""
        resp = self._send(ProtocolId.SET_GET_JOG_COMMON_PARAMS)
        return S.unpack_JOGCommonParams(resp.params)
