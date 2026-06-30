"""Sensor-feedback navigation primitives for the Magician GO.

The GO's built-in closed-loop commands (``rotate``/``move_dist``/``arc_*``/
``increment_closed_loop``) HANG on this chassis: the firmware queues them with
``isWaitForFinish`` and the completion callback never arrives, so the call
blocks until its (~7-day) timeout. Continuous velocity control (``move``), on
the other hand, works reliably. This module therefore builds its *own* closed
loop out of continuous ``move`` plus odometer/IMU feedback, stopping the car
the moment a target is reached.

Two layers, mirroring the proven reference implementations
(``magiciango_go/precise_move.py`` and ``waypoint_nav.py``):

* :class:`PreciseMover` — straight-line / strafe / in-place-turn primitives that
  drive at a capped, near-target-decelerated speed until the measured travel (or
  turn) reaches the target, then stop.
* :class:`WaypointNav` — absolute mat-coordinate waypoint navigation layered on
  top of :class:`PreciseMover`: zero the odometer to the mat frame, then
  repeatedly measure pose, face the target bearing, and drive to it.

Heading-source rule (research doc §2.3 / §3.5 — they have **different**
references, so they must not be mixed):

* **"Which way am I facing"** (the current absolute mat heading, used by
  :meth:`WaypointNav.pose_cm`) is read from the **odometer yaw**, because
  :meth:`MagicianGO.set_odometer` is the only thing that zeroes a yaw source to
  the mat frame.
* **"How far have I turned"** (the rotation amount measured inside
  :meth:`PreciseMover.turn_degrees`) is read from the **IMU yaw** delta: it is a
  power-on-referenced absolute angle whose *relative* change is stable and
  responsive over a short turn, and it needs no mat-frame zero.

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
from typing import Any, Dict, Optional

from dobotkit.go.geometry import bearing, clamp_speed, cm_to_mm, mm_to_cm, yaw_delta

__all__ = ["PreciseMover", "WaypointNav"]

#: Control-loop period (seconds) between successive sensor read + move commands.
LOOP_DT: float = 0.05

#: Final fraction of the move/turn over which speed is proportionally tapered
#: down toward ``min_speed`` to limit overshoot near the target.
SLOW_BAND: float = 0.30

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
    ) -> Dict[str, Any]:
        """Travel ``|distance_mm|`` along ``axis`` then stop; the sign sets direction.

        ``axis="x"`` is forward/back (``+`` forward); ``axis="y"`` is strafe
        (``+`` left). The odometer is **not** reset — it stays in whatever
        (mat/world) frame an outer caller (e.g. :class:`WaypointNav`) has zeroed
        it to. Because the GO odometer is a world-frame, yaw-aware integral,
        travel is measured as the straight-line displacement magnitude
        ``hypot(dx, dy)`` from the start pose and the move stops once that
        reaches ``|distance_mm|``. Speed tapers near the target; the intended
        direction is clearance-checked first.

        Args:
            distance_mm: Signed target distance in millimetres.
            speed: Base speed magnitude (capped into ``[min_speed, max_speed]``).
            axis: ``"x"`` (forward/back) or ``"y"`` (strafe left/right).
            threshold: Minimum required clearance (cm) ahead before moving.
            timeout_s: Absolute wall-clock safety timeout (seconds).

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
            return result

        try:
            start = self.go.odometer()
            deadline = time.monotonic() + timeout_s
            traveled = 0.0
            while True:
                if time.monotonic() >= deadline:
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
        return result

    # ---- in-place rotation -------------------------------------------------

    def turn_degrees(
        self,
        deg: float,
        speed: float = 25,
        threshold: float = 20,
        timeout_s: float = 8.0,
    ) -> Dict[str, Any]:
        """Turn in place by ``deg`` then stop; the sign sets direction (``r+`` = CCW).

        Records the start IMU yaw and stops once the IMU yaw change (with +-180
        wraparound handling) reaches ``|deg|``. The rotation amount is measured
        from the **IMU** yaw delta (a stable *relative* change), distinct from
        the odometer yaw used for absolute mat heading. All-around clearance is
        checked before turning.

        Args:
            deg: Signed target turn in degrees (``+`` = CCW / left).
            speed: Base angular speed magnitude (capped into ``[min, max]``).
            threshold: Minimum required clearance (cm) all around before turning.
            timeout_s: Absolute wall-clock safety timeout (seconds).

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
            return result

        try:
            start_yaw = self.go.imu_angle()["yaw"]
            deadline = time.monotonic() + timeout_s
            turned = 0.0
            while True:
                if time.monotonic() >= deadline:
                    result["timed_out"] = True
                    break
                cur_yaw = self.go.imu_angle()["yaw"]
                # Rotation amount = IMU yaw delta (current - start), +-180 wrapped.
                turned = yaw_delta(cur_yaw, start_yaw)
                remaining = abs(deg) - abs(turned)
                if remaining <= 0:
                    break
                v = self._profiled_speed(remaining, deg, base) * direction
                self.go.move(r=v)
                time.sleep(LOOP_DT)
            result["achieved"] = float(turned)
            result["error"] = float(deg) - float(turned)
        finally:
            self._settle_stop()
        return result


class WaypointNav:
    """Absolute mat-coordinate waypoint navigation layered on :class:`PreciseMover`.

    The GO odometer ``(x, y, yaw)`` is a planar pose frozen at the last
    :meth:`~dobotkit.go.magiciango.MagicianGO.set_odometer` call, so zeroing it
    to a known mat start point makes the odometer read out *mat coordinates*.
    Navigation then drives toward absolute mat ``(x, y)`` targets.

    Coordinate / unit convention (applied consistently throughout):

    * Mat coordinates are centimetres (same as the SDK position values); the
      underlying :class:`PreciseMover` primitives work in millimetres, so the
      cm<->mm conversion (x10 / /10) happens **only** here.
    * ``x+`` = forward (the direction heading ``0deg`` points), ``y+`` = strafe
      left (odometer convention).
    * ``heading_deg`` is the absolute mat bearing: ``0deg`` faces ``+X``,
      counter-clockwise positive — matching ``atan2(dy, dx)`` and ``r+`` = CCW.
    * Target bearing = ``atan2(dy, dx)`` deg; turn amount = ``yaw_delta(bearing,
      current_heading)``.

    Args:
        go: A :class:`~dobotkit.go.magiciango.MagicianGO` (or compatible object).
        mover: An optional pre-built :class:`PreciseMover`; one is created
            wrapping ``go`` if omitted.
    """

    def __init__(self, go: GoLike, mover: Optional[PreciseMover] = None) -> None:
        self.go = go
        self.mover = mover if mover is not None else PreciseMover(go)
        self._heading = 0.0  # last recorded mat heading (deg)

    # ---- start pose: zero the odometer to mat coordinates ------------------

    def set_start(self, x_cm: float, y_cm: float, heading_deg: float = 0.0) -> Dict[str, float]:
        """Declare the GO's current mat pose as ``(x_cm, y_cm, heading_deg)``.

        Sets the odometer to this value (cm -> mm) so subsequent
        :meth:`pose_cm` reads return mat coordinates, and seeds the yaw with the
        heading. Note: these values must match the GO's *actual* position/heading
        on the mat for navigation to be correct (human calibration required).

        Returns:
            ``{x_cm, y_cm, heading_deg}`` echoing the declared start pose.
        """
        self.go.set_odometer(cm_to_mm(x_cm), cm_to_mm(y_cm), float(heading_deg))
        self._heading = float(heading_deg)
        return {
            "x_cm": float(x_cm),
            "y_cm": float(y_cm),
            "heading_deg": float(heading_deg),
        }

    # ---- current pose (cm) -------------------------------------------------

    def pose_cm(self) -> Dict[str, float]:
        """Return the current mat pose ``{x_cm, y_cm, heading_deg}``.

        Converts the odometer ``x``/``y`` (mm) to cm. The heading is the
        **odometer yaw** — the only source zeroed to the mat frame by
        :meth:`set_start`. The IMU yaw is a power-on-referenced absolute angle
        unrelated to ``set_start`` (measured >=24deg off in practice) and must
        **not** be used here.
        """
        odo = self.go.odometer()
        heading = odo.get("yaw", self._heading)
        self._heading = float(heading)
        return {
            "x_cm": mm_to_cm(odo["x"]),
            "y_cm": mm_to_cm(odo["y"]),
            "heading_deg": float(heading),
        }

    # ---- rotate to an absolute heading -------------------------------------

    def face(
        self,
        heading_deg: float,
        speed: float = 25,
        threshold: float = 20,
        timeout_s: float = 8.0,
    ) -> Dict[str, Any]:
        """Turn in place to face the absolute mat heading ``heading_deg``.

        The shortest turn from the current heading is
        ``yaw_delta(heading_deg, current)``, executed via
        :meth:`PreciseMover.turn_degrees`.

        Returns:
            The :meth:`PreciseMover.turn_degrees` result dict plus
            ``{bearing, from_heading}`` — ``bearing`` is the requested absolute
            heading, ``from_heading`` the heading when the turn started.
        """
        cur = self.pose_cm()["heading_deg"]
        turn = yaw_delta(heading_deg, cur)
        res = self.mover.turn_degrees(
            turn, speed=speed, threshold=threshold, timeout_s=timeout_s
        )
        res["bearing"] = float(heading_deg)
        res["from_heading"] = float(cur)
        return res

    # ---- drive to an absolute mat coordinate -------------------------------

    def go_to(
        self,
        x_cm: float,
        y_cm: float,
        speed: float = 25,
        arrive_tol_cm: float = 2.0,
        max_iters: int = 3,
        threshold: float = 20,
        turn_timeout_s: float = 8.0,
        move_timeout_s: float = 8.0,
    ) -> Dict[str, Any]:
        """Drive to the absolute mat coordinate ``(x_cm, y_cm)``.

        Each iteration: measure the current pose, compute ``dx, dy`` (cm) to the
        target, turn to the bearing ``atan2(dy, dx)``, then drive that distance
        (converted to mm) along ``axis="x"``. Stops when within ``arrive_tol_cm``
        or after ``max_iters`` (re-measuring each leg corrects odometer drift and
        turn error).

        Returns:
            ``{start, target, final, residual_cm, iters, legs, arrived}`` where
            ``legs`` is a per-iteration list of
            ``{iter, bearing, dist_cm, turn, move}``.
        """
        start = self.pose_cm()
        target = {"x_cm": float(x_cm), "y_cm": float(y_cm)}
        legs = []
        arrived = False
        iters = 0

        for i in range(max(1, int(max_iters))):
            iters = i + 1
            cur = self.pose_cm()
            dx = x_cm - cur["x_cm"]
            dy = y_cm - cur["y_cm"]
            dist_cm = (dx * dx + dy * dy) ** 0.5
            if dist_cm <= arrive_tol_cm:
                arrived = True
                break

            target_bearing = bearing(dx, dy)
            turn_res = self.face(
                target_bearing, speed=speed, threshold=threshold, timeout_s=turn_timeout_s
            )
            # cm -> mm for the straight-line primitive (x+ = forward).
            move_res = self.mover.goto_distance(
                cm_to_mm(dist_cm),
                speed=speed,
                axis="x",
                threshold=threshold,
                timeout_s=move_timeout_s,
            )
            legs.append(
                {
                    "iter": iters,
                    "bearing": target_bearing,
                    "dist_cm": dist_cm,
                    "turn": turn_res,
                    "move": move_res,
                }
            )

            # If the path is clearance-blocked, further attempts are pointless.
            if move_res.get("aborted") or turn_res.get("aborted"):
                break

        final = self.pose_cm()
        residual = (
            (final["x_cm"] - x_cm) ** 2 + (final["y_cm"] - y_cm) ** 2
        ) ** 0.5
        if residual <= arrive_tol_cm:
            arrived = True
        return {
            "start": start,
            "target": target,
            "final": final,
            "residual_cm": residual,
            "iters": iters,
            "legs": legs,
            "arrived": arrived,
        }
