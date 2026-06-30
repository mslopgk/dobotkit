"""CP / ARC / Circle low-level commands (Task 2.5).

Continuous-path (CP), arc, and circle motion plus their parameter get/set
pairs. Every method follows the canonical pattern: build params with a
``structures.pack_*`` helper, call :meth:`_send` with the right
:class:`~dobotkit.arm.ids.ProtocolId` and ``rw``/``queued`` ctrl bits, and
(for GET) decode the response with the matching ``structures.unpack_*``.

GET/SET pairs share one ``ProtocolId`` and differ only by the ``rw`` bit
(0 = get, 1 = set). Queued setters return the 64-bit queue index via
:meth:`_queued_index`.
"""
from __future__ import annotations

import struct
from typing import Optional, Sequence

from dobotkit.arm import structures as S
from dobotkit.arm.ids import ProtocolId
from dobotkit.arm.lowlevel._base import _LowLevelProtocol


class CpArcMixin(_LowLevelProtocol):
    """CP / ARC / Circle command set for the low-level arm."""

    # -- CP commands -------------------------------------------------------

    def set_cp_cmd(
        self,
        cp_mode: int,
        x: float,
        y: float,
        z: float,
        velocity: float,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Issue a continuous-path motion command (SetCPCmd)."""
        params = S.pack_CPCmd(cp_mode, x, y, z, velocity)
        resp = self._send(ProtocolId.SET_CP_CMD, params, rw=True, queued=queued)
        return self._queued_index(resp) if queued else None

    def set_cp2_cmd(
        self,
        cp_mode: int,
        x: float,
        y: float,
        z: float,
        velocity: float = 100.0,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Issue a CP2 motion command (SetCP2Cmd)."""
        params = S.pack_CP2Cmd(cp_mode, x, y, z, velocity)
        resp = self._send(ProtocolId.SET_CP2_CMD, params, rw=True, queued=queued)
        return self._queued_index(resp) if queued else None

    def set_cp_le_cmd(
        self,
        cp_mode: int,
        x: float,
        y: float,
        z: float,
        power: float,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Issue a CP command with laser engraving power (SetCPLECmd).

        The laser power is carried in the CPCmd ``velocity`` field per the SDK.
        """
        params = S.pack_CPCmd(cp_mode, x, y, z, power)
        resp = self._send(ProtocolId.SET_CP_LE_CMD, params, rw=True, queued=queued)
        return self._queued_index(resp) if queued else None

    # -- CP params ---------------------------------------------------------

    def set_cp_params(
        self,
        plan_acc: float,
        junction_vel: float,
        acc: float,
        real_time_track: int = 0,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Set CP planning params (SetCPParams)."""
        params = S.pack_CPParams(plan_acc, junction_vel, acc, real_time_track)
        resp = self._send(ProtocolId.SET_GET_CP_PARAMS, params, rw=True, queued=queued)
        return self._queued_index(resp) if queued else None

    def get_cp_params(self) -> S.CPParams:
        """Get CP planning params (GetCPParams)."""
        resp = self._send(ProtocolId.SET_GET_CP_PARAMS, rw=False)
        return S.unpack_CPParams(resp.params)

    def set_cp_common_params(
        self,
        velocity_ratio: float,
        acceleration_ratio: float,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Set CP common velocity/acceleration ratios (SetCPCommonParams)."""
        params = S.pack_CPCommonParams(velocity_ratio, acceleration_ratio)
        resp = self._send(
            ProtocolId.SET_GET_CP_COMMON_PARAMS, params, rw=True, queued=queued
        )
        return self._queued_index(resp) if queued else None

    def get_cp_common_params(self) -> S.CPCommonParams:
        """Get CP common velocity/acceleration ratios (GetCPCommonParams)."""
        resp = self._send(ProtocolId.SET_GET_CP_COMMON_PARAMS, rw=False)
        return S.unpack_CPCommonParams(resp.params)

    def set_cpr_hold_enable(self, is_enable: bool, *, queued: bool = False) -> Optional[int]:
        """Enable/disable CP real-time hold (SetCPRHoldEnable).

        Carries a single ``c_bool``. NOTE: uses the dedicated
        ``ProtocolId.SET_GET_CPR_HOLD_ENABLE`` member; its id value is still
        ``# unverified`` pending hardware confirmation.
        """
        params = struct.pack("<?", bool(is_enable))
        resp = self._send(
            ProtocolId.SET_GET_CPR_HOLD_ENABLE, params, rw=True, queued=queued
        )
        return self._queued_index(resp) if queued else None

    def get_cpr_hold_enable(self) -> bool:
        """Get the CP real-time hold enable flag (GetCPRHoldEnable).

        NOTE: uses the dedicated ``ProtocolId.SET_GET_CPR_HOLD_ENABLE`` member
        (id value still ``# unverified``).
        """
        resp = self._send(ProtocolId.SET_GET_CPR_HOLD_ENABLE, rw=False)
        return bool(struct.unpack("<?", resp.params[:1])[0]) if resp.params else False

    # -- ARC / Circle commands --------------------------------------------

    def set_arc_cmd(
        self,
        cir_point: Sequence[float],
        to_point: Sequence[float],
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Issue an arc motion command (SetARCCmd).

        ``cir_point`` and ``to_point`` are each ``(x, y, z, rHead)``.
        """
        params = S.pack_ARCCmd(
            S.ARCPoint(*cir_point), S.ARCPoint(*to_point)
        )
        resp = self._send(ProtocolId.SET_ARC_CMD, params, rw=True, queued=queued)
        return self._queued_index(resp) if queued else None

    def set_circle_cmd(
        self,
        cir_point: Sequence[float],
        to_point: Sequence[float],
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Issue a circle motion command (SetCircleCmd).

        ``cir_point`` and ``to_point`` are each ``(x, y, z, rHead)``.
        """
        params = S.pack_CircleCmd(
            S.ARCPoint(*cir_point), S.ARCPoint(*to_point)
        )
        resp = self._send(ProtocolId.SET_CIRCLE_CMD, params, rw=True, queued=queued)
        return self._queued_index(resp) if queued else None

    # -- ARC params --------------------------------------------------------

    def set_arc_params(
        self,
        xyz_velocity: float,
        r_velocity: float,
        xyz_acceleration: float,
        r_acceleration: float,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Set ARC velocity/acceleration params (SetARCParams)."""
        params = S.pack_ARCParams(
            xyz_velocity, r_velocity, xyz_acceleration, r_acceleration
        )
        resp = self._send(ProtocolId.SET_GET_ARC_PARAMS, params, rw=True, queued=queued)
        return self._queued_index(resp) if queued else None

    def get_arc_params(self) -> S.ARCParams:
        """Get ARC velocity/acceleration params (GetARCParams)."""
        resp = self._send(ProtocolId.SET_GET_ARC_PARAMS, rw=False)
        return S.unpack_ARCParams(resp.params)

    def set_arc_common_params(
        self,
        velocity_ratio: float,
        acceleration_ratio: float,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Set ARC common velocity/acceleration ratios (SetARCCommonParams)."""
        params = S.pack_ARCCommonParams(velocity_ratio, acceleration_ratio)
        resp = self._send(
            ProtocolId.SET_GET_ARC_COMMON_PARAMS, params, rw=True, queued=queued
        )
        return self._queued_index(resp) if queued else None

    def get_arc_common_params(self) -> S.ARCCommonParams:
        """Get ARC common velocity/acceleration ratios (GetARCCommonParams)."""
        resp = self._send(ProtocolId.SET_GET_ARC_COMMON_PARAMS, rw=False)
        return S.unpack_ARCCommonParams(resp.params)
