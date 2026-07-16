"""Tests for the DobotLink-era ergonomic groups (Task 6).

``EffectorGroup`` / ``SensorGroup`` / ``IOGroup`` are thin facades over
:class:`~dobotkit.arm.commands.ArmCommands`. Sensor reads are guarded: a
missing MagicBox/peripheral degrades to ``None`` + ``RuntimeWarning`` instead
of raising.
"""
import pytest

from tests.conftest import FakeClient
from dobotkit.arm.commands import ArmCommands
from dobotkit.arm.groups import EffectorGroup, IOGroup, SensorGroup
from dobotkit.exceptions import DobotProtocolError, DobotTimeoutError


def _cmds(**results):
    return ArmCommands(FakeClient(results=results), "COM8")


def test_suck_delegates():
    c = FakeClient(results={"Magician.SetEndEffectorSuctionCup": {"queuedCmdIndex": 1}})
    EffectorGroup(ArmCommands(c, "COM8")).suck(True)
    _, p = c.find_call("Magician.SetEndEffectorSuctionCup")
    assert p == {"portName": "COM8", "enableCtrl": True, "on": True, "isQueued": True}


def test_grip_delegates():
    c = FakeClient(results={"Magician.SetEndEffectorGripper": {"queuedCmdIndex": 2}})
    EffectorGroup(ArmCommands(c, "COM8")).grip(False, enable=False, queued=False)
    _, p = c.find_call("Magician.SetEndEffectorGripper")
    assert p == {"portName": "COM8", "enableCtrl": False, "on": False, "isQueued": False}


def test_servo_delegates():
    c = FakeClient(results={"Magician.SetServoAngle": {"queuedCmdIndex": 3}})
    EffectorGroup(ArmCommands(c, "COM8")).servo(1, 45.0)
    _, p = c.find_call("Magician.SetServoAngle")
    assert p == {"portName": "COM8", "index": 1, "value": 45.0, "isQueued": True}


def test_adc_sets_mux_then_reads_value():
    c = FakeClient(results={"Magician.GetIOADC": {"port": 0, "value": 3565},
                            "Magician.SetIOMultiplexing": True})
    assert SensorGroup(ArmCommands(c, "COM8")).adc(24) == 3565
    assert c.find_call("Magician.SetIOMultiplexing")[1]["multiplex"] == 4


def test_di_reads_level_with_single_call():
    c = FakeClient(results={"Magician.GetIODI": {"port": 25, "level": 1}})
    assert SensorGroup(ArmCommands(c, "COM8")).di(25) == 1
    assert c.methods_called().count("Magician.GetIODI") == 1


def test_color_enables_then_reads():
    c = FakeClient(results={"Magician.GetColorSensor": {"r": 1, "g": 2, "b": 3}})
    assert SensorGroup(ArmCommands(c, "COM8")).color(0) == {"r": 1, "g": 2, "b": 3}
    assert c.find_call("Magician.SetColorSensor") is not None


def test_infrared_enables_then_reads():
    c = FakeClient(results={"Magician.GetInfraredSensor": {"value": 7}})
    assert SensorGroup(ArmCommands(c, "COM8")).infrared(1) == {"value": 7}
    assert c.find_call("Magician.SetInfraredSensor") is not None


def test_distance_temp_light_delegate():
    c = FakeClient(results={
        "Magician.GetSeeedDistanceSensor": {"value": 10},
        "Magician.GetSeeedTempSensor": {"value": 20},
        "Magician.GetSeeedLightSensor": {"value": 30},
    })
    s = SensorGroup(ArmCommands(c, "COM8"))
    assert s.distance(0) == {"value": 10}
    assert s.temp(0) == {"value": 20}
    assert s.light(0) == {"value": 30}


def test_rgb_delegates():
    c = FakeClient(results={"Magician.SetSeeedRGBLED": True})
    assert SensorGroup(ArmCommands(c, "COM8")).rgb(0, 255.0) is True
    _, p = c.find_call("Magician.SetSeeedRGBLED")
    assert p["rgb"] == 255.0


def test_sensor_timeout_returns_none_and_warns():
    class Boom(FakeClient):
        def call(self, method, **p):
            raise DobotTimeoutError("no response")
    with pytest.warns(RuntimeWarning):
        assert SensorGroup(ArmCommands(Boom(), "COM8")).color(0) is None


def test_sensor_protocol_error_returns_none_and_warns():
    class Boom(FakeClient):
        def call(self, method, **p):
            raise DobotProtocolError("bad checksum")
    with pytest.warns(RuntimeWarning):
        assert SensorGroup(ArmCommands(Boom(), "COM8")).distance(0) is None


def test_io_set_do_delegates():
    c = FakeClient(results={"Magician.SetIODO": {"queuedCmdIndex": 4}})
    IOGroup(ArmCommands(c, "COM8")).set_do(5, 1)
    _, p = c.find_call("Magician.SetIODO")
    assert p["address"] == 5 and p["level"] == 1


def test_io_get_di_delegates():
    c = FakeClient(results={"Magician.GetIODI": {"port": 7, "level": 0}})
    assert IOGroup(ArmCommands(c, "COM8")).get_di(7) == 0


def test_io_get_adc_delegates():
    c = FakeClient(results={"Magician.GetIOADC": {"port": 3, "value": 2048}})
    assert IOGroup(ArmCommands(c, "COM8")).get_adc(3) == 2048


def test_io_set_pwm_delegates():
    c = FakeClient(results={"Magician.SetIOPWM": {"queuedCmdIndex": 6}})
    IOGroup(ArmCommands(c, "COM8")).set_pwm(4, 1000.0, 50.0)
    _, p = c.find_call("Magician.SetIOPWM")
    assert p["frequency"] == 1000.0 and p["dutyCycle"] == 50.0


def test_io_set_multiplexing_delegates():
    c = FakeClient(results={"Magician.SetIOMultiplexing": True})
    IOGroup(ArmCommands(c, "COM8")).set_multiplexing(2, 1)
    _, p = c.find_call("Magician.SetIOMultiplexing")
    assert p["multiplex"] == 1


def test_io_peripheral_timeout_returns_none_and_warns():
    class Boom(FakeClient):
        def call(self, method, **p):
            raise DobotTimeoutError("no response")
    with pytest.warns(RuntimeWarning):
        assert IOGroup(ArmCommands(Boom(), "COM8")).get_adc(0) is None
