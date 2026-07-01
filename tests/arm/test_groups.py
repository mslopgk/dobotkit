"""Tests for the ergonomic device groups (Task 3.2).

``IOGroup`` / ``SensorGroup`` / ``EffectorGroup`` are thin facades over
:class:`~dobotkit.arm.lowlevel.LowLevelArm`. Each group method must delegate to
the correct low-level method with the correct arguments, and pass through the
low-level return value unchanged.

The low-level arm is a :class:`unittest.mock.MagicMock` (no hardware, no
serial): we assert ``ll.<method>.assert_called_once_with(...)`` and that the
group method returns the mock's return value.
"""
from unittest.mock import MagicMock, sentinel

import pytest

from dobotkit.arm.groups import EffectorGroup, IOGroup, SensorGroup


# --------------------------------------------------------------------------- #
# EffectorGroup
# --------------------------------------------------------------------------- #
def test_effector_suck_on_delegates_to_suction_cup():
    ll = MagicMock()
    ll.set_end_effector_suction_cup.return_value = sentinel.idx
    eff = EffectorGroup(ll)

    assert eff.suck(True) is sentinel.idx
    ll.set_end_effector_suction_cup.assert_called_once_with(
        enable_ctrl=True, on=True, queued=True
    )


def test_effector_suck_off_keeps_control_enabled():
    # Releasing must keep enable_ctrl True (control on, vacuum off), else the
    # cup floats; on=False is the release.
    ll = MagicMock()
    eff = EffectorGroup(ll)

    eff.suck(False)
    ll.set_end_effector_suction_cup.assert_called_once_with(
        enable_ctrl=True, on=False, queued=True
    )


def test_effector_suck_pump_off_disables_control():
    # enable=False cuts the air pump entirely (enable_ctrl=False).
    ll = MagicMock()
    eff = EffectorGroup(ll)

    eff.suck(False, enable=False)
    ll.set_end_effector_suction_cup.assert_called_once_with(
        enable_ctrl=False, on=False, queued=True
    )


def test_effector_grip_pump_off_disables_control():
    ll = MagicMock()
    eff = EffectorGroup(ll)

    eff.grip(False, enable=False)
    ll.set_end_effector_gripper.assert_called_once_with(
        enable_ctrl=False, on=False, queued=True
    )


def test_effector_suck_honours_queued_flag():
    ll = MagicMock()
    eff = EffectorGroup(ll)

    eff.suck(True, queued=False)
    ll.set_end_effector_suction_cup.assert_called_once_with(
        enable_ctrl=True, on=True, queued=False
    )


def test_effector_grip_delegates_to_gripper():
    ll = MagicMock()
    ll.set_end_effector_gripper.return_value = sentinel.idx
    eff = EffectorGroup(ll)

    assert eff.grip(True) is sentinel.idx
    ll.set_end_effector_gripper.assert_called_once_with(
        enable_ctrl=True, on=True, queued=True
    )


def test_effector_grip_open():
    ll = MagicMock()
    eff = EffectorGroup(ll)

    eff.grip(False)
    ll.set_end_effector_gripper.assert_called_once_with(
        enable_ctrl=True, on=False, queued=True
    )


def test_effector_laser_on_off():
    ll = MagicMock()
    eff = EffectorGroup(ll)

    eff.laser(True)
    ll.set_end_effector_laser.assert_called_once_with(
        enable_ctrl=True, on=True, queued=True
    )

    ll.reset_mock()
    eff.laser(False)
    ll.set_end_effector_laser.assert_called_once_with(
        enable_ctrl=True, on=False, queued=True
    )


def test_effector_set_type_delegates():
    ll = MagicMock()
    ll.set_end_effector_type.return_value = sentinel.idx
    eff = EffectorGroup(ll)

    assert eff.set_type(2) is sentinel.idx
    ll.set_end_effector_type.assert_called_once_with(2, queued=False)


def test_effector_get_type_delegates():
    ll = MagicMock()
    ll.get_end_effector_type.return_value = 1
    eff = EffectorGroup(ll)

    assert eff.get_type() == 1
    ll.get_end_effector_type.assert_called_once_with()


def test_effector_servo_set_get():
    ll = MagicMock()
    ll.set_servo_angle.return_value = sentinel.idx
    ll.get_servo_angle.return_value = 90.0
    eff = EffectorGroup(ll)

    assert eff.set_servo(1, 45.0) is sentinel.idx
    ll.set_servo_angle.assert_called_once_with(1, 45.0, queued=False)

    assert eff.get_servo(1) == 90.0
    ll.get_servo_angle.assert_called_once_with(1)


# --------------------------------------------------------------------------- #
# SensorGroup
# --------------------------------------------------------------------------- #
def test_sensor_seeed_distance_delegates():
    ll = MagicMock()
    ll.get_seeed_distance_sensor.return_value = sentinel.reading
    s = SensorGroup(ll)

    assert s.seeed_distance(2) is sentinel.reading
    ll.get_seeed_distance_sensor.assert_called_once_with(2)


def test_sensor_seeed_color_set_and_read():
    ll = MagicMock()
    ll.get_seeed_color_sensor.return_value = sentinel.color
    s = SensorGroup(ll)

    assert s.seeed_color(1) is sentinel.color
    ll.set_seeed_color_sensor.assert_called_once_with(1)
    ll.get_seeed_color_sensor.assert_called_once_with()


def test_sensor_seeed_temp_set_and_read():
    ll = MagicMock()
    ll.get_seeed_temp_sensor.return_value = sentinel.temp
    s = SensorGroup(ll)

    assert s.seeed_temp(3) is sentinel.temp
    ll.set_seeed_temp_sensor.assert_called_once_with(3)
    ll.get_seeed_temp_sensor.assert_called_once_with()


def test_sensor_seeed_light_set_and_read():
    ll = MagicMock()
    ll.get_seeed_light_sensor.return_value = sentinel.light
    s = SensorGroup(ll)

    assert s.seeed_light(0) is sentinel.light
    ll.set_seeed_light_sensor.assert_called_once_with(0)
    ll.get_seeed_light_sensor.assert_called_once_with()


def test_sensor_seeed_rgb_delegates():
    ll = MagicMock()
    ll.set_seeed_rgb.return_value = sentinel.idx
    s = SensorGroup(ll)

    assert s.seeed_rgb(1, 255.0) is sentinel.idx
    ll.set_seeed_rgb.assert_called_once_with(1, 255.0)


def test_sensor_color_enable_and_read():
    ll = MagicMock()
    ll.get_color_sensor.return_value = sentinel.rgb
    s = SensorGroup(ll)

    assert s.color(0) is sentinel.rgb
    ll.set_color_sensor.assert_called_once_with(enable=1, port=0)
    ll.get_color_sensor.assert_called_once_with()


def test_sensor_infrared_enable_and_read():
    ll = MagicMock()
    ll.get_infrared_sensor.return_value = sentinel.ir
    s = SensorGroup(ll)

    assert s.infrared(1) is sentinel.ir
    ll.set_infrared_sensor.assert_called_once_with(enable=1, port=1)
    ll.get_infrared_sensor.assert_called_once_with(1)


# --------------------------------------------------------------------------- #
# IOGroup
# --------------------------------------------------------------------------- #
def test_io_set_do_delegates():
    ll = MagicMock()
    ll.set_io_do.return_value = sentinel.idx
    io = IOGroup(ll)

    assert io.set_do(5, 1) is sentinel.idx
    ll.set_io_do.assert_called_once_with(5, 1, queued=False)


def test_io_set_do_queued():
    ll = MagicMock()
    io = IOGroup(ll)

    io.set_do(5, 0, queued=True)
    ll.set_io_do.assert_called_once_with(5, 0, queued=True)


def test_io_get_do_returns_level():
    ll = MagicMock()
    ll.get_io_do.return_value = type("R", (), {"level": 1})()
    io = IOGroup(ll)

    assert io.get_do(5) == 1
    ll.get_io_do.assert_called_once_with(5)


def test_io_get_di_returns_level():
    ll = MagicMock()
    ll.get_io_di.return_value = type("R", (), {"level": 0})()
    io = IOGroup(ll)

    assert io.get_di(7) == 0
    ll.get_io_di.assert_called_once_with(7)


def test_io_get_adc_returns_value():
    ll = MagicMock()
    ll.get_io_adc.return_value = type("R", (), {"value": 2048})()
    io = IOGroup(ll)

    assert io.get_adc(3) == 2048
    ll.get_io_adc.assert_called_once_with(3)


def test_io_set_pwm_delegates():
    ll = MagicMock()
    ll.set_io_pwm.return_value = sentinel.idx
    io = IOGroup(ll)

    assert io.set_pwm(4, 1000.0, 50.0) is sentinel.idx
    ll.set_io_pwm.assert_called_once_with(4, 1000.0, 50.0, queued=False)


def test_io_set_pwm_queued():
    ll = MagicMock()
    io = IOGroup(ll)

    io.set_pwm(4, 1000.0, 50.0, queued=True)
    ll.set_io_pwm.assert_called_once_with(4, 1000.0, 50.0, queued=True)


def test_io_set_multiplexing_delegates():
    ll = MagicMock()
    io = IOGroup(ll)

    io.set_multiplexing(2, 1)
    ll.set_io_multiplexing.assert_called_once_with(2, 1, queued=False)


def test_io_get_multiplexing_delegates():
    ll = MagicMock()
    ll.get_io_multiplexing.return_value = sentinel.mux
    io = IOGroup(ll)

    assert io.get_multiplexing(2) is sentinel.mux
    ll.get_io_multiplexing.assert_called_once_with(2)


def test_io_e_motor_delegates():
    ll = MagicMock()
    ll.set_e_motor.return_value = sentinel.idx
    io = IOGroup(ll)

    assert io.set_motor(0, True, 1000) is sentinel.idx
    ll.set_e_motor.assert_called_once_with(0, 1, 1000, queued=False)


def test_io_e_motor_steps_delegates():
    ll = MagicMock()
    io = IOGroup(ll)

    io.set_motor_steps(1, False, 500, 2000, queued=True)
    ll.set_e_motors.assert_called_once_with(1, 0, 500, 2000, queued=True)


# --------------------------------------------------------------------------- #
# Construction / attribute wiring
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("group_cls", [IOGroup, SensorGroup, EffectorGroup])
def test_group_stores_lowlevel_reference(group_cls):
    ll = MagicMock()
    group = group_cls(ll)
    assert group.lowlevel is ll
