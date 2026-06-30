"""System commands: queue control, alarms, speed ratio, lost-step, motor mode,
HHT trigger, angle-sensor / base-decoder calibration, WiFi, and firmware upgrade.

All methods follow the canonical low-level pattern (see :mod:`._base`): build a
frame with :meth:`_send` (``id`` from :class:`~dobotkit.arm.ids.ProtocolId`,
``rw``/``queued`` bits via ``make_ctrl``), then decode any GET response via the
:mod:`~dobotkit.arm.structures` (un)packers. Queued setters return the 64-bit
queue index via :meth:`_queued_index`.

GET/SET pairs share one ``ProtocolId`` and differ only by the ``rw`` control bit.
The queue passthroughs delegate to the shared :class:`~dobotkit.arm.queue.CommandQueue`
on ``self.queue`` so the SDK-coverage cross-check (Task 2.10) finds them here too.
"""
from __future__ import annotations

import struct
from typing import Optional, Tuple

from dobotkit.arm import structures as S
from dobotkit.arm.ids import ProtocolId
from dobotkit.arm.lowlevel._base import _LowLevelProtocol

# Backwards-compatible aliases: these previously held bare integer literals and
# are now thin references to the dedicated (still ``# unverified``) ProtocolId
# members. Kept so external imports (and the test helpers) resolve to the same
# id values.
_QUEUED_CMD_START_DOWNLOAD = ProtocolId.SET_QUEUED_CMD_START_DOWNLOAD
_QUEUED_CMD_STOP_DOWNLOAD = ProtocolId.SET_QUEUED_CMD_STOP_DOWNLOAD
_SET_LOST_STEP_ENABLE_AND_PARAMS = ProtocolId.SET_GET_LOST_STEP_ENABLE_AND_PARAMS
_UPGRADE_FW_READY = ProtocolId.SET_GET_UPGRADE_FW_READY


class SystemMixin(_LowLevelProtocol):
    """Queue / alarm / speed / lost-step / motor-mode / WiFi / firmware commands."""

    # ===================================================================== #
    # Queue control (thin passthroughs to the shared CommandQueue)
    # ===================================================================== #

    def queued_cmd_clear(self) -> None:
        """Empty the on-device command queue, discarding pending commands."""
        self.queue.clear()

    def queued_cmd_start_exec(self) -> None:
        """Begin executing queued commands in FIFO order."""
        self.queue.start()

    def queued_cmd_stop_exec(self) -> None:
        """Stop executing queued commands after the current one finishes."""
        self.queue.stop()

    def queued_cmd_force_stop_exec(self) -> None:
        """Immediately abort the running queue without waiting for completion."""
        self.queue.force_stop()

    def queued_cmd_start_download(self, total_loop: int, line_per_loop: int) -> None:
        """Enter offline download mode for ``total_loop`` loops of ``line_per_loop``.

        Uses ``ProtocolId.SET_QUEUED_CMD_START_DOWNLOAD`` (id 243, between
        FORCE_STOP_EXEC=242 and CLEAR=245; value still ``# unverified``).
        """
        self._send(
            ProtocolId.SET_QUEUED_CMD_START_DOWNLOAD,
            struct.pack("<II", total_loop, line_per_loop),
            rw=True,
        )

    def queued_cmd_stop_download(self) -> None:
        """Leave offline download mode (``ProtocolId.SET_QUEUED_CMD_STOP_DOWNLOAD``)."""
        self._send(ProtocolId.SET_QUEUED_CMD_STOP_DOWNLOAD, rw=True)

    def get_queued_cmd_current_index(self) -> int:
        """Return the index of the most recently executed queued command."""
        return self.queue.current_index()

    def get_queued_cmd_motion_finish(self) -> bool:
        """Return ``True`` when all queued motion commands have completed."""
        return self.queue.motion_finished()

    # ===================================================================== #
    # Alarms
    # ===================================================================== #

    def get_alarms_state(self) -> bytes:
        """Return the raw active-alarm bitmap.

        The SDK returns a variable-length byte buffer (one bit per alarm code);
        decode it with :func:`dobotkit.arm.alarms.decode_alarms`.
        """
        resp = self._send(ProtocolId.GET_ALARMS_STATE)
        return resp.params

    def clear_all_alarms_state(self) -> None:
        """Clear all active alarms."""
        self._send(ProtocolId.CLEAR_ALL_ALARMS_STATE, rw=True)

    # ===================================================================== #
    # Speed ratio
    # ===================================================================== #

    def set_arm_speed_ratio(
        self, params_mode: int, speed_ratio: int, *, queued: bool = False
    ) -> Optional[int]:
        """Set the global arm speed ratio (paramsMode selects velocity/acc set)."""
        resp = self._send(
            ProtocolId.SET_GET_ARM_SPEED_RATIO,
            struct.pack("<BB", params_mode, speed_ratio),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_arm_speed_ratio(self, params_mode: int = 0) -> int:
        """Return the arm speed ratio for ``params_mode``."""
        resp = self._send(
            ProtocolId.SET_GET_ARM_SPEED_RATIO, struct.pack("<B", params_mode)
        )
        return resp.params[0] if resp.params else 0

    def set_l_speed_ratio(
        self, params_mode: int, speed_ratio: int, *, queued: bool = False
    ) -> Optional[int]:
        """Set the linear-rail (L-axis) speed ratio."""
        resp = self._send(
            ProtocolId.SET_GET_L_SPEED_RATIO,
            struct.pack("<BB", params_mode, speed_ratio),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_l_speed_ratio(self, params_mode: int = 0) -> int:
        """Return the linear-rail (L-axis) speed ratio for ``params_mode``."""
        resp = self._send(
            ProtocolId.SET_GET_L_SPEED_RATIO, struct.pack("<B", params_mode)
        )
        return resp.params[0] if resp.params else 0

    # ===================================================================== #
    # Motor mode
    # ===================================================================== #

    def set_motor_mode(self, mode: int) -> None:
        """Set the stepper-motor control mode."""
        self._send(ProtocolId.SET_GET_MOTOR_MODE, struct.pack("<i", mode), rw=True)

    def get_motor_mode(self) -> int:
        """Return the current stepper-motor control mode."""
        resp = self._send(ProtocolId.SET_GET_MOTOR_MODE)
        (mode,) = struct.unpack("<i", resp.params[:4])
        return int(mode)

    # ===================================================================== #
    # Lost-step
    # ===================================================================== #

    def set_lost_step_params(
        self, threshold: float, *, queued: bool = False
    ) -> Optional[int]:
        """Set the lost-step detection threshold (degrees)."""
        resp = self._send(
            ProtocolId.SET_GET_LOST_STEP_PARAMS,
            struct.pack("<f", threshold),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def set_lost_step_cmd(self, *, queued: bool = False) -> Optional[int]:
        """Trigger a lost-step self-check."""
        resp = self._send(
            ProtocolId.SET_LOST_STEP_CMD, rw=True, queued=queued
        )
        return self._queued_index(resp) if queued else None

    def set_lost_step_enable_and_params(
        self, enable: bool, threshold: float, *, queued: bool = False
    ) -> Optional[int]:
        """Enable lost-step detection and set its threshold in one command.

        Uses ``ProtocolId.SET_GET_LOST_STEP_ENABLE_AND_PARAMS`` (id 177;
        distinct from the legacy 170/171, value still ``# unverified``).
        """
        resp = self._send(
            ProtocolId.SET_GET_LOST_STEP_ENABLE_AND_PARAMS,
            struct.pack("<Bf", 1 if enable else 0, threshold),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_lost_step_enable_and_params(self) -> Tuple[bool, float]:
        """Return ``(enabled, threshold)`` for lost-step detection."""
        resp = self._send(ProtocolId.SET_GET_LOST_STEP_ENABLE_AND_PARAMS)
        enable, threshold = struct.unpack("<Bf", resp.params[:5])
        return (bool(enable), float(threshold))

    # ===================================================================== #
    # Hand-hold teaching (HHT) trigger
    # ===================================================================== #

    def set_hht_trig_mode(self, mode: int) -> None:
        """Set the hand-hold-teaching trigger mode."""
        self._send(
            ProtocolId.SET_GET_HHTTRIG_MODE, struct.pack("<i", mode), rw=True
        )

    def get_hht_trig_mode(self) -> int:
        """Return the hand-hold-teaching trigger mode."""
        resp = self._send(ProtocolId.SET_GET_HHTTRIG_MODE)
        (mode,) = struct.unpack("<i", resp.params[:4])
        return int(mode)

    def set_hht_trig_output_enabled(self, enabled: bool) -> None:
        """Enable or disable HHT trigger output."""
        self._send(
            ProtocolId.SET_GET_HHTTRIG_OUTPUT_ENABLED,
            struct.pack("<?", bool(enabled)),
            rw=True,
        )

    def get_hht_trig_output_enabled(self) -> bool:
        """Return whether HHT trigger output is enabled."""
        resp = self._send(ProtocolId.SET_GET_HHTTRIG_OUTPUT_ENABLED)
        return bool(resp.params[0]) if resp.params else False

    def get_hht_trig_output(self) -> bool:
        """Return ``True`` when a HHT trigger pulse is currently available."""
        resp = self._send(ProtocolId.GET_HHTTRIG_OUTPUT)
        return bool(resp.params[0]) if resp.params else False

    # ===================================================================== #
    # Angle-sensor / base-decoder calibration
    # ===================================================================== #

    def set_angle_sensor_static_error(
        self, rear_arm_angle_error: float, front_arm_angle_error: float
    ) -> None:
        """Set the static error correction for the two arm angle sensors."""
        self._send(
            ProtocolId.SET_GET_ANGLE_SENSOR_STATIC_ERROR,
            struct.pack("<ff", rear_arm_angle_error, front_arm_angle_error),
            rw=True,
        )

    def get_angle_sensor_static_error(self) -> Tuple[float, float]:
        """Return ``(rear_arm_angle_error, front_arm_angle_error)``."""
        resp = self._send(ProtocolId.SET_GET_ANGLE_SENSOR_STATIC_ERROR)
        rear, front = struct.unpack("<ff", resp.params[:8])
        return (float(rear), float(front))

    def set_angle_sensor_coef(
        self, rear_arm_angle_coef: float, front_arm_angle_coef: float
    ) -> None:
        """Set the scale coefficients for the two arm angle sensors."""
        self._send(
            ProtocolId.SET_GET_ANGLE_SENSOR_COEF,
            struct.pack("<ff", rear_arm_angle_coef, front_arm_angle_coef),
            rw=True,
        )

    def get_angle_sensor_coef(self) -> Tuple[float, float]:
        """Return ``(rear_arm_angle_coef, front_arm_angle_coef)``."""
        resp = self._send(ProtocolId.SET_GET_ANGLE_SENSOR_COEF)
        rear, front = struct.unpack("<ff", resp.params[:8])
        return (float(rear), float(front))

    def set_base_decoder_static_error(self, base_decoder_error: float) -> None:
        """Set the static error correction for the base decoder."""
        self._send(
            ProtocolId.SET_GET_BASE_DECODER_STATIC_ERROR,
            struct.pack("<f", base_decoder_error),
            rw=True,
        )

    def get_base_decoder_static_error(self) -> float:
        """Return the base-decoder static error correction."""
        resp = self._send(ProtocolId.SET_GET_BASE_DECODER_STATIC_ERROR)
        (err,) = struct.unpack("<f", resp.params[:4])
        return float(err)

    # ===================================================================== #
    # WiFi
    # ===================================================================== #

    def set_wifi_config_mode(self, enable: bool) -> None:
        """Enter or leave WiFi configuration mode."""
        self._send(
            ProtocolId.SET_GET_WIFI_CONFIG_MODE,
            struct.pack("<?", bool(enable)),
            rw=True,
        )

    def get_wifi_config_mode(self) -> bool:
        """Return whether WiFi configuration mode is active."""
        resp = self._send(ProtocolId.SET_GET_WIFI_CONFIG_MODE)
        return bool(resp.params[0]) if resp.params else False

    def set_wifi_ssid(self, ssid: str) -> None:
        """Set the WiFi SSID to join."""
        self._send(
            ProtocolId.SET_GET_WIFI_SSID,
            ssid.encode("utf-8") + b"\x00",
            rw=True,
        )

    def get_wifi_ssid(self) -> str:
        """Return the configured WiFi SSID."""
        resp = self._send(ProtocolId.SET_GET_WIFI_SSID)
        return resp.params.split(b"\x00", 1)[0].decode("utf-8")

    def set_wifi_password(self, password: str) -> None:
        """Set the WiFi password."""
        self._send(
            ProtocolId.SET_GET_WIFI_PASSWORD,
            password.encode("utf-8") + b"\x00",
            rw=True,
        )

    def get_wifi_password(self) -> str:
        """Return the configured WiFi password."""
        resp = self._send(ProtocolId.SET_GET_WIFI_PASSWORD)
        return resp.params.split(b"\x00", 1)[0].decode("utf-8")

    def set_wifi_ip_address(
        self, dhcp: int, addr1: int, addr2: int, addr3: int, addr4: int
    ) -> None:
        """Set the WiFi IPv4 address (DHCP flag + 4 octets)."""
        self._send(
            ProtocolId.SET_GET_WIFI_IP_ADDRESS,
            S.pack_WIFIIPAddress(dhcp, addr1, addr2, addr3, addr4),
            rw=True,
        )

    def get_wifi_ip_address(self) -> S.WIFIIPAddress:
        """Return the configured WiFi IPv4 address."""
        resp = self._send(ProtocolId.SET_GET_WIFI_IP_ADDRESS)
        return S.unpack_WIFIIPAddress(resp.params)

    def set_wifi_netmask(self, addr1: int, addr2: int, addr3: int, addr4: int) -> None:
        """Set the WiFi netmask (4 octets)."""
        self._send(
            ProtocolId.SET_GET_WIFI_NETMASK,
            S.pack_WIFINetmask(addr1, addr2, addr3, addr4),
            rw=True,
        )

    def get_wifi_netmask(self) -> S.WIFINetmask:
        """Return the configured WiFi netmask."""
        resp = self._send(ProtocolId.SET_GET_WIFI_NETMASK)
        return S.unpack_WIFINetmask(resp.params)

    def set_wifi_gateway(self, addr1: int, addr2: int, addr3: int, addr4: int) -> None:
        """Set the WiFi gateway address (4 octets)."""
        self._send(
            ProtocolId.SET_GET_WIFI_GATEWAY,
            S.pack_WIFIGateway(addr1, addr2, addr3, addr4),
            rw=True,
        )

    def get_wifi_gateway(self) -> S.WIFIGateway:
        """Return the configured WiFi gateway address."""
        resp = self._send(ProtocolId.SET_GET_WIFI_GATEWAY)
        return S.unpack_WIFIGateway(resp.params)

    def set_wifi_dns(self, addr1: int, addr2: int, addr3: int, addr4: int) -> None:
        """Set the WiFi DNS server address (4 octets)."""
        self._send(
            ProtocolId.SET_GET_WIFI_DNS,
            S.pack_WIFIDNS(addr1, addr2, addr3, addr4),
            rw=True,
        )

    def get_wifi_dns(self) -> S.WIFIDNS:
        """Return the configured WiFi DNS server address."""
        resp = self._send(ProtocolId.SET_GET_WIFI_DNS)
        return S.unpack_WIFIDNS(resp.params)

    def get_wifi_connect_status(self) -> bool:
        """Return ``True`` when the arm is connected to a WiFi network."""
        resp = self._send(ProtocolId.GET_WIFI_CONNECT_STATUS)
        return bool(resp.params[0]) if resp.params else False

    # ===================================================================== #
    # Firmware upgrade
    # ===================================================================== #

    def set_upgrade_fw_ready(self, fw_size: int, md5: str) -> None:
        """Announce a pending firmware upgrade (size + hex MD5 digest).

        Uses ``ProtocolId.SET_GET_UPGRADE_FW_READY`` (id 250; value still
        ``# unverified``).
        """
        self._send(
            ProtocolId.SET_GET_UPGRADE_FW_READY,
            S.pack_UpgradeFWReadyCmd(fw_size, bytes.fromhex(md5)),
            rw=True,
        )

    def get_upgrade_fw_ready(self, fw_size: int, md5: str) -> bool:
        """Query whether the device is ready to receive the firmware upgrade."""
        resp = self._send(
            ProtocolId.SET_GET_UPGRADE_FW_READY,
            S.pack_UpgradeFWReadyCmd(fw_size, bytes.fromhex(md5)),
        )
        return bool(resp.params[0]) if resp.params else False
