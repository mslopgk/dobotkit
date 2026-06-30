"""End-effector commands (Task 2.6).

Covers the tool-center-point bias (``EndTypeParams``), the three actuator
enable/on pairs (laser, suction cup, gripper), the end-effector *type*, and
servo angle.

GET/SET pairs share one :class:`~dobotkit.arm.ids.ProtocolId` and differ only by
the ``rw`` ctrl bit. Queued setters return the on-device queue index decoded by
:meth:`~dobotkit.arm.lowlevel._base._LowLevelBase._queued_index`.

MagicBox-routed servo path: in the SDK ``SetServoAngle`` / ``GetServoAngle`` are
addressed to slave id ``-1`` (the MagicBox), unlike the other end-effector
commands which target the connected controller directly. Over this serial
transport the master/slave addressing is not part of the frame, so the wire
payload is unaffected; the routing distinction is documented here for parity.
"""
from __future__ import annotations

import struct
from typing import Optional, Tuple

from dobotkit.arm import structures as S
from dobotkit.arm.ids import ProtocolId
from dobotkit.arm.lowlevel._base import _LowLevelProtocol

# Inline payload formats (no dedicated struct).
_ON_OFF_FMT = "<BB"  # enableCtrl, on  (laser / suction cup / gripper SET)
_END_TYPE_FMT = "<B"  # endType (c_uint8)
_SERVO_ID_FMT = "<B"  # servoId (c_uint8)  -- GET request payload
_SERVO_SET_FMT = "<Bf"  # servoId, angle    -- SET payload
_SERVO_ANGLE_FMT = "<f"  # angle (c_float)   -- GET response payload


class EffectorMixin(_LowLevelProtocol):
    """End-effector commands."""

    # -- end-effector params (tool-center-point bias) ----------------------

    def set_end_effector_params(
        self,
        x_bias: float,
        y_bias: float,
        z_bias: float,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Set the end-effector TCP bias (xBias, yBias, zBias)."""
        resp = self._send(
            ProtocolId.SET_GET_END_EFFECTOR_PARAMS,
            S.pack_EndTypeParams(x_bias, y_bias, z_bias),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_end_effector_params(self) -> S.EndTypeParams:
        """Get the end-effector TCP bias."""
        resp = self._send(ProtocolId.SET_GET_END_EFFECTOR_PARAMS)
        return S.unpack_EndTypeParams(resp.params)

    # -- laser -------------------------------------------------------------

    def set_end_effector_laser(
        self,
        enable_ctrl: bool,
        on: bool,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Enable/disable laser control and switch it on/off."""
        resp = self._send(
            ProtocolId.SET_GET_END_EFFECTOR_LASER,
            struct.pack(_ON_OFF_FMT, int(enable_ctrl), int(on)),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_end_effector_laser(self) -> Tuple[bool, bool]:
        """Get laser state as ``(enable_ctrl, on)``."""
        resp = self._send(ProtocolId.SET_GET_END_EFFECTOR_LASER)
        enable_ctrl, on = struct.unpack(_ON_OFF_FMT, resp.params[:2])
        return bool(enable_ctrl), bool(on)

    # -- suction cup -------------------------------------------------------

    def set_end_effector_suction_cup(
        self,
        enable_ctrl: bool,
        on: bool,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Enable/disable suction-cup control and switch it on/off."""
        resp = self._send(
            ProtocolId.SET_GET_END_EFFECTOR_SUCTION_CUP,
            struct.pack(_ON_OFF_FMT, int(enable_ctrl), int(on)),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_end_effector_suction_cup(self) -> Tuple[bool, bool]:
        """Get suction-cup state as ``(enable_ctrl, on)``."""
        resp = self._send(ProtocolId.SET_GET_END_EFFECTOR_SUCTION_CUP)
        enable_ctrl, on = struct.unpack(_ON_OFF_FMT, resp.params[:2])
        return bool(enable_ctrl), bool(on)

    # -- gripper -----------------------------------------------------------

    def set_end_effector_gripper(
        self,
        enable_ctrl: bool,
        on: bool,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Enable/disable gripper control and switch it on/off."""
        resp = self._send(
            ProtocolId.SET_GET_END_EFFECTOR_GRIPPER,
            struct.pack(_ON_OFF_FMT, int(enable_ctrl), int(on)),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_end_effector_gripper(self) -> Tuple[bool, bool]:
        """Get gripper state as ``(enable_ctrl, on)``."""
        resp = self._send(ProtocolId.SET_GET_END_EFFECTOR_GRIPPER)
        enable_ctrl, on = struct.unpack(_ON_OFF_FMT, resp.params[:2])
        return bool(enable_ctrl), bool(on)

    # -- end-effector type -------------------------------------------------

    def set_end_effector_type(
        self,
        end_type: int,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Set the end-effector type (see :class:`~dobotkit.enums.EndEffectorType`)."""
        resp = self._send(
            ProtocolId.SET_GET_END_EFFECTOR_TYPE,
            struct.pack(_END_TYPE_FMT, int(end_type)),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_end_effector_type(self) -> int:
        """Get the current end-effector type code."""
        resp = self._send(ProtocolId.SET_GET_END_EFFECTOR_TYPE)
        return int(struct.unpack(_END_TYPE_FMT, resp.params[:1])[0])

    # -- servo angle (MagicBox-routed) -------------------------------------

    def set_servo_angle(
        self,
        servo_id: int,
        angle: float,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Set a servo angle.

        Routed to the MagicBox (SDK slave id ``-1``); see the module docstring.
        """
        resp = self._send(
            ProtocolId.SET_GET_SERVO_ANGLE,
            struct.pack(_SERVO_SET_FMT, int(servo_id), angle),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_servo_angle(self, servo_id: int) -> float:
        """Get a servo angle.

        Routed to the MagicBox (SDK slave id ``-1``); see the module docstring.
        """
        resp = self._send(
            ProtocolId.SET_GET_SERVO_ANGLE,
            struct.pack(_SERVO_ID_FMT, int(servo_id)),
        )
        return float(struct.unpack(_SERVO_ANGLE_FMT, resp.params[:4])[0])
