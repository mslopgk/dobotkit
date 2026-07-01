"""Dobot Communication Protocol command IDs.

``ProtocolId`` enumerates every command ID understood by the Dobot serial
protocol. Each :class:`Message` carries one of these in its ``id`` byte.

Verification status
-------------------
The values were originally reconstructed from a partial *pydobot* seed plus the
Dobot categorical numbering rule, with interpolated entries tagged
``# unverified``. They have since been cross-referenced against two genuinely
authoritative artifacts:

1. the official **Dobot ``ProtocolID.h``** (Shenzhen Yuejiang copyright,
   V1.2.0); and
2. the official **Dobot-Arm / DobotLink Magician-Lite ``cmd_id.h``**.

As of this pass **72 command values are verified** against those sources (tagged
``# verified``), and **16 were corrected** to match them (tagged
``# corrected``). The remaining members are DobotDll *function-name-only* calls
with no public protocol id in either header (and several collide with unrelated
Magician-Lite commands); they stay tagged ``# unverified`` pending hardware or
official-doc confirmation.

Known naming / structural discrepancies that could not be applied to ``ids.py``
alone without breaking shipping code are recorded in the code review notes for
this change (fabricated ``GET_DEVICE_ID`` / ``GET_DEVICE_INFO`` members,
``GET_AUTO_LEVELING`` folding into id 32, and ``GET_QUEUED_CMD_MOTION_FINISH``
whose id 247 is really ``QueuedCmdLeftSpace``).

Protocol-id constraint: the wire frame stores the command id in a single byte,
so every ``ProtocolId`` value must lie in ``range(0, 256)``. The uniqueness test
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
    GET_SET_DEVICE_SN = 0  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    GET_SET_DEVICE_NAME = 1  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    GET_DEVICE_VERSION = 2  # verified: official ProtocolID.h
    # corrected: official ProtocolID.h / DobotLink define ProtocolDeviceWithL =
    # DeviceInfoBase+3 = 3 (was 6, on the false premise id 3 was taken).
    SET_GET_DEVICE_WITH_L = 3  # corrected: official ProtocolID.h (DeviceWithL = 3)
    GET_DEVICE_TIME = 4  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    # unverified (FABRICATED): no GetDeviceID exists in the Dobot protocol; the
    # authoritative DeviceInfo block is only SN=0/Name=1/Version=2/WithL=3/Time=4.
    # Retained (parked at 6, the old DeviceWithL slot) only because shipping
    # device.py + tests reference it; has no real protocol id.
    GET_DEVICE_ID = 6  # unverified (fabricated; kept for back-compat only)
    RESTART_MAGIC_BOX = 7  # unverified
    # corrected: official ProtocolID.h ProtocolCheckUART4PeripheralsModel =
    # ChenckModelBase(180)+1 = 181 (was 8, which lies in the DeviceInfo range).
    GET_UART4_PERIPHERALS_TYPE = 181  # corrected: official ProtocolID.h (=181)
    # unverified (FABRICATED): no GetDeviceInfo=5 in official ProtocolID.h.
    # Retained (at its original 5) only because shipping device.py + tests
    # reference it; has no real protocol id.
    GET_DEVICE_INFO = 5  # unverified (fabricated; kept for back-compat only)

    # --- Real-time pose / kinematics (10-19) ---
    GET_POSE = 10  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    RESET_POSE = 11  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    GET_KINEMATICS = 12  # verified: official ProtocolID.h
    GET_POSE_L = 13  # verified: official ProtocolID.h
    # corrected: official ProtocolID.h ProtocolUserParams = TESTBase(220)+0 = 220
    # (was 14, an unused slot in the Pose range).
    GET_USER_PARAMS = 220  # corrected: official ProtocolID.h (TEST block = 220)

    # --- Alarm (20-29) ---
    GET_ALARMS_STATE = 20  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    CLEAR_ALL_ALARMS_STATE = 21  # verified: official ProtocolID.h

    # --- Homing (30-39) ---
    SET_GET_HOME_PARAMS = 30  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    SET_HOME_CMD = 31  # verified: official ProtocolID.h
    SET_AUTO_LEVELING = 32  # verified: official ProtocolID.h (single Set/Get at 32)
    # unverified: official headers have NO separate GET id 33 — AutoLeveling is a
    # single Set/Get sharing id 32 (in Magician-Lite 33 is HomeStatus, unrelated).
    # Retained at 33 only because shipping pose.py + tests reference it.
    GET_AUTO_LEVELING = 33  # unverified (phantom split; official folds into 32)

    # --- Hand-hold teaching trigger (40-49) ---
    SET_GET_HHTTRIG_MODE = 40  # verified: official ProtocolID.h
    SET_GET_HHTTRIG_OUTPUT_ENABLED = 41  # verified: official ProtocolID.h
    GET_HHTTRIG_OUTPUT = 42  # verified: official ProtocolID.h

    # --- Arm orientation (50-59) ---
    SET_GET_ARM_ORIENTATION = 50  # verified: official ProtocolID.h

    # --- End effector (60-69) ---
    SET_GET_END_EFFECTOR_PARAMS = 60  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    SET_GET_END_EFFECTOR_LASER = 61  # verified: official ProtocolID.h
    SET_GET_END_EFFECTOR_SUCTION_CUP = 62  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    SET_GET_END_EFFECTOR_GRIPPER = 63  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    SET_GET_END_EFFECTOR_TYPE = 64  # verified: official ProtocolID.h
    SET_GET_SERVO_ANGLE = 65  # verified: official ProtocolID.h

    # --- JOG (70-79) ---
    SET_GET_JOG_JOINT_PARAMS = 70  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    SET_GET_JOG_COORDINATE_PARAMS = 71  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    SET_GET_JOG_COMMON_PARAMS = 72  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    SET_JOG_CMD = 73  # verified: official ProtocolID.h
    SET_GET_JOG_L_PARAMS = 74  # verified: official ProtocolID.h

    # --- PTP (80-89) ---
    SET_GET_PTP_JOINT_PARAMS = 80  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    SET_GET_PTP_COORDINATE_PARAMS = 81  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    SET_GET_PTP_JUMP_PARAMS = 82  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    SET_GET_PTP_COMMON_PARAMS = 83  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    SET_PTP_CMD = 84  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    SET_GET_PTP_L_PARAMS = 85  # verified: official ProtocolID.h
    SET_PTP_WITH_L_CMD = 86  # verified: official ProtocolID.h
    SET_GET_PTP_JUMP2_PARAMS = 87  # verified: official ProtocolID.h
    SET_PTP_PO_CMD = 88  # verified: official ProtocolID.h
    SET_PTP_PO_WITH_L_CMD = 89  # verified: official ProtocolID.h

    # --- CP (90-99) ---
    # The 92-95 block was a rotation; corrected to the official layout
    # (both ProtocolID.h and Magician-Lite cmd_id.h): CPLE=92, CPRHold=93,
    # CPCommon=94, CP2=95.
    SET_GET_CP_PARAMS = 90  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    SET_CP_CMD = 91  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    SET_CP_LE_CMD = 92  # corrected: official headers (CPLECmd = CPBase+2 = 92)
    SET_GET_CPR_HOLD_ENABLE = 93  # corrected: official headers (CPRHoldEnable = CPBase+3 = 93)
    SET_GET_CP_COMMON_PARAMS = 94  # corrected: official headers (CPCommonParams = CPBase+4 = 94)
    SET_CP2_CMD = 95  # corrected: Magician-Lite cmd_id.h (CP2Cmd = CPBase+5 = 95)

    # --- ARC / Circle (100-109) ---
    SET_GET_ARC_PARAMS = 100  # verified: official ProtocolID.h
    SET_ARC_CMD = 101  # verified: official ProtocolID.h
    SET_CIRCLE_CMD = 102  # verified: official ProtocolID.h
    SET_GET_ARC_COMMON_PARAMS = 103  # verified: official ProtocolID.h

    # --- WAIT (110-119) ---
    SET_WAIT_CMD = 110  # verified: official ProtocolID.h + Magician-Lite cmd_id.h

    # --- TRIG (120-129) ---
    SET_TRIG_CMD = 120  # verified: official ProtocolID.h + Magician-Lite cmd_id.h

    # --- Calibration / angle sensor (140-143) ---
    # corrected: the invented 211-214 block is really the CAL block
    # (official ProtocolID.h): CALBase=140, AngleSensorStaticError=140,
    # AngleSensorCoef=141, BaseDecoderStaticError=142, LRHandCalibrateValue=143.
    # The redundant SET_GET_BASE_DECODER (was 175) and SET_GET_LR_HANDED_CONFIG
    # (was 176) duplicate members were deleted — they named the same commands as
    # 142 / 143 and would have collided once corrected.
    SET_GET_ANGLE_SENSOR_STATIC_ERROR = 140  # corrected: official ProtocolID.h (CALBase+0)
    SET_GET_ANGLE_SENSOR_COEF = 141  # corrected: official ProtocolID.h (CALBase+1)
    SET_GET_BASE_DECODER_STATIC_ERROR = 142  # corrected: official ProtocolID.h (CALBase+2)
    SET_GET_LR_HANDED_CALIB = 143  # corrected: official ProtocolID.h (CALBase+3)

    # --- IO / EMotor / sensors (130-139) ---
    SET_GET_IO_MULTIPLEXING = 130  # verified: official ProtocolID.h
    SET_GET_IO_DO = 131  # verified: official ProtocolID.h
    SET_GET_IO_PWM = 132  # verified: official ProtocolID.h
    GET_IO_DI = 133  # verified: official ProtocolID.h
    GET_IO_ADC = 134  # verified: official ProtocolID.h
    SET_EMOTOR = 135  # verified: official ProtocolID.h
    SET_EMOTOR_S = 136  # verified: official ProtocolID.h
    SET_GET_COLOR_SENSOR = 137  # verified: official ProtocolID.h
    SET_GET_IR_SWITCH = 138  # verified: official ProtocolID.h

    # --- WiFi (150-159) ---
    SET_GET_WIFI_CONFIG_MODE = 150  # verified: official ProtocolID.h
    SET_GET_WIFI_SSID = 151  # verified: official ProtocolID.h
    SET_GET_WIFI_PASSWORD = 152  # verified: official ProtocolID.h
    SET_GET_WIFI_IP_ADDRESS = 153  # verified: official ProtocolID.h
    SET_GET_WIFI_NETMASK = 154  # verified: official ProtocolID.h
    SET_GET_WIFI_GATEWAY = 155  # verified: official ProtocolID.h
    SET_GET_WIFI_DNS = 156  # verified: official ProtocolID.h
    GET_WIFI_CONNECT_STATUS = 157  # verified: official ProtocolID.h

    # --- Lost-step / motor mode / speed ratio (170-177) ---
    SET_GET_LOST_STEP_PARAMS = 170  # verified: official ProtocolID.h
    SET_LOST_STEP_CMD = 171  # verified: official ProtocolID.h
    SET_GET_MOTOR_MODE = 172  # unverified
    SET_GET_ARM_SPEED_RATIO = 173  # unverified
    SET_GET_L_SPEED_RATIO = 174  # unverified
    SET_GET_LOST_STEP_ENABLE_AND_PARAMS = 177  # unverified (combined enable+params; distinct from 170/171)

    # --- Seeed grove sensors (215-219) ---
    # Invented block: Grove/Seeed sensors are routed via generic I2C or the
    # legacy ColorSensor=137, not a dedicated 215-219 block. DLL-name-only calls
    # with no public numeric id; kept within the single-byte id range (0-255).
    SET_GET_SEEED_DISTANCE = 215  # unverified
    SET_GET_SEEED_COLOR = 216  # unverified
    SET_GET_SEEED_TEMP = 217  # unverified
    SET_GET_SEEED_LIGHT = 218  # unverified
    SET_SEEED_RGB = 219  # unverified

    # --- Queue control (240-249) ---
    SET_QUEUED_CMD_START_EXEC = 240  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    SET_QUEUED_CMD_STOP_EXEC = 241  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    SET_QUEUED_CMD_FORCE_STOP_EXEC = 242  # verified: official ProtocolID.h
    SET_QUEUED_CMD_START_DOWNLOAD = 243  # verified: official ProtocolID.h
    SET_QUEUED_CMD_STOP_DOWNLOAD = 244  # verified: official ProtocolID.h
    SET_QUEUED_CMD_CLEAR = 245  # verified: official ProtocolID.h + Magician-Lite cmd_id.h
    GET_QUEUED_CMD_CURRENT_INDEX = 246  # verified: official ProtocolID.h
    # verified value 247 (QueuedCmdBase+7) per both official headers. NAME NOTE:
    # id 247 is really ProtocolQueuedCmdLeftSpace (remaining queue space), not
    # "MotionFinish". Kept under the current name because shipping queue.py's
    # motion_finished() + tests reference it; see review notes for the rename.
    GET_QUEUED_CMD_MOTION_FINISH = 247  # verified (value); name is QueuedCmdLeftSpace

    # --- Firmware upgrade (250-259) ---
    SET_GET_UPGRADE_FW_READY = 250  # unverified (firmware-upgrade-ready handshake)
