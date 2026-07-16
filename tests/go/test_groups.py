"""Tests for the GO's MagicBox peripheral facades (``GoSensorGroup`` / ``GoIOGroup``).

The GO reads its MagicBox on the DobotLink ``MagicBox.*`` namespace (verified on
hardware 2026-07-16) while staying connected via ``MagicianGO.ConnectDobot``.
Two addressing schemes, from the official apiBook:

* ADC / DI / DO / PWM -> raw **EIO pin 1..26** (test unit's pot = EIO 22).
* color / infrared / Seeed -> **Grove connector 1..6**.

Every sensor read is guarded: a missing MagicBox/peripheral degrades to ``None``
+ ``RuntimeWarning`` instead of raising.
"""
import pytest

from tests.conftest import FakeClient
from dobotkit.go.groups import GoIOGroup, GoSensorGroup
from dobotkit.exceptions import DobotProtocolError, DobotTimeoutError


def test_adc_sets_eio_mux_then_reads_value():
    c = FakeClient(results={"MagicBox.GetIOADC": {"port": 22, "value": 424},
                            "MagicBox.SetIOMultiplexing": {"multiplex": 4, "port": 22}})
    assert GoSensorGroup(c, "COM5").adc(22) == 424
    # mux set on the MagicBox namespace, ADC mode (4), addressed by EIO pin.
    _, p = c.find_call("MagicBox.SetIOMultiplexing")
    assert p == {"portName": "COM5", "port": 22, "multiplex": 4}
    _, pr = c.find_call("MagicBox.GetIOADC")
    assert pr == {"portName": "COM5", "port": 22}


def test_di_reads_level_single_call():
    c = FakeClient(results={"MagicBox.GetIODI": {"port": 22, "level": 1}})
    assert GoSensorGroup(c, "COM5").di(22) == 1
    assert c.methods_called().count("MagicBox.GetIODI") == 1
    _, p = c.find_call("MagicBox.GetIODI")
    assert p == {"portName": "COM5", "port": 22}


def test_color_enables_then_reads():
    c = FakeClient(results={"MagicBox.GetColorSensor": {"red": 1, "green": 0, "blue": 0},
                            "MagicBox.SetColorSensor": True})
    assert GoSensorGroup(c, "COM5").color(1) == {"red": 1, "green": 0, "blue": 0}
    _, p = c.find_call("MagicBox.SetColorSensor")
    assert p == {"portName": "COM5", "enable": 1, "colorPort": 1, "version": 1}


def test_infrared_enables_then_reads_with_infraredport():
    c = FakeClient(results={"MagicBox.GetInfraredSensor": {"status": 1},
                            "MagicBox.SetInfraredSensor": True})
    assert GoSensorGroup(c, "COM5").infrared(1) == {"status": 1}
    _, ps = c.find_call("MagicBox.SetInfraredSensor")
    assert ps == {"portName": "COM5", "enable": 1, "infraredPort": 1, "version": 1}
    _, pg = c.find_call("MagicBox.GetInfraredSensor")
    assert pg == {"portName": "COM5", "infraredPort": 1}


def test_seeed_distance_temp_light_use_grove_port():
    c = FakeClient(results={
        "MagicBox.GetSeeedDistanceSensor": {"value": 10},
        "MagicBox.GetSeeedTempSensor": {"value": 20},
        "MagicBox.GetSeeedLightSensor": {"value": 30},
    })
    s = GoSensorGroup(c, "COM5")
    assert s.distance(1) == {"value": 10}
    assert s.temp(1) == {"value": 20}
    assert s.light(1) == {"value": 30}
    _, p = c.find_call("MagicBox.GetSeeedLightSensor")
    assert p == {"portName": "COM5", "port": 1}


def test_seeed_rgb_sets_grove_port_and_value():
    c = FakeClient(results={"MagicBox.SetSeeedRGBLed": True})
    assert GoSensorGroup(c, "COM5").rgb(1, 255.0) is True
    _, p = c.find_call("MagicBox.SetSeeedRGBLed")
    assert p == {"portName": "COM5", "port": 1, "rgb": 255.0}


def test_sensor_timeout_returns_none_and_warns():
    class Boom(FakeClient):
        def call(self, method, **p):
            raise DobotTimeoutError("no response")
    with pytest.warns(RuntimeWarning):
        assert GoSensorGroup(Boom(), "COM5").light(1) is None


def test_sensor_protocol_error_returns_none_and_warns():
    class Boom(FakeClient):
        def call(self, method, **p):
            raise DobotProtocolError("bad checksum")
    with pytest.warns(RuntimeWarning):
        assert GoSensorGroup(Boom(), "COM5").color(1) is None


def test_io_set_do_uses_port_and_level():
    c = FakeClient(results={"MagicBox.SetIODO": {"level": 1, "port": 17}})
    GoIOGroup(c, "COM5").set_do(17, 1)
    _, p = c.find_call("MagicBox.SetIODO")
    assert p == {"portName": "COM5", "port": 17, "level": 1}


def test_io_get_di_reads_level():
    c = FakeClient(results={"MagicBox.GetIODI": {"port": 22, "level": 0}})
    assert GoIOGroup(c, "COM5").get_di(22) == 0


def test_io_get_adc_reads_value():
    c = FakeClient(results={"MagicBox.GetIOADC": {"port": 22, "value": 2048}})
    assert GoIOGroup(c, "COM5").get_adc(22) == 2048


def test_io_set_pwm_uses_dutycycle_wire_name():
    c = FakeClient(results={"MagicBox.SetIOPWM": {"dutyCycle": 50, "frequency": 1000, "port": 17}})
    GoIOGroup(c, "COM5").set_pwm(17, 1000.0, 50.0)
    _, p = c.find_call("MagicBox.SetIOPWM")
    assert p == {"portName": "COM5", "port": 17, "frequency": 1000.0, "dutyCycle": 50.0}


def test_io_set_multiplexing_uses_port():
    c = FakeClient(results={"MagicBox.SetIOMultiplexing": True})
    GoIOGroup(c, "COM5").set_multiplexing(22, 4)
    _, p = c.find_call("MagicBox.SetIOMultiplexing")
    assert p == {"portName": "COM5", "port": 22, "multiplex": 4}


def test_io_peripheral_timeout_returns_none_and_warns():
    class Boom(FakeClient):
        def call(self, method, **p):
            raise DobotTimeoutError("no response")
    with pytest.warns(RuntimeWarning):
        assert GoIOGroup(Boom(), "COM5").get_adc(22) is None
