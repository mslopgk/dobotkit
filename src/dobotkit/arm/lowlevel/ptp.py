"""PTP (point-to-point) motion commands (Task 2.3).

This mixin maps the SDK's PTP functions 1:1: the two motion commands
(``SetPTPCmd``, ``SetPTPWithLCmd``) plus the five SET/GET parameter pairs
(joint, coordinate, L/sliding-rail, jump, common). Each SET/GET pair shares a
single :class:`~dobotkit.arm.ids.ProtocolId` and differs only by the ``rw``
control bit. Queued setters return the 64-bit queue index decoded from the
response; immediate setters return ``None``.

Built on :class:`dobotkit.arm.lowlevel._base._LowLevelBase`, which provides
``_send`` and ``_queued_index``.
"""
from __future__ import annotations

from typing import Optional, Sequence

from dobotkit.arm import structures as S
from dobotkit.arm.ids import ProtocolId
from dobotkit.arm.lowlevel._base import _LowLevelProtocol


class PtpMixin(_LowLevelProtocol):
    """PTP motion commands and parameter SET/GET pairs."""

    # -- motion commands ---------------------------------------------------

    def set_ptp_cmd(
        self,
        mode: int,
        x: float,
        y: float,
        z: float,
        r: float,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Execute a point-to-point move (id 84).

        Returns the queued-command index when ``queued`` is ``True``, else
        ``None``.
        """
        resp = self._send(
            ProtocolId.SET_PTP_CMD,
            S.pack_PTPCmd(mode, x, y, z, r),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def set_ptp_with_l_cmd(
        self,
        mode: int,
        x: float,
        y: float,
        z: float,
        r: float,
        l: float,  # noqa: E741  L-axis (sliding-rail) — protocol field name
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Execute a PTP move with a sliding-rail (L-axis) target (id 86)."""
        resp = self._send(
            ProtocolId.SET_PTP_WITH_L_CMD,
            S.pack_PTPWithLCmd(mode, x, y, z, r, l),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    # -- joint params (id 80) ---------------------------------------------

    def set_ptp_joint_params(
        self,
        velocities: Sequence[float],
        accelerations: Sequence[float],
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Set per-joint PTP velocities and accelerations (joint1..4)."""
        resp = self._send(
            ProtocolId.SET_GET_PTP_JOINT_PARAMS,
            S.pack_PTPJointParams(velocities, accelerations),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_ptp_joint_params(self) -> S.PTPJointParams:
        """Read the per-joint PTP velocity/acceleration params."""
        resp = self._send(ProtocolId.SET_GET_PTP_JOINT_PARAMS)
        return S.unpack_PTPJointParams(resp.params)

    # -- coordinate params (id 81) ----------------------------------------

    def set_ptp_coordinate_params(
        self,
        xyz_velocity: float,
        r_velocity: float,
        xyz_acceleration: float,
        r_acceleration: float,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Set Cartesian-mode PTP velocity/acceleration params."""
        resp = self._send(
            ProtocolId.SET_GET_PTP_COORDINATE_PARAMS,
            S.pack_PTPCoordinateParams(
                xyz_velocity, r_velocity, xyz_acceleration, r_acceleration
            ),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_ptp_coordinate_params(self) -> S.PTPCoordinateParams:
        """Read the Cartesian-mode PTP velocity/acceleration params."""
        resp = self._send(ProtocolId.SET_GET_PTP_COORDINATE_PARAMS)
        return S.unpack_PTPCoordinateParams(resp.params)

    # -- L (sliding-rail) params (id 85) ----------------------------------

    def set_ptp_l_params(
        self,
        velocity: float,
        acceleration: float,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Set sliding-rail (L-axis) PTP velocity/acceleration params."""
        resp = self._send(
            ProtocolId.SET_GET_PTP_L_PARAMS,
            S.pack_PTPLParams(velocity, acceleration),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_ptp_l_params(self) -> S.PTPLParams:
        """Read the sliding-rail (L-axis) PTP velocity/acceleration params."""
        resp = self._send(ProtocolId.SET_GET_PTP_L_PARAMS)
        return S.unpack_PTPLParams(resp.params)

    # -- jump params (id 82) ----------------------------------------------

    def set_ptp_jump_params(
        self,
        jump_height: float,
        z_limit: float,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Set PTP jump-mode params (jump height, z limit)."""
        resp = self._send(
            ProtocolId.SET_GET_PTP_JUMP_PARAMS,
            S.pack_PTPJumpParams(jump_height, z_limit),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_ptp_jump_params(self) -> S.PTPJumpParams:
        """Read the PTP jump-mode params."""
        resp = self._send(ProtocolId.SET_GET_PTP_JUMP_PARAMS)
        return S.unpack_PTPJumpParams(resp.params)

    # -- common params (id 83) --------------------------------------------

    def set_ptp_common_params(
        self,
        velocity_ratio: float,
        acceleration_ratio: float,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Set PTP common velocity/acceleration ratios."""
        resp = self._send(
            ProtocolId.SET_GET_PTP_COMMON_PARAMS,
            S.pack_PTPCommonParams(velocity_ratio, acceleration_ratio),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_ptp_common_params(self) -> S.PTPCommonParams:
        """Read the PTP common velocity/acceleration ratios."""
        resp = self._send(ProtocolId.SET_GET_PTP_COMMON_PARAMS)
        return S.unpack_PTPCommonParams(resp.params)
