"""Tests for ``dobotkit.go.navigation`` — ``PreciseMover`` (feedback motion).

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
from dobotkit.go.navigation import PreciseMover

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



def test_goto_distance_raise_on_abort_on_clearance_block():
    import pytest

    from dobotkit.go.navigation import NavigationAborted, PreciseMover

    go = SimulatedGo(clearances={"front": 5.0, "back": 100.0,
                                 "left": 100.0, "right": 100.0})
    mover = PreciseMover(go)
    # Default behaviour is unchanged: a quiet result dict.
    res = mover.goto_distance(100, speed=20, threshold=20)
    assert res["aborted"] is True
    # Opt-in behaviour: loud failure carrying the same result dict.
    with pytest.raises(NavigationAborted) as excinfo:
        mover.goto_distance(100, speed=20, threshold=20, raise_on_abort=True)
    assert excinfo.value.result["aborted"] is True
    assert "clearance" in excinfo.value.result["reason"]


def test_turn_degrees_raise_on_abort_on_clearance_block():
    import pytest

    from dobotkit.go.navigation import NavigationAborted, PreciseMover

    go = SimulatedGo(clearances={"front": 5.0, "back": 5.0,
                                 "left": 5.0, "right": 5.0})
    with pytest.raises(NavigationAborted):
        PreciseMover(go).turn_degrees(90, speed=20, threshold=20,
                                      raise_on_abort=True)



# ---- stall guard / mid-move clearance recheck (hardware incident 2026-07-03) --

def _advancing_clock(monkeypatch, clock, step):
    """sleep() advances the fake clock by ``step`` seconds per loop iteration."""
    monkeypatch.setattr(navigation.time, "sleep", lambda *_a, **_k: clock.advance(step))


def test_goto_distance_stall_aborts_before_timeout(monkeypatch):
    # The car pressed into a wall: wheels commanded, odometer frozen. The stall
    # guard must abort within ~STALL_WINDOW_S instead of pushing until timeout.
    clock = FakeClock()
    _patch_time(monkeypatch, clock)
    _advancing_clock(monkeypatch, clock, 0.3)
    go = SimulatedGo(dist_per_tick=0.0)   # never advances = stalled against wall
    mover = PreciseMover(go)

    res = mover.goto_distance(200, speed=15, axis="x", timeout_s=10.0)

    assert res["aborted"] is True
    assert "stall" in res["reason"]
    assert res["timed_out"] is False       # aborted long before the 10 s timeout
    assert go.emergency_stops >= 1         # and the car was stopped


def test_turn_degrees_stall_aborts(monkeypatch):
    clock = FakeClock()
    _patch_time(monkeypatch, clock)
    _advancing_clock(monkeypatch, clock, 0.3)
    go = SimulatedGo(deg_per_tick=0.0)     # wedged: IMU never advances
    mover = PreciseMover(go)

    res = mover.turn_degrees(90, speed=15, timeout_s=10.0)

    assert res["aborted"] is True
    assert "stall" in res["reason"]
    assert go.emergency_stops >= 1


def test_goto_distance_aborts_when_clearance_lost_mid_move(monkeypatch):
    # An obstacle appearing (or a sensor-offset error) after the pre-check must
    # stop the move at the next mid-move recheck, not at the destination.
    clock = FakeClock()
    _patch_time(monkeypatch, clock)
    _advancing_clock(monkeypatch, clock, 0.3)

    class BlockedMidwayGo(SimulatedGo):
        def __init__(self):
            super().__init__(dist_per_tick=1.0)
            self._reads = 0

        def ultrasonic(self):
            self._reads += 1
            if self._reads > 2:            # clear at pre-check, blocked after
                return {"front": 5.0, "back": 40.0, "left": 40.0, "right": 40.0}
            return super().ultrasonic()

    go = BlockedMidwayGo()
    mover = PreciseMover(go)

    res = mover.goto_distance(500, speed=15, axis="x", timeout_s=10.0)

    assert res["aborted"] is True
    assert "clearance lost mid-move" in res["reason"]
    assert abs(res["achieved"]) < 500      # stopped well short of the target
    assert go.emergency_stops >= 1
