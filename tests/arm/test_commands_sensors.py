"""Tests for sensor and alarm RPC wrappers."""
from tests.conftest import FakeClient
from dobotkit.arm.commands.sensors import SensorMixin


class _Cmds(SensorMixin):
    """Compose SensorMixin locally to avoid importing concurrent edits."""
    pass


def test_color_sensor_set_and_get():
    c = FakeClient(results={"Magician.GetColorSensor": {"r": 10, "g": 20, "b": 30}})
    cmd = _Cmds(c, "COM8")
    cmd.set_color_sensor(1, 0)
    _, p = c.find_call("Magician.SetColorSensor")
    assert p == {"portName": "COM8", "enable": 1, "colorPort": 0, "version": 1}
    assert cmd.get_color_sensor() == {"r": 10, "g": 20, "b": 30}


def test_infrared_get_maps_port():
    c = FakeClient(results={"Magician.GetInfraredSensor": {"value": 1}})
    assert _Cmds(c, "COM8").get_infrared_sensor(1) == {"value": 1}
    _, p = c.find_call("Magician.GetInfraredSensor")
    assert p == {"portName": "COM8", "infraredPort": 1}


def test_infrared_set_with_version():
    c = FakeClient()
    cmd = _Cmds(c, "COM8")
    cmd.set_infrared_sensor(1, 2, version=2)
    _, p = c.find_call("Magician.SetInfraredSensor")
    assert p == {"portName": "COM8", "enable": 1, "infraredPort": 2, "version": 2}


def test_seeed_distance_sensor():
    c = FakeClient(results={"Magician.GetSeeedDistanceSensor": {"distance": 100}})
    assert _Cmds(c, "COM8").get_seeed_distance(1) == {"distance": 100}
    _, p = c.find_call("Magician.GetSeeedDistanceSensor")
    assert p == {"portName": "COM8", "port": 1}


def test_seeed_temp_sensor():
    c = FakeClient(results={"Magician.GetSeeedTempSensor": {"temp": 25.5}})
    assert _Cmds(c, "COM8").get_seeed_temp(2) == {"temp": 25.5}
    _, p = c.find_call("Magician.GetSeeedTempSensor")
    assert p == {"portName": "COM8", "port": 2}


def test_seeed_light_sensor():
    c = FakeClient(results={"Magician.GetSeeedLightSensor": {"light": 500}})
    assert _Cmds(c, "COM8").get_seeed_light(3) == {"light": 500}
    _, p = c.find_call("Magician.GetSeeedLightSensor")
    assert p == {"portName": "COM8", "port": 3}


def test_seeed_rgb_led():
    c = FakeClient(results={"Magician.SetSeeedRGBLed": {"result": "ok"}})
    assert _Cmds(c, "COM8").set_seeed_rgb(1, 255.0) == {"result": "ok"}
    _, p = c.find_call("Magician.SetSeeedRGBLed")
    assert p == {"portName": "COM8", "port": 1, "rgb": 255.0}


def test_alarms_state():
    c = FakeClient(results={"Magician.GetAlarmsState": {"alarms": []}})
    assert _Cmds(c, "COM8").get_alarms_state() == {"alarms": []}
    _, p = c.find_call("Magician.GetAlarmsState")
    assert p == {"portName": "COM8"}
