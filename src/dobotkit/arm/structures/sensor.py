"""Sensor / color / IR / Seeed structures (Task 2.8).

The sensor command set has **no** dedicated ``DobotDllType`` ``Structure``
classes: the golden SDK builds every sensor payload inline from scalar C
arguments (``c_uint8`` ports / enables, ``c_ushort`` / ``c_ubyte`` readings,
a ``c_float`` RGB value). The wire formats below are therefore derived from the
DLL *call signatures* (``api.Set*`` / ``api.Get*``) rather than from a
``Structure._fields_`` list — but they follow the same little-endian, packed
convention as the rest of the protocol.

Naming mirrors the SDK: ``pack_<Name>`` builds a request payload, and
``unpack_<Name>`` decodes a multi-value GET response into a typed
:class:`typing.NamedTuple`.

Structures:

* ``ColorSensorParams``      — SET color sensor  (``<BBB``: enable, port, version)
* ``ColorSensorReading``     — GET color sensor  (``<BBB``: r, g, b)
* ``InfraredSensorParams``   — SET IR sensor      (``<BBB``: enable, port, version)
* ``InfraredSensorReading``  — GET IR sensor      (``<B``:   value)
* ``SeeedColorReading``      — GET Seeed colour   (``<HHHH``: r, g, b, cct)
* ``SeeedTempReading``       — GET Seeed temp     (``<HH``:  temperature, humidity)
* ``SeeedLightReading``      — GET Seeed light    (``<H``:   lux)
* ``SeeedDistanceReading``   — GET Seeed distance (``<B``:   distance)
* ``SeeedRgbParams``         — SET Seeed RGB      (``<Bf``:  port, rgb)
"""
from __future__ import annotations

import struct
from typing import NamedTuple

__all__ = [
    "ColorSensorParams",
    "pack_ColorSensorParams",
    "unpack_ColorSensorParams",
    "ColorSensorReading",
    "pack_ColorSensorReading",
    "unpack_ColorSensorReading",
    "InfraredSensorParams",
    "pack_InfraredSensorParams",
    "unpack_InfraredSensorParams",
    "InfraredSensorReading",
    "pack_InfraredSensorReading",
    "unpack_InfraredSensorReading",
    "SeeedColorReading",
    "pack_SeeedColorReading",
    "unpack_SeeedColorReading",
    "SeeedTempReading",
    "pack_SeeedTempReading",
    "unpack_SeeedTempReading",
    "SeeedLightReading",
    "pack_SeeedLightReading",
    "unpack_SeeedLightReading",
    "SeeedDistanceReading",
    "pack_SeeedDistanceReading",
    "unpack_SeeedDistanceReading",
    "SeeedRgbParams",
    "pack_SeeedRgbParams",
    "unpack_SeeedRgbParams",
]


# --------------------------------------------------------------------------- #
# ColorSensorParams  ->  <BBB  (3 bytes)  (isEnable, colorPort, version)
# --------------------------------------------------------------------------- #
_COLORSENSORPARAMS_FMT = "<BBB"


class ColorSensorParams(NamedTuple):
    enable: int
    port: int
    version: int


def pack_ColorSensorParams(enable: int, port: int, version: int = 0) -> bytes:
    """Pack a SetColorSensor request (isEnable, colorPort, version)."""
    return struct.pack(_COLORSENSORPARAMS_FMT, int(bool(enable)), port, version)


def unpack_ColorSensorParams(data: bytes) -> ColorSensorParams:
    return ColorSensorParams(*struct.unpack(_COLORSENSORPARAMS_FMT, data))


# --------------------------------------------------------------------------- #
# ColorSensorReading  ->  <BBB  (3 bytes)  (r, g, b)
# --------------------------------------------------------------------------- #
_COLORSENSORREADING_FMT = "<BBB"


class ColorSensorReading(NamedTuple):
    r: int
    g: int
    b: int


def pack_ColorSensorReading(r: int, g: int, b: int) -> bytes:
    """Pack a GetColorSensor response (r, g, b)."""
    return struct.pack(_COLORSENSORREADING_FMT, r, g, b)


def unpack_ColorSensorReading(data: bytes) -> ColorSensorReading:
    return ColorSensorReading(*struct.unpack(_COLORSENSORREADING_FMT, data))


# --------------------------------------------------------------------------- #
# InfraredSensorParams  ->  <BBB  (3 bytes)  (isEnable, infraredPort, version)
# --------------------------------------------------------------------------- #
_INFRAREDSENSORPARAMS_FMT = "<BBB"


class InfraredSensorParams(NamedTuple):
    enable: int
    port: int
    version: int


def pack_InfraredSensorParams(enable: int, port: int, version: int = 0) -> bytes:
    """Pack a SetInfraredSensor request (isEnable, infraredPort, version)."""
    return struct.pack(_INFRAREDSENSORPARAMS_FMT, int(bool(enable)), port, version)


def unpack_InfraredSensorParams(data: bytes) -> InfraredSensorParams:
    return InfraredSensorParams(*struct.unpack(_INFRAREDSENSORPARAMS_FMT, data))


# --------------------------------------------------------------------------- #
# InfraredSensorReading  ->  <B  (1 byte)  (value)
# --------------------------------------------------------------------------- #
_INFRAREDSENSORREADING_FMT = "<B"


class InfraredSensorReading(NamedTuple):
    value: int


def pack_InfraredSensorReading(value: int) -> bytes:
    """Pack a GetInfraredSensor response (value)."""
    return struct.pack(_INFRAREDSENSORREADING_FMT, value)


def unpack_InfraredSensorReading(data: bytes) -> InfraredSensorReading:
    return InfraredSensorReading(*struct.unpack(_INFRAREDSENSORREADING_FMT, data))


# --------------------------------------------------------------------------- #
# SeeedColorReading  ->  <HHHH  (8 bytes)  (r, g, b, cct)  [c_ushort each]
# --------------------------------------------------------------------------- #
_SEEEDCOLORREADING_FMT = "<HHHH"


class SeeedColorReading(NamedTuple):
    r: int
    g: int
    b: int
    cct: int


def pack_SeeedColorReading(r: int, g: int, b: int, cct: int) -> bytes:
    """Pack a GetSeeedColorSensor response (r, g, b, cct)."""
    return struct.pack(_SEEEDCOLORREADING_FMT, r, g, b, cct)


def unpack_SeeedColorReading(data: bytes) -> SeeedColorReading:
    return SeeedColorReading(*struct.unpack(_SEEEDCOLORREADING_FMT, data))


# --------------------------------------------------------------------------- #
# SeeedTempReading  ->  <HH  (4 bytes)  (temperature, humidity)  [c_ushort each]
# --------------------------------------------------------------------------- #
_SEEEDTEMPREADING_FMT = "<HH"


class SeeedTempReading(NamedTuple):
    temperature: int
    humidity: int


def pack_SeeedTempReading(temperature: int, humidity: int) -> bytes:
    """Pack a GetSeeedTempSensor response (temperature, humidity)."""
    return struct.pack(_SEEEDTEMPREADING_FMT, temperature, humidity)


def unpack_SeeedTempReading(data: bytes) -> SeeedTempReading:
    return SeeedTempReading(*struct.unpack(_SEEEDTEMPREADING_FMT, data))


# --------------------------------------------------------------------------- #
# SeeedLightReading  ->  <H  (2 bytes)  (lux)  [c_ushort]
# --------------------------------------------------------------------------- #
_SEEEDLIGHTREADING_FMT = "<H"


class SeeedLightReading(NamedTuple):
    lux: int


def pack_SeeedLightReading(lux: int) -> bytes:
    """Pack a GetSeeedLightSensor response (lux)."""
    return struct.pack(_SEEEDLIGHTREADING_FMT, lux)


def unpack_SeeedLightReading(data: bytes) -> SeeedLightReading:
    return SeeedLightReading(*struct.unpack(_SEEEDLIGHTREADING_FMT, data))


# --------------------------------------------------------------------------- #
# SeeedDistanceReading  ->  <B  (1 byte)  (distance)  [c_ubyte]
# --------------------------------------------------------------------------- #
_SEEEDDISTANCEREADING_FMT = "<B"


class SeeedDistanceReading(NamedTuple):
    distance: int


def pack_SeeedDistanceReading(distance: int) -> bytes:
    """Pack a GetSeeedDistanceSensor response (distance)."""
    return struct.pack(_SEEEDDISTANCEREADING_FMT, distance)


def unpack_SeeedDistanceReading(data: bytes) -> SeeedDistanceReading:
    return SeeedDistanceReading(*struct.unpack(_SEEEDDISTANCEREADING_FMT, data))


# --------------------------------------------------------------------------- #
# SeeedRgbParams  ->  <Bf  (5 bytes)  (port, rgb)  [c_ubyte, c_float]
# --------------------------------------------------------------------------- #
_SEEEDRGBPARAMS_FMT = "<Bf"


class SeeedRgbParams(NamedTuple):
    port: int
    rgb: float


def pack_SeeedRgbParams(port: int, rgb: float) -> bytes:
    """Pack a SetSeeedRgb request (SeeedPort, Rgb)."""
    return struct.pack(_SEEEDRGBPARAMS_FMT, port, rgb)


def unpack_SeeedRgbParams(data: bytes) -> SeeedRgbParams:
    return SeeedRgbParams(*struct.unpack(_SEEEDRGBPARAMS_FMT, data))
