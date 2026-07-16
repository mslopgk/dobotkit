"""MagicBox peripheral facades for the Magician GO.

The GO carries the same **MagicBox** peripheral hub as the arm, but its sensor
reads are issued on the DobotLink ``MagicBox.*`` JSON-RPC namespace (not
``MagicianGO.*``). The two namespaces coexist on a single connection: connect
the car once with ``MagicianGO.ConnectDobot`` and these ``MagicBox.*`` reads
work alongside the native drive/battery/ultrasonic calls (hardware-verified
2026-07-16). There is **no** separate ``MagicBox.ConnectDobot`` step — issuing
one actually knocks the GO chassis offline, so this module never does it.

Two addressing schemes, straight from the official DobotLab apiBook
(``magicbox.get_ad`` / ``get_di`` / ``set_port`` vs the sensor blocks):

* **ADC / DI / DO / PWM** address a raw **EIO pin (1..26)** -- e.g. the test
  unit's rotary potentiometer on Grove connector 4 reads on EIO pin **22**.
  ``set_port(port, io_func=4)`` selects ADC before reading (``4`` = ADC).
* **color / infrared / Seeed** address the labelled **Grove connector (1..6)**.

Every read here is *guarded* (see :func:`_guard`): a missing MagicBox or
peripheral answers with :class:`~dobotkit.exceptions.DobotTimeoutError` /
:class:`~dobotkit.exceptions.DobotProtocolError`, which is caught and degraded
to ``None`` + a ``RuntimeWarning`` so teaching/beginner code keeps running. A
genuine connection error (DobotLink down / GO not connected) still raises.
"""
from __future__ import annotations

import warnings
from typing import Any, Callable, Optional, TypeVar

from dobotkit.enums import GPIOType
from dobotkit.exceptions import DobotProtocolError, DobotTimeoutError

__all__ = ["GoSensorGroup", "GoIOGroup"]

_T = TypeVar("_T")

# A connected ``DobotLinkClient`` (or any object exposing ``call``).
ClientLike = Any

#: Warning emitted when a MagicBox-routed peripheral read gets no response.
#: Bilingual so it reads in both the Korean teaching materials and English docs.
_UNAVAILABLE = (
    "주변장치 응답이 없습니다 — 매직박스/센서 연결을 확인하세요 "
    "(no peripheral response; check the MagicBox and its device)"
)


def _guard(call: Callable[[], _T]) -> Optional[_T]:
    """Run a MagicBox-routed peripheral read, degrading to ``None`` if absent."""
    try:
        return call()
    except (DobotTimeoutError, DobotProtocolError):
        warnings.warn(_UNAVAILABLE, RuntimeWarning, stacklevel=3)
        return None


class _MagicBoxBase:
    """Base holding the client + port; issues ``MagicBox.*`` RPCs for the GO.

    The car is connected via ``MagicianGO.ConnectDobot`` elsewhere; these calls
    ride the same open port using the ``MagicBox.*`` namespace and the GO's
    ``portName``.
    """

    def __init__(self, client: ClientLike, port_name: str) -> None:
        self._client = client
        self.port_name = port_name

    def _mb(self, func: str, **params: Any) -> Any:
        """Issue ``MagicBox.<func>`` with the GO's ``portName``."""
        params["portName"] = self.port_name
        return self._client.call(f"MagicBox.{func}", **params)


class GoSensorGroup(_MagicBoxBase):
    """Ergonomic MagicBox sensor reads for the GO (all guarded -> ``None``).

    ``adc``/``di`` take an **EIO pin (1..26)**; ``color``/``infrared``/
    ``distance``/``temp``/``light``/``rgb`` take a **Grove connector (1..6)**.
    """

    def adc(self, eio: int) -> Optional[int]:
        """Select ADC mode on **EIO pin** ``eio`` (1..26) and read its analog value.

        Example: the test unit's potentiometer on Grove connector 4 is EIO pin
        ``22`` -> ``go.sensors.adc(22)``.
        """
        def _read() -> int:
            self._mb("SetIOMultiplexing", port=int(eio), multiplex=int(GPIOType.ADC))
            return int(self._mb("GetIOADC", port=int(eio))["value"])

        return _guard(_read)

    def di(self, eio: int) -> Optional[int]:
        """Read the digital-input level (0/1) of **EIO pin** ``eio`` (1..26)."""
        def _read() -> int:
            return int(self._mb("GetIODI", port=int(eio)).get("level", 0))

        return _guard(_read)

    def color(self, port: int) -> Optional[Any]:
        """Enable and read the color sensor on **Grove connector** ``port`` (1..6).

        Returns ``{"red", "green", "blue"}``.
        """
        def _read() -> Any:
            self._mb("SetColorSensor", enable=1, colorPort=int(port), version=1)
            return self._mb("GetColorSensor")

        return _guard(_read)

    def infrared(self, port: int) -> Optional[Any]:
        """Enable and read the infrared (photoelectric) sensor on Grove ``port``.

        Returns ``{"status": 0|1}`` (1 = object detected).
        """
        def _read() -> Any:
            self._mb("SetInfraredSensor", enable=1, infraredPort=int(port), version=1)
            return self._mb("GetInfraredSensor", infraredPort=int(port))

        return _guard(_read)

    def distance(self, port: int) -> Optional[Any]:
        """Read the Seeed distance sensor on **Grove connector** ``port`` (1..6)."""
        return _guard(lambda: self._mb("GetSeeedDistanceSensor", port=int(port)))

    def temp(self, port: int) -> Optional[Any]:
        """Read the Seeed temperature/humidity sensor on Grove ``port`` (1..6)."""
        return _guard(lambda: self._mb("GetSeeedTempSensor", port=int(port)))

    def light(self, port: int) -> Optional[Any]:
        """Read the Seeed light sensor on **Grove connector** ``port`` (1..6)."""
        return _guard(lambda: self._mb("GetSeeedLightSensor", port=int(port)))

    def rgb(self, port: int, value: float) -> Optional[Any]:
        """Set the Seeed RGB LED on Grove ``port`` (1..6) to ``value``."""
        return _guard(lambda: self._mb("SetSeeedRGBLed", port=int(port), rgb=float(value)))


class GoIOGroup(_MagicBoxBase):
    """Ergonomic MagicBox digital/analog I/O for the GO, addressed by **EIO pin** (1..26)."""

    def set_do(self, eio: int, level: int) -> Any:
        """Set the digital-output level (0/1) of **EIO pin** ``eio`` (1..26)."""
        return self._mb("SetIODO", port=int(eio), level=int(level))

    def get_di(self, eio: int) -> Optional[int]:
        """Read the digital-input level (0/1) of **EIO pin** ``eio`` (1..26)."""
        def _read() -> int:
            return int(self._mb("GetIODI", port=int(eio)).get("level", 0))

        return _guard(_read)

    def get_adc(self, eio: int) -> Optional[int]:
        """Read the ADC value of **EIO pin** ``eio`` (1..26)."""
        return _guard(lambda: int(self._mb("GetIOADC", port=int(eio))["value"]))

    def set_pwm(self, eio: int, frequency: float, duty: float) -> Any:
        """Configure PWM (frequency Hz, duty % 0..100) on **EIO pin** ``eio``."""
        return self._mb("SetIOPWM", port=int(eio), frequency=float(frequency), dutyCycle=float(duty))

    def set_multiplexing(self, eio: int, multiplex: int) -> Any:
        """Assign a multiplex function (see :class:`~dobotkit.enums.GPIOType`) to EIO ``eio``."""
        return self._mb("SetIOMultiplexing", port=int(eio), multiplex=int(multiplex))
