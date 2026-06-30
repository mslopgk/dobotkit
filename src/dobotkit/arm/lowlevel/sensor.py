"""Sensor commands (Task 2.8): color / infrared / Seeed sensors.

Implements the SDK's color-sensor, infrared-sensor and Seeed-sensor command
set 1:1 on :class:`SensorMixin`. Each SET / GET pair shares a single
:class:`~dobotkit.arm.ids.ProtocolId` and differs only by the frame's
read/write bit (``rw``); ``isQueued`` is exposed as ``queued: bool = False``.

GET methods decode their (multi-value) responses via the matching
``structures.unpack_*`` helper and return a typed ``NamedTuple``. Queued
setters return the 64-bit queued-command index (via ``_queued_index``);
immediate setters return ``None``.

``_ext`` / ``_ext_ex`` variants
-------------------------------
The SDK exposes ``*Ext`` (MagicBox-routed) and ``*ExtEx`` (route + block until
the queued command executes) wrappers around each base command. Per the
project's Ext-routing convention (research doc §1 / Task 2.7) the base commands
already auto-route to the connected peripheral, so the ``_ext`` / ``_ext_ex``
methods here are thin DRY wrappers that delegate to the single base
implementation rather than duplicating the frame-building logic.
"""
from __future__ import annotations

from typing import Optional

from dobotkit.arm import structures as S
from dobotkit.arm.ids import ProtocolId
from dobotkit.arm.lowlevel._base import _LowLevelProtocol


class SensorMixin(_LowLevelProtocol):
    """Color / infrared / Seeed sensor commands."""

    # ------------------------------------------------------------------ #
    # Color sensor  ->  SET_GET_COLOR_SENSOR (137)
    # ------------------------------------------------------------------ #
    def set_color_sensor(
        self,
        enable: int,
        port: int,
        version: int = 0,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Enable/disable the color sensor on ``port`` (SetColorSensor)."""
        params = S.pack_ColorSensorParams(enable, port, version)
        resp = self._send(
            ProtocolId.SET_GET_COLOR_SENSOR, params, rw=True, queued=queued
        )
        return self._queued_index(resp) if queued else None

    def get_color_sensor(self) -> S.ColorSensorReading:
        """Read the color sensor RGB triplet (GetColorSensor)."""
        resp = self._send(ProtocolId.SET_GET_COLOR_SENSOR, b"", rw=False)
        return S.unpack_ColorSensorReading(resp.params)

    def set_color_sensor_ext(
        self,
        enable: int,
        port: int,
        version: int = 0,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """MagicBox-routed ``set_color_sensor`` (SetColorSensorExt)."""
        return self.set_color_sensor(enable, port, version, queued=queued)

    def set_color_sensor_ext_ex(
        self,
        enable: int,
        port: int,
        version: int = 0,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Routed + blocking ``set_color_sensor`` (SetColorSensorExtEx)."""
        return self.set_color_sensor_ext(enable, port, version, queued=queued)

    def get_color_sensor_ext(self) -> S.ColorSensorReading:
        """MagicBox-routed ``get_color_sensor`` (GetColorSensorExt)."""
        return self.get_color_sensor()

    # ------------------------------------------------------------------ #
    # Infrared sensor  ->  SET_GET_IR_SWITCH (138)
    # ------------------------------------------------------------------ #
    def set_infrared_sensor(
        self,
        enable: int,
        port: int,
        version: int = 0,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Enable/disable the infrared sensor on ``port`` (SetInfraredSensor)."""
        params = S.pack_InfraredSensorParams(enable, port, version)
        resp = self._send(
            ProtocolId.SET_GET_IR_SWITCH, params, rw=True, queued=queued
        )
        return self._queued_index(resp) if queued else None

    def get_infrared_sensor(self, port: int) -> S.InfraredSensorReading:
        """Read the infrared sensor value on ``port`` (GetInfraredSensor)."""
        params = S.pack_InfraredSensorReading(port)
        resp = self._send(ProtocolId.SET_GET_IR_SWITCH, params, rw=False)
        return S.unpack_InfraredSensorReading(resp.params)

    def set_infrared_sensor_ext(
        self,
        enable: int,
        port: int,
        version: int = 0,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """MagicBox-routed ``set_infrared_sensor`` (SetInfraredSensorExt)."""
        return self.set_infrared_sensor(enable, port, version, queued=queued)

    def set_infrared_sensor_ext_ex(
        self,
        enable: int,
        port: int,
        version: int = 0,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Routed + blocking ``set_infrared_sensor`` (SetInfraredSensorExtEx)."""
        return self.set_infrared_sensor_ext(enable, port, version, queued=queued)

    def get_infrared_sensor_ext(self, port: int) -> S.InfraredSensorReading:
        """MagicBox-routed ``get_infrared_sensor`` (GetInfraredSensorExt)."""
        return self.get_infrared_sensor(port)

    # ------------------------------------------------------------------ #
    # Seeed distance sensor  ->  SET_GET_SEEED_DISTANCE (215, # unverified)
    # ------------------------------------------------------------------ #
    def get_seeed_distance_sensor(self, port: int) -> S.SeeedDistanceReading:
        """Read the Seeed distance sensor on ``port`` (GetSeeedDistanceSensor)."""
        params = S.pack_SeeedDistanceReading(port)
        resp = self._send(ProtocolId.SET_GET_SEEED_DISTANCE, params, rw=False)
        return S.unpack_SeeedDistanceReading(resp.params)

    def get_seeed_distance_sensor_ext(self, port: int) -> S.SeeedDistanceReading:
        """MagicBox-routed ``get_seeed_distance_sensor``."""
        return self.get_seeed_distance_sensor(port)

    # ------------------------------------------------------------------ #
    # Seeed color sensor  ->  SET_GET_SEEED_COLOR (216, # unverified)
    # ------------------------------------------------------------------ #
    def set_seeed_color_sensor(
        self, port: int, *, queued: bool = False
    ) -> Optional[int]:
        """Select the Seeed color sensor on ``port`` (SetSeeedColorSensor)."""
        params = S.pack_SeeedDistanceReading(port)
        resp = self._send(
            ProtocolId.SET_GET_SEEED_COLOR, params, rw=True, queued=queued
        )
        return self._queued_index(resp) if queued else None

    def get_seeed_color_sensor(self) -> S.SeeedColorReading:
        """Read the Seeed color sensor (r, g, b, cct) (GetSeeedColorSensor)."""
        resp = self._send(ProtocolId.SET_GET_SEEED_COLOR, b"", rw=False)
        return S.unpack_SeeedColorReading(resp.params)

    def set_seeed_color_sensor_ext(
        self, port: int, *, queued: bool = False
    ) -> Optional[int]:
        """MagicBox-routed ``set_seeed_color_sensor`` (SetSeeedColorSensorExt)."""
        return self.set_seeed_color_sensor(port, queued=queued)

    def set_seeed_color_sensor_ext_ex(
        self, port: int, *, queued: bool = False
    ) -> Optional[int]:
        """Routed + blocking ``set_seeed_color_sensor`` (…ExtEx)."""
        return self.set_seeed_color_sensor_ext(port, queued=queued)

    def get_seeed_color_sensor_ext(self) -> S.SeeedColorReading:
        """MagicBox-routed ``get_seeed_color_sensor`` (GetSeeedColorSensorExt)."""
        return self.get_seeed_color_sensor()

    # ------------------------------------------------------------------ #
    # Seeed temperature/humidity sensor  ->  SET_GET_SEEED_TEMP (217, # unverified)
    # ------------------------------------------------------------------ #
    def set_seeed_temp_sensor(
        self, port: int, *, queued: bool = False
    ) -> Optional[int]:
        """Select the Seeed temp/humidity sensor on ``port`` (SetSeeedTempSensor)."""
        params = S.pack_SeeedDistanceReading(port)
        resp = self._send(
            ProtocolId.SET_GET_SEEED_TEMP, params, rw=True, queued=queued
        )
        return self._queued_index(resp) if queued else None

    def get_seeed_temp_sensor(self) -> S.SeeedTempReading:
        """Read Seeed temperature + humidity (GetSeeedTempSensor)."""
        resp = self._send(ProtocolId.SET_GET_SEEED_TEMP, b"", rw=False)
        return S.unpack_SeeedTempReading(resp.params)

    def set_seeed_temp_sensor_ext(
        self, port: int, *, queued: bool = False
    ) -> Optional[int]:
        """MagicBox-routed ``set_seeed_temp_sensor`` (SetSeeedTempSensorExt)."""
        return self.set_seeed_temp_sensor(port, queued=queued)

    def set_seeed_temp_sensor_ext_ex(
        self, port: int, *, queued: bool = False
    ) -> Optional[int]:
        """Routed + blocking ``set_seeed_temp_sensor`` (…ExtEx)."""
        return self.set_seeed_temp_sensor_ext(port, queued=queued)

    def get_seeed_temp_sensor_ext(self) -> S.SeeedTempReading:
        """MagicBox-routed ``get_seeed_temp_sensor`` (GetSeeedTempSensorExt)."""
        return self.get_seeed_temp_sensor()

    # ------------------------------------------------------------------ #
    # Seeed light sensor  ->  SET_GET_SEEED_LIGHT (218, # unverified)
    # ------------------------------------------------------------------ #
    def set_seeed_light_sensor(
        self, port: int, *, queued: bool = False
    ) -> Optional[int]:
        """Select the Seeed light sensor on ``port`` (SetSeeedLightSensor)."""
        params = S.pack_SeeedDistanceReading(port)
        resp = self._send(
            ProtocolId.SET_GET_SEEED_LIGHT, params, rw=True, queued=queued
        )
        return self._queued_index(resp) if queued else None

    def get_seeed_light_sensor(self) -> S.SeeedLightReading:
        """Read the Seeed light sensor lux value (GetSeeedLightSensor)."""
        resp = self._send(ProtocolId.SET_GET_SEEED_LIGHT, b"", rw=False)
        return S.unpack_SeeedLightReading(resp.params)

    def set_seeed_light_sensor_ext(
        self, port: int, *, queued: bool = False
    ) -> Optional[int]:
        """MagicBox-routed ``set_seeed_light_sensor`` (SetSeeedLightSensorExt)."""
        return self.set_seeed_light_sensor(port, queued=queued)

    def set_seeed_light_sensor_ext_ex(
        self, port: int, *, queued: bool = False
    ) -> Optional[int]:
        """Routed + blocking ``set_seeed_light_sensor`` (…ExtEx)."""
        return self.set_seeed_light_sensor_ext(port, queued=queued)

    def get_seeed_light_sensor_ext(self) -> S.SeeedLightReading:
        """MagicBox-routed ``get_seeed_light_sensor`` (GetSeeedLightSensorExt)."""
        return self.get_seeed_light_sensor()

    # ------------------------------------------------------------------ #
    # Seeed RGB LED  ->  SET_SEEED_RGB (219, # unverified)
    # ------------------------------------------------------------------ #
    def set_seeed_rgb(
        self, port: int, rgb: float, *, queued: bool = False
    ) -> Optional[int]:
        """Set the Seeed RGB LED on ``port`` to ``rgb`` (SetSeeedRgb)."""
        params = S.pack_SeeedRgbParams(port, rgb)
        resp = self._send(
            ProtocolId.SET_SEEED_RGB, params, rw=True, queued=queued
        )
        return self._queued_index(resp) if queued else None

    def set_seeed_rgb_ext(
        self, port: int, rgb: float, *, queued: bool = False
    ) -> Optional[int]:
        """MagicBox-routed ``set_seeed_rgb`` (SetSeeedRgbExt)."""
        return self.set_seeed_rgb(port, rgb, queued=queued)

    def set_seeed_rgb_ext_ex(
        self, port: int, rgb: float, *, queued: bool = False
    ) -> Optional[int]:
        """Routed + blocking ``set_seeed_rgb`` (SetSeeedRgbExtEx)."""
        return self.set_seeed_rgb_ext(port, rgb, queued=queued)
