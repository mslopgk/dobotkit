"""In-memory device fakes powering the GUI ``--demo`` mode (no hardware).

The two classes here stand in for :class:`dobotkit.arm.magician.Magician` and
:class:`dobotkit.go.magiciango.MagicianGO`, exposing exactly the public method
surface the :mod:`dobotkit.gui` controllers drive. They keep a little internal
state so the live UI *looks* alive with nothing plugged in:

* :class:`FakeArmDevice` -- holds a mutable :class:`~dobotkit.arm.structures.Pose`
  that drifts on every move/jog/home, reports device info, and never has active
  alarms. It exposes the ``effector`` / ``io`` / ``sensors`` / ``lowlevel``
  groups the arm controller reaches into (each a tiny recorder that returns
  plausible values).
* :class:`FakeGoDevice` -- integrates a commanded velocity into an odometer/IMU
  pose and reports slowly-changing ultrasonic distances, a draining battery and
  a stub camera result, matching the GO controller's snapshot reads.

Import safety
-------------
This module imports **no** ``tkinter`` and constructs no device on import; it
only defines classes. It is injected into the controllers by
:func:`dobotkit.gui.app.main` when ``--demo`` is passed. Nothing here talks to a
serial port or a socket, so it is fully headless.

The arm controller is driven by injecting a :class:`FakeArmDevice` as the
``device`` and the GO controller by injecting a :class:`FakeGoDevice` as ``go``;
in both cases the controller's own ``connect()`` path is exercised against the
fake (which flips its ``connected`` flag), so the UI's connect/disconnect
buttons behave just as they would against real hardware.
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Tuple

from dobotkit.arm.structures import Pose
from dobotkit.enums import PTPMode

__all__ = ["FakeArmDevice", "FakeGoDevice", "FakeLinkClient"]


# --------------------------------------------------------------------------- #
# Arm-side group recorders
# --------------------------------------------------------------------------- #
class _FakeEffector:
    """Stand-in for :class:`dobotkit.arm.groups.EffectorGroup`.

    Every method mirrors the real signature and simply returns ``None`` (the
    real methods return an optional queued-command index the GUI ignores).
    """

    def __init__(self) -> None:
        self.suction: bool = False
        self.gripper: bool = False
        self.laser_on: bool = False
        self.servos: Dict[int, float] = {}

    def suck(
        self, on: bool, *, enable: bool = True, queued: bool = True
    ) -> Optional[int]:
        # Pump off (enable=False) forces the vacuum state off too.
        self.suction = bool(on) and bool(enable)
        return None

    def grip(
        self, on: bool, *, enable: bool = True, queued: bool = True
    ) -> Optional[int]:
        self.gripper = bool(on) and bool(enable)
        return None

    def laser(
        self, on: bool, *, enable: bool = True, queued: bool = True
    ) -> Optional[int]:
        self.laser_on = bool(on) and bool(enable)
        return None

    def set_servo(
        self, servo_id: int, angle: float, *, queued: bool = False
    ) -> Optional[int]:
        self.servos[int(servo_id)] = float(angle)
        return None


class _FakeSensors:
    """Stand-in for :class:`dobotkit.arm.groups.SensorGroup` (plausible reads)."""

    def color(self, port: int) -> Tuple[int, int, int]:
        return (
            random.randint(0, 255),
            random.randint(0, 255),
            random.randint(0, 255),
        )

    def infrared(self, port: int) -> int:
        return random.randint(0, 1)

    def seeed_distance(self, port: int) -> float:
        return round(random.uniform(2.0, 80.0), 1)

    def seeed_temp(self, port: int) -> Tuple[float, float]:
        return (round(random.uniform(20.0, 26.0), 1), round(random.uniform(40.0, 60.0), 1))

    def seeed_light(self, port: int) -> float:
        return round(random.uniform(100.0, 900.0), 1)


class _FakeIO:
    """Stand-in for :class:`dobotkit.arm.groups.IOGroup` (in-memory registers)."""

    def __init__(self) -> None:
        self._do: Dict[int, int] = {}

    def set_do(self, address: int, level: int, *, queued: bool = False) -> Optional[int]:
        self._do[int(address)] = int(level)
        return None

    def get_do(self, address: int) -> int:
        return self._do.get(int(address), 0)

    def get_di(self, address: int) -> int:
        return random.randint(0, 1)

    def get_adc(self, address: int) -> int:
        return random.randint(0, 4095)

    def set_pwm(
        self, address: int, frequency: float, duty_cycle: float, *, queued: bool = False
    ) -> Optional[int]:
        return None


class _FakeLowLevel:
    """Minimal mirror of the ``lowlevel`` surface the arm GUI touches.

    Exposes ``set_jog_cmd`` (used to start/stop jogging -- moves the demo pose),
    the alarm read/clear pair (always reports "no alarms"), and the device-info
    reads used by :meth:`ArmController.device_info`.
    """

    def __init__(self, arm: "FakeArmDevice") -> None:
        self._arm = arm

    def set_jog_cmd(
        self, is_joint: int, cmd: int, *, queued: bool = False
    ) -> Optional[int]:
        # cmd 0 == idle/stop; 1..8 == axis +/-. Nudge the demo pose while jogging
        # so the live view visibly moves under a press-and-hold jog button.
        if cmd:
            axis = (cmd - 1) // 2  # 0..3 -> x/y/z/r
            positive = (cmd % 2) == 1  # odd == positive direction
            step = 3.0 if positive else -3.0
            self._arm._nudge_axis(axis, step)
        return None

    def get_alarms_state(self) -> bytes:
        # No active alarms in the demo -- an all-zero bitmap decodes to [].
        return b"\x00" * 16

    def clear_all_alarms_state(self) -> None:
        return None

    def get_device_sn(self) -> str:
        return "DEMO-SN-0001"

    def get_device_name(self) -> str:
        return "Dobot Magician (demo)"

    def get_device_version(self) -> str:
        return "demo 1.0.0"


# --------------------------------------------------------------------------- #
# FakeArmDevice
# --------------------------------------------------------------------------- #
class FakeArmDevice:
    """In-memory fake of :class:`dobotkit.arm.magician.Magician` for ``--demo``.

    Holds a mutable pose that drifts a little on each move/jog/home so the live
    pose grid updates without any hardware. Matches the subset of the Magician
    surface the arm controller drives: ``connect`` / ``disconnect``, ``home`` /
    ``move_to`` / ``move_relative`` / ``set_speed``, ``get_pose``, and the
    ``effector`` / ``io`` / ``sensors`` / ``lowlevel`` groups.
    """

    def __init__(self) -> None:
        self.connected: bool = False
        # Start at the arm's nominal home-ish pose.
        self._x = 200.0
        self._y = 0.0
        self._z = 0.0
        self._r = 0.0
        self._j = [0.0, 0.0, 0.0, 0.0]
        self.effector = _FakeEffector()
        self.io = _FakeIO()
        self.sensors = _FakeSensors()
        self.lowlevel = _FakeLowLevel(self)

    # -- lifecycle --------------------------------------------------------- #
    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    # -- internal pose helpers -------------------------------------------- #
    def _nudge_axis(self, axis: int, step: float) -> None:
        """Move one Cartesian axis by ``step`` (axis 0..3 -> x/y/z/r)."""
        if axis == 0:
            self._x += step
        elif axis == 1:
            self._y += step
        elif axis == 2:
            self._z += step
        else:
            self._r += step
        self._resync_joints()

    def _resync_joints(self) -> None:
        """Fabricate plausible joint angles from the Cartesian pose + jitter."""
        self._j[0] = math.degrees(math.atan2(self._y, self._x))
        self._j[1] = self._z * 0.1 + random.uniform(-0.2, 0.2)
        self._j[2] = self._z * 0.05 + random.uniform(-0.2, 0.2)
        self._j[3] = self._r

    # -- motion ------------------------------------------------------------ #
    def home(
        self,
        x: float = 200,
        y: float = 0,
        z: float = 0,
        r: float = 0,
        *,
        wait: bool = True,
    ) -> Optional[int]:
        self._x, self._y, self._z, self._r = float(x), float(y), float(z), float(r)
        self._resync_joints()
        return None

    def move_to(
        self,
        x: float,
        y: float,
        z: float,
        r: float = 0,
        *,
        mode: PTPMode = PTPMode.MOVL_XYZ,
        wait: bool = False,
        check_alarms: bool = False,
    ) -> Optional[int]:
        # Land near the target with a touch of drift, so the pose readout looks
        # like a real (slightly imperfect) servo settle rather than an exact snap.
        self._x = float(x) + random.uniform(-0.3, 0.3)
        self._y = float(y) + random.uniform(-0.3, 0.3)
        self._z = float(z) + random.uniform(-0.3, 0.3)
        self._r = float(r)
        self._resync_joints()
        return None

    def move_relative(
        self,
        dx: float = 0,
        dy: float = 0,
        dz: float = 0,
        dr: float = 0,
        *,
        wait: bool = False,
        check_alarms: bool = False,
    ) -> Optional[int]:
        self._x += float(dx)
        self._y += float(dy)
        self._z += float(dz)
        self._r += float(dr)
        self._resync_joints()
        return None

    def set_speed(self, velocity: float, acceleration: float) -> None:
        return None

    # -- pose -------------------------------------------------------------- #
    def get_pose(self) -> Pose:
        # A hair of live jitter so the readout ticks even when idle.
        return Pose(
            x=round(self._x + random.uniform(-0.05, 0.05), 3),
            y=round(self._y + random.uniform(-0.05, 0.05), 3),
            z=round(self._z + random.uniform(-0.05, 0.05), 3),
            r=round(self._r, 3),
            j1=round(self._j[0], 3),
            j2=round(self._j[1], 3),
            j3=round(self._j[2], 3),
            j4=round(self._j[3], 3),
        )

    # -- pydobot-style aliases (present for parity; unused by the GUI) ----- #
    def suck(self, on: bool) -> Optional[int]:
        return self.effector.suck(on)

    def grip(self, on: bool) -> Optional[int]:
        return self.effector.grip(on)


# --------------------------------------------------------------------------- #
# FakeLinkClient
# --------------------------------------------------------------------------- #
class FakeLinkClient:
    """No-op stand-in for :class:`dobotkit.go.client.DobotLinkClient`.

    The GO controller opens a link (``client.connect()``) alongside the GO and
    closes it on disconnect (``client.close()``); in demo mode there is no
    WebSocket, so this satisfies that lifecycle without a network call. Its
    ``call`` / ``notify`` are present for parity but unused -- the demo GO device
    does not route through a client.
    """

    def __init__(self) -> None:
        self.connected: bool = False

    def connect(self) -> "FakeLinkClient":
        self.connected = True
        return self

    def close(self) -> None:
        self.connected = False

    def call(self, method: str, **params: Any) -> Any:  # pragma: no cover - parity only
        return None

    def notify(self, method: str, **params: Any) -> None:  # pragma: no cover - parity only
        return None


# --------------------------------------------------------------------------- #
# FakeGoDevice
# --------------------------------------------------------------------------- #
class FakeGoDevice:
    """In-memory fake of :class:`dobotkit.go.magiciango.MagicianGO` for ``--demo``.

    Latches a commanded velocity from the ``drive_*`` calls and integrates it
    into an odometer/IMU pose on each sensor read (like
    ``tests/go/conftest.py::SimulatedGo``, but self-contained here), so the live
    telemetry grid animates while a drive button is held. Ultrasonic distances
    wander a little and the battery slowly drains, so a static demo screen still
    ticks.

    Matches the surface the GO controller drives: ``connect`` / drive /
    ``stop`` / ``emergency_stop``, ``rgb`` / ``buzzer``, the ``trace_*`` /
    ``auto_trace`` line-trace set, sensor reads (``ultrasonic`` / ``odometer`` /
    ``imu_angle`` / ``battery``), ``set_odometer``, ``clearance_ok`` and
    ``car_camera_obj``.
    """

    def __init__(self) -> None:
        self.connected: bool = False
        self.port_name: str = "DEMO"
        # World-frame odometer pose (mm, mm, deg) + IMU yaw (deg).
        self._x = 0.0
        self._y = 0.0
        self._yaw = 0.0
        self._imu_yaw = 0.0
        # Latched commanded velocity (x fwd, y left, r CCW).
        self._vx = 0.0
        self._vy = 0.0
        self._vr = 0.0
        # Slowly-changing environment/state.
        self._battery_pct = 87.0
        self._us = {"front": 60.0, "back": 55.0, "left": 45.0, "right": 48.0}
        self._tracing = False

    # -- connection -------------------------------------------------------- #
    def connect(self, verify: bool = True) -> Any:
        self.connected = True
        return self.battery() if verify else None

    def disconnect_robot(self) -> Any:
        self.connected = False
        return None

    # -- continuous drive (latch a velocity) ------------------------------ #
    def move(self, x: float = 0, y: float = 0, r: float = 0) -> Any:
        self._vx, self._vy, self._vr = float(x), float(y), float(r)
        return None

    def forward(self, speed: float) -> Any:
        return self.move(x=speed)

    def backward(self, speed: float) -> Any:
        return self.move(x=-speed)

    def strafe(self, speed: float) -> Any:
        return self.move(y=speed)

    def spin(self, speed: float) -> Any:
        return self.move(r=speed)

    def stop(self) -> Any:
        self._vx = self._vy = self._vr = 0.0
        return None

    def emergency_stop(self) -> None:
        self._vx = self._vy = self._vr = 0.0

    # -- internal integration --------------------------------------------- #
    def _advance(self) -> None:
        """Integrate the latched velocity into pose by one small tick.

        Called from each sensor read so the telemetry visibly moves while a
        drive command is in effect and holds still once stopped. Scaled small so
        the demo drifts gently rather than racing off.
        """
        if self._vr:
            self._yaw = self._wrap180(self._yaw + self._vr * 0.4)
            self._imu_yaw = self._wrap180(self._imu_yaw + self._vr * 0.4)
        if self._vx or self._vy:
            h = math.radians(self._yaw)
            fx, fy = math.cos(h), math.sin(h)
            lx, ly = -math.sin(h), math.cos(h)
            step_f = self._vx * 0.5
            step_l = self._vy * 0.5
            self._x += fx * step_f + lx * step_l
            self._y += fy * step_f + ly * step_l
        # Ultrasonic distances wander a little (clamped to a sane range).
        for key in self._us:
            self._us[key] = max(
                5.0, min(120.0, self._us[key] + random.uniform(-1.5, 1.5))
            )
        # Battery drains very slowly; never below 1%.
        self._battery_pct = max(1.0, self._battery_pct - 0.02)

    @staticmethod
    def _wrap180(deg: float) -> float:
        d = deg % 360.0
        return d - 360.0 if d > 180.0 else d

    # -- sensors (read advances the sim, then reports) -------------------- #
    def ultrasonic(self) -> Dict[str, float]:
        self._advance()
        return {k: round(v, 1) for k, v in self._us.items()}

    def odometer(self) -> Dict[str, float]:
        self._advance()
        return {"x": round(self._x, 1), "y": round(self._y, 1), "yaw": round(self._yaw, 1)}

    def imu_angle(self) -> Dict[str, float]:
        self._advance()
        return {"yaw": round(self._imu_yaw, 1)}

    def battery(self) -> Dict[str, float]:
        # Voltage tracks percentage across a plausible 3S-ish LiPo band.
        voltage = 9.9 + (self._battery_pct / 100.0) * 2.7
        return {
            "powerVoltage": round(voltage, 2),
            "powerPercentage": round(self._battery_pct, 1),
        }

    def set_odometer(self, x: float, y: float, yaw: float) -> Any:
        self._x, self._y, self._yaw = float(x), float(y), float(yaw)
        return None

    # -- safety ------------------------------------------------------------ #
    def clearance_ok(
        self, x: float = 0, y: float = 0, r: float = 0, threshold: float = 20
    ) -> Tuple[bool, Any]:
        u = {k: round(v, 1) for k, v in self._us.items()}
        if x > 0 and u["front"] < threshold:
            return False, f"front={u['front']}<{threshold}"
        if x < 0 and u["back"] < threshold:
            return False, f"back={u['back']}<{threshold}"
        if y != 0 and min(u["left"], u["right"]) < threshold:
            return False, f"side min={min(u['left'], u['right'])}<{threshold}"
        if r != 0 and min(u.values()) < threshold:
            return False, f"around min={min(u.values())}<{threshold}"
        return True, u

    # -- output: LED / buzzer --------------------------------------------- #
    def rgb(
        self,
        number: Any,
        effect: int,
        r: int,
        g: int,
        b: int,
        cycle: int,
        counts: int,
    ) -> Any:
        return None

    def buzzer(self, index: int, tone: int, beat: int) -> Any:
        return None

    # -- line-trace -------------------------------------------------------- #
    def auto_trace(self, on: Any) -> Any:
        self._tracing = bool(on)
        # A latched forward crawl makes the odometer creep while tracing is on.
        self._vx = 8.0 if self._tracing else 0.0
        return None

    def trace_speed(self, speed: float) -> Any:
        return None

    def trace_pid(self, p: float, i: float, d: float) -> Any:
        return None

    def trace_angle(self) -> Any:
        return {"angle": round(random.uniform(-15.0, 15.0), 1), "count": 1}

    # -- camera ------------------------------------------------------------ #
    def car_camera_obj(self) -> Any:
        objs: List[Dict[str, Any]] = [
            {"label": "cube", "x": random.randint(0, 320), "y": random.randint(0, 240)}
        ]
        return {"count": len(objs), "dl_obj": objs}
