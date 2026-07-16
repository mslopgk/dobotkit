"""Sensor-feedback navigation primitives for the Magician GO.

The GO's built-in closed-loop commands (``rotate``/``move_dist``/``arc_*``/
``increment_closed_loop``) HANG on this chassis: the firmware queues them with
``isWaitForFinish`` and the completion callback never arrives, so the call
blocks until its (~7-day) timeout. Continuous velocity control (``move``), on
the other hand, works reliably. This module therefore builds its *own* closed
loop out of continuous ``move`` plus odometer/IMU feedback, stopping the car
the moment a target is reached.

:class:`PreciseMover` mirrors the proven reference implementation
(``magiciango_go/precise_move.py``): straight-line / strafe / in-place-turn
primitives that drive at a capped, near-target-decelerated speed until the
measured travel (or turn) reaches the target, then stop.

Heading-source rule (research doc §2.3 / §3.5): **"how far have I turned"** (the
rotation amount measured inside :meth:`PreciseMover.turn_degrees`) is read from
the **IMU yaw** delta — a power-on-referenced absolute angle whose *relative*
change is stable and responsive over a short turn, and it needs no mat-frame
zero. (For absolute mat *heading* you would instead zero the odometer yaw with
:meth:`MagicianGO.set_odometer`; the two references must not be mixed.)

Safety (research doc §8 — a past open-loop test drove into a wall and tripped
the power, so this matters):

* Every control loop has an **absolute wall-clock timeout**
  (:func:`time.monotonic`); it can never spin forever even if the target is
  never reached (``timed_out=True`` in the result).
* Each motion checks :meth:`MagicianGO.clearance_ok` for the intended direction
  *before* moving; if blocked it aborts immediately (``aborted=True`` plus a
  ``reason``).
* Every code path — normal finish, timeout, or exception — ends in
  ``emergency_stop`` (via a ``try/finally``).
* Commanded speed is conservatively capped (``max_speed``) and floored near the
  target (``min_speed``) so a crawl still actually stops.
"""
from __future__ import annotations

import time
from typing import Any, Dict

from dobotkit.exceptions import DobotError
from dobotkit.go.geometry import clamp_speed, yaw_delta

__all__ = ["NavigationAborted", "PreciseMover"]


class NavigationAborted(DobotError, RuntimeError):
    """Raised (opt-in via ``raise_on_abort=True``) when a motion aborts/times out.

    By default the motion primitives report failure only inside their result
    dict (``aborted``/``timed_out``), which beginner code routinely forgets to
    check. Passing ``raise_on_abort=True`` makes failure loud instead. The full
    result dict is available as :attr:`result`.

    Inherits :class:`~dobotkit.exceptions.DobotError` so downstream consumers
    with ``except DobotError`` handlers (e.g. GUI controllers that must never
    let device errors reach the UI thread) catch it without changes.
    """

    def __init__(self, result: Dict[str, Any]) -> None:
        super().__init__(
            f"motion aborted/timed out: {result.get('reason', 'timed out')} "
            f"(target={result.get('target')}, achieved={result.get('achieved')})"
        )
        self.result = result


def _finish(result: Dict[str, Any], raise_on_abort: bool) -> Dict[str, Any]:
    """Return ``result``, or raise :class:`NavigationAborted` when opted in."""
    if raise_on_abort and (result.get("aborted") or result.get("timed_out")):
        raise NavigationAborted(result)
    return result

#: Control-loop period (seconds) between successive sensor read + move commands.
LOOP_DT: float = 0.05

#: Final fraction of the move/turn over which speed is proportionally tapered
#: down toward ``min_speed`` to limit overshoot near the target.
SLOW_BAND: float = 0.30

#: Stall guard (hardware incident 2026-07-03: the car pressed a wall for the
#: full timeout): if the measured progress advances less than ``STALL_EPS``
#: for ``STALL_WINDOW_S`` seconds while a velocity is commanded, the motion
#: aborts as a suspected collision instead of pushing until timeout.
STALL_WINDOW_S: float = 1.0
STALL_EPS_MM: float = 3.0    # translation progress epsilon (mm)
STALL_EPS_DEG: float = 2.0   # rotation progress epsilon (degrees)

#: Period (seconds) between mid-move clearance re-checks during travel.
RECHECK_S: float = 0.25

# Anything exposing the MagicianGO method surface used here (move/forward/spin/
# odometer/imu_angle/ultrasonic/clearance_ok/stop/emergency_stop/set_odometer).
GoLike = Any


class PreciseMover:
    """Odometer/IMU-feedback closed-loop motion primitives over continuous ``move``.

    Builds a software closed loop on top of the GO's reliable continuous
    velocity control: command a velocity, sample the odometer (translation) or
    IMU (rotation) each tick, and stop the instant the measured travel reaches
    the target. Speed is capped into ``[min_speed, max_speed]`` and tapered down
    over the final :data:`SLOW_BAND` of the move to limit overshoot.

    Args:
        go: A :class:`~dobotkit.go.magiciango.MagicianGO` (or any object with the
            same ``move``/``odometer``/``imu_angle``/``ultrasonic``/
            ``clearance_ok``/``stop``/``emergency_stop`` surface).
        max_speed: Absolute upper cap on commanded speed magnitude. Defaults to
            ``30`` (the conservative safety cap from the reference).
        min_speed: Lower floor on commanded speed magnitude near the target, so a
            slowing crawl still moves enough to finish. Defaults to ``8``.
    """

    def __init__(self, go: GoLike, max_speed: float = 30, min_speed: float = 8) -> None:
        self.go = go
        self.max_speed = float(max_speed)
        self.min_speed = float(min_speed)

    # ---- internal helpers --------------------------------------------------

    def _profiled_speed(self, remaining: float, total: float, base_speed: float) -> float:
        """Commanded speed *magnitude* with ``remaining`` (absolute) left to go.

        Over the final :data:`SLOW_BAND` fraction of the move the speed is
        proportionally tapered toward ``min_speed`` (precision / overshoot
        guard). The result is always clamped into ``[min_speed, max_speed]``.
        """
        base = min(abs(base_speed), self.max_speed)
        band = max(abs(total) * SLOW_BAND, 1e-6)
        if remaining < band:
            scaled = base * (remaining / band)
            return max(min(scaled, base), self.min_speed)
        return max(base, self.min_speed)

    def _settle_stop(self) -> None:
        """Stop for sure: fire-and-forget ``emergency_stop``, then a confirming ``stop``.

        ``emergency_stop`` is a no-wait notify, so a follow-up blocking ``stop``
        confirms the car actually halted; if that confirming read fails the
        emergency stop is re-fired.
        """
        self.go.emergency_stop()
        try:
            self.go.stop()
        except Exception:  # noqa: BLE001 -- any link error -> re-fire the safe stop
            self.go.emergency_stop()

    # ---- straight-line / strafe travel -------------------------------------

    def goto_distance(
        self,
        distance_mm: float,
        speed: float = 25,
        axis: str = "x",
        threshold: float = 20,
        timeout_s: float = 8.0,
        raise_on_abort: bool = False,
    ) -> Dict[str, Any]:
        """Travel ``|distance_mm|`` along ``axis`` then stop; the sign sets direction.

        ``axis="x"`` is forward/back (``+`` forward); ``axis="y"`` is strafe
        (``+`` left). The odometer is **not** reset — it stays in whatever
        (mat/world) frame an outer caller (e.g. :class:`WaypointNav`) has zeroed
        it to. Because the GO odometer is a world-frame, yaw-aware integral,
        travel is measured as the straight-line displacement magnitude
        ``hypot(dx, dy)`` from the start pose and the move stops once that
        reaches ``|distance_mm|``. Speed tapers near the target. Safety, in
        layers (the pre-check alone proved insufficient on hardware): the
        intended direction is clearance-checked **before** moving, re-checked
        every :data:`RECHECK_S` seconds **during** the move, and a stall guard
        aborts if the odometer stops advancing for :data:`STALL_WINDOW_S`
        seconds while a velocity is commanded (suspected collision).

        .. note:: **Unit boundary.** This primitive works in **millimetres**
            (odometer units); :class:`WaypointNav` works in **centimetres**
            (mat/SDK units) and converts only at its own boundary. Speed units
            are firmware-defined and unconfirmed — 8..30 is the practical range.

        Args:
            distance_mm: Signed target distance in **millimetres**.
            speed: Base speed magnitude (capped into ``[min_speed, max_speed]``;
                units unconfirmed, 8..30 practical).
            axis: ``"x"`` (forward/back) or ``"y"`` (strafe left/right).
            threshold: Minimum required clearance (cm) ahead before moving.
            timeout_s: Absolute wall-clock safety timeout (seconds).
            raise_on_abort: When ``True``, raise :class:`NavigationAborted`
                instead of returning an ``aborted``/``timed_out`` result dict —
                use this to make failures loud in beginner/teaching code.

        Returns:
            ``{target, achieved, error, axis, timed_out, aborted}``. When the
            clearance check blocks the move, ``aborted`` is ``True`` and a
            ``reason`` key is added; ``error = target - achieved``.
        """
        if axis not in ("x", "y"):
            raise ValueError("axis must be 'x' or 'y'")

        direction = 0.0 if distance_mm == 0 else (1.0 if distance_mm > 0 else -1.0)
        base = clamp_speed(speed, self.min_speed, self.max_speed)
        result: Dict[str, Any] = {
            "target": float(distance_mm),
            "achieved": 0.0,
            "error": float(distance_mm),
            "axis": axis,
            "timed_out": False,
            "aborted": False,
        }

        # Pre-check clearance in the intended direction of travel.
        cx = direction * base if axis == "x" else 0.0
        cy = direction * base if axis == "y" else 0.0
        ok, info = self.go.clearance_ok(x=cx, y=cy, threshold=threshold)
        if not ok:
            result["aborted"] = True
            result["reason"] = f"clearance blocked: {info}"
            return _finish(result, raise_on_abort)

        try:
            start = self.go.odometer()
            now = time.monotonic()
            deadline = now + timeout_s
            traveled = 0.0
            # Stall guard state (hardware incident 2026-07-03: the car pressed
            # into a wall for the full timeout because nothing watched progress).
            best_progress = 0.0
            progress_t = now
            recheck_t = now
            while True:
                now = time.monotonic()
                if now >= deadline:
                    result["timed_out"] = True
                    break
                odo = self.go.odometer()
                # World-frame odometer: progress = displacement magnitude from
                # the start pose (direction-agnostic), re-signed by direction.
                dist = (
                    (odo["x"] - start["x"]) ** 2 + (odo["y"] - start["y"]) ** 2
                ) ** 0.5
                traveled = direction * dist
                remaining = abs(distance_mm) - abs(traveled)
                if remaining <= 0:
                    break
                # Stall guard: wheels commanded but odometer frozen -> the car
                # is most likely pressing an obstacle (or wedged). Stop pushing.
                if abs(traveled) > best_progress + STALL_EPS_MM:
                    best_progress = abs(traveled)
                    progress_t = now
                elif now - progress_t >= STALL_WINDOW_S:
                    result["aborted"] = True
                    result["reason"] = (
                        f"stall: no odometer progress for {STALL_WINDOW_S:.1f}s "
                        f"while driving (collision?)"
                    )
                    break
                # Mid-move clearance recheck: the pre-check alone cannot see an
                # obstacle entering the path (or sensor offset error) once moving.
                if now - recheck_t >= RECHECK_S:
                    recheck_t = now
                    ok, info = self.go.clearance_ok(x=cx, y=cy, threshold=threshold)
                    if not ok:
                        result["aborted"] = True
                        result["reason"] = f"clearance lost mid-move: {info}"
                        break
                v = self._profiled_speed(remaining, distance_mm, base) * direction
                if axis == "x":
                    self.go.move(x=v)
                else:
                    self.go.move(y=v)
                time.sleep(LOOP_DT)
            result["achieved"] = float(traveled)
            result["error"] = float(distance_mm) - float(traveled)
        finally:
            self._settle_stop()
        return _finish(result, raise_on_abort)

    # ---- in-place rotation -------------------------------------------------

    def turn_degrees(
        self,
        deg: float,
        speed: float = 25,
        threshold: float = 20,
        timeout_s: float = 8.0,
        raise_on_abort: bool = False,
    ) -> Dict[str, Any]:
        """Turn in place by ``deg`` then stop; the sign sets direction (``r+`` = CCW).

        Records the start IMU yaw and stops once the IMU yaw change (with +-180
        wraparound handling) reaches ``|deg|``. The rotation amount is measured
        from the **IMU** yaw delta (a stable *relative* change), distinct from
        the odometer yaw used for absolute mat heading. All-around clearance is
        checked before turning.

        Args:
            deg: Signed target turn in degrees (``+`` = CCW / left).
            speed: Base angular speed magnitude (capped into ``[min, max]``;
                units unconfirmed, 8..30 practical).
            threshold: Minimum required clearance (cm) all around before turning.
            timeout_s: Absolute wall-clock safety timeout (seconds).
            raise_on_abort: When ``True``, raise :class:`NavigationAborted`
                instead of returning an ``aborted``/``timed_out`` result dict.

        Returns:
            ``{target, achieved, error, timed_out, aborted}``. When the clearance
            check blocks the turn, ``aborted`` is ``True`` and a ``reason`` key is
            added; ``error = target - achieved``.
        """
        direction = 0.0 if deg == 0 else (1.0 if deg > 0 else -1.0)
        base = clamp_speed(speed, self.min_speed, self.max_speed)
        result: Dict[str, Any] = {
            "target": float(deg),
            "achieved": 0.0,
            "error": float(deg),
            "timed_out": False,
            "aborted": False,
        }

        ok, info = self.go.clearance_ok(r=direction * base, threshold=threshold)
        if not ok:
            result["aborted"] = True
            result["reason"] = f"clearance blocked: {info}"
            return _finish(result, raise_on_abort)

        try:
            start_yaw = self.go.imu_angle()["yaw"]
            now = time.monotonic()
            deadline = now + timeout_s
            turned = 0.0
            best_progress = 0.0
            progress_t = now
            while True:
                now = time.monotonic()
                if now >= deadline:
                    result["timed_out"] = True
                    break
                cur_yaw = self.go.imu_angle()["yaw"]
                # Rotation amount = IMU yaw delta (current - start), +-180 wrapped.
                turned = yaw_delta(cur_yaw, start_yaw)
                remaining = abs(deg) - abs(turned)
                if remaining <= 0:
                    break
                # Stall guard: commanded to spin but the IMU is frozen -> the
                # chassis is most likely wedged. Stop pushing.
                if abs(turned) > best_progress + STALL_EPS_DEG:
                    best_progress = abs(turned)
                    progress_t = now
                elif now - progress_t >= STALL_WINDOW_S:
                    result["aborted"] = True
                    result["reason"] = (
                        f"stall: no IMU progress for {STALL_WINDOW_S:.1f}s "
                        f"while turning (wedged?)"
                    )
                    break
                v = self._profiled_speed(remaining, deg, base) * direction
                self.go.move(r=v)
                time.sleep(LOOP_DT)
            result["achieved"] = float(turned)
            result["error"] = float(deg) - float(turned)
        finally:
            self._settle_stop()
        return _finish(result, raise_on_abort)
