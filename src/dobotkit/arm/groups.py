"""Ergonomic facades over :class:`~dobotkit.arm.commands.ArmCommands`.

These are *thin* facades over ``ArmCommands`` (the DobotLink RPC wrapper).
They exist purely to give the high-level ``MagicianLite`` API readable,
intent-revealing accessors (``arm.effector.suck(True)``,
``arm.sensors.distance(2)``, ``arm.io.set_do(5, 1)``) without leaking the
verbose ``Magician.*`` RPC method names. Every method delegates to exactly one
``ArmCommands`` method and passes its return value through (after unwrapping
the single scalar the caller wants, where relevant).

Design choices baked into these facades:

* **Effector on/off pairs** (suction cup, gripper) default to
  ``enable=True`` -- the control circuit/air pump stays powered while ``on``
  toggles the actuator (grab vs release). They default to ``queued=True`` so
  they sequence correctly inside a motion program (pick -> move -> place).
* **Sensor reads that are routed through the MagicBox** (color, infrared,
  Seeed distance/temp/light/RGB, ADC) are *guarded*: a missing MagicBox or
  peripheral answers with :class:`~dobotkit.exceptions.DobotTimeoutError` or
  :class:`~dobotkit.exceptions.DobotProtocolError`, which is caught here and
  degraded to ``None`` + a ``RuntimeWarning`` instead of raising, so
  teaching/beginner code keeps running. See :func:`_guard`.
"""
from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, Callable, Optional, TypeVar

from dobotkit.enums import GPIOType
from dobotkit.exceptions import DobotProtocolError, DobotTimeoutError

if TYPE_CHECKING:  # pragma: no cover - imported only for type checking
    from dobotkit.arm.commands import ArmCommands

__all__ = ["EffectorGroup", "SensorGroup", "IOGroup"]

_T = TypeVar("_T")

#: Warning message emitted when a MagicBox-routed peripheral call gets no
#: response. Bilingual so it reads in both the Korean teaching materials and
#: the English API docs.
_UNAVAILABLE = (
    "주변장치 응답이 없습니다 — 매직박스/센서 연결을 확인하세요 "
    "(no peripheral response; check the MagicBox and its device)"
)


def _guard(call: Callable[[], _T]) -> Optional[_T]:
    """Run a MagicBox-routed peripheral call, degrading to ``None`` if absent."""
    try:
        return call()
    except (DobotTimeoutError, DobotProtocolError):
        warnings.warn(_UNAVAILABLE, RuntimeWarning, stacklevel=3)
        return None


class _Group:
    """Base for the device groups: holds the shared ``ArmCommands`` reference."""

    def __init__(self, cmds: "ArmCommands") -> None:
        self.cmds = cmds


class EffectorGroup(_Group):
    """Ergonomic accessors for the arm's end effectors."""

    def suck(self, on: bool, *, enable: bool = True, queued: bool = True) -> Optional[int]:
        """Drive the suction cup (``on`` = grab, ``enable`` = pump power)."""
        return self.cmds.set_suction_cup(enable, on, queued=queued)

    def grip(self, on: bool, *, enable: bool = True, queued: bool = True) -> Optional[int]:
        """Drive the gripper (``on`` = close, ``enable`` = pump power)."""
        return self.cmds.set_gripper(enable, on, queued=queued)

    def servo(self, index: int, angle: float, *, queued: bool = True) -> Optional[int]:
        """Set the angle of servo ``index`` on the end effector."""
        return self.cmds.set_servo_angle(index, angle, queued=queued)


class SensorGroup(_Group):
    """Ergonomic accessors for the arm's sensors.

    Every read here is MagicBox-routed and therefore guarded: it returns
    ``None`` (with a ``RuntimeWarning``) instead of raising when the MagicBox
    or the attached sensor is not connected. See :func:`_guard`.
    """

    def adc(self, port: int) -> Optional[int]:
        """Select ADC mode on ``port`` and read its analog value."""
        def _read() -> int:
            self.cmds.set_io_multiplexing(port, int(GPIOType.ADC))
            return int(self.cmds.get_io_adc(port)["value"])

        return _guard(_read)

    def di(self, port: int) -> Optional[int]:
        """Read the digital-input level of ``port``."""
        def _read() -> int:
            result = self.cmds.get_io_di(port)
            return int(result.get("level", 0))

        return _guard(_read)

    def color(self, port: int) -> Optional[Any]:
        """Enable the color sensor on ``port`` and read its reading."""
        def _read() -> Any:
            self.cmds.set_color_sensor(1, port)
            return self.cmds.get_color_sensor()

        return _guard(_read)

    def infrared(self, port: int) -> Optional[Any]:
        """Enable the infrared sensor on ``port`` and read its reading."""
        def _read() -> Any:
            self.cmds.set_infrared_sensor(1, port)
            return self.cmds.get_infrared_sensor(port)

        return _guard(_read)

    def distance(self, port: int) -> Optional[Any]:
        """Read the Seeed distance sensor on ``port``."""
        return _guard(lambda: self.cmds.get_seeed_distance(port))

    def temp(self, port: int) -> Optional[Any]:
        """Read the Seeed temperature/humidity sensor on ``port``."""
        return _guard(lambda: self.cmds.get_seeed_temp(port))

    def light(self, port: int) -> Optional[Any]:
        """Read the Seeed light sensor on ``port``."""
        return _guard(lambda: self.cmds.get_seeed_light(port))

    def rgb(self, port: int, value: float) -> Optional[int]:
        """Set the Seeed RGB LED on ``port`` to ``value``."""
        return _guard(lambda: self.cmds.set_seeed_rgb(port, value))


class IOGroup(_Group):
    """Ergonomic accessors for the arm's digital/analog I/O."""

    def set_do(self, address: int, level: int) -> Any:
        """Set the digital-output level of I/O pin ``address``."""
        return self.cmds.set_io_do(address, level)

    def get_di(self, address: int) -> Optional[int]:
        """Read the digital-input level of I/O pin ``address``."""
        def _read() -> int:
            result = self.cmds.get_io_di(address)
            return int(result.get("level", 0))

        return _guard(_read)

    def get_adc(self, address: int) -> Optional[int]:
        """Read the ADC value of I/O pin ``address``."""
        return _guard(lambda: int(self.cmds.get_io_adc(address)["value"]))

    def set_pwm(self, address: int, frequency: float, duty: float) -> Any:
        """Configure PWM (frequency Hz, duty cycle %) on I/O pin ``address``."""
        return self.cmds.set_io_pwm(address, frequency, duty)

    def set_multiplexing(self, address: int, multiplex: int) -> Any:
        """Assign a multiplex function to I/O pin ``address``."""
        return self.cmds.set_io_multiplexing(address, multiplex)
