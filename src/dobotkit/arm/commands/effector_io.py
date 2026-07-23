"""End-effector and digital/analog I/O RPC wrappers. Filled in later."""
from __future__ import annotations
from typing import Any
from dobotkit.arm.commands._base import _Base


class EffectorIoMixin(_Base):
    """RPC wrappers for end-effector control and digital/analog I/O."""

    # -- end effectors --
    def set_suction_cup(self, enable_ctrl: bool, on: bool, queued: bool = True) -> int:
        """Set suction cup state.

        Args:
            enable_ctrl: Enable/disable control.
            on: Turn on/off.
            queued: Queue the command (default True).

        Returns:
            Queued command index.
        """
        # DobotLink's param for pump power is `enable` (bool), NOT the SDK's `enableCtrl`.
        # Sending `enableCtrl` is silently ignored (RPC returns True, pump never powers → the
        # cup never actuates). Verified live on COM8 via GetEndEffectorSuctionCup readback:
        # enable=True,on=True -> {isEnabled:True,isOn:True}; enableCtrl was a no-op. `on` is correct.
        return self._queued_index(self._call(
            "SetEndEffectorSuctionCup", enable=bool(enable_ctrl), on=bool(on), isQueued=queued))

    def set_gripper(self, enable_ctrl: bool, on: bool, queued: bool = True) -> int:
        """Set gripper state.

        Args:
            enable_ctrl: Enable/disable control.
            on: Open/close gripper.
            queued: Queue the command (default True).

        Returns:
            Queued command index.
        """
        # DobotLink's param for pump power is `enable` (bool), NOT the SDK's `enableCtrl` — see
        # set_suction_cup. Verified live: enable=True,on=True -> {isEnabled:True,isOn:True} (close).
        return self._queued_index(self._call(
            "SetEndEffectorGripper", enable=bool(enable_ctrl), on=bool(on), isQueued=queued))

    def set_servo_angle(self, index: int, angle: float, queued: bool = True) -> int:
        """Set servo angle.

        Args:
            index: Servo index.
            angle: Angle in degrees.
            queued: Queue the command (default True).

        Returns:
            Queued command index.
        """
        return self._queued_index(self._call(
            "SetServoAngle", index=int(index), value=float(angle), isQueued=queued))

    # -- IO --
    def set_io_multiplexing(self, address: int, multiplex: int) -> Any:
        """Set I/O multiplexing mode.

        Args:
            address: I/O address.
            multiplex: Multiplex mode.

        Returns:
            Command result.
        """
        return self._call("SetIOMultiplexing", address=int(address), multiplex=int(multiplex))

    def get_io_adc(self, address: int) -> Any:
        """Get I/O ADC value.

        Args:
            address: I/O address.

        Returns:
            ADC reading dict with keys: port, value.
        """
        return self._call("GetIOADC", address=int(address))

    def get_io_di(self, address: int) -> Any:
        """Get I/O digital input value.

        Args:
            address: I/O address.

        Returns:
            DI reading dict with keys: port, level.
        """
        return self._call("GetIODI", address=int(address))

    def set_io_do(self, address: int, level: int, queued: bool = False) -> Any:
        """Set I/O digital output value.

        Args:
            address: I/O address.
            level: Output level (0 or 1).
            queued: Queue the command (default False).

        Returns:
            Command result.
        """
        return self._call("SetIODO", address=int(address), level=int(level), isQueued=queued)

    def set_io_pwm(self, address: int, frequency: float, duty: float, queued: bool = False) -> Any:
        """Set I/O PWM output.

        Args:
            address: I/O address.
            frequency: PWM frequency in Hz.
            duty: Duty cycle (0.0-1.0).
            queued: Queue the command (default False).

        Returns:
            Command result.
        """
        return self._call("SetIOPWM", address=int(address),
                          frequency=float(frequency), dutyCycle=float(duty), isQueued=queued)
