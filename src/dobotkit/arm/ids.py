"""Dobot Communication Protocol command IDs.

``ProtocolId`` enumerates every command ID understood by the Dobot serial
protocol. Each :class:`Message` carries one of these in its ``id`` byte.

Reconstruction sources (per the design spec / implementation plan):

1. ``pydobot/enums/CommunicationProtocolIDs.py`` — a partial set of
   independently *verified* values. These are authoritative and untagged.
2. The official Dobot Communication Protocol categorical numbering, which
   assigns IDs in contiguous blocks per functional category
   (device 0-9, pose 10-19, alarm 20-29, home 30-39, HHT 40-49,
   arm-orientation 50-59, end-effector 60-69, JOG 70-79, PTP 80-89,
   CP 90-99, ARC 100-109, WAIT/TRIG 110-129, IO 130-139, EMotor 135-136,
   sensors 137-139 / 211-214, WiFi 150-159, lost-step 170-172,
   speed-ratio 173-176, queue control 240-249).

Values interpolated from the categorical numbering rule (i.e. not present in
the verified pydobot seed) are tagged with a trailing ``# unverified``
comment so that hardware testing can later confirm them. The uniqueness test
(:mod:`tests.arm.test_ids`) guards against accidental collisions.

The ``_ext`` / ``_extEx`` SDK variants reuse the **same** ID as their base
command (they differ only by routing to the MagicBox slave -1, encoded
elsewhere in the frame), so they get no separate enum members here.
"""
from __future__ import annotations

from enum import IntEnum


class ProtocolId(IntEnum):
    """Numeric command IDs for the Dobot serial communication protocol."""

    # --- Device information (0-9) ---
    GET_SET_DEVICE_SN = 0
    GET_SET_DEVICE_NAME = 1
    GET_DEVICE_VERSION = 2  # unverified
    GET_DEVICE_ID = 3  # unverified
    GET_DEVICE_TIME = 4  # unverified
    GET_DEVICE_INFO = 5  # unverified

    # --- Real-time pose / kinematics (10-19) ---
    GET_POSE = 10
    RESET_POSE = 11
    GET_KINEMATICS = 12  # unverified
    GET_POSE_L = 13  # unverified

    # --- Alarm (20-29) ---
    GET_ALARMS_STATE = 20
    CLEAR_ALL_ALARMS_STATE = 21

    # --- Homing (30-39) ---
    SET_GET_HOME_PARAMS = 30
    SET_HOME_CMD = 31
    SET_AUTO_LEVELING = 32  # unverified
    GET_AUTO_LEVELING = 33  # unverified

    # --- Hand-hold teaching trigger (40-49) ---
    SET_GET_HHTTRIG_MODE = 40
    SET_GET_HHTTRIG_OUTPUT_ENABLED = 41
    GET_HHTTRIG_OUTPUT = 42

    # --- Arm orientation (50-59) ---
    SET_GET_ARM_ORIENTATION = 50

    # --- End effector (60-69) ---
    SET_GET_END_EFFECTOR_PARAMS = 60
    SET_GET_END_EFFECTOR_LASER = 61
    SET_GET_END_EFFECTOR_SUCTION_CUP = 62
    SET_GET_END_EFFECTOR_GRIPPER = 63
    SET_GET_END_EFFECTOR_TYPE = 64  # unverified
    SET_GET_SERVO_ANGLE = 65  # unverified

    # --- JOG (70-79) ---
    SET_GET_JOG_JOINT_PARAMS = 70
    SET_GET_JOG_COORDINATE_PARAMS = 71
    SET_GET_JOG_COMMON_PARAMS = 72
    SET_JOG_CMD = 73
    SET_GET_JOG_L_PARAMS = 74  # unverified

    # --- PTP (80-89) ---
    SET_GET_PTP_JOINT_PARAMS = 80
    SET_GET_PTP_COORDINATE_PARAMS = 81
    SET_GET_PTP_JUMP_PARAMS = 82
    SET_GET_PTP_COMMON_PARAMS = 83
    SET_PTP_CMD = 84
    SET_GET_PTP_L_PARAMS = 85
    SET_PTP_WITH_L_CMD = 86
    SET_GET_PTP_JUMP2_PARAMS = 87  # unverified
    SET_PTP_PO_CMD = 88  # unverified
    SET_PTP_PO_WITH_L_CMD = 89  # unverified

    # --- CP (90-99) ---
    SET_GET_CP_PARAMS = 90
    SET_CP_CMD = 91
    SET_CP2_CMD = 92  # unverified
    SET_GET_CP_COMMON_PARAMS = 93  # unverified
    SET_CP_LE_CMD = 94  # unverified

    # --- ARC / Circle (100-109) ---
    SET_GET_ARC_PARAMS = 100
    SET_ARC_CMD = 101
    SET_CIRCLE_CMD = 102  # unverified
    SET_GET_ARC_COMMON_PARAMS = 103  # unverified

    # --- WAIT (110-119) ---
    SET_WAIT_CMD = 110

    # --- TRIG (120-129) ---
    SET_TRIG_CMD = 120

    # --- IO / EMotor / sensors (130-139) ---
    SET_GET_IO_MULTIPLEXING = 130
    SET_GET_IO_DO = 131
    SET_GET_IO_PWM = 132
    GET_IO_DI = 133
    GET_IO_ADC = 134
    SET_EMOTOR = 135
    SET_EMOTOR_S = 136  # unverified
    SET_GET_COLOR_SENSOR = 137
    SET_GET_IR_SWITCH = 138

    # --- WiFi (150-159) ---
    SET_GET_WIFI_CONFIG_MODE = 150  # unverified
    SET_GET_WIFI_SSID = 151  # unverified
    SET_GET_WIFI_PASSWORD = 152  # unverified
    SET_GET_WIFI_IP_ADDRESS = 153  # unverified
    SET_GET_WIFI_NETMASK = 154  # unverified
    SET_GET_WIFI_GATEWAY = 155  # unverified
    SET_GET_WIFI_DNS = 156  # unverified
    GET_WIFI_CONNECT_STATUS = 157  # unverified

    # --- Lost-step / motor mode / speed ratio (170-176) ---
    SET_GET_LOST_STEP_PARAMS = 170  # unverified
    SET_LOST_STEP_CMD = 171  # unverified
    SET_GET_MOTOR_MODE = 172  # unverified
    SET_GET_ARM_SPEED_RATIO = 173  # unverified
    SET_GET_L_SPEED_RATIO = 174  # unverified
    SET_GET_BASE_DECODER = 175  # unverified
    SET_GET_LR_HANDED_CONFIG = 176  # unverified

    # --- Angle sensor / Seeed (211-214) ---
    SET_GET_ANGLE_SENSOR_STATIC_ERROR = 211  # unverified
    SET_GET_ANGLE_SENSOR_COEF = 212  # unverified
    SET_GET_BASE_DECODER_STATIC_ERROR = 213  # unverified
    SET_GET_LR_HANDED_CALIB = 214  # unverified

    # --- Queue control (240-249) ---
    SET_QUEUED_CMD_START_EXEC = 240
    SET_QUEUED_CMD_STOP_EXEC = 241
    SET_QUEUED_CMD_FORCE_STOP_EXEC = 242
    SET_QUEUED_CMD_CLEAR = 245
    GET_QUEUED_CMD_CURRENT_INDEX = 246
    GET_QUEUED_CMD_MOTION_FINISH = 247
