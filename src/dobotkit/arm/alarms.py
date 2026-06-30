"""Dobot arm alarm bitmap decoding (Task 3.1).

The arm reports active faults through ``GetAlarmsState`` (``ProtocolId.GET_ALARMS_STATE``),
which returns a raw byte *bitmap* buffer. Each **bit index** in that buffer maps
directly to an alarm-code value: bit 0 is the least-significant bit of byte 0,
bit 8 is the LSB of byte 1, bit ``n`` lives at ``byte n // 8, bit n % 8``. A set
bit ``n`` means the alarm whose code value equals ``n`` is active.

:class:`AlarmCode` enumerates the documented codes from the Dobot Communication
Protocol alarm specification. The codes are grouped by their high nibble:

* ``0x00``-``0x0F`` -- common / public faults (reset, real-time, etc.)
* ``0x10``-``0x1F`` -- planning faults (inverse kinematics, data convert, ...)
* ``0x20``-``0x2F`` -- kinematics faults (inverse resolve / calculation)
* ``0x30``-``0x3F`` -- lost-step faults
* ``0x40``-``0x4F`` -- limit faults (per-joint positive / negative travel limits)

Exact values within each group vary across firmware revisions and the published
spec is incomplete, so individual members not anchored by the protocol document
are tagged ``# unverified``. :func:`decode_alarms` works regardless of which
names are defined: it maps each set bit index straight to ``AlarmCode(index)``
and falls back to a raw :class:`AlarmCode` pseudo-member for undocumented bits.
"""
from __future__ import annotations

from enum import IntEnum
from typing import List


class AlarmCode(IntEnum):
    """Documented Dobot arm alarm codes (bit index == code value).

    Values uncertain against the official Communication Protocol are tagged
    ``# unverified``. Undocumented set bits decode to dynamically created
    pseudo-members (see :func:`decode_alarms`) rather than raising.
    """

    # --- Common / public (0x00-0x0F) ------------------------------------- #
    COMMON_RESET = 0x00
    COMMON_UNDEFINED_INSTRUCTION = 0x01  # unverified
    COMMON_FILE_SYSTEM = 0x02  # unverified
    COMMON_COMMUNICATION = 0x03  # unverified
    COMMON_ANGLE_SENSOR_READ = 0x04  # unverified

    # --- Planning (0x10-0x1F) -------------------------------------------- #
    PLANNING_INVERSE_KINEMATIC = 0x10  # unverified
    PLANNING_INVERSE_LIMIT = 0x11  # unverified
    PLANNING_DATA_REPEAT = 0x12  # unverified
    PLANNING_DATA_CONVERT = 0x13  # unverified
    PLANNING_NUM_OVERFLOW = 0x14  # unverified
    PLANNING_FILE_SYSTEM = 0x15  # unverified

    # --- Kinematics (0x20-0x2F) ------------------------------------------ #
    KINEMATIC_INVERSE_CALC = 0x20  # unverified
    KINEMATIC_INVERSE_LIMIT = 0x21  # unverified
    KINEMATIC_FORWARD_LIMIT = 0x22  # unverified

    # --- Lost-step (0x30-0x3F) ------------------------------------------- #
    MOTOR_LOST_STEP = 0x30  # unverified

    # --- Limit faults (0x40-0x4F): per-joint travel limits --------------- #
    LIMIT_JOINT1_POSITIVE = 0x40  # unverified
    LIMIT_JOINT1_NEGATIVE = 0x41  # unverified
    LIMIT_JOINT2_POSITIVE = 0x42  # unverified
    LIMIT_JOINT2_NEGATIVE = 0x43  # unverified
    LIMIT_JOINT3_POSITIVE = 0x44  # unverified
    LIMIT_JOINT3_NEGATIVE = 0x45  # unverified
    LIMIT_JOINT4_POSITIVE = 0x46  # unverified
    LIMIT_JOINT4_NEGATIVE = 0x47  # unverified


def decode_alarms(bitmap: bytes) -> List[AlarmCode]:
    """Decode a raw alarm bitmap into the list of active :class:`AlarmCode`.

    Each set bit ``n`` (byte ``n // 8``, bit ``n % 8``) yields the alarm code
    whose value is ``n``. Codes are returned in ascending bit-index order. An
    empty or all-zero ``bitmap`` returns ``[]``.

    Bits that do not correspond to a named :class:`AlarmCode` member still
    decode -- ``AlarmCode(n)`` for an undocumented ``n`` creates an unnamed
    pseudo-member -- so a firmware reporting a code newer than this table never
    silently drops the fault.
    """
    active: List[AlarmCode] = []
    for byte_index, byte in enumerate(bitmap):
        if not byte:
            continue
        for bit in range(8):
            if byte & (1 << bit):
                active.append(AlarmCode(byte_index * 8 + bit))
    return active
