"""Pose / home / kinematics / auto-leveling commands (Task 2.2).

Every method follows the canonical low-level pattern (see Task 2.1):

* build params with :mod:`dobotkit.arm.structures` ``pack_*`` (or an inline
  ``struct`` for primitive payloads);
* call :meth:`~dobotkit.arm.lowlevel._base._LowLevelBase._send` with the right
  :class:`~dobotkit.arm.ids.ProtocolId`, ``rw`` bit (``False`` = GET/read,
  ``True`` = SET/write) and ``queued`` flag;
* decode GET responses via ``structures.unpack_*``;
* return the queued-command index from queued setters via
  :meth:`~dobotkit.arm.lowlevel._base._LowLevelBase._queued_index`.

GET/SET pairs share one ``ProtocolId`` and differ only by the ``rw`` ctrl bit.
"""
from __future__ import annotations

import struct
from typing import Optional

from dobotkit.arm import structures as S
from dobotkit.arm.ids import ProtocolId
from dobotkit.arm.lowlevel._base import _LowLevelProtocol


class PoseMixin(_LowLevelProtocol):
    """Pose / home / kinematics / auto-leveling commands."""

    # -- real-time pose / kinematics --------------------------------------

    def get_pose(self) -> S.Pose:
        """Read the current Cartesian + joint pose (GetPose)."""
        resp = self._send(ProtocolId.GET_POSE)
        return S.unpack_Pose(resp.params)

    def get_pose_l(self) -> float:
        """Read the sliding-rail (L-axis) position in mm (GetPoseL)."""
        resp = self._send(ProtocolId.GET_POSE_L)
        return float(struct.unpack("<f", resp.params[:4])[0])

    def get_pose_ex(self, index: int) -> float:
        """Return one pose component (GetPoseEx).

        ``index == 0`` -> the L-axis (rail) position; ``index`` 1..8 -> the
        corresponding :class:`~dobotkit.arm.structures.Pose` field
        (x, y, z, r, j1, j2, j3, j4), rounded to 4 decimals, mirroring the SDK.
        """
        if index == 0:
            return round(self.get_pose_l(), 4)
        pose = self.get_pose()
        return round(pose[index - 1], 4)

    def get_kinematics(self) -> S.Kinematics:
        """Read the real-time velocity / acceleration (GetKinematics)."""
        resp = self._send(ProtocolId.GET_KINEMATICS)
        return S.unpack_Kinematics(resp.params)

    def reset_pose(
        self,
        manual: int,
        rear_arm_angle: float,
        front_arm_angle: float,
    ) -> None:
        """Recalibrate the pose from known arm angles (ResetPose).

        ``manual`` is a flag (0/1); when set, the rear/front arm angles are used
        as the calibration reference. This is an immediate (non-queued) set.
        """
        params = struct.pack("<Bff", manual, rear_arm_angle, front_arm_angle)
        self._send(ProtocolId.RESET_POSE, params, rw=True)

    # -- homing -----------------------------------------------------------

    def set_home_params(
        self,
        x: float,
        y: float,
        z: float,
        r: float,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Set the homing target pose (SetHOMEParams)."""
        resp = self._send(
            ProtocolId.SET_GET_HOME_PARAMS,
            S.pack_HOMEParams(x, y, z, r),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_home_params(self) -> S.HOMEParams:
        """Read the homing target pose (GetHOMEParams)."""
        resp = self._send(ProtocolId.SET_GET_HOME_PARAMS)
        return S.unpack_HOMEParams(resp.params)

    def set_home_cmd(self, temp: float = 0.0, *, queued: bool = False) -> Optional[int]:
        """Execute homing (SetHOMECmd). ``temp`` is reserved/unused."""
        resp = self._send(
            ProtocolId.SET_HOME_CMD,
            S.pack_HOMECmd(temp),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    # -- auto leveling ----------------------------------------------------

    def set_auto_leveling(
        self,
        control_flag: int,
        precision: float,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Start/stop auto-leveling (SetAutoLevelingCmd)."""
        resp = self._send(
            ProtocolId.SET_AUTO_LEVELING,
            S.pack_AutoLevelingCmd(control_flag, precision),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_auto_leveling_result(self) -> float:
        """Read the achieved auto-leveling precision (GetAutoLevelingResult)."""
        resp = self._send(ProtocolId.GET_AUTO_LEVELING)
        return float(struct.unpack("<f", resp.params[:4])[0])

    # -- arm orientation --------------------------------------------------

    def set_arm_orientation(
        self,
        arm_orientation: int,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Set the arm orientation (left/right handed) (SetArmOrientation)."""
        resp = self._send(
            ProtocolId.SET_GET_ARM_ORIENTATION,
            struct.pack("<B", arm_orientation),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_arm_orientation(self) -> int:
        """Read the arm orientation (GetArmOrientation)."""
        resp = self._send(ProtocolId.SET_GET_ARM_ORIENTATION)
        return int(struct.unpack("<i", resp.params[:4])[0])

    # -- user params ------------------------------------------------------

    def get_user_params(self) -> S.UserParams:
        """Read the eight user parameters (GetUserParams).

        NOTE: uses the dedicated ``ProtocolId.GET_USER_PARAMS`` member (formerly
        collided with ``GET_POSE_L=13``); its id value is still ``# unverified``
        pending hardware confirmation.
        """
        resp = self._send(ProtocolId.GET_USER_PARAMS)
        return S.unpack_UserParams(resp.params)
