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


def test_magicbox_groups_wired_with_same_client_and_port():
    from dobotkit.go.groups import GoIOGroup, GoSensorGroup

    go, fc = make_go(port_name="COM7")
    assert isinstance(go.sensors, GoSensorGroup)
    assert isinstance(go.io, GoIOGroup)
    # The groups share the wrapper's client + port, so MagicBox reads ride the
    # same connection as the native MagicianGO calls.
    assert go.sensors.port_name == "COM7" and go.io.port_name == "COM7"
    assert go.sensors._client is fc and go.io._client is fc


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


# ---- safety: clearance -----------------------------------------------------

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

def test_ultrasonic_validates_and_clamps():
    # Hardware clamps at 40 cm — readings above the ceiling are normalised down
    # so callers can't mistake ">=40" for a precise long-range measurement.
    go, fc = make_go(results={"MagicianGO.GetUltrasoundData":
                              {"front": 30, "back": 40, "left": 50, "right": 60}})
    assert go.ultrasonic() == {"front": 30, "back": 40, "left": 40, "right": 40}
    assert fc.calls[0] == ("MagicianGO.GetUltrasoundData", {"portName": "COM5"})


def test_ultrasonic_missing_key_returns_none():
    go, _ = make_go(results={"MagicianGO.GetUltrasoundData":
                             {"front": 30, "back": 40, "left": 40}})
    assert go.ultrasonic() is None


def test_ultrasonic_sentinel_returns_none():
    # 0/negative values are absent-sensor sentinels -> unknown -> None.
    go, _ = make_go(results={"MagicianGO.GetUltrasoundData":
                             {"front": 0, "back": 40, "left": 40, "right": 40}})
    assert go.ultrasonic() is None


def test_ultrasonic_non_dict_returns_none():
    go, _ = make_go(results={"MagicianGO.GetUltrasoundData": None})
    assert go.ultrasonic() is None


def test_ultrasonic_raw_passes_through():
    raw = {"front": 55, "back": 40, "left": 40, "right": 40, "extra": 1}
    go, _ = make_go(results={"MagicianGO.GetUltrasoundData": raw})
    assert go.ultrasonic_raw() == raw


def test_clearance_ok_blocks_on_invalid_ultrasonic():
    # Unknown means stop: a malformed read is itself a blocking reason.
    go, _ = make_go(results={"MagicianGO.GetUltrasoundData": {"front": 40}})
    ok, info = go.clearance_ok(x=10, threshold=20)
    assert ok is False
    assert "invalid" in info


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


def test_move_clamps_speed_magnitude():
    go, fc = make_go()
    go.move(x=1000, y=-999, r=31)
    _, params = fc.calls[0]
    assert params["x"] == 30.0
    assert params["y"] == -30.0
    assert params["r"] == 30.0


def test_move_within_cap_passes_through():
    go, fc = make_go()
    go.move(x=10, y=0, r=5)
    _, params = fc.calls[0]
    assert (params["x"], params["y"], params["r"]) == (10, 0, 5)


def test_drive_for_moves_then_always_stops(monkeypatch):
    from dobotkit.go import magiciango as mod

    slept = []
    monkeypatch.setattr(mod.time, "sleep", lambda s: slept.append(s))
    go, fc = make_go()
    go.drive_for(x=15, seconds=0.4)
    # move -> (sleep) -> emergency_stop (notify) -> confirming stop (call).
    assert fc.calls[0][0] == "MagicianGO.SetMoveSpeed"
    assert fc.calls[0][1]["x"] == 15
    assert slept == [0.4]
    assert fc.notifies[0][0] == "MagicianGO.SetMoveSpeed"
    assert fc.notifies[0][1] == {"portName": "COM5", "x": 0, "y": 0, "r": 0}
    assert fc.calls[-1][1] == {"x": 0, "y": 0, "r": 0, "portName": "COM5"}


def test_drive_for_clamps_duration(monkeypatch):
    from dobotkit.go import magiciango as mod

    slept = []
    monkeypatch.setattr(mod.time, "sleep", lambda s: slept.append(s))
    go, _ = make_go()
    go.drive_for(x=10, seconds=60)
    assert slept == [5.0]


# ---- context manager / open() -----------------------------------------------

def test_context_manager_teardown_on_exception():
    # A crash inside the with-block must still stop the car: fire the no-wait
    # emergency stop (notify) AND issue a confirming blocking stop -- a crashed
    # script must never leave the car driving.
    import pytest

    go, fc = make_go()
    with pytest.raises(RuntimeError):
        with go:
            go.forward(15)
            raise RuntimeError("student code crashed")
    # Emergency stop fired as a fire-and-forget notify.
    assert ("MagicianGO.SetMoveSpeed", {"portName": "COM5", "x": 0, "y": 0, "r": 0}) \
        in fc.notifies
    # A confirming blocking SetMoveSpeed(0,0,0) was also issued (via stop()).
    assert ("MagicianGO.SetMoveSpeed", {"portName": "COM5", "x": 0.0, "y": 0.0, "r": 0.0}) \
        in fc.calls


def test_context_manager_teardown_swallows_errors():
    class ExplodingClient(FakeClient):
        def call(self, method, **params):
            raise RuntimeError("link died")

    go = MagicianGO(ExplodingClient(), port_name="COM5")
    with go:
        pass  # teardown must not raise even though every call explodes


def test_open_connects_verifies_and_owns_client(monkeypatch):
    from dobotkit import link as link_mod

    created = {}

    class StubClient:
        def __init__(self, host="localhost", port=9090, timeout=10.0, **_):
            created["args"] = (host, port, timeout)
            self.fake = FakeClient(
                results={"MagicianGO.GetBatteryVoltage": {"powerVoltage": 11.7}}
            )
            self.closed = False

        def connect(self):
            return self

        def close(self):
            self.closed = True

        def call(self, method, **params):
            return self.fake.call(method, **params)

        def notify(self, method, **params):
            self.fake.notify(method, **params)

    monkeypatch.setattr(link_mod, "DobotLinkClient", StubClient)
    with MagicianGO.open(port_name="COM7", timeout=3.0) as go:
        assert go.port_name == "COM7"
        methods = go._client.fake.methods_called()
        assert methods[0] == "MagicianGO.ConnectDobot"       # connect
        assert "MagicianGO.GetBatteryVoltage" in methods      # link verification
    assert created["args"] == ("localhost", 9090, 3.0)
    assert go._client.closed is True                          # owned socket closed


# ---- adversarial-review regressions (2026-07-03 verification findings) -------

def test_move_nan_refuses_to_drive():
    # Naive max(min(...)) clamping turns NaN into +SPEED_CAP (full speed!)
    # because NaN comparisons are False — non-finite input must map to 0.
    go, fc = make_go()
    go.move(x=float("nan"), y=float("inf"), r=float("-inf"))
    _, params = fc.calls[0]
    assert params["x"] == 0.0
    assert params["y"] == 0.0
    assert params["r"] == 0.0


def test_ultrasonic_nan_returns_none():
    # NaN passes `<= 0` and isinstance(float) checks and would then defeat
    # clearance_ok (`nan < threshold` is False -> reads as clear).
    go, _ = make_go(results={"MagicianGO.GetUltrasoundData":
                             {"front": float("nan"), "back": 35,
                              "left": 35, "right": 35}})
    assert go.ultrasonic() is None


def test_clearance_ok_blocks_on_nan_reading():
    go, _ = make_go(results={"MagicianGO.GetUltrasoundData":
                             {"front": float("nan"), "back": 35,
                              "left": 35, "right": 35}})
    ok, info = go.clearance_ok(x=10, threshold=20)
    assert ok is False


def test_navigation_aborted_is_a_dobot_error():
    # Downstream consumers guard with `except DobotError` — NavigationAborted
    # must be caught by them (dobotkit-gui contract: never raise into the UI).
    from dobotkit.exceptions import DobotError
    from dobotkit.go.navigation import NavigationAborted

    exc = NavigationAborted({"aborted": True, "reason": "x", "target": 1, "achieved": 0})
    assert isinstance(exc, DobotError)
    assert isinstance(exc, RuntimeError)


# ---- connected lifecycle flag -------------------------------------------------

def test_connected_flag_lifecycle():
    # Consumers (e.g. dobotkit-gui's GoController.is_connected) gate device
    # features on go.connected — it must track the connection lifecycle.
    go, fc = make_go(results={"MagicianGO.GetBatteryVoltage": {"powerVoltage": 11.7}})
    assert go.connected is False                 # initial
    go.connect()
    assert go.connected is True                  # after verified connect
    go.disconnect_robot()
    assert go.connected is False                 # after disconnect


def test_connected_flag_reset_when_verify_fails():
    # False-success handshake: ConnectDobot "succeeds" but the battery
    # verification read dies -> the device must NOT report itself connected.
    import pytest

    class DeadLinkClient(FakeClient):
        def call(self, method, **params):
            if method.endswith("GetBatteryVoltage"):
                raise RuntimeError("link dead")
            return super().call(method, **params)

    go = MagicianGO(DeadLinkClient(), port_name="COM5")
    with pytest.raises(RuntimeError):
        go.connect(verify=True)
    assert go.connected is False


def test_connected_flag_cleared_on_context_exit():
    go, fc = make_go(results={"MagicianGO.GetBatteryVoltage": {"powerVoltage": 11.7}})
    go.connect()
    with go:
        assert go.connected is True
    assert go.connected is False                 # session over after teardown
