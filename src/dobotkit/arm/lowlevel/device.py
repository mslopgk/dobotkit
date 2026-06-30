"""Device / connection commands (Task 2.1).

These wrap the SDK's device-identity and connection-management functions:
serial number, device name, firmware/hardware version, device id, uptime, and
the MagicBox / linear-rail toggles. They build on the ``_send`` /
``_queued_index`` primitives provided by :class:`._base._LowLevelBase` and decode
GET responses through :mod:`dobotkit.arm.structures`.

The canonical call pattern (shared by every category mixin)::

    resp = self._send(ProtocolId.X, params, rw=?, queued=queued)
    return S.unpack_Y(resp.params)        # GET
    return self._queued_index(resp)        # queued SET

A few SDK functions here (``RestartMagicBox``, ``SetDeviceWithL`` /
``GetDeviceWithL``, ``GetUART4PeripheralsType``) now have their own dedicated
``ProtocolId`` members (``RESTART_MAGIC_BOX``, ``SET_GET_DEVICE_WITH_L``,
``GET_UART4_PERIPHERALS_TYPE``); those id values remain ``# unverified`` pending
hardware/official-doc confirmation. String fields are NUL-terminated UTF-8 on
the wire.
"""
from __future__ import annotations

import struct
from typing import Optional

from dobotkit.arm import structures as S
from dobotkit.arm.ids import ProtocolId
from dobotkit.arm.lowlevel._base import _LowLevelProtocol


def _decode_cstr(data: bytes) -> str:
    """Decode a NUL-terminated UTF-8 byte string (ignoring trailing padding)."""
    return data.split(b"\x00", 1)[0].decode("utf-8", errors="replace")


def _encode_cstr(text: str) -> bytes:
    """Encode ``text`` to NUL-terminated UTF-8 wire bytes."""
    return text.encode("utf-8") + b"\x00"


class DeviceMixin(_LowLevelProtocol):
    """Device-identity and connection-management commands."""

    # -- serial number -----------------------------------------------------

    def get_device_sn(self) -> str:
        """Read the device serial number (UTF-8 string)."""
        resp = self._send(ProtocolId.GET_SET_DEVICE_SN)
        return _decode_cstr(resp.params)

    def set_device_sn(self, sn: str) -> None:
        """Write the device serial number."""
        self._send(ProtocolId.GET_SET_DEVICE_SN, _encode_cstr(sn), rw=True)

    # -- device name -------------------------------------------------------

    def set_device_name(self, name: str) -> None:
        """Write the device's human-readable name."""
        self._send(ProtocolId.GET_SET_DEVICE_NAME, _encode_cstr(name), rw=True)

    def set_device_num_name(self, num: int) -> None:
        """Write the device name as a numeric id.

        The SDK's ``SetDeviceNumName`` reuses the ``SetDeviceName`` DLL entry but
        sends a raw ``c_int`` instead of a UTF-8 string; this mirrors that by
        writing the little-endian 32-bit integer to the same protocol id.
        """
        self._send(ProtocolId.GET_SET_DEVICE_NAME, struct.pack("<i", num), rw=True)

    def get_device_name(self) -> str:
        """Read the device's human-readable name (UTF-8 string)."""
        resp = self._send(ProtocolId.GET_SET_DEVICE_NAME)
        return _decode_cstr(resp.params)

    # -- version / id ------------------------------------------------------

    def get_device_version(self) -> S.DeviceVersion:
        """Read firmware + hardware version (eight bytes)."""
        resp = self._send(ProtocolId.GET_DEVICE_VERSION)
        return S.unpack_DeviceVersion(resp.params)

    def get_device_version_ex(self) -> S.DeviceVersion:
        """Read the controller-box version (``GetDeviceVersionEx``).

        In the SDK this targets the controller box rather than the arm and may
        return two devices' versions; here it reuses the version protocol id and
        decodes a single :class:`~dobotkit.arm.structures.DeviceVersion`.
        """
        resp = self._send(ProtocolId.GET_DEVICE_VERSION)
        return S.unpack_DeviceVersion(resp.params[:8])

    def get_device_id(self) -> S.DeviceID:
        """Read the three 32-bit device-identity words."""
        resp = self._send(ProtocolId.GET_DEVICE_ID)
        return S.unpack_DeviceID(resp.params)

    def get_device_time(self) -> int:
        """Read the device uptime counter (``c_uint32``)."""
        resp = self._send(ProtocolId.GET_DEVICE_TIME)
        return int(struct.unpack("<I", resp.params[:4])[0])

    def get_device_info(self) -> S.DeviceCountInfo:
        """Read cumulative run-time / power-on / power-off counters."""
        resp = self._send(ProtocolId.GET_DEVICE_INFO)
        return S.unpack_DeviceCountInfo(resp.params)

    # -- MagicBox / linear-rail / peripherals ------------------------------

    def restart_magic_box(self) -> None:
        """Restart the MagicBox controller.

        NOTE: uses the dedicated ``ProtocolId.RESTART_MAGIC_BOX`` member; its id
        value is still ``# unverified`` pending hardware confirmation. The frame
        is sent with the write bit set.
        """
        self._send(ProtocolId.RESTART_MAGIC_BOX, rw=True)

    def set_cmd_timeout(self, timeout_ms: int) -> None:
        """Set the per-command response timeout, in milliseconds.

        ``SetCmdTimeout`` is a local (non-wire) setting in the SDK; here it
        adjusts the transport's read timeout (seconds) accordingly.
        """
        self.transport.timeout = timeout_ms / 1000.0

    def set_device_with_l(
        self,
        is_with_l: bool,
        version: int = 0,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Enable/disable the linear-rail ("with L") configuration.

        Wire payload is ``<?B`` (isWithL bool, version uint8). When ``queued``,
        returns the queued-command index.

        NOTE: uses the dedicated ``ProtocolId.SET_GET_DEVICE_WITH_L`` member; its
        id value is still ``# unverified`` pending hardware confirmation.
        """
        params = struct.pack("<?B", bool(is_with_l), version & 0xFF)
        resp = self._send(
            ProtocolId.SET_GET_DEVICE_WITH_L, params, rw=True, queued=queued
        )
        return self._queued_index(resp) if queued else None

    def get_device_with_l(self) -> bool:
        """Read whether the linear-rail ("with L") configuration is enabled.

        NOTE: uses the dedicated ``ProtocolId.SET_GET_DEVICE_WITH_L`` member; its
        id value is still ``# unverified`` pending hardware confirmation.
        """
        resp = self._send(ProtocolId.SET_GET_DEVICE_WITH_L)
        return bool(resp.params[0]) if resp.params else False

    def get_uart4_peripherals_type(self) -> int:
        """Read the type code of the peripheral attached to UART4 (``c_uint8``).

        NOTE: uses the dedicated ``ProtocolId.GET_UART4_PERIPHERALS_TYPE``
        member; its id value is still ``# unverified`` pending hardware
        confirmation.
        """
        resp = self._send(ProtocolId.GET_UART4_PERIPHERALS_TYPE)
        return resp.params[0] if resp.params else 0
