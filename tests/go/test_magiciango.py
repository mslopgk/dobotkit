"""Tests for ``dobotkit.go.magiciango.MagicianGO``.

``MagicianGO`` is a thin, typed wrapper over a connected ``DobotLinkClient``.
Every method issues ``client.call("MagicianGO.<Func>", portName=..., **params)``
(``search`` is the lone exception — it sends no ``portName``), and
``emergency_stop`` uses ``client.notify`` so it never blocks.

These tests drive the wrapper through the in-memory ``FakeClient`` double from
``tests/go/conftest.py``, which records every ``(method, params)`` tuple and
returns canned results, so no socket is ever opened. The assertions pin down the
exact RPC name and parameter shape sent on the wire, mirroring the proven
``magiciango/go.py`` reference behaviour.
"""
from __future__ import annotations

from dobotkit.enums import LEDChannel
from dobotkit.go.magiciango import MagicianGO

from .conftest import FakeClient


def make_go(result=None, results=None, port_name: str = "COM5") -> tuple[MagicianGO, FakeClient]:
    fc = FakeClient(result=result, results=results)
    return MagicianGO(fc, port_name=port_name), fc


# ---- construction ----------------------------------------------------------

def test_default_port_name():
    go, _ = make_go()
    assert go.port_name == "COM5"


def test_custom_port_name():
    go, _ = make_go(port_name="COM7")
    assert go.port_name == "COM7"


# ---- connection ------------------------------------------------------------

def test_search_has_no_portname():
    go, fc = make_go()
    go.search()
    assert fc.calls[0] == ("MagicianGO.SearchDobot", {})


def test_connect_robot_sends_portname():
    go, fc = make_go()
    go.connect_robot()
    assert fc.calls[0] == ("MagicianGO.ConnectDobot", {"portName": "COM5"})


def test_disconnect_robot_sends_portname():
    go, fc = make_go(port_name="COM7")
    go.disconnect_robot()
    assert fc.calls[0] == ("MagicianGO.DisconnectDobot", {"portName": "COM7"})


def test_set_running_mode():
    go, fc = make_go()
    go.set_running_mode(1)
    assert fc.calls[0] == ("MagicianGO.SetRunningMode", {"runningMode": 1, "portName": "COM5"})


def test_connect_verifies_link_with_battery():
    # connect(verify=True) must call connect_robot THEN battery (the link check).
    go, fc = make_go(results={"MagicianGO.GetBatteryVoltage": {"powerVoltage": 11.2,
                                                               "powerPercentage": 80}})
    result = go.connect()
    methods = fc.methods_called()
    assert methods[0] == "MagicianGO.ConnectDobot"
    assert "MagicianGO.GetBatteryVoltage" in methods
    assert methods.index("MagicianGO.ConnectDobot") < methods.index("MagicianGO.GetBatteryVoltage")
    assert result == {"powerVoltage": 11.2, "powerPercentage": 80}


def test_connect_without_verify_skips_battery():
    go, fc = make_go()
    go.connect(verify=False)
    assert fc.methods_called() == ["MagicianGO.ConnectDobot"]


# ---- continuous drive (trusted) --------------------------------------------

def test_move_sends_setmovespeed_with_port():
    go, fc = make_go()
    go.move(x=10, y=0, r=5)
    assert fc.calls[0] == (
        "MagicianGO.SetMoveSpeed",
        {"x": 10, "y": 0, "r": 5, "portName": "COM5"},
    )


def test_move_defaults_zero():
    go, fc = make_go()
    go.move()
    assert fc.calls[0][1] == {"x": 0, "y": 0, "r": 0, "portName": "COM5"}


def test_move_direct_renames_direction_to_dir():
    go, fc = make_go()
    go.move_direct(direction=0, speed=20)
    assert fc.calls[0] == (
        "MagicianGO.SetMoveSpeedDirect",
        {"dir": 0, "speed": 20, "portName": "COM5"},
    )


def test_forward_sets_only_x():
    go, fc = make_go()
    go.forward(15)
    assert fc.calls[0] == ("MagicianGO.SetMoveSpeed",
                           {"x": 15, "y": 0, "r": 0, "portName": "COM5"})


def test_backward_negates_x():
    go, fc = make_go()
    go.backward(15)
    assert fc.calls[0][1] == {"x": -15, "y": 0, "r": 0, "portName": "COM5"}


def test_strafe_sets_only_y():
    go, fc = make_go()
    go.strafe(12)
    assert fc.calls[0][1] == {"x": 0, "y": 12, "r": 0, "portName": "COM5"}


def test_spin_sets_only_r():
    go, fc = make_go()
    go.spin(8)
    assert fc.calls[0][1] == {"x": 0, "y": 0, "r": 8, "portName": "COM5"}


def test_stop_is_zero_move():
    go, fc = make_go()
    go.stop()
    assert fc.calls[0] == ("MagicianGO.SetMoveSpeed",
                           {"x": 0, "y": 0, "r": 0, "portName": "COM5"})


def test_emergency_stop_uses_notify_not_call():
    go, fc = make_go()
    go.emergency_stop()
    assert fc.calls == []  # never uses a blocking call
    assert fc.notifies[0] == (
        "MagicianGO.SetMoveSpeed",
        {"portName": "COM5", "x": 0, "y": 0, "r": 0},
    )


# ---- closed-loop (HANG-warned) ---------------------------------------------

_WAIT_KEYS = {"isQueued": True, "isWaitForFinish": True, "timeout": 604800000}


def test_rotate_includes_queue_flags():
    go, fc = make_go()
    go.rotate(r=90, Vr=30)
    method, params = fc.calls[0]
    assert method == "MagicianGO.SetRotate"
    assert params["r"] == 90 and params["Vr"] == 30
    for k, v in _WAIT_KEYS.items():
        assert params[k] == v
    assert params["portName"] == "COM5"


def test_move_dist_includes_queue_flags():
    go, fc = make_go()
    go.move_dist(x=30, y=0, Vx=30, Vy=0)
    method, params = fc.calls[0]
    assert method == "MagicianGO.SetMoveDist"
    assert (params["x"], params["y"], params["Vx"], params["Vy"]) == (30, 0, 30, 0)
    for k, v in _WAIT_KEYS.items():
        assert params[k] == v


def test_arc_rad_includes_queue_flags():
    go, fc = make_go()
    go.arc_rad(velocity=30, radius=50, angle=30, mode=0)
    method, params = fc.calls[0]
    assert method == "MagicianGO.SetArcRad"
    assert (params["velocity"], params["radius"], params["angle"], params["mode"]) == (30, 50, 30, 0)
    for k, v in _WAIT_KEYS.items():
        assert params[k] == v


def test_arc_cent_includes_queue_flags():
    go, fc = make_go()
    go.arc_cent(velocity=30, x=50, y=0, angle=30, mode=0)
    method, params = fc.calls[0]
    assert method == "MagicianGO.SetArcCent"
    assert (params["velocity"], params["x"], params["y"], params["angle"], params["mode"]) == \
        (30, 50, 0, 30, 0)
    for k, v in _WAIT_KEYS.items():
        assert params[k] == v


def test_coord_closed_loop_has_no_wait_flags():
    # Per research doc 3.4: SetCoordClosedLoop does NOT carry the _WAIT flags.
    go, fc = make_go()
    go.coord_closed_loop(is_enable=True, angle=45)
    method, params = fc.calls[0]
    assert method == "MagicianGO.SetCoordClosedLoop"
    assert params == {"isEnable": True, "angle": 45, "portName": "COM5"}
    assert "isQueued" not in params


def test_increment_closed_loop_includes_queue_flags():
    go, fc = make_go()
    go.increment_closed_loop(x=30, y=0, angle=0)
    method, params = fc.calls[0]
    assert method == "MagicianGO.SetIncrementClosedLoop"
    assert (params["x"], params["y"], params["angle"]) == (30, 0, 0)
    for k, v in _WAIT_KEYS.items():
        assert params[k] == v


# ---- safety: clearance_ok --------------------------------------------------

def test_clearance_ok_passes_when_clear():
    go, _ = make_go(results={"MagicianGO.GetUltrasoundData":
                             {"front": 40, "back": 40, "left": 40, "right": 40}})
    ok, info = go.clearance_ok(x=10, threshold=20)
    assert ok is True
    assert info["front"] == 40


def test_clearance_ok_blocks_when_front_too_close():
    go, _ = make_go(results={"MagicianGO.GetUltrasoundData":
                             {"front": 5, "back": 40, "left": 40, "right": 40}})
    ok, info = go.clearance_ok(x=10, threshold=20)
    assert ok is False
    assert "front" in info


def test_clearance_ok_blocks_when_back_too_close():
    go, _ = make_go(results={"MagicianGO.GetUltrasoundData":
                             {"front": 40, "back": 5, "left": 40, "right": 40}})
    ok, info = go.clearance_ok(x=-10, threshold=20)
    assert ok is False
    assert "back" in info


def test_clearance_ok_blocks_when_side_too_close():
    go, _ = make_go(results={"MagicianGO.GetUltrasoundData":
                             {"front": 40, "back": 40, "left": 8, "right": 40}})
    ok, info = go.clearance_ok(y=10, threshold=20)
    assert ok is False
    assert "side" in info


def test_clearance_spin_requires_all_sides():
    go, _ = make_go(results={"MagicianGO.GetUltrasoundData":
                             {"front": 40, "back": 40, "left": 8, "right": 40}})
    ok, info = go.clearance_ok(r=10, threshold=20)
    assert ok is False
    assert "around" in info


# ---- output: rgb / buzzer --------------------------------------------------

def test_rgb_accepts_named_led():
    go, fc = make_go()
    go.rgb("LED_ALL", effect=1, r=255, g=0, b=0, cycle=0, counts=0)
    method, params = fc.calls[0]
    assert method == "MagicianGO.SetLightRGB"
    assert params["number"] == 5


def test_rgb_accepts_int_number():
    go, fc = make_go()
    go.rgb(1, effect=1, r=0, g=255, b=0, cycle=0, counts=0)
    method, params = fc.calls[0]
    assert method == "MagicianGO.SetLightRGB"
    assert params["number"] == 1
    assert params == {"number": 1, "effect": 1, "r": 0, "g": 255, "b": 0,
                      "cycle": 0, "counts": 0, "portName": "COM5"}


def test_rgb_accepts_led_channel_enum():
    go, fc = make_go()
    go.rgb(LEDChannel.LED_2, effect=1, r=1, g=2, b=3, cycle=0, counts=0)
    _, params = fc.calls[0]
    assert params["number"] == 2
    assert isinstance(params["number"], int)


def test_buzzer():
    go, fc = make_go()
    go.buzzer(index=1, tone=1, beat=1)
    assert fc.calls[0] == ("MagicianGO.SetBuzzerSound",
                           {"index": 1, "tone": 1, "beat": 1, "portName": "COM5"})


# ---- sensors ---------------------------------------------------------------

def test_ultrasonic():
    go, fc = make_go(results={"MagicianGO.GetUltrasoundData":
                              {"front": 30, "back": 40, "left": 50, "right": 60}})
    assert go.ultrasonic() == {"front": 30, "back": 40, "left": 50, "right": 60}
    assert fc.calls[0] == ("MagicianGO.GetUltrasoundData", {"portName": "COM5"})


def test_odometer():
    go, fc = make_go(results={"MagicianGO.GetSpeedometer": {"x": 1, "y": 2, "yaw": 3}})
    assert go.odometer() == {"x": 1, "y": 2, "yaw": 3}
    assert fc.calls[0] == ("MagicianGO.GetSpeedometer", {"portName": "COM5"})


def test_set_odometer():
    go, fc = make_go()
    go.set_odometer(x=0, y=0, yaw=0)
    assert fc.calls[0] == ("MagicianGO.SetSpeedometer",
                           {"x": 0, "y": 0, "yaw": 0, "portName": "COM5"})


def test_battery_returns_client_result():
    go, fc = make_go(results={"MagicianGO.GetBatteryVoltage":
                              {"powerVoltage": 11.2, "powerPercentage": 80}})
    assert go.battery() == {"powerVoltage": 11.2, "powerPercentage": 80}
    assert fc.calls[0] == ("MagicianGO.GetBatteryVoltage", {"portName": "COM5"})


def test_imu_angle():
    go, fc = make_go(results={"MagicianGO.GetImuAngle": {"yaw": 12.3}})
    assert go.imu_angle() == {"yaw": 12.3}
    assert fc.calls[0] == ("MagicianGO.GetImuAngle", {"portName": "COM5"})


def test_imu_speed():
    go, fc = make_go(results={"MagicianGO.GetImuSpeed": {"yaw": 1.0}})
    assert go.imu_speed() == {"yaw": 1.0}
    assert fc.calls[0] == ("MagicianGO.GetImuSpeed", {"portName": "COM5"})


# ---- line-trace ------------------------------------------------------------

def test_auto_trace_sends_loop_then_auto():
    go, fc = make_go()
    go.auto_trace(True)
    assert fc.calls[0][0] == "MagicianGO.SetTraceLoop"
    assert fc.calls[0][1]["enable"] is True
    assert fc.calls[1][0] == "MagicianGO.SetTraceAuto"
    assert fc.calls[1][1]["isTrace"] is True


def test_auto_trace_off_coerces_bool():
    go, fc = make_go()
    go.auto_trace(0)
    assert fc.calls[0][1]["enable"] is False
    assert fc.calls[1][1]["isTrace"] is False


def test_trace_speed():
    go, fc = make_go()
    go.trace_speed(30)
    assert fc.calls[0] == ("MagicianGO.SetTraceSpeed", {"speed": 30, "portName": "COM5"})


def test_trace_pid():
    go, fc = make_go()
    go.trace_pid(50, 0, 10)
    assert fc.calls[0] == ("MagicianGO.SetTracePid",
                           {"p": 50, "i": 0, "d": 10, "portName": "COM5"})


def test_trace_angle():
    go, fc = make_go(results={"MagicianGO.GetCarCameraAngle": {"angle": 5, "count": 1}})
    assert go.trace_angle() == {"angle": 5, "count": 1}
    assert fc.calls[0] == ("MagicianGO.GetCarCameraAngle", {"portName": "COM5"})


# ---- camera (defensive parsing) --------------------------------------------

def test_car_camera_obj():
    go, fc = make_go(results={"MagicianGO.GetCarCameraObj":
                              {"count": 2, "dl_obj": [{"a": 1}, {"a": 2}]}})
    res = go.car_camera_obj()
    assert res == {"count": 2, "dl_obj": [{"a": 1}, {"a": 2}]}
    assert fc.calls[0] == ("MagicianGO.GetCarCameraObj", {"portName": "COM5"})


def test_arm_camera_obj():
    go, fc = make_go(results={"MagicianGO.GetArmCameraObj": {"count": 0, "dl_obj": []}})
    assert go.arm_camera_obj() == {"count": 0, "dl_obj": []}
    assert fc.calls[0] == ("MagicianGO.GetArmCameraObj", {"portName": "COM5"})


def test_arm_camera_tag():
    go, fc = make_go(results={"MagicianGO.GetArmCameraTag": {"tags": []}})
    assert go.arm_camera_tag() == {"tags": []}
    assert fc.calls[0] == ("MagicianGO.GetArmCameraTag", {"portName": "COM5"})
