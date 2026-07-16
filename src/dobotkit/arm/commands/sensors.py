"""Sensor RPC wrappers. Filled in later."""
from __future__ import annotations
from typing import Any
from dobotkit.arm.commands._base import _Base


class SensorMixin(_Base):
    """Sensor and alarm RPC wrapper methods."""

    # -- sensors --
    def set_color_sensor(self, enable: int, port: int, version: int = 1) -> Any:
        return self._call("SetColorSensor", enable=int(enable),
                          colorPort=int(port), version=int(version))

    def get_color_sensor(self) -> Any:
        return self._call("GetColorSensor")

    def set_infrared_sensor(self, enable: int, port: int, version: int = 1) -> Any:
        return self._call("SetInfraredSensor", enable=int(enable),
                          infraredPort=int(port), version=int(version))

    def get_infrared_sensor(self, port: int) -> Any:
        return self._call("GetInfraredSensor", infraredPort=int(port))

    def get_seeed_distance(self, port: int) -> Any:
        return self._call("GetSeeedDistanceSensor", port=int(port))

    def get_seeed_temp(self, port: int) -> Any:
        return self._call("GetSeeedTempSensor", port=int(port))

    def get_seeed_light(self, port: int) -> Any:
        return self._call("GetSeeedLightSensor", port=int(port))

    def set_seeed_rgb(self, port: int, rgb: float) -> Any:
        return self._call("SetSeeedRGBLED", port=int(port), rgb=float(rgb))

    def get_alarms_state(self) -> Any:
        return self._call("GetAlarmsState")
