"""Device / connection payload structures (Task 2.1).

Mirrors the ``DobotDllType`` device-info ``Structure`` classes. Wire format is
little-endian, packed (``_pack_ = 1``) — derived mechanically from each oracle
``_fields_`` list:

- ``DeviceVersion``  -> ``<8b``   (eight signed ``c_byte`` version fields)
- ``DeviceID``       -> ``<3I``   (three ``c_uint32`` IDs)
- ``DevInfo``        -> ``<ii50s50sf`` (devId, type, firmwareName[50],
  firwareVersion[50], runTime)
- ``DeviceCountInfo``-> ``<QII``  (deviceRunTime ``c_uint64``, devicePowerOn
  ``c_uint32``, devicePowerOff ``c_uint32``)

Each ``unpack_*`` returns a typed :class:`typing.NamedTuple`. Fixed byte-array
fields are exposed as ``bytes`` by the unpacker and as ``str``/``bytes`` by the
packer (NUL-padded to the field width).
"""
from __future__ import annotations

import struct
from typing import NamedTuple, Union

__all__ = [
    "DeviceVersion",
    "pack_DeviceVersion",
    "unpack_DeviceVersion",
    "DeviceID",
    "pack_DeviceID",
    "unpack_DeviceID",
    "DevInfo",
    "pack_DevInfo",
    "unpack_DevInfo",
    "DeviceCountInfo",
    "pack_DeviceCountInfo",
    "unpack_DeviceCountInfo",
]


# --------------------------------------------------------------------------- #
# DeviceVersion  ->  <8b  (8 bytes)
# fw_major, fw_minor, fw_revision, fw_alpha, hw_major, hw_minor, hw_revision,
# hw_alpha  (all signed c_byte)
# --------------------------------------------------------------------------- #
_DEVICEVERSION_FMT = "<8b"


class DeviceVersion(NamedTuple):
    fw_major: int
    fw_minor: int
    fw_revision: int
    fw_alpha: int
    hw_major: int
    hw_minor: int
    hw_revision: int
    hw_alpha: int


def pack_DeviceVersion(
    fw_major: int,
    fw_minor: int,
    fw_revision: int,
    fw_alpha: int,
    hw_major: int,
    hw_minor: int,
    hw_revision: int,
    hw_alpha: int,
) -> bytes:
    """Pack the firmware/hardware version octet (eight signed bytes)."""
    return struct.pack(
        _DEVICEVERSION_FMT,
        fw_major,
        fw_minor,
        fw_revision,
        fw_alpha,
        hw_major,
        hw_minor,
        hw_revision,
        hw_alpha,
    )


def unpack_DeviceVersion(data: bytes) -> DeviceVersion:
    return DeviceVersion(*struct.unpack(_DEVICEVERSION_FMT, data))


# --------------------------------------------------------------------------- #
# DeviceID  ->  <3I  (12 bytes)  (deviceID1..3, c_uint32)
# --------------------------------------------------------------------------- #
_DEVICEID_FMT = "<3I"


class DeviceID(NamedTuple):
    device_id1: int
    device_id2: int
    device_id3: int


def pack_DeviceID(device_id1: int, device_id2: int, device_id3: int) -> bytes:
    """Pack the three 32-bit device-identity words."""
    return struct.pack(_DEVICEID_FMT, device_id1, device_id2, device_id3)


def unpack_DeviceID(data: bytes) -> DeviceID:
    return DeviceID(*struct.unpack(_DEVICEID_FMT, data))


# --------------------------------------------------------------------------- #
# DevInfo  ->  <ii50s50sf  (112 bytes)
# devId (c_int), type (c_int), firmwareName (c_byte*50),
# firwareVersion (c_byte*50), runTime (c_float)
# --------------------------------------------------------------------------- #
_DEVINFO_FMT = "<ii50s50sf"


class DevInfo(NamedTuple):
    dev_id: int
    type: int
    firmware_name: bytes
    firmware_version: bytes
    run_time: float


def _to_fixed_bytes(value: Union[str, bytes], width: int) -> bytes:
    """Encode ``value`` (str or bytes) to exactly ``width`` NUL-padded bytes."""
    if isinstance(value, str):
        raw = value.encode("utf-8")
    else:
        raw = bytes(value)
    if len(raw) > width:
        raise ValueError(f"field too long: {len(raw)} > {width}")
    return raw  # struct '<Ns' NUL-pads to width on pack


def pack_DevInfo(
    dev_id: int,
    type: int,
    firmware_name: Union[str, bytes] = b"",
    firmware_version: Union[str, bytes] = b"",
    run_time: float = 0.0,
) -> bytes:
    """Pack peripheral device info (id, type, firmware name/version, run time)."""
    return struct.pack(
        _DEVINFO_FMT,
        dev_id,
        type,
        _to_fixed_bytes(firmware_name, 50),
        _to_fixed_bytes(firmware_version, 50),
        run_time,
    )


def unpack_DevInfo(data: bytes) -> DevInfo:
    dev_id, type_, fw_name, fw_version, run_time = struct.unpack(_DEVINFO_FMT, data)
    return DevInfo(
        dev_id=dev_id,
        type=type_,
        firmware_name=fw_name,
        firmware_version=fw_version,
        run_time=run_time,
    )


# --------------------------------------------------------------------------- #
# DeviceCountInfo  ->  <QII  (16 bytes)
# deviceRunTime (c_uint64), devicePowerOn (c_uint32), devicePowerOff (c_uint32)
# --------------------------------------------------------------------------- #
_DEVICECOUNTINFO_FMT = "<QII"


class DeviceCountInfo(NamedTuple):
    device_run_time: int
    device_power_on: int
    device_power_off: int


def pack_DeviceCountInfo(
    device_run_time: int,
    device_power_on: int,
    device_power_off: int,
) -> bytes:
    """Pack cumulative run-time / power-on / power-off counters."""
    return struct.pack(
        _DEVICECOUNTINFO_FMT,
        device_run_time,
        device_power_on,
        device_power_off,
    )


def unpack_DeviceCountInfo(data: bytes) -> DeviceCountInfo:
    return DeviceCountInfo(*struct.unpack(_DEVICECOUNTINFO_FMT, data))
