"""IO / EMotor / WAIT / TRIG payload structures (Task 2.7).

Each (un)packer mirrors a ``DobotDllType`` ``Structure`` (``_pack_ = 1``), so the
wire format is **little-endian, packed** (no alignment padding). Formats are
derived directly from the oracle ``_fields_`` lists:

==================  ===========================================  ========
Struct              ctypes ``_fields_``                          format
==================  ===========================================  ========
IOMultiplexing      address(c_byte), multiplex(c_byte)           ``<bb``
IODO                address(c_byte), level(c_byte)               ``<bb``
IOPWM               address(c_byte), frequency(f), dutyCycle(f)  ``<bff``
IODI                address(c_byte), level(c_byte)               ``<bb``
IOADC               address(c_byte), value(c_int)                ``<bi``
EMotor              index(b), isEnabled(b), speed(c_int32)       ``<bbi``
EMotorS             index(b), isEnabled(b), speed(i), dist(I)    ``<bbiI``
WAITCmd             waitTime(c_uint32)                           ``<I``
TRIGCmd             address(b), mode(b), condition(b), thr(H)    ``<bbbH``
==================  ===========================================  ========
"""
from __future__ import annotations

import struct
from typing import NamedTuple

__all__ = [
    "IOMultiplexing",
    "pack_IOMultiplexing",
    "unpack_IOMultiplexing",
    "IODO",
    "pack_IODO",
    "unpack_IODO",
    "IOPWM",
    "pack_IOPWM",
    "unpack_IOPWM",
    "IODI",
    "pack_IODI",
    "unpack_IODI",
    "IOADC",
    "pack_IOADC",
    "unpack_IOADC",
    "EMotor",
    "pack_EMotor",
    "unpack_EMotor",
    "EMotorS",
    "pack_EMotorS",
    "unpack_EMotorS",
    "WAITCmd",
    "pack_WAITCmd",
    "unpack_WAITCmd",
    "TRIGCmd",
    "pack_TRIGCmd",
    "unpack_TRIGCmd",
]


# --------------------------------------------------------------------------- #
# IOMultiplexing  ->  <bb  (2 bytes)
# --------------------------------------------------------------------------- #
_IOMULTIPLEXING_FMT = "<bb"


class IOMultiplexing(NamedTuple):
    address: int
    multiplex: int


def pack_IOMultiplexing(address: int, multiplex: int) -> bytes:
    """Pack an IO multiplexing assignment (pin address, multiplex function)."""
    return struct.pack(_IOMULTIPLEXING_FMT, address, multiplex)


def unpack_IOMultiplexing(data: bytes) -> IOMultiplexing:
    return IOMultiplexing(*struct.unpack(_IOMULTIPLEXING_FMT, data))


# --------------------------------------------------------------------------- #
# IODO  ->  <bb  (2 bytes)
# --------------------------------------------------------------------------- #
_IODO_FMT = "<bb"


class IODO(NamedTuple):
    address: int
    level: int


def pack_IODO(address: int, level: int) -> bytes:
    """Pack a digital-output command (pin address, output level)."""
    return struct.pack(_IODO_FMT, address, level)


def unpack_IODO(data: bytes) -> IODO:
    return IODO(*struct.unpack(_IODO_FMT, data))


# --------------------------------------------------------------------------- #
# IOPWM  ->  <bff  (9 bytes)
# --------------------------------------------------------------------------- #
_IOPWM_FMT = "<bff"


class IOPWM(NamedTuple):
    address: int
    frequency: float
    duty_cycle: float


def pack_IOPWM(address: int, frequency: float, duty_cycle: float) -> bytes:
    """Pack a PWM-output command (pin address, frequency Hz, duty cycle %)."""
    return struct.pack(_IOPWM_FMT, address, frequency, duty_cycle)


def unpack_IOPWM(data: bytes) -> IOPWM:
    return IOPWM(*struct.unpack(_IOPWM_FMT, data))


# --------------------------------------------------------------------------- #
# IODI  ->  <bb  (2 bytes)
# --------------------------------------------------------------------------- #
_IODI_FMT = "<bb"


class IODI(NamedTuple):
    address: int
    level: int


def pack_IODI(address: int, level: int = 0) -> bytes:
    """Pack a digital-input query (pin address; ``level`` is the read result)."""
    return struct.pack(_IODI_FMT, address, level)


def unpack_IODI(data: bytes) -> IODI:
    return IODI(*struct.unpack(_IODI_FMT, data))


# --------------------------------------------------------------------------- #
# IOADC  ->  <bi  (5 bytes)
# --------------------------------------------------------------------------- #
_IOADC_FMT = "<bi"


class IOADC(NamedTuple):
    address: int
    value: int


def pack_IOADC(address: int, value: int = 0) -> bytes:
    """Pack an ADC query (pin address; ``value`` is the read result)."""
    return struct.pack(_IOADC_FMT, address, value)


def unpack_IOADC(data: bytes) -> IOADC:
    return IOADC(*struct.unpack(_IOADC_FMT, data))


# --------------------------------------------------------------------------- #
# EMotor  ->  <bbi  (6 bytes)
# --------------------------------------------------------------------------- #
_EMOTOR_FMT = "<bbi"


class EMotor(NamedTuple):
    # ``index`` shadows tuple.index(); the name matches the protocol field.
    index: int  # type: ignore[assignment]
    is_enabled: int
    speed: int


def pack_EMotor(index: int, is_enabled: int, speed: int) -> bytes:
    """Pack an extended-motor command (motor index, enable flag, speed)."""
    return struct.pack(_EMOTOR_FMT, index, is_enabled, speed)


def unpack_EMotor(data: bytes) -> EMotor:
    return EMotor(*struct.unpack(_EMOTOR_FMT, data))


# --------------------------------------------------------------------------- #
# EMotorS  ->  <bbiI  (10 bytes)
# --------------------------------------------------------------------------- #
_EMOTORS_FMT = "<bbiI"


class EMotorS(NamedTuple):
    # ``index`` shadows tuple.index(); the name matches the protocol field.
    index: int  # type: ignore[assignment]
    is_enabled: int
    speed: int
    distance: int


def pack_EMotorS(index: int, is_enabled: int, speed: int, distance: int) -> bytes:
    """Pack a stepped extended-motor command (index, enable, speed, distance)."""
    return struct.pack(_EMOTORS_FMT, index, is_enabled, speed, distance)


def unpack_EMotorS(data: bytes) -> EMotorS:
    return EMotorS(*struct.unpack(_EMOTORS_FMT, data))


# --------------------------------------------------------------------------- #
# WAITCmd  ->  <I  (4 bytes)
# --------------------------------------------------------------------------- #
_WAITCMD_FMT = "<I"


class WAITCmd(NamedTuple):
    wait_time: int


def pack_WAITCmd(wait_time: int) -> bytes:
    """Pack a queued wait command (wait duration, milliseconds)."""
    return struct.pack(_WAITCMD_FMT, int(wait_time))


def unpack_WAITCmd(data: bytes) -> WAITCmd:
    return WAITCmd(*struct.unpack(_WAITCMD_FMT, data))


# --------------------------------------------------------------------------- #
# TRIGCmd  ->  <bbbH  (5 bytes)
# --------------------------------------------------------------------------- #
_TRIGCMD_FMT = "<bbbH"


class TRIGCmd(NamedTuple):
    address: int
    mode: int
    condition: int
    threshold: int


def pack_TRIGCmd(address: int, mode: int, condition: int, threshold: int) -> bytes:
    """Pack a trigger command (pin address, mode, condition, threshold)."""
    return struct.pack(_TRIGCMD_FMT, address, mode, condition, threshold)


def unpack_TRIGCmd(data: bytes) -> TRIGCmd:
    return TRIGCmd(*struct.unpack(_TRIGCMD_FMT, data))
