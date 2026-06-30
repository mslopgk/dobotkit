"""All enumerations used across dobotkit."""
from __future__ import annotations
from enum import IntEnum


class PTPMode(IntEnum):
    JUMP_XYZ = 0
    MOVJ_XYZ = 1
    MOVL_XYZ = 2
    JUMP_ANGLE = 3
    MOVJ_ANGLE = 4
    MOVL_ANGLE = 5
    MOVJ_ANGLE_INC = 6
    MOVL_XYZ_INC = 7
    MOVJ_XYZ_INC = 8
    JUMP_MOVL_XYZ = 9


class JOGMode(IntEnum):
    """SetJOGCmd `cmd` values. 0 = idle/stop; 1..8 = axis +/-; 9..10 = L-axis +/-."""
    IDLE = 0
    AP_DOWN = 1
    AN_DOWN = 2
    BP_DOWN = 3
    BN_DOWN = 4
    CP_DOWN = 5
    CN_DOWN = 6
    DP_DOWN = 7
    DN_DOWN = 8
    LP_DOWN = 9
    LN_DOWN = 10


class ContinuousPathMode(IntEnum):
    RELATIVE = 0
    ABSOLUTE = 1


class GPIOType(IntEnum):
    DUMMY = 0
    DO = 1
    PWM = 2
    DI = 3
    ADC = 4
    DIPU = 5
    DIPD = 6


class EndEffectorType(IntEnum):
    NONE = 0
    SUCTION_CUP = 1
    GRIPPER = 2
    LASER = 3


class ColorPort(IntEnum):
    GP1 = 0
    GP2 = 1
    GP4 = 2
    GP5 = 3


class LEDChannel(IntEnum):
    """GO RGB LED channel; SetLightRGB `number`."""
    LED_1 = 1
    LED_2 = 2
    LED_3 = 3
    LED_4 = 4
    LED_ALL = 5
