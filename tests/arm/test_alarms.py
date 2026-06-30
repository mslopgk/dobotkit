"""Tests for the alarm bitmap decode table (Task 3.1).

``GetAlarmsState`` returns a raw byte buffer that is a *bitmap*: bit ``n`` (LSB
of byte 0 is bit 0, LSB of byte 1 is bit 8, ...) set means alarm code ``n`` is
active. :func:`dobotkit.arm.alarms.decode_alarms` turns that bitmap into a list
of :class:`~dobotkit.arm.alarms.AlarmCode` values.
"""
from enum import IntEnum

from dobotkit.arm.alarms import AlarmCode, decode_alarms


# --------------------------------------------------------------------------- #
# AlarmCode enum
# --------------------------------------------------------------------------- #
def test_alarmcode_is_intenum():
    assert issubclass(AlarmCode, IntEnum)


def test_alarmcode_known_values():
    # Common reset / public alarms occupy the low byte.
    assert AlarmCode.COMMON_RESET == 0x00
    # The enum carries the documented group anchors.
    assert AlarmCode.PLANNING_INVERSE_KINEMATIC == 0x10
    assert AlarmCode.LIMIT_JOINT1_POSITIVE == 0x40


def test_alarmcode_values_unique():
    values = [m.value for m in AlarmCode]
    assert len(values) == len(set(values)), "duplicate alarm codes"


# --------------------------------------------------------------------------- #
# decode_alarms
# --------------------------------------------------------------------------- #
def test_decode_empty_bitmap_returns_empty_list():
    assert decode_alarms(b"") == []
    assert decode_alarms(b"\x00\x00\x00\x00") == []


def test_decode_bit_zero_set_yields_code_zero():
    # bit 0 of byte 0 set -> code 0x00 active.
    result = decode_alarms(b"\x01")
    assert AlarmCode.COMMON_RESET in result
    assert result == [AlarmCode.COMMON_RESET]


def test_decode_known_bitmap_each_set_bit_maps_to_its_code():
    # Build a bitmap with a chosen set of bit indices set, then confirm each
    # set bit n decodes to the code whose value is n, and nothing else appears.
    bit_indices = [0x00, 0x10, 0x40]
    bitmap = bytearray(16)
    for n in bit_indices:
        bitmap[n // 8] |= 1 << (n % 8)
    result = decode_alarms(bytes(bitmap))
    assert {int(c) for c in result} == set(bit_indices)
    # Order is ascending by bit index.
    assert [int(c) for c in result] == sorted(bit_indices)


def test_decode_high_byte_bit_indices():
    # bit 16 lives in byte 2 (0x10 group anchor at code 0x10 == bit 16).
    bitmap = bytes([0x00, 0x00, 0x01])  # only bit 16 set
    result = decode_alarms(bitmap)
    assert result == [AlarmCode.PLANNING_INVERSE_KINEMATIC]


def test_decode_all_defined_codes_roundtrip():
    # A bitmap with exactly the defined-code bits set decodes back to those
    # codes (proves every named code is reachable from its bit index).
    codes = list(AlarmCode)
    highest = max(int(c) for c in codes)
    bitmap = bytearray(highest // 8 + 1)
    for c in codes:
        bitmap[int(c) // 8] |= 1 << (int(c) % 8)
    result = decode_alarms(bytes(bitmap))
    assert set(result) == set(codes)


def test_decode_returns_alarmcode_instances():
    result = decode_alarms(b"\x01")
    assert all(isinstance(c, AlarmCode) for c in result)
