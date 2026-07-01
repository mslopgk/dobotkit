"""Tests for :class:`dobotkit.gui.go_controller.GoController`.

Headless: no DobotLink socket, no Tk root. The controller is driven with the
injected :class:`~tests.gui.conftest.FakeGo` (recording stand-in for
:class:`~dobotkit.go.magiciango.MagicianGO`). We assert that GUI intents map to
the right GO calls, that the emergency stop goes through, that snapshot has the
documented shape from the fake's canned readings, and that a device error is
surfaced as ``(ok=False, ...)`` instead of raising.
"""
from __future__ import annotations

from typing import Any, Dict

import pytest

from dobotkit.exceptions import DobotError, DobotLinkError
from dobotkit.gui.go_controller import GoController

from .conftest import FakeGo


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _connected_go() -> FakeGo:
    return FakeGo(connected=True)


def _last(go: FakeGo) -> tuple:
    return go.calls[-1]


def _methods(go: FakeGo) -> list:
    return [name for name, _args, _kw in go.calls]


class _BoomGo(FakeGo):
    """A FakeGo whose drive/read methods raise a device error.

    Used to prove the controller never lets a :class:`DobotError` escape into
    the UI and instead returns ``(False, message)`` / resilient dicts.
    """

    def forward(self, speed: float) -> Any:  # type: ignore[override]
        raise DobotLinkError("device on fire")

    def emergency_stop(self) -> None:  # type: ignore[override]
        raise DobotError("estop wire cut")

    def ultrasonic(self) -> Dict[str, float]:  # type: ignore[override]
        raise DobotLinkError("no ultrasonic")


# --------------------------------------------------------------------------- #
# Import safety (headless)
# --------------------------------------------------------------------------- #
def test_import_is_headless_no_tk() -> None:
    import importlib
    import sys

    # Importing the controller module in a clean interpreter must not pull in
    # tkinter (verified out-of-process so an unrelated in-process import of tk
    # by another test cannot mask a regression here).
    code = (
        "import sys, importlib; "
        "importlib.import_module('dobotkit.gui.go_controller'); "
        "sys.exit(1 if 'tkinter' in sys.modules else 0)"
    )
    import subprocess

    proc = subprocess.run([sys.executable, "-c", code])
    assert proc.returncode == 0, "importing go_controller must not import tkinter"

    # Re-import in-process is a no-op define; constructing with no device must
    # not touch hardware.
    importlib.import_module("dobotkit.gui.go_controller")
    ctrl = GoController()
    assert ctrl.go is None
    assert ctrl.client is None
    assert ctrl.is_connected is False


# --------------------------------------------------------------------------- #
# Connection state
# --------------------------------------------------------------------------- #
def test_injected_go_reports_connected() -> None:
    ctrl = GoController(go=_connected_go())
    assert ctrl.is_connected is True


def test_disconnected_go_not_connected() -> None:
    ctrl = GoController(go=FakeGo(connected=False))
    assert ctrl.is_connected is False


def test_disconnect_clears_device() -> None:
    ctrl = GoController(go=_connected_go())
    ok, _msg = ctrl.disconnect()
    assert ok is True
    assert ctrl.go is None
    assert ctrl.is_connected is False


# --------------------------------------------------------------------------- #
# Drive delegation
# --------------------------------------------------------------------------- #
def test_drive_forward_calls_go_forward() -> None:
    go = _connected_go()
    ctrl = GoController(go=go)
    ok, _msg = ctrl.drive_forward(20)
    assert ok is True
    assert _last(go) == ("forward", (20,), {})


def test_drive_forward_uses_stored_speed_by_default() -> None:
    go = _connected_go()
    ctrl = GoController(go=go)
    ctrl.set_speed(17)
    ok, _msg = ctrl.drive_forward()
    assert ok is True
    assert _last(go) == ("forward", (17.0,), {})


def test_drive_backward_calls_go_backward() -> None:
    go = _connected_go()
    ctrl = GoController(go=go)
    ctrl.drive_backward(12)
    assert _last(go) == ("backward", (12,), {})


def test_strafe_left_and_right_signs() -> None:
    go = _connected_go()
    ctrl = GoController(go=go)
    ctrl.strafe_left(10)
    assert _last(go) == ("strafe", (10,), {})
    ctrl.strafe_right(10)
    assert _last(go) == ("strafe", (-10,), {})


def test_spin_left_and_right_signs() -> None:
    go = _connected_go()
    ctrl = GoController(go=go)
    ctrl.spin_left(8)
    assert _last(go) == ("spin", (8,), {})
    ctrl.spin_right(8)
    assert _last(go) == ("spin", (-8,), {})


def test_stop_calls_go_stop() -> None:
    go = _connected_go()
    ctrl = GoController(go=go)
    ctrl.stop()
    assert _last(go) == ("stop", (), {})


def test_emergency_stop_calls_go_emergency_stop() -> None:
    go = _connected_go()
    ctrl = GoController(go=go)
    ok, _msg = ctrl.emergency_stop()
    assert ok is True
    assert _last(go) == ("emergency_stop", (), {})


# --------------------------------------------------------------------------- #
# set_speed
# --------------------------------------------------------------------------- #
def test_set_speed_stores_value() -> None:
    ctrl = GoController(go=_connected_go())
    ok, _msg = ctrl.set_speed(42)
    assert ok is True
    assert ctrl.speed == 42.0


# --------------------------------------------------------------------------- #
# LED / buzzer
# --------------------------------------------------------------------------- #
def test_rgb_delegates_with_effect_and_blink_defaults() -> None:
    go = _connected_go()
    ctrl = GoController(go=go)
    ok, _msg = ctrl.rgb(5, 255, 0, 0)
    assert ok is True
    # rgb(number, effect, r, g, b, cycle, counts)
    assert _last(go) == ("rgb", (5, 1, 255, 0, 0, 0, 0), {})


def test_buzzer_delegates() -> None:
    go = _connected_go()
    ctrl = GoController(go=go)
    ctrl.buzzer(1, 2, 3)
    assert _last(go) == ("buzzer", (1, 2, 3), {})


# --------------------------------------------------------------------------- #
# Line-trace
# --------------------------------------------------------------------------- #
def test_line_trace_start_configures_then_starts() -> None:
    go = _connected_go()
    ctrl = GoController(go=go)
    ok, _msg = ctrl.line_trace_start(15, 1.0, 0.1, 0.2)
    assert ok is True
    names = _methods(go)
    # PID and speed configured before auto_trace is enabled.
    assert names[-3:] == ["trace_pid", "trace_speed", "auto_trace"]
    assert ("trace_pid", (1.0, 0.1, 0.2), {}) in go.calls
    assert ("trace_speed", (15,), {}) in go.calls
    assert ("auto_trace", (True,), {}) in go.calls


def test_line_trace_stop_disables() -> None:
    go = _connected_go()
    ctrl = GoController(go=go)
    ctrl.line_trace_stop()
    assert _last(go) == ("auto_trace", (False,), {})


# --------------------------------------------------------------------------- #
# Navigation / precise move (return the result dicts)
# --------------------------------------------------------------------------- #
def test_nav_goto_returns_waypoint_result_dict() -> None:
    go = _connected_go()
    ctrl = GoController(go=go)
    res = ctrl.nav_goto(0, 0)
    # Already at (0,0) per the fake's canned odometer -> arrives immediately.
    assert isinstance(res, dict)
    assert res.get("arrived") is True
    assert set(res) >= {"start", "target", "final", "residual_cm", "iters", "legs", "arrived"}
    assert "error" not in res


def test_precise_forward_returns_mover_result_dict() -> None:
    go = _connected_go()
    ctrl = GoController(go=go)
    res = ctrl.precise_forward(0, speed=10)
    assert isinstance(res, dict)
    assert res["axis"] == "x"
    assert set(res) >= {"target", "achieved", "error", "axis", "timed_out", "aborted"}


# --------------------------------------------------------------------------- #
# clearance_ok passthrough
# --------------------------------------------------------------------------- #
def test_clearance_ok_passthrough_clear() -> None:
    go = _connected_go()
    ctrl = GoController(go=go)
    ok, info = ctrl.clearance_ok(x=1, threshold=20)
    assert ok is True
    assert info == go.ultrasonic_reading


def test_clearance_ok_passthrough_blocked() -> None:
    go = _connected_go()
    go.ultrasonic_reading = {"front": 5.0, "back": 50.0, "left": 50.0, "right": 50.0}
    ctrl = GoController(go=go)
    ok, info = ctrl.clearance_ok(x=1, threshold=20)
    assert ok is False
    assert "front" in str(info)


# --------------------------------------------------------------------------- #
# Camera (guarded)
# --------------------------------------------------------------------------- #
def test_read_camera_returns_object() -> None:
    go = _connected_go()
    ctrl = GoController(go=go)
    obj = ctrl.read_camera()
    assert obj == {"count": 0, "dl_obj": []}
    assert _last(go) == ("car_camera_obj", (), {})


def test_read_camera_none_when_disconnected() -> None:
    ctrl = GoController()  # no device
    assert ctrl.read_camera() is None


# --------------------------------------------------------------------------- #
# snapshot shape
# --------------------------------------------------------------------------- #
def test_snapshot_shape_from_fake_canned_values() -> None:
    go = _connected_go()
    ctrl = GoController(go=go)
    snap = ctrl.snapshot()

    assert snap["connected"] is True
    assert snap["error"] is None
    assert snap["ultrasonic"] == {
        "front": 50.0,
        "back": 50.0,
        "left": 50.0,
        "right": 50.0,
    }
    assert snap["odometer"] == {"x": 0.0, "y": 0.0, "yaw": 0.0}
    assert snap["imu"] == {"yaw": 0.0}
    assert snap["battery"] == {"voltage": 12.0, "percentage": 100.0}


def test_snapshot_reflects_overridden_readings() -> None:
    go = _connected_go()
    go.battery_reading = {"powerVoltage": 11.1, "powerPercentage": 73.0}
    go.imu_reading = {"yaw": 42.0}
    ctrl = GoController(go=go)
    snap = ctrl.snapshot()
    assert snap["battery"] == {"voltage": 11.1, "percentage": 73.0}
    assert snap["imu"] == {"yaw": 42.0}


def test_snapshot_no_device_is_all_none() -> None:
    ctrl = GoController()
    snap = ctrl.snapshot()
    assert snap["connected"] is False
    assert snap["ultrasonic"] is None
    assert snap["odometer"] is None
    assert snap["imu"] is None
    assert snap["battery"] is None
    assert snap["error"] is None


def test_snapshot_is_resilient_to_device_error() -> None:
    ctrl = GoController(go=_BoomGo(connected=True))
    snap = ctrl.snapshot()
    # ultrasonic read blows up; the rest still populate; error is captured.
    assert snap["ultrasonic"] is None
    assert snap["error"] is not None
    assert snap["odometer"] == {"x": 0.0, "y": 0.0, "yaw": 0.0}
    assert snap["battery"] == {"voltage": 12.0, "percentage": 100.0}


# --------------------------------------------------------------------------- #
# Error surfacing: device errors become (ok=False, ...), never raise
# --------------------------------------------------------------------------- #
def test_drive_forward_device_error_surfaced() -> None:
    ctrl = GoController(go=_BoomGo(connected=True))
    ok, msg = ctrl.drive_forward(20)
    assert ok is False
    assert "device on fire" in msg


def test_emergency_stop_device_error_surfaced() -> None:
    ctrl = GoController(go=_BoomGo(connected=True))
    ok, msg = ctrl.emergency_stop()
    assert ok is False
    assert "estop wire cut" in msg


def test_drive_when_not_connected_surfaced_not_raised() -> None:
    ctrl = GoController()  # no device
    ok, msg = ctrl.drive_forward(20)
    assert ok is False
    assert "not connected" in msg


def test_nav_goto_device_error_returns_error_dict() -> None:
    ctrl = GoController()  # no device -> _require_go raises DobotError
    res = ctrl.nav_goto(10, 10)
    assert "error" in res
    assert "not connected" in res["error"]


def test_precise_forward_device_error_returns_error_dict() -> None:
    ctrl = GoController()
    res = ctrl.precise_forward(100)
    assert "error" in res


@pytest.mark.parametrize(
    "call",
    [
        lambda c: c.drive_backward(5),
        lambda c: c.strafe_left(5),
        lambda c: c.strafe_right(5),
        lambda c: c.spin_left(5),
        lambda c: c.spin_right(5),
        lambda c: c.stop(),
        lambda c: c.rgb(1, 1, 2, 3),
        lambda c: c.buzzer(1, 2, 3),
        lambda c: c.line_trace_start(10, 1, 0, 0),
        lambda c: c.line_trace_stop(),
    ],
)
def test_commands_never_raise_when_disconnected(call: Any) -> None:
    ctrl = GoController()  # no device
    ok, msg = call(ctrl)
    assert ok is False
    assert isinstance(msg, str)
