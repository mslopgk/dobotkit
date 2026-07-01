"""Reusable fakes for the GUI controller tests.

These stand in for the real device front-ends so controller logic can be tested
headless -- no serial port, no DobotLink, no window. They deliberately mirror the
*public* method surface the controllers drive:

* :class:`FakeArm` mimics :class:`dobotkit.arm.magician.Magician` (the subset the
  arm controller uses). It records every call in :attr:`FakeArm.calls`, tracks a
  ``connected`` flag, and returns a canned :class:`~dobotkit.arm.structures.Pose`
  (and the pydobot-style 8-tuple from :meth:`pose`). Its ``effector`` / ``io`` /
  ``sensors`` / ``lowlevel`` groups are lightweight recorders exposing the same
  method names the real groups do.
* :class:`FakeGo` mimics :class:`dobotkit.go.magiciango.MagicianGO`. It records
  drive calls and returns canned ``ultrasonic`` / ``odometer`` / ``imu_angle`` /
  ``battery`` dicts with the real firmware key names.

Each is exposed both as its class (for direct construction) and as a pytest
fixture returning a fresh instance.

Signatures were mirrored from the real sources:
``src/dobotkit/arm/magician.py``, ``src/dobotkit/arm/groups.py``,
``src/dobotkit/arm/lowlevel/jog.py`` and ``src/dobotkit/go/magiciango.py``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pytest

from dobotkit.arm.structures import Pose
from dobotkit.enums import PTPMode

# (method_name, args_tuple, kwargs_dict) as recorded by the fakes.
Call = Tuple[str, tuple, Dict[str, Any]]


# --------------------------------------------------------------------------- #
# Arm-side group recorders
# --------------------------------------------------------------------------- #
class _RecordingGroup:
    """Base recorder: shares the owning fake's ``calls`` log, prefixing entries.

    Records under ``"<prefix>.<method>"`` so a controller test can assert on,
    e.g., ``("effector.suck", (True,), {})`` in the arm's single call log.
    """

    def __init__(self, prefix: str, sink: List[Call]) -> None:
        self._prefix = prefix
        self._sink = sink

    def _record(self, method: str, *args: Any, **kwargs: Any) -> None:
        self._sink.append((f"{self._prefix}.{method}", args, kwargs))


class FakeEffectorGroup(_RecordingGroup):
    """Mirror of :class:`dobotkit.arm.groups.EffectorGroup` (recording)."""

    def suck(self, on: bool, *, queued: bool = True) -> Optional[int]:
        self._record("suck", on, queued=queued)
        return None

    def grip(self, on: bool, *, queued: bool = True) -> Optional[int]:
        self._record("grip", on, queued=queued)
        return None

    def laser(self, on: bool, *, queued: bool = True) -> Optional[int]:
        self._record("laser", on, queued=queued)
        return None


class FakeSensorGroup(_RecordingGroup):
    """Mirror of :class:`dobotkit.arm.groups.SensorGroup` (recording)."""

    def color(self, port: int) -> Tuple[int, int, int]:
        self._record("color", port)
        return (0, 0, 0)

    def infrared(self, port: int) -> int:
        self._record("infrared", port)
        return 0

    def seeed_distance(self, port: int) -> float:
        self._record("seeed_distance", port)
        return 0.0


class FakeIOGroup(_RecordingGroup):
    """Mirror of :class:`dobotkit.arm.groups.IOGroup` (recording)."""

    def set_do(self, address: int, level: int, *, queued: bool = False) -> Optional[int]:
        self._record("set_do", address, level, queued=queued)
        return None

    def get_do(self, address: int) -> int:
        self._record("get_do", address)
        return 0

    def get_di(self, address: int) -> int:
        self._record("get_di", address)
        return 0

    def get_adc(self, address: int) -> int:
        self._record("get_adc", address)
        return 0


class FakeLowLevelArm(_RecordingGroup):
    """Minimal mirror of the ``lowlevel`` surface the GUI touches.

    Currently just JOG (``set_jog_cmd(is_joint, cmd, *, queued=False)``) -- the
    signature used by :meth:`dobotkit.arm.lowlevel.jog.set_jog_cmd`.
    """

    def set_jog_cmd(
        self, is_joint: int, cmd: int, *, queued: bool = False
    ) -> Optional[int]:
        self._record("set_jog_cmd", is_joint, cmd, queued=queued)
        return None


# --------------------------------------------------------------------------- #
# FakeArm
# --------------------------------------------------------------------------- #
class FakeArm:
    """In-memory stand-in for :class:`dobotkit.arm.magician.Magician`.

    Records calls, tracks a ``connected`` flag, and returns a canned pose. Set
    :attr:`next_pose` to change what :meth:`get_pose` / :meth:`pose` report.
    """

    def __init__(self, pose: Optional[Pose] = None, connected: bool = False) -> None:
        self.calls: List[Call] = []
        self.connected = connected
        self.next_pose: Pose = pose or Pose(
            x=200.0, y=0.0, z=0.0, r=0.0, j1=0.0, j2=0.0, j3=0.0, j4=0.0
        )
        self.effector = FakeEffectorGroup("effector", self.calls)
        self.sensors = FakeSensorGroup("sensors", self.calls)
        self.io = FakeIOGroup("io", self.calls)
        self.lowlevel = FakeLowLevelArm("lowlevel", self.calls)

    def _record(self, method: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((method, args, kwargs))

    # -- lifecycle --------------------------------------------------------- #
    def connect(self) -> None:
        self._record("connect")
        self.connected = True

    def disconnect(self) -> None:
        self._record("disconnect")
        self.connected = False

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
        self._record("home", x, y, z, r, wait=wait)
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
        self._record("move_to", x, y, z, r, mode=mode, wait=wait, check_alarms=check_alarms)
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
        self._record(
            "move_relative", dx, dy, dz, dr, wait=wait, check_alarms=check_alarms
        )
        return None

    def set_speed(self, velocity: float, acceleration: float) -> None:
        self._record("set_speed", velocity, acceleration)

    # -- pose -------------------------------------------------------------- #
    def get_pose(self) -> Pose:
        self._record("get_pose")
        return self.next_pose

    def pose(self) -> Tuple[float, float, float, float, float, float, float, float]:
        self._record("pose")
        p = self.next_pose
        return (p.x, p.y, p.z, p.r, p.j1, p.j2, p.j3, p.j4)

    # -- pydobot-style effector / IO aliases ------------------------------- #
    def suck(self, on: bool) -> Optional[int]:
        self._record("suck", on)
        return None

    def grip(self, on: bool) -> Optional[int]:
        self._record("grip", on)
        return None

    def get_eio(self, addr: int) -> int:
        self._record("get_eio", addr)
        return 0

    def set_eio(self, addr: int, val: int) -> Optional[int]:
        self._record("set_eio", addr, val)
        return None


# --------------------------------------------------------------------------- #
# FakeGo
# --------------------------------------------------------------------------- #
class FakeGo:
    """In-memory stand-in for :class:`dobotkit.go.magiciango.MagicianGO`.

    Records drive/output calls and returns canned sensor dicts using the real
    firmware key names. Override the ``*_reading`` attributes to change what the
    read methods report.
    """

    def __init__(self, connected: bool = False) -> None:
        self.calls: List[Call] = []
        self.connected = connected
        self.ultrasonic_reading: Dict[str, float] = {
            "front": 50.0,
            "back": 50.0,
            "left": 50.0,
            "right": 50.0,
        }
        self.odometer_reading: Dict[str, float] = {"x": 0.0, "y": 0.0, "yaw": 0.0}
        self.imu_reading: Dict[str, float] = {"yaw": 0.0}
        self.battery_reading: Dict[str, float] = {
            "powerVoltage": 12.0,
            "powerPercentage": 100.0,
        }

    def _record(self, method: str, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((method, args, kwargs))

    # -- connection -------------------------------------------------------- #
    def connect(self, verify: bool = True) -> Any:
        self._record("connect", verify=verify)
        self.connected = True
        return self.battery_reading if verify else None

    # -- continuous drive -------------------------------------------------- #
    def move(self, x: float = 0, y: float = 0, r: float = 0) -> Any:
        self._record("move", x, y, r)
        return None

    def forward(self, speed: float) -> Any:
        self._record("forward", speed)
        return None

    def backward(self, speed: float) -> Any:
        self._record("backward", speed)
        return None

    def strafe(self, speed: float) -> Any:
        self._record("strafe", speed)
        return None

    def spin(self, speed: float) -> Any:
        self._record("spin", speed)
        return None

    def stop(self) -> Any:
        self._record("stop")
        return None

    def emergency_stop(self) -> None:
        self._record("emergency_stop")

    # -- sensors ----------------------------------------------------------- #
    def ultrasonic(self) -> Dict[str, float]:
        self._record("ultrasonic")
        return dict(self.ultrasonic_reading)

    def odometer(self) -> Dict[str, float]:
        self._record("odometer")
        return dict(self.odometer_reading)

    def imu_angle(self) -> Dict[str, float]:
        self._record("imu_angle")
        return dict(self.imu_reading)

    def battery(self) -> Dict[str, float]:
        self._record("battery")
        return dict(self.battery_reading)

    def clearance_ok(
        self, x: float = 0, y: float = 0, r: float = 0, threshold: float = 20
    ) -> Tuple[bool, Any]:
        self._record("clearance_ok", x, y, r, threshold=threshold)
        u = dict(self.ultrasonic_reading)
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
        self._record("rgb", number, effect, r, g, b, cycle, counts)
        return None

    def buzzer(self, index: int, tone: int, beat: int) -> Any:
        self._record("buzzer", index, tone, beat)
        return None

    # -- line-trace -------------------------------------------------------- #
    def auto_trace(self, on: Any) -> Any:
        self._record("auto_trace", on)
        return None

    def trace_speed(self, speed: float) -> Any:
        self._record("trace_speed", speed)
        return None

    def trace_pid(self, p: float, i: float, d: float) -> Any:
        self._record("trace_pid", p, i, d)
        return None

    def trace_angle(self) -> Any:
        self._record("trace_angle")
        return {"angle": 0.0, "count": 0}

    # -- camera ------------------------------------------------------------ #
    def car_camera_obj(self) -> Any:
        self._record("car_camera_obj")
        return {"count": 0, "dl_obj": []}


@pytest.fixture()
def fake_arm() -> FakeArm:
    """A fresh :class:`FakeArm` (disconnected, canned home pose)."""
    return FakeArm()


@pytest.fixture()
def fake_go() -> FakeGo:
    """A fresh :class:`FakeGo` (disconnected, canned sensor readings)."""
    return FakeGo()
