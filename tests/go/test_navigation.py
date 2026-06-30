"""Tests for ``dobotkit.go.navigation`` — ``PreciseMover`` and ``WaypointNav``.

These exercise the software closed loop (continuous ``move`` + odometer/IMU
feedback) without any socket or real device, using the ``SimulatedGo`` double
from ``tests/go/conftest.py``. ``SimulatedGo`` latches a commanded velocity on
``move`` and advances its integrating odometer/IMU pose by one tick on every
sensor read, so a feedback loop sampling it repeatedly converges exactly like
the real chassis.

Two things are monkeypatched on the ``navigation`` module's ``time`` so the
loops are deterministic and fast:

* ``time.sleep`` -> no-op (the loop period must not actually wait).
* ``time.monotonic`` -> a controllable fake clock so a test can either freeze it
  (target reached well within the timeout) or make it leap past the deadline
  (forcing ``timed_out=True``).

The behaviours pinned down (per research doc §6-7): reaching the target stops
within tolerance; a clearance-blocked direction returns ``aborted=True`` with a
``reason``; a never-reached target trips the absolute timeout
(``timed_out=True``); and every path ends in ``emergency_stop``.
"""
from __future__ import annotations

import dobotkit.go.navigation as navigation
from dobotkit.go.navigation import PreciseMover, WaypointNav

from .conftest import SimulatedGo


# --------------------------------------------------------------------------
# Test plumbing: deterministic clock + no-wait sleep on the navigation module.
# --------------------------------------------------------------------------
class FakeClock:
    """A controllable monotonic clock substituted into the navigation module.

    ``now`` is returned verbatim by ``monotonic()`` and only changes when a test
    moves it, so loops never trip their wall-clock deadline unless asked to.
    """

    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, dt: float) -> None:
        self.now += dt


def _patch_time(monkeypatch, clock: FakeClock) -> None:
    """Freeze ``time.sleep`` and route ``time.monotonic`` through ``clock``."""
    monkeypatch.setattr(navigation.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(navigation.time, "monotonic", clock.monotonic)


# ==========================================================================
# PreciseMover.goto_distance
# ==========================================================================
def test_goto_distance_reaches_target_and_stops(monkeypatch):
    clock = FakeClock()
    _patch_time(monkeypatch, clock)
    go = SimulatedGo(dist_per_tick=1.0)  # 1 mm per speed-unit per read
    mover = PreciseMover(go)

    res = mover.goto_distance(50, speed=25, axis="x", timeout_s=8.0)

    assert res["aborted"] is False
    assert res["timed_out"] is False
    # World-frame displacement reaches the +50 mm target (loop stops at >= 0 remaining).
    assert res["achieved"] >= 50.0
    assert abs(res["error"]) <= 1.0  # error = target - achieved, within ~one tick
    assert res["axis"] == "x"
    # Every path must end in an emergency stop (settle_stop fires it).
    assert go.emergency_stops >= 1


def test_goto_distance_negative_direction(monkeypatch):
    clock = FakeClock()
    _patch_time(monkeypatch, clock)
    go = SimulatedGo(dist_per_tick=1.0)
    mover = PreciseMover(go)

    res = mover.goto_distance(-30, speed=20, axis="x", timeout_s=8.0)

    assert res["aborted"] is False
    assert res["timed_out"] is False
    # Travel is re-signed by direction: a backward move yields negative achieved.
    assert res["achieved"] <= -30.0
    # The car was actually commanded backward (negative vx) at least once.
    assert any(vx < 0 for vx, _vy, _vr in go.moves)
    assert go.emergency_stops >= 1


def test_goto_distance_strafe_axis_y(monkeypatch):
    clock = FakeClock()
    _patch_time(monkeypatch, clock)
    go = SimulatedGo(dist_per_tick=1.0)
    mover = PreciseMover(go)

    res = mover.goto_distance(40, speed=20, axis="y", timeout_s=8.0)

    assert res["aborted"] is False
    assert res["timed_out"] is False
    assert res["axis"] == "y"
    assert res["achieved"] >= 40.0
    # A strafe commands vy, never vx.
    assert all(vx == 0 for vx, _vy, _vr in go.moves)
    assert any(vy > 0 for _vx, vy, _vr in go.moves)


def test_goto_distance_clearance_blocked_aborts(monkeypatch):
    clock = FakeClock()
    _patch_time(monkeypatch, clock)
    # Front blocked (< threshold): a forward move must abort before driving.
    go = SimulatedGo(clearances={"front": 5.0, "back": 100.0, "left": 100.0, "right": 100.0})
    mover = PreciseMover(go)

    res = mover.goto_distance(50, speed=25, axis="x", threshold=20, timeout_s=8.0)

    assert res["aborted"] is True
    assert "reason" in res
    assert "clearance blocked" in res["reason"]
    assert "front" in res["reason"]
    # Aborted before the loop -> the car was never commanded to move.
    assert go.moves == []


def test_goto_distance_times_out(monkeypatch):
    clock = FakeClock()
    _patch_time(monkeypatch, clock)
    # dist_per_tick=0 -> reading the odometer never advances position, so the
    # target is unreachable and only the absolute wall-clock timeout stops it.
    go = SimulatedGo(dist_per_tick=0.0)
    mover = PreciseMover(go)

    # Each loop iteration's sleep is a no-op, so advance the fake clock from
    # inside it to guarantee the deadline is crossed.
    real_noop = navigation.time.sleep

    def advancing_sleep(*_a, **_k):
        clock.advance(10.0)  # leap past any reasonable timeout
        return real_noop()

    monkeypatch.setattr(navigation.time, "sleep", advancing_sleep)

    res = mover.goto_distance(100, speed=25, axis="x", timeout_s=2.0)

    assert res["timed_out"] is True
    assert res["aborted"] is False
    assert res["achieved"] == 0.0  # never moved
    assert go.emergency_stops >= 1  # still stops on the way out


# ==========================================================================
# PreciseMover.turn_degrees
# ==========================================================================
def test_turn_degrees_reaches_target_and_stops(monkeypatch):
    clock = FakeClock()
    _patch_time(monkeypatch, clock)
    go = SimulatedGo(deg_per_tick=1.0)  # 1 deg per speed-unit per read
    mover = PreciseMover(go)

    res = mover.turn_degrees(45, speed=20, timeout_s=8.0)

    assert res["aborted"] is False
    assert res["timed_out"] is False
    assert res["achieved"] >= 45.0  # measured via IMU yaw delta
    # Discrete simulation overshoots by at most one floor step (min_speed/tick).
    assert abs(res["error"]) <= mover.min_speed
    # Turning commands vr (rotation), positive for a CCW (+) turn.
    assert any(vr > 0 for _vx, _vy, vr in go.moves)
    assert go.emergency_stops >= 1


def test_turn_degrees_negative_direction(monkeypatch):
    clock = FakeClock()
    _patch_time(monkeypatch, clock)
    go = SimulatedGo(deg_per_tick=1.0)
    mover = PreciseMover(go)

    res = mover.turn_degrees(-30, speed=20, timeout_s=8.0)

    assert res["aborted"] is False
    assert res["timed_out"] is False
    assert res["achieved"] <= -30.0
    assert any(vr < 0 for _vx, _vy, vr in go.moves)


def test_turn_degrees_clearance_blocked_aborts(monkeypatch):
    clock = FakeClock()
    _patch_time(monkeypatch, clock)
    # In-place rotation requires all-around clearance; one near side blocks it.
    go = SimulatedGo(clearances={"front": 100.0, "back": 100.0, "left": 5.0, "right": 100.0})
    mover = PreciseMover(go)

    res = mover.turn_degrees(90, speed=20, threshold=20, timeout_s=8.0)

    assert res["aborted"] is True
    assert "reason" in res
    assert "clearance blocked" in res["reason"]
    assert "around" in res["reason"]
    assert go.moves == []


def test_turn_degrees_times_out(monkeypatch):
    clock = FakeClock()
    _patch_time(monkeypatch, clock)
    go = SimulatedGo(deg_per_tick=0.0)  # IMU never advances -> unreachable
    mover = PreciseMover(go)

    real_noop = navigation.time.sleep

    def advancing_sleep(*_a, **_k):
        clock.advance(10.0)
        return real_noop()

    monkeypatch.setattr(navigation.time, "sleep", advancing_sleep)

    res = mover.turn_degrees(90, speed=20, timeout_s=2.0)

    assert res["timed_out"] is True
    assert res["aborted"] is False
    assert res["achieved"] == 0.0
    assert go.emergency_stops >= 1


def test_turn_degrees_handles_yaw_wraparound(monkeypatch):
    clock = FakeClock()
    _patch_time(monkeypatch, clock)
    # Start near +180 so a CCW turn crosses the +-180 seam; yaw_delta must keep
    # the measured travel monotonic (not jump by 360).
    go = SimulatedGo(yaw=170.0, deg_per_tick=1.0)
    mover = PreciseMover(go)

    res = mover.turn_degrees(30, speed=20, timeout_s=8.0)

    assert res["timed_out"] is False
    # The +-180 seam must not corrupt the measured travel: yaw_delta keeps it
    # continuous, so the turn reaches +30 and stops just past it (overshoot
    # bounded by one commanded step) rather than reporting a ~360 jump.
    assert 30.0 <= res["achieved"] < 360.0


# ==========================================================================
# WaypointNav: set_start / pose_cm
# ==========================================================================
def test_set_start_zeros_odometer_to_mat_cm(monkeypatch):
    clock = FakeClock()
    _patch_time(monkeypatch, clock)
    go = SimulatedGo()
    nav = WaypointNav(go)

    echoed = nav.set_start(100, 48, heading_deg=0.0)

    assert echoed == {"x_cm": 100.0, "y_cm": 48.0, "heading_deg": 0.0}
    # Odometer was set in mm (cm * 10), yaw in degrees.
    assert go.set_odometer_calls[-1] == (1000.0, 480.0, 0.0)


def test_pose_cm_converts_mm_to_cm(monkeypatch):
    clock = FakeClock()
    _patch_time(monkeypatch, clock)
    go = SimulatedGo(x=1000.0, y=480.0, yaw=0.0)  # mm
    nav = WaypointNav(go)

    pose = nav.pose_cm()

    assert pose["x_cm"] == 100.0
    assert pose["y_cm"] == 48.0
    assert pose["heading_deg"] == 0.0


# ==========================================================================
# WaypointNav.face
# ==========================================================================
def test_face_turns_to_absolute_heading(monkeypatch):
    clock = FakeClock()
    _patch_time(monkeypatch, clock)
    go = SimulatedGo(yaw=0.0, deg_per_tick=1.0)
    nav = WaypointNav(go)

    res = nav.face(90, speed=20, timeout_s=8.0)

    # face() augments the turn result with the requested + starting headings.
    assert res["bearing"] == 90.0
    assert res["from_heading"] == 0.0
    # Turned ~90 deg CCW (positive vr commanded).
    assert any(vr > 0 for _vx, _vy, vr in go.moves)
    assert res["timed_out"] is False
    assert go.emergency_stops >= 1


def test_face_shortest_turn_is_negative_when_target_behind_right(monkeypatch):
    clock = FakeClock()
    _patch_time(monkeypatch, clock)
    # Facing +90 already, asked to face 0 -> shortest turn is -90 (CW).
    go = SimulatedGo(yaw=90.0, deg_per_tick=1.0)
    nav = WaypointNav(go)

    res = nav.face(0, speed=20, timeout_s=8.0)

    assert res["bearing"] == 0.0
    assert res["from_heading"] == 90.0
    assert res["target"] == -90.0  # turn_degrees target = yaw_delta(0, 90)
    assert any(vr < 0 for _vx, _vy, vr in go.moves)


# ==========================================================================
# WaypointNav.go_to
# ==========================================================================
def test_go_to_reaches_waypoint_within_tolerance(monkeypatch):
    clock = FakeClock()
    _patch_time(monkeypatch, clock)
    # Already facing +X (heading 0); target is straight ahead in +X.
    go = SimulatedGo(dist_per_tick=1.0, deg_per_tick=1.0)
    nav = WaypointNav(go)
    nav.set_start(0, 0, heading_deg=0.0)

    res = nav.go_to(12, 0, speed=20, arrive_tol_cm=2.0, max_iters=3)

    assert res["arrived"] is True
    assert res["residual_cm"] <= 2.0
    assert res["target"] == {"x_cm": 12.0, "y_cm": 0.0}
    assert len(res["legs"]) >= 1
    # Each recorded leg carries the navigation breakdown.
    leg = res["legs"][0]
    assert set(leg) == {"iter", "bearing", "dist_cm", "turn", "move"}
    assert go.emergency_stops >= 1


def test_go_to_already_at_target_arrives_immediately(monkeypatch):
    clock = FakeClock()
    _patch_time(monkeypatch, clock)
    go = SimulatedGo(dist_per_tick=1.0, deg_per_tick=1.0)
    nav = WaypointNav(go)
    nav.set_start(50, 50, heading_deg=0.0)

    res = nav.go_to(50, 50, arrive_tol_cm=2.0, max_iters=3)

    assert res["arrived"] is True
    assert res["residual_cm"] <= 2.0
    assert res["legs"] == []  # within tolerance on the first measure -> no legs
    # No drive commands were issued.
    assert go.moves == []


def test_go_to_aborts_when_path_blocked(monkeypatch):
    clock = FakeClock()
    _patch_time(monkeypatch, clock)
    # Front blocked: the straight-line leg toward +X aborts on clearance.
    go = SimulatedGo(
        dist_per_tick=1.0,
        deg_per_tick=1.0,
        clearances={"front": 5.0, "back": 100.0, "left": 100.0, "right": 100.0},
    )
    nav = WaypointNav(go)
    nav.set_start(0, 0, heading_deg=0.0)

    res = nav.go_to(30, 0, speed=20, arrive_tol_cm=2.0, max_iters=3)

    assert res["arrived"] is False
    # The move leg reports the abort with a reason and the loop stopped early.
    assert len(res["legs"]) == 1
    assert res["legs"][0]["move"]["aborted"] is True
    assert "clearance blocked" in res["legs"][0]["move"]["reason"]
