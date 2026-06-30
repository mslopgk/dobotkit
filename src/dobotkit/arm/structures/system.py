"""System / params / WIFI / firmware structures (Task 2.9).

Every wire payload mirrors a ``DobotDllType`` ``Structure``; the serial protocol
is **little-endian, packed (no alignment padding)**. Each ``unpack_*`` returns a
typed :class:`typing.NamedTuple`.

Structures defined here:

* ``AlarmsState`` -> ``<i`` (the oracle struct is a single ``c_int32``). Note the
  ``GetAlarmsState`` SDK call actually returns a raw alarm *bitmap* buffer rather
  than this 4-byte struct; this packer mirrors the declared ``Structure`` so the
  golden-oracle byte-match holds.
* ``WIFIIPAddress`` -> ``<5B`` (dhcp + 4 address octets).
* ``WIFINetmask`` / ``WIFIGateway`` / ``WIFIDNS`` -> ``<4B`` (4 address octets).
* ``UpgradeFWReadyCmd`` -> ``<I16s`` (firmware size + 16-byte MD5 digest). The
  oracle declares ``md5`` as a ``c_char_p`` *pointer*, so ``bytes(StructX(...))``
  contains only the 4-byte ``fwSize`` prefix followed by a pointer slot; the wire
  frame instead carries the raw 16-byte MD5 digest inline after ``fwSize``.

(``UserParams`` lives in the pose category per the task split.)
"""
from __future__ import annotations

import struct
from typing import NamedTuple

__all__ = [
    "AlarmsState",
    "pack_AlarmsState",
    "unpack_AlarmsState",
    "WIFIIPAddress",
    "pack_WIFIIPAddress",
    "unpack_WIFIIPAddress",
    "WIFINetmask",
    "pack_WIFINetmask",
    "unpack_WIFINetmask",
    "WIFIGateway",
    "pack_WIFIGateway",
    "unpack_WIFIGateway",
    "WIFIDNS",
    "pack_WIFIDNS",
    "unpack_WIFIDNS",
    "UpgradeFWReadyCmd",
    "pack_UpgradeFWReadyCmd",
    "unpack_UpgradeFWReadyCmd",
]


# --------------------------------------------------------------------------- #
# AlarmsState  ->  <i  (4 bytes)  (single c_int32 alarmsState)
# --------------------------------------------------------------------------- #
_ALARMSSTATE_FMT = "<i"


class AlarmsState(NamedTuple):
    alarms_state: int


def pack_AlarmsState(alarms_state: int) -> bytes:
    """Pack the (declared) single-int32 alarm-state struct."""
    return struct.pack(_ALARMSSTATE_FMT, alarms_state)


def unpack_AlarmsState(data: bytes) -> AlarmsState:
    return AlarmsState(*struct.unpack(_ALARMSSTATE_FMT, data[:4]))


# --------------------------------------------------------------------------- #
# WIFIIPAddress  ->  <5B  (5 bytes)  (dhcp, addr1..addr4)
# --------------------------------------------------------------------------- #
# The oracle declares the fields as signed ``c_byte``; packing the same octet
# values as unsigned ``B`` produces byte-identical output (e.g. 192 -> 0xc0)
# while accepting the natural 0-255 IP-octet range.
_WIFIIPADDRESS_FMT = "<5B"


class WIFIIPAddress(NamedTuple):
    dhcp: int
    addr1: int
    addr2: int
    addr3: int
    addr4: int


def pack_WIFIIPAddress(
    dhcp: int, addr1: int, addr2: int, addr3: int, addr4: int
) -> bytes:
    """Pack a WiFi IPv4 address config (DHCP flag + 4 octets)."""
    return struct.pack(_WIFIIPADDRESS_FMT, dhcp, addr1, addr2, addr3, addr4)


def unpack_WIFIIPAddress(data: bytes) -> WIFIIPAddress:
    return WIFIIPAddress(*struct.unpack(_WIFIIPADDRESS_FMT, data[:5]))


# --------------------------------------------------------------------------- #
# WIFINetmask  ->  <4B  (4 bytes)  (addr1..addr4)
# --------------------------------------------------------------------------- #
_WIFI4OCTET_FMT = "<4B"


class WIFINetmask(NamedTuple):
    addr1: int
    addr2: int
    addr3: int
    addr4: int


def pack_WIFINetmask(addr1: int, addr2: int, addr3: int, addr4: int) -> bytes:
    """Pack a WiFi netmask (4 octets)."""
    return struct.pack(_WIFI4OCTET_FMT, addr1, addr2, addr3, addr4)


def unpack_WIFINetmask(data: bytes) -> WIFINetmask:
    return WIFINetmask(*struct.unpack(_WIFI4OCTET_FMT, data[:4]))


# --------------------------------------------------------------------------- #
# WIFIGateway  ->  <4B  (4 bytes)  (addr1..addr4)
# --------------------------------------------------------------------------- #
class WIFIGateway(NamedTuple):
    addr1: int
    addr2: int
    addr3: int
    addr4: int


def pack_WIFIGateway(addr1: int, addr2: int, addr3: int, addr4: int) -> bytes:
    """Pack a WiFi gateway address (4 octets)."""
    return struct.pack(_WIFI4OCTET_FMT, addr1, addr2, addr3, addr4)


def unpack_WIFIGateway(data: bytes) -> WIFIGateway:
    return WIFIGateway(*struct.unpack(_WIFI4OCTET_FMT, data[:4]))


# --------------------------------------------------------------------------- #
# WIFIDNS  ->  <4B  (4 bytes)  (addr1..addr4)
# --------------------------------------------------------------------------- #
class WIFIDNS(NamedTuple):
    addr1: int
    addr2: int
    addr3: int
    addr4: int


def pack_WIFIDNS(addr1: int, addr2: int, addr3: int, addr4: int) -> bytes:
    """Pack a WiFi DNS server address (4 octets)."""
    return struct.pack(_WIFI4OCTET_FMT, addr1, addr2, addr3, addr4)


def unpack_WIFIDNS(data: bytes) -> WIFIDNS:
    return WIFIDNS(*struct.unpack(_WIFI4OCTET_FMT, data[:4]))


# --------------------------------------------------------------------------- #
# UpgradeFWReadyCmd  ->  <I16s  (20 bytes)  (fwSize + 16-byte MD5 digest)
# --------------------------------------------------------------------------- #
# The oracle declares ``md5`` as a ``c_char_p`` *pointer*; the on-wire frame
# instead carries the raw 16-byte MD5 digest inline after the uint32 ``fwSize``.
_UPGRADEFW_FMT = "<I16s"


class UpgradeFWReadyCmd(NamedTuple):
    fw_size: int
    md5: bytes


def pack_UpgradeFWReadyCmd(fw_size: int, md5: bytes = b"") -> bytes:
    """Pack a firmware-upgrade-ready command (fwSize + 16-byte MD5 digest).

    ``md5`` is the raw 16-byte digest (a 32-char hex string can be converted with
    ``bytes.fromhex``); it is right-padded / truncated to 16 bytes.
    """
    digest = bytes(md5)[:16].ljust(16, b"\x00")
    return struct.pack(_UPGRADEFW_FMT, fw_size, digest)


def unpack_UpgradeFWReadyCmd(data: bytes) -> UpgradeFWReadyCmd:
    fw_size, digest = struct.unpack(_UPGRADEFW_FMT, data[:20])
    return UpgradeFWReadyCmd(fw_size=fw_size, md5=digest)
