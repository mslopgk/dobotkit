"""Tests for EffectorIoMixin RPC wrappers."""
from dobotkit.arm.commands.effector_io import EffectorIoMixin
from tests.conftest import FakeClient


class _Cmds(EffectorIoMixin):
    """Local composition of EffectorIoMixin for testing (avoids importing ArmCommands)."""
    pass


def test_suction_cup_maps():
    """Test set_suction_cup maps to SetEndEffectorSuctionCup with correct params."""
    c = FakeClient(results={"Magician.SetEndEffectorSuctionCup": {"queuedCmdIndex": 1}})
    result = _Cmds(c, "COM8").set_suction_cup(True, True, queued=True)
    _, p = c.find_call("Magician.SetEndEffectorSuctionCup")
    # `enable` is the hardware-verified DobotLink key for pump power (NOT the SDK's `enableCtrl`,
    # which DobotLink silently ignores). Do not "correct" this back — see effector_io.py.
    assert p == {"portName": "COM8", "enable": True, "on": True, "isQueued": True}
    assert result == 1


def test_set_io_multiplexing_maps():
    """Test set_io_multiplexing maps to SetIOMultiplexing with correct params."""
    c = FakeClient(results={"Magician.SetIOMultiplexing": True})
    _Cmds(c, "COM8").set_io_multiplexing(24, 4)
    _, p = c.find_call("Magician.SetIOMultiplexing")
    assert p == {"portName": "COM8", "address": 24, "multiplex": 4}


def test_get_io_adc_passthrough():
    """Test get_io_adc returns the full result dict."""
    c = FakeClient(results={"Magician.GetIOADC": {"port": 0, "value": 3565}})
    result = _Cmds(c, "COM8").get_io_adc(24)
    assert result == {"port": 0, "value": 3565}


def test_gripper_maps():
    """Test set_gripper maps to SetEndEffectorGripper with correct params."""
    c = FakeClient(results={"Magician.SetEndEffectorGripper": {"queuedCmdIndex": 2}})
    result = _Cmds(c, "COM8").set_gripper(False, True, queued=True)
    _, p = c.find_call("Magician.SetEndEffectorGripper")
    assert p == {"portName": "COM8", "enable": False, "on": True, "isQueued": True}
    assert result == 2


def test_set_servo_angle_maps():
    """Test set_servo_angle maps to SetServoAngle with correct params."""
    c = FakeClient(results={"Magician.SetServoAngle": {"queuedCmdIndex": 3}})
    result = _Cmds(c, "COM8").set_servo_angle(1, 45.5, queued=True)
    _, p = c.find_call("Magician.SetServoAngle")
    assert p == {"portName": "COM8", "index": 1, "value": 45.5, "isQueued": True}
    assert result == 3


def test_get_io_di_maps():
    """Test get_io_di maps to GetIODI with correct params."""
    c = FakeClient(results={"Magician.GetIODI": {"port": 1, "level": 1}})
    result = _Cmds(c, "COM8").get_io_di(25)
    _, p = c.find_call("Magician.GetIODI")
    assert p == {"portName": "COM8", "address": 25}
    assert result == {"port": 1, "level": 1}


def test_set_io_do_maps():
    """Test set_io_do maps to SetIODO with correct params."""
    c = FakeClient(results={"Magician.SetIODO": True})
    _Cmds(c, "COM8").set_io_do(25, 1, queued=False)
    _, p = c.find_call("Magician.SetIODO")
    assert p == {"portName": "COM8", "address": 25, "level": 1, "isQueued": False}


def test_set_io_pwm_maps():
    """Test set_io_pwm maps to SetIOPWM with correct params."""
    c = FakeClient(results={"Magician.SetIOPWM": True})
    _Cmds(c, "COM8").set_io_pwm(26, 1000.0, 0.5, queued=True)
    _, p = c.find_call("Magician.SetIOPWM")
    assert p == {"portName": "COM8", "address": 26, "frequency": 1000.0, "dutyCycle": 0.5, "isQueued": True}


def test_suction_cup_default_queued():
    """Test set_suction_cup uses queued=True by default."""
    c = FakeClient(results={"Magician.SetEndEffectorSuctionCup": {"queuedCmdIndex": 5}})
    _Cmds(c, "COM8").set_suction_cup(True, False)
    _, p = c.find_call("Magician.SetEndEffectorSuctionCup")
    assert p["isQueued"] is True


def test_set_io_multiplexing_never_sends_is_queued():
    """set_io_multiplexing has no `queued` param -- isQueued is never sent."""
    c = FakeClient(results={"Magician.SetIOMultiplexing": True})
    _Cmds(c, "COM8").set_io_multiplexing(24, 4)
    _, p = c.find_call("Magician.SetIOMultiplexing")
    assert "isQueued" not in p
