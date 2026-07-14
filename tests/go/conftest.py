"""Shared GO test fixtures and in-memory doubles.

Three layers of fakes, each one notch higher than the last, so a GO test can
plug in at whatever level it is exercising:

- ``FakeWebSocket`` — replaces the raw ``websockets`` connection used by
  ``DobotLinkClient``. Lets a test queue JSON-RPC response frames and inspect
  the frames the client sent. Use this to test ``DobotLinkClient`` itself.
- ``FakeClient`` — replaces a connected ``DobotLinkClient``. Records every
  ``(method, params)`` passed to ``call``/``notify`` and returns programmable
  results, so ``MagicianGO`` / navigation can be tested with no socket at all.
- ``SimulatedGo`` — a fake ``MagicianGO`` whose drive commands mutate internal
  odometer/IMU state and whose sensor readers report it back, for closed-loop
  navigation tests (``PreciseMover`` / ``WaypointNav``).

These mirror the *real* call shapes:

- ``DobotLinkClient`` (``go/client.py``, modelled on the working
  ``magiciango/client.py``) calls ``ws.send(json_str)`` then loops on
  ``ws.recv(timeout=...)`` reading JSON strings, matching on the request id,
  and ``ws.close()`` on teardown.
- ``MagicianGO._call(func, **p)`` issues ``client.call("MagicianGO.<func>",
  portName=..., **p)``; ``emergency_stop`` uses ``client.notify(...)``.
- Navigation primitives call ``go.move(...)`` / ``go.forward(...)`` /
  ``go.spin(...)`` and read back ``go.odometer()`` / ``go.imu_angle()`` /
  ``go.ultrasonic()`` in a feedback loop, ending in ``go.emergency_stop()``.
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional, Tuple

import pytest


class FakeWebSocket:
    """In-memory double for the ``websockets`` connection ``DobotLinkClient`` uses.

    The real client (see ``magiciango/client.py``) drives the socket like this::

        ws.send(json.dumps(payload))      # JSON-RPC request, str
        raw = ws.recv(timeout=...)        # JSON-RPC response, str
        ws.close()

    so this double captures every ``send`` frame and serves queued ``recv``
    frames in order. Responses may be queued as dicts (auto JSON-encoded) or as
    raw strings, which lets a test feed malformed/out-of-order/notification
    frames to exercise the client's id-matching loop.
    """

    def __init__(self, responses: Optional[List[Any]] = None) -> None:
        # Captured outbound frames.
        self.sent: List[str] = []
        # Pending inbound frames (FIFO).
        self._rx: List[Any] = list(responses or [])
        self.closed = False

    # ---- websockets connection surface ----
    def send(self, data: str) -> None:
        self.sent.append(data)

    def recv(self, timeout: Optional[float] = None) -> str:
        if not self._rx:
            # Mirror websockets.sync: a read with nothing available times out.
            raise TimeoutError("no queued FakeWebSocket frame")
        frame = self._rx.pop(0)
        return frame if isinstance(frame, str) else json.dumps(frame)

    def close(self) -> None:
        self.closed = True

    # ---- test helpers ----
    def queue_response(self, frame: Any) -> None:
        """Append a response frame (dict -> auto JSON, str -> verbatim)."""
        self._rx.append(frame)

    def queue_result(self, result: Any, *, id: int = 1) -> None:
        """Queue a well-formed JSON-RPC success response carrying ``result``."""
        self._rx.append({"jsonrpc": "2.0", "id": id, "result": result})

    def queue_error(self, message: str = "boom", *, code: int = -32000,
                    id: int = 1) -> None:
        """Queue a JSON-RPC error response (drives ``DobotLinkError``)."""
        self._rx.append(
            {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}
        )

    def last_sent(self) -> Dict[str, Any]:
        """Decode the most recently sent frame as a JSON-RPC request dict."""
        return json.loads(self.sent[-1])


class FakeClient:
    """Double for a connected ``DobotLinkClient`` — records calls, returns canned results.

    Records ``(method, params)`` for every ``call`` and ``notify`` so a test can
    assert exactly what ``MagicianGO`` / navigation sent on the wire, with no
    socket involved.

    Programmable results, in priority order:
      1. ``results[method]`` — per-method override (most specific).
      2. ``result`` — a single default returned for any otherwise-unmatched call.
    A result entry may be a list/tuple, in which case successive calls to the
    same method pop the next value (a one-shot queue), so closed-loop reads can
    be scripted to advance.
    """

    def __init__(self, result: Any = None,
                 results: Optional[Dict[str, Any]] = None) -> None:
        self.calls: List[Tuple[str, Dict[str, Any]]] = []
        self.notifies: List[Tuple[str, Dict[str, Any]]] = []
        self._result = result
        self._results = dict(results or {})

    def call(self, method: str, **params: Any) -> Any:
        self.calls.append((method, params))
        if method in self._results:
            programmed = self._results[method]
            if isinstance(programmed, list):
                # One-shot queue: pop next, stick on last value when exhausted.
                if len(programmed) > 1:
                    return programmed.pop(0)
                return programmed[0]
            return programmed
        return self._result

    def notify(self, method: str, **params: Any) -> None:
        self.notifies.append((method, params))

    # ---- test helpers ----
    def methods_called(self) -> List[str]:
        return [m for m, _ in self.calls]

    def find_call(self, method: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Return the first recorded call to ``method``, or ``None``."""
        for entry in self.calls:
            if entry[0] == method:
                return entry
        return None


class SimulatedGo:
    """A fake ``MagicianGO`` with integrating odometer/IMU state for closed-loop tests.

    Continuous-drive commands (``move``/``forward``/``backward``/``strafe``/
    ``spin``) latch a commanded velocity ``(vx, vy, vr)``. Each subsequent
    sensor read (``odometer``/``imu_angle``) *advances* the simulated state by
    one tick of that velocity before reporting it — modelling the real GO, whose
    pose keeps changing while a velocity command is in effect and which a
    feedback loop samples repeatedly. ``stop``/``emergency_stop`` zero the
    velocity so state stops advancing (the loop converges and halts).

    Units match the real device: odometer ``x``/``y`` in mm (world frame),
    ``yaw`` and IMU ``yaw`` in degrees, ultrasonic distances in cm.

    Tunables:
      ``dist_per_tick`` — mm advanced per velocity-unit per odometer read.
      ``deg_per_tick``  — degrees turned per velocity-unit per IMU read.
      ``clearances``    — ultrasonic dict returned by ``ultrasonic()``.
    """

    def __init__(self, *, x: float = 0.0, y: float = 0.0, yaw: float = 0.0,
                 dist_per_tick: float = 1.0, deg_per_tick: float = 1.0,
                 clearances: Optional[Dict[str, float]] = None) -> None:
        # World-frame odometer pose (mm, mm, deg).
        self.x = float(x)
        self.y = float(y)
        self.yaw = float(yaw)
        # IMU yaw (deg) — independent absolute reference, advanced by spins.
        self.imu_yaw = float(yaw)
        # Latched commanded velocity.
        self.vx = 0.0
        self.vy = 0.0
        self.vr = 0.0
        # Integration gains per sensor read.
        self.dist_per_tick = float(dist_per_tick)
        self.deg_per_tick = float(deg_per_tick)
        # Ultrasonic readings (cm). Default: all clear (40 = hardware ceiling).
        # Set to ``None`` to simulate a malformed read (real API returns None).
        self.clearances: Optional[Dict[str, float]] = dict(
            clearances or {"front": 40.0, "back": 40.0,
                           "left": 40.0, "right": 40.0}
        )
        # Recorded command/notify history for assertions.
        self.moves: List[Tuple[float, float, float]] = []
        self.stops = 0
        self.emergency_stops = 0
        self.set_odometer_calls: List[Tuple[float, float, float]] = []

    # ---- continuous drive (latch velocity) ----
    def move(self, x: float = 0.0, y: float = 0.0, r: float = 0.0) -> None:
        self.vx, self.vy, self.vr = float(x), float(y), float(r)
        self.moves.append((self.vx, self.vy, self.vr))

    def forward(self, speed: float) -> None:
        self.move(x=speed)

    def backward(self, speed: float) -> None:
        self.move(x=-speed)

    def strafe(self, speed: float) -> None:
        self.move(y=speed)

    def spin(self, speed: float) -> None:
        self.move(r=speed)

    def stop(self) -> None:
        self.vx = self.vy = self.vr = 0.0
        self.stops += 1

    def emergency_stop(self) -> None:
        self.vx = self.vy = self.vr = 0.0
        self.emergency_stops += 1

    # ---- internal state advance ----
    def _advance_translation(self) -> None:
        """Integrate latched linear velocity into the world-frame pose by one tick.

        Linear motion is applied in the heading direction the GO is currently
        facing (odometer yaw), matching the real world-frame integration: vx is
        forward along heading, vy is to the left (heading + 90 deg).
        """
        if self.vx == 0.0 and self.vy == 0.0:
            return
        h = math.radians(self.yaw)
        # Forward axis (along heading) and left axis (heading + 90 deg).
        fx, fy = math.cos(h), math.sin(h)
        lx, ly = -math.sin(h), math.cos(h)
        step_fwd = self.vx * self.dist_per_tick
        step_left = self.vy * self.dist_per_tick
        self.x += fx * step_fwd + lx * step_left
        self.y += fy * step_fwd + ly * step_left

    def _advance_rotation(self) -> None:
        """Integrate latched angular velocity into yaw/IMU yaw by one tick."""
        if self.vr == 0.0:
            return
        dyaw = self.vr * self.deg_per_tick
        self.yaw = self._wrap180(self.yaw + dyaw)
        self.imu_yaw = self._wrap180(self.imu_yaw + dyaw)

    @staticmethod
    def _wrap180(deg: float) -> float:
        d = deg % 360.0
        if d > 180.0:
            d -= 360.0
        return d

    # ---- sensors (read advances state, then reports it) ----
    def odometer(self) -> Dict[str, float]:
        self._advance_translation()
        self._advance_rotation()
        return {"x": self.x, "y": self.y, "yaw": self.yaw}

    def imu_angle(self) -> Dict[str, float]:
        self._advance_translation()
        self._advance_rotation()
        return {"yaw": self.imu_yaw}

    def ultrasonic(self) -> Optional[Dict[str, float]]:
        # Mirrors the real MagicianGO contract: values clamp at the 40 cm
        # hardware ceiling, and ``clearances = None`` simulates a malformed
        # read (the real method returns None -> "unknown -> stop").
        if self.clearances is None:
            return None
        return {k: min(float(v), 40.0) for k, v in self.clearances.items()}

    def set_odometer(self, x: float, y: float, yaw: float) -> None:
        self.x, self.y, self.yaw = float(x), float(y), float(yaw)
        self.set_odometer_calls.append((self.x, self.y, self.yaw))

    # ---- safety gate (mirrors MagicianGO.clearance_ok) ----
    def clearance_ok(self, x: float = 0.0, y: float = 0.0, r: float = 0.0,
                     threshold: float = 20.0) -> Tuple[bool, Any]:
        u = self.ultrasonic()
        if u is None:
            return False, "ultrasonic read invalid (unknown -> stop)"
        if x > 0 and u["front"] < threshold:
            return False, f"front={u['front']}<{threshold}"
        if x < 0 and u["back"] < threshold:
            return False, f"back={u['back']}<{threshold}"
        if y != 0 and min(u["left"], u["right"]) < threshold:
            return False, f"side min={min(u['left'], u['right'])}<{threshold}"
        if r != 0 and min(u.values()) < threshold:
            return False, f"around min={min(u.values())}<{threshold}"
        return True, u


@pytest.fixture
def fake_ws() -> FakeWebSocket:
    """A fresh ``FakeWebSocket`` with no queued responses."""
    return FakeWebSocket()


@pytest.fixture
def fake_client() -> FakeClient:
    """A fresh ``FakeClient`` recording calls, returning ``None`` by default."""
    return FakeClient()


@pytest.fixture
def sim_go() -> SimulatedGo:
    """A fresh ``SimulatedGo`` at the origin, facing 0 deg, all-clear ultrasonics."""
    return SimulatedGo()
