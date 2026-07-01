"""Tests for :class:`dobotkit.gui.arm_controller.ArmController`.

These exercise the logic layer headless -- no serial port, no Tk root -- against
the :class:`FakeArm` from ``tests/gui/conftest.py``. The assertions fall into
four groups:

* **Delegation** -- each action calls the right Magician/group method with the
  right positional + keyword arguments (read off ``FakeArm.calls``).
* **State** -- connect/disconnect toggle :attr:`ArmController.is_connected` and
  record the port.
* **Snapshot** -- :meth:`snapshot` returns the documented dict shape built from
  the fake's canned pose, and stays resilient.
* **Error handling** -- a device whose methods raise :class:`DobotError` is
  surfaced as ``(ok=False, message=...)`` rather than propagating.
"""
from __future__ import annotations

from typing import Any, List, Tuple

import pytest

from dobotkit.arm.structures import Pose
from dobotkit.enums import JOGMode, PTPMode
from dobotkit.exceptions import DobotConnectionError, DobotError
from dobotkit.gui.arm_controller import ActionResult, ArmController

from .conftest import FakeArm

Call = Tuple[str, tuple, dict]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _find(calls: List[Call], name: str) -> Call:
    """Return the single recorded call named ``name`` (fails if not exactly one)."""
    matches = [c for c in calls if c[0] == name]
    assert len(matches) == 1, f"expected exactly one {name!r} call, got {matches}"
    return matches[0]


class RaisingArm(FakeArm):
    """A :class:`FakeArm` whose every driven method raises :class:`DobotError`.

    Used to prove the controller catches device errors and returns
    ``(ok=False, ...)`` instead of letting the exception reach the UI.
    """

    def __init__(self) -> None:
        super().__init__(connected=True)

    def _boom(self, *_a: Any, **_k: Any) -> Any:
        raise DobotError("kaboom")

    # lifecycle + motion + pose the controller calls directly
    connect = _boom  # type: ignore[assignment]
    disconnect = _boom  # type: ignore[assignment]
    home = _boom  # type: ignore[assignment]
    move_to = _boom  # type: ignore[assignment]
    move_relative = _boom  # type: ignore[assignment]
    set_speed = _boom  # type: ignore[assignment]
    get_pose = _boom  # type: ignore[assignment]


# --------------------------------------------------------------------------- #
# construction / connection state
# --------------------------------------------------------------------------- #
def test_new_controller_without_device_is_disconnected() -> None:
    ctrl = ArmController()
    assert ctrl.is_connected is False
    assert ctrl.port is None
    assert ctrl.device is None


def test_injected_disconnected_device_reads_disconnected(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    assert ctrl.is_connected is False


def test_connect_uses_injected_device_and_toggles_state(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    result = ctrl.connect("COM7")
    assert isinstance(result, ActionResult)
    assert result.ok is True
    assert ctrl.is_connected is True
    assert ctrl.port == "COM7"
    assert _find(fake_arm.calls, "connect") == ("connect", (), {})


def test_disconnect_toggles_state_back(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    ctrl.connect("COM7")
    result = ctrl.disconnect()
    assert result.ok is True
    assert ctrl.is_connected is False
    assert _find(fake_arm.calls, "disconnect") == ("disconnect", (), {})


def test_connect_uses_factory_when_no_device() -> None:
    built: List[str] = []

    def factory(port: str) -> Any:
        built.append(port)
        return FakeArm(connected=True)

    ctrl = ArmController(device_factory=factory)
    result = ctrl.connect("COM9")
    assert result.ok is True
    assert built == ["COM9"]
    assert ctrl.is_connected is True
    assert ctrl.port == "COM9"


def test_result_is_tuple_unpackable(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    ok, message = ctrl.connect("COM1")
    assert ok is True
    assert isinstance(message, str)


# --------------------------------------------------------------------------- #
# discovery
# --------------------------------------------------------------------------- #
def test_available_ports_delegates_to_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "dobotkit.gui.arm_controller.SerialTransport.search",
        staticmethod(lambda: ["COM3", "COM4"]),
    )
    assert ArmController().available_ports() == ["COM3", "COM4"]


def test_available_ports_safe_when_search_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom() -> List[str]:
        raise OSError("no driver")

    monkeypatch.setattr(
        "dobotkit.gui.arm_controller.SerialTransport.search",
        staticmethod(boom),
    )
    assert ArmController().available_ports() == []


# --------------------------------------------------------------------------- #
# motion delegation
# --------------------------------------------------------------------------- #
def test_home_delegates_with_wait(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    result = ctrl.home(wait=True)
    assert result.ok is True
    name, args, kwargs = _find(fake_arm.calls, "home")
    assert kwargs == {"wait": True}


def test_move_to_delegates_positional_and_mode(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    result = ctrl.move_to(200.0, 10.0, 20.0, 5.0, mode=PTPMode.MOVJ_XYZ, wait=False)
    assert result.ok is True
    name, args, kwargs = _find(fake_arm.calls, "move_to")
    assert args == (200.0, 10.0, 20.0, 5.0)
    assert kwargs["mode"] == PTPMode.MOVJ_XYZ
    assert kwargs["wait"] is False


def test_move_to_default_mode_is_movl_xyz(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    ctrl.move_to(1.0, 2.0, 3.0)
    _, _, kwargs = _find(fake_arm.calls, "move_to")
    assert kwargs["mode"] == PTPMode.MOVL_XYZ


def test_move_relative_delegates(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    result = ctrl.move_relative(1.0, -2.0, 3.0, 0.5, wait=False)
    assert result.ok is True
    _, args, kwargs = _find(fake_arm.calls, "move_relative")
    assert args == (1.0, -2.0, 3.0, 0.5)
    assert kwargs["wait"] is False


def test_set_speed_delegates(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    result = ctrl.set_speed(100.0, 50.0)
    assert result.ok is True
    assert _find(fake_arm.calls, "set_speed") == ("set_speed", (100.0, 50.0), {})


# --------------------------------------------------------------------------- #
# jogging
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "axis,positive,expected_cmd",
    [
        (1, True, JOGMode.AP_DOWN),
        (1, False, JOGMode.AN_DOWN),
        (2, True, JOGMode.BP_DOWN),
        (2, False, JOGMode.BN_DOWN),
        (3, True, JOGMode.CP_DOWN),
        (4, True, JOGMode.DP_DOWN),
        (4, False, JOGMode.DN_DOWN),
    ],
)
def test_jog_start_maps_axis_to_cmd(
    fake_arm: FakeArm, axis: int, positive: bool, expected_cmd: JOGMode
) -> None:
    ctrl = ArmController(device=fake_arm)
    result = ctrl.jog_start(axis, positive)
    assert result.ok is True
    name, args, kwargs = _find(fake_arm.calls, "lowlevel.set_jog_cmd")
    # coordinate frame by default -> is_joint == 0
    assert args == (0, int(expected_cmd))


def test_jog_start_joint_frame_sets_is_joint(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    ctrl.jog_start(1, True, joint=True)
    _, args, _ = _find(fake_arm.calls, "lowlevel.set_jog_cmd")
    assert args[0] == 1


def test_jog_stop_sends_idle(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    ctrl.jog_start(2, True)  # coordinate frame
    fake_arm.calls.clear()
    result = ctrl.jog_stop()
    assert result.ok is True
    _, args, _ = _find(fake_arm.calls, "lowlevel.set_jog_cmd")
    assert args == (0, int(JOGMode.IDLE))


def test_jog_stop_uses_last_jog_frame(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    ctrl.jog_start(1, True, joint=True)  # joint frame -> is_joint 1
    fake_arm.calls.clear()
    ctrl.jog_stop()
    _, args, _ = _find(fake_arm.calls, "lowlevel.set_jog_cmd")
    assert args == (1, int(JOGMode.IDLE))


def test_jog_start_bad_axis_is_caught(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    result = ctrl.jog_start(9, True)
    assert result.ok is False
    assert "jog" in result.message.lower()


# --------------------------------------------------------------------------- #
# end effector
# --------------------------------------------------------------------------- #
def test_suck_delegates_to_effector(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    result = ctrl.suck(True)
    assert result.ok is True
    name, args, _ = _find(fake_arm.calls, "effector.suck")
    assert args == (True,)


def test_grip_delegates_to_effector(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    result = ctrl.grip(False)
    assert result.ok is True
    name, args, _ = _find(fake_arm.calls, "effector.grip")
    assert args == (False,)


def test_laser_delegates_to_effector(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    result = ctrl.laser(True)
    assert result.ok is True
    name, args, _ = _find(fake_arm.calls, "effector.laser")
    assert args == (True,)


def test_suck_pump_off_passes_enable_false(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    result = ctrl.suck(False, enable=False)
    assert result.ok is True
    assert "pump off" in result.message.lower()
    _name, args, kwargs = _find(fake_arm.calls, "effector.suck")
    assert args == (False,)
    assert kwargs.get("enable") is False


def test_grip_pump_off_passes_enable_false(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    result = ctrl.grip(False, enable=False)
    assert result.ok is True
    assert "pump off" in result.message.lower()
    _name, args, kwargs = _find(fake_arm.calls, "effector.grip")
    assert kwargs.get("enable") is False


def test_suck_default_enables_pump(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    ctrl.suck(True)
    _name, _args, kwargs = _find(fake_arm.calls, "effector.suck")
    assert kwargs.get("enable") is True


# --------------------------------------------------------------------------- #
# IO delegation
# --------------------------------------------------------------------------- #
def test_io_set_do_delegates(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    result = ctrl.io_set_do(5, 1)
    assert result.ok is True
    _, args, _ = _find(fake_arm.calls, "io.set_do")
    assert args == (5, 1)


def test_io_get_di_delegates_and_reports(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    result = ctrl.io_get_di(3)
    assert result.ok is True
    _, args, _ = _find(fake_arm.calls, "io.get_di")
    assert args == (3,)
    assert "0" in result.message  # canned reading


def test_io_get_adc_delegates(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    result = ctrl.io_get_adc(2)
    assert result.ok is True
    _, args, _ = _find(fake_arm.calls, "io.get_adc")
    assert args == (2,)


# --------------------------------------------------------------------------- #
# sensors
# --------------------------------------------------------------------------- #
def test_read_color_delegates(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    result = ctrl.read_color(1)
    assert result.ok is True
    _, args, _ = _find(fake_arm.calls, "sensors.color")
    assert args == (1,)


def test_read_infrared_delegates(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    result = ctrl.read_infrared(2)
    assert result.ok is True
    _, args, _ = _find(fake_arm.calls, "sensors.infrared")
    assert args == (2,)


def test_read_seeed_distance_delegates(fake_arm: FakeArm) -> None:
    ctrl = ArmController(device=fake_arm)
    result = ctrl.read_seeed_distance(4)
    assert result.ok is True
    _, args, _ = _find(fake_arm.calls, "sensors.seeed_distance")
    assert args == (4,)


# --------------------------------------------------------------------------- #
# snapshot
# --------------------------------------------------------------------------- #
def test_snapshot_shape_from_canned_pose(fake_arm: FakeArm) -> None:
    fake_arm.next_pose = Pose(
        x=201.0, y=1.0, z=2.0, r=3.0, j1=4.0, j2=5.0, j3=6.0, j4=7.0
    )
    ctrl = ArmController(device=fake_arm)
    ctrl.connect("COM5")
    snap = ctrl.snapshot()

    assert set(snap) == {"connected", "port", "pose", "alarms", "error"}
    assert snap["connected"] is True
    assert snap["port"] == "COM5"
    assert snap["error"] is None
    assert snap["alarms"] == []
    assert snap["pose"] == {
        "x": 201.0,
        "y": 1.0,
        "z": 2.0,
        "r": 3.0,
        "j1": 4.0,
        "j2": 5.0,
        "j3": 6.0,
        "j4": 7.0,
    }


def test_snapshot_without_device_reports_disconnected() -> None:
    snap = ArmController().snapshot()
    assert snap["connected"] is False
    assert snap["pose"] is None
    assert snap["alarms"] == []
    assert snap["error"] is None
    assert snap["port"] is None


def test_snapshot_is_resilient_when_pose_read_raises() -> None:
    ctrl = ArmController(device=RaisingArm())
    snap = ctrl.snapshot()
    # never raised; pose is None and the failure is surfaced under "error"
    assert snap["pose"] is None
    assert snap["error"] is not None
    assert snap["connected"] is True


# --------------------------------------------------------------------------- #
# error handling (device raises -> (ok=False, message))
# --------------------------------------------------------------------------- #
def test_action_catches_dobot_error_and_returns_failure() -> None:
    ctrl = ArmController(device=RaisingArm())
    result = ctrl.home()
    assert isinstance(result, ActionResult)
    assert result.ok is False
    assert "kaboom" in result.message


def test_move_to_catches_dobot_error() -> None:
    ctrl = ArmController(device=RaisingArm())
    result = ctrl.move_to(1.0, 2.0, 3.0)
    assert result.ok is False
    assert "kaboom" in result.message


def test_actions_on_disconnected_controller_fail_gracefully() -> None:
    ctrl = ArmController()  # no device
    result = ctrl.home()
    assert result.ok is False
    assert "not connected" in result.message.lower()


def test_connect_catches_dobot_error_from_factory() -> None:
    def factory(_port: str) -> Any:
        raise DobotConnectionError("port busy")

    ctrl = ArmController(device_factory=factory)
    result = ctrl.connect("COM2")
    assert result.ok is False
    assert ctrl.is_connected is False
    assert "port busy" in result.message


def test_disconnect_when_never_connected_is_ok() -> None:
    ctrl = ArmController()
    result = ctrl.disconnect()
    assert result.ok is True
