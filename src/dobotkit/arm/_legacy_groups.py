"""Ergonomic device groups for the *serial-era* :class:`~dobotkit.arm.magician.Magician`.

.. note::
    **Private/legacy module (2026-07-16).** This is the pre-DobotLink-rewrite
    ``arm/groups.py`` content, kept only so the soon-to-be-removed serial
    ``Magician``/``LowLevelArm`` stack keeps working until it is deleted
    wholesale (see the MagicianLite DobotLink rewrite plan, Task 8). The public
    ``dobotkit.arm.groups`` module now hosts the DobotLink/``ArmCommands``-based
    replacement consumed by ``MagicianLite``. Do not add new callers of this
    module; when Task 8 deletes ``arm/magician.py`` (and ``arm/lowlevel``),
    delete this file and ``tests/arm/test_groups_magicbox_absent.py`` /
    ``tests/arm/test_groups.py`` alongside it.

These are *thin* facades over :class:`~dobotkit.arm.lowlevel.LowLevelArm`. They
exist purely to give the high-level :class:`~dobotkit.arm.magician.Magician`
API readable, intent-revealing accessors (``arm.effector.suck(True)``,
``arm.sensors.seeed_distance(2)``, ``arm.io.set_do(5, 1)``) without leaking the
verbose SDK method names. Every method delegates to exactly one low-level
method and passes its return value straight through.

Design choices baked into these facades:

* **Effector on/off pairs** (suction cup, gripper, laser) default to
  ``enable_ctrl=True`` — the control circuit / air pump stays powered while
  ``on`` toggles the actuator (grab vs release). Pass ``enable=False`` to cut
  the pump/control power entirely (e.g. ``suck(False, enable=False)`` stops the
  air pump). They default to ``queued=True`` so they sequence correctly inside a
  motion program (pick → move → place).
* **IO / sensor scalar helpers** unwrap the low-level ``NamedTuple`` readings to
  the single value the caller actually wants (``get_di`` → ``int`` level,
  ``get_adc`` → ``int`` value), while readers that return rich tuples (color,
  temperature, distance) are passed through unchanged.
* **Sensor read helpers** that require enabling a sensor first (color, infrared,
  Seeed color/temp/light) issue the ``set_*`` selection then return the matching
  ``get_*`` reading in one call.
"""
from __future__ import annotations

import struct
import warnings
from typing import TYPE_CHECKING, Callable, Optional, TypeVar

from dobotkit.exceptions import DobotProtocolError, DobotTimeoutError

if TYPE_CHECKING:  # pragma: no cover - imported only for type checking
    from dobotkit.arm import structures as S
    from dobotkit.arm.lowlevel import LowLevelArm

__all__ = ["EffectorGroup", "SensorGroup", "IOGroup"]

_T = TypeVar("_T")

#: Warning message emitted when a MagicBox-routed peripheral call gets no
#: response. Bilingual so it reads in both the Korean teaching materials and
#: the English API docs.
_PERIPHERAL_UNAVAILABLE_MSG = (
    "주변장치 응답이 없습니다 — 매직박스와 연결된 센서/서보/모터를 확인하세요 "
    "(no peripheral response; check the MagicBox and its attached device)"
)


def _guard(call: Callable[[], _T]) -> Optional[_T]:
    """Run a MagicBox-routed peripheral call, degrading to ``None`` if absent.

    Sensors, the external servo, the extended motors and the Seeed RGB LED are
    reached through the MagicBox. Without it (or its device) the call fails in
    one of three ways, all caught here so beginner/teaching code keeps running
    (we warn once and return ``None``):

    * :class:`~dobotkit.exceptions.DobotTimeoutError` -- no response frame.
    * :class:`~dobotkit.exceptions.DobotProtocolError` -- a corrupt frame.
    * :class:`struct.error` -- observed on real hardware (2026-07-16): the arm
      answers *without* a timeout but with an empty/short payload, so the
      ``unpack_*`` decoder runs out of bytes. The frame is well-formed (checksum
      passes), so this is not a ``DobotProtocolError``.

    Setup errors that are *not* "peripheral missing" -- notably
    :class:`~dobotkit.exceptions.DobotConnectionError` (the port was never
    opened) -- are deliberately **not** caught, so they still surface loudly.

    Note: some peripherals (e.g. the infrared sensor) instead return a plausible
    default value with no error at all; that case cannot be detected here and is
    returned as-is.
    """
    try:
        return call()
    except (DobotTimeoutError, DobotProtocolError, struct.error):
        warnings.warn(_PERIPHERAL_UNAVAILABLE_MSG, RuntimeWarning, stacklevel=3)
        return None


class _Group:
    """Base for the device groups: holds the low-level arm reference."""

    def __init__(self, lowlevel: "LowLevelArm") -> None:
        self.lowlevel = lowlevel


class EffectorGroup(_Group):
    """Ergonomic accessors for the arm's end effectors."""

    def suck(
        self, on: bool, *, enable: bool = True, queued: bool = True
    ) -> Optional[int]:
        """Drive the suction cup.

        ``on`` is the vacuum state (``True`` = grab, ``False`` = release/blow).
        ``enable`` is the control-circuit / air-pump power: it defaults to
        ``True`` (pump powered), but pass ``enable=False`` to cut the pump
        entirely (fully off). To grab: ``suck(True)``; to release: ``suck(False)``;
        to stop the pump: ``suck(False, enable=False)``.
        """
        return self.lowlevel.set_end_effector_suction_cup(
            enable_ctrl=bool(enable), on=bool(on), queued=queued
        )

    def grip(
        self, on: bool, *, enable: bool = True, queued: bool = True
    ) -> Optional[int]:
        """Drive the gripper.

        ``on`` toggles the actuator (``True`` = close, ``False`` = open).
        ``enable`` is the air-pump / control power (default ``True``); pass
        ``enable=False`` to switch the pump off entirely.
        """
        return self.lowlevel.set_end_effector_gripper(
            enable_ctrl=bool(enable), on=bool(on), queued=queued
        )

    def laser(
        self, on: bool, *, enable: bool = True, queued: bool = True
    ) -> Optional[int]:
        """Switch the laser on or off (``enable`` powers the control circuit)."""
        return self.lowlevel.set_end_effector_laser(
            enable_ctrl=bool(enable), on=bool(on), queued=queued
        )

    def set_type(self, end_type: int, *, queued: bool = False) -> Optional[int]:
        """Set the end-effector type (see :class:`~dobotkit.enums.EndEffectorType`)."""
        return self.lowlevel.set_end_effector_type(end_type, queued=queued)

    def get_type(self) -> int:
        """Read the current end-effector type code."""
        return self.lowlevel.get_end_effector_type()

    def set_servo(
        self, servo_id: int, angle: float, *, queued: bool = False
    ) -> Optional[int]:
        """Set the angle of a servo on the end effector.

        MagicBox-routed: returns ``None`` (with a warning) if the MagicBox/servo
        is not connected. See :func:`_guard`.
        """
        return _guard(
            lambda: self.lowlevel.set_servo_angle(servo_id, angle, queued=queued)
        )

    def get_servo(self, servo_id: int) -> Optional[float]:
        """Read the angle of a servo on the end effector.

        MagicBox-routed: returns ``None`` (with a warning) if the MagicBox/servo
        is not connected. See :func:`_guard`.
        """
        return _guard(lambda: self.lowlevel.get_servo_angle(servo_id))


class SensorGroup(_Group):
    """Ergonomic accessors for the arm's sensors."""

    # All sensors are MagicBox-routed: every read below returns ``None`` (with a
    # warning) instead of raising when the MagicBox/sensor is not connected.
    # See :func:`_guard`.

    def color(self, port: int) -> "Optional[S.ColorSensorReading]":
        """Enable the color sensor on ``port`` and read its RGB triplet."""
        def _read() -> "S.ColorSensorReading":
            self.lowlevel.set_color_sensor(enable=1, port=port)
            return self.lowlevel.get_color_sensor()

        return _guard(_read)

    def infrared(self, port: int) -> "Optional[S.InfraredSensorReading]":
        """Enable the infrared sensor on ``port`` and read its value."""
        def _read() -> "S.InfraredSensorReading":
            self.lowlevel.set_infrared_sensor(enable=1, port=port)
            return self.lowlevel.get_infrared_sensor(port)

        return _guard(_read)

    def seeed_distance(self, port: int) -> "Optional[S.SeeedDistanceReading]":
        """Read the Seeed distance sensor on ``port``."""
        return _guard(lambda: self.lowlevel.get_seeed_distance_sensor(port))

    def seeed_color(self, port: int) -> "Optional[S.SeeedColorReading]":
        """Select the Seeed color sensor on ``port`` and read (r, g, b, cct)."""
        def _read() -> "S.SeeedColorReading":
            self.lowlevel.set_seeed_color_sensor(port)
            return self.lowlevel.get_seeed_color_sensor()

        return _guard(_read)

    def seeed_temp(self, port: int) -> "Optional[S.SeeedTempReading]":
        """Select the Seeed temp/humidity sensor on ``port`` and read it."""
        def _read() -> "S.SeeedTempReading":
            self.lowlevel.set_seeed_temp_sensor(port)
            return self.lowlevel.get_seeed_temp_sensor()

        return _guard(_read)

    def seeed_light(self, port: int) -> "Optional[S.SeeedLightReading]":
        """Select the Seeed light sensor on ``port`` and read its lux value."""
        def _read() -> "S.SeeedLightReading":
            self.lowlevel.set_seeed_light_sensor(port)
            return self.lowlevel.get_seeed_light_sensor()

        return _guard(_read)

    def seeed_rgb(self, port: int, rgb: float) -> Optional[int]:
        """Set the Seeed RGB LED on ``port`` to ``rgb``.

        MagicBox-routed: returns ``None`` (with a warning) if not connected.
        """
        return _guard(lambda: self.lowlevel.set_seeed_rgb(port, rgb))


class IOGroup(_Group):
    """Ergonomic accessors for the arm's digital/analog IO and extended motors."""

    # -- digital output ---------------------------------------------------- #

    def set_do(self, address: int, level: int, *, queued: bool = False) -> Optional[int]:
        """Set the digital-output level of IO pin ``address``."""
        return self.lowlevel.set_io_do(address, level, queued=queued)

    def get_do(self, address: int) -> int:
        """Read the digital-output level currently set on IO pin ``address``."""
        return self.lowlevel.get_io_do(address).level

    # -- digital input ----------------------------------------------------- #

    def get_di(self, address: int) -> int:
        """Read the digital-input level of IO pin ``address``."""
        return self.lowlevel.get_io_di(address).level

    # -- analog input ------------------------------------------------------ #

    def get_adc(self, address: int) -> int:
        """Read the ADC value of IO pin ``address``."""
        return self.lowlevel.get_io_adc(address).value

    # -- PWM --------------------------------------------------------------- #

    def set_pwm(
        self,
        address: int,
        frequency: float,
        duty_cycle: float,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Configure PWM (frequency Hz, duty cycle %) on IO pin ``address``."""
        return self.lowlevel.set_io_pwm(address, frequency, duty_cycle, queued=queued)

    # -- multiplexing ------------------------------------------------------ #

    def set_multiplexing(
        self, address: int, multiplex: int, *, queued: bool = False
    ) -> Optional[int]:
        """Assign a multiplex function to IO pin ``address``."""
        return self.lowlevel.set_io_multiplexing(address, multiplex, queued=queued)

    def get_multiplexing(self, address: int) -> "S.IOMultiplexing":
        """Read the multiplex function assigned to IO pin ``address``."""
        return self.lowlevel.get_io_multiplexing(address)

    # -- extended motors --------------------------------------------------- #

    def set_motor(
        self, index: int, enabled: bool, speed: int, *, queued: bool = False
    ) -> Optional[int]:
        """Drive extended motor ``index`` at a continuous ``speed``.

        Extended motors are reached over the MagicBox-routed bus: returns
        ``None`` (with a warning) if not connected. See :func:`_guard`.
        """
        return _guard(
            lambda: self.lowlevel.set_e_motor(index, int(enabled), speed, queued=queued)
        )

    def set_motor_steps(
        self,
        index: int,
        enabled: bool,
        speed: int,
        distance: int,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Drive extended motor ``index`` a fixed ``distance`` at ``speed``.

        Extended motors are reached over the MagicBox-routed bus: returns
        ``None`` (with a warning) if not connected. See :func:`_guard`.
        """
        return _guard(
            lambda: self.lowlevel.set_e_motors(
                index, int(enabled), speed, distance, queued=queued
            )
        )
