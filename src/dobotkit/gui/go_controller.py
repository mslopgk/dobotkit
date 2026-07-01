"""Logic-layer controller for the Magician GO GUI panel.

``GoController`` is a thin, fully-typed adapter that sits between the Tkinter
view and the :mod:`dobotkit.go` public API. It owns an optional
:class:`~dobotkit.go.client.DobotLinkClient` and
:class:`~dobotkit.go.magiciango.MagicianGO` (both ``None`` until
:meth:`connect`, and injectable for a ``--demo`` mode / tests), and translates
GUI intents into GO commands.

Design rules:

* **Never raise into the UI.** Every command method catches the dobotkit error
  hierarchy (:class:`~dobotkit.exceptions.DobotError`, which includes
  :class:`~dobotkit.exceptions.DobotLinkError`) and returns an ``(ok, message)``
  tuple. A caller can surface ``message`` verbatim; ``ok`` drives the UI state.
* **Import-safe / headless.** This module imports no Tkinter and constructs no
  device on import; it only defines the class. A GO/client is created lazily in
  :meth:`connect` (or injected via the constructor).
* **Snapshot is resilient.** :meth:`snapshot` reads every sensor independently
  and never raises, so a periodic UI refresh loop can call it unconditionally.

Drive convention (mirrors :class:`~dobotkit.go.magiciango.MagicianGO`):
``forward`` = ``move(x+)``, ``strafe`` ``+`` = left, ``spin`` ``+`` = CCW/left.
The current drive speed set by :meth:`set_speed` is *stored* on the controller
and used as the default magnitude by the ``drive_*`` helpers.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from dobotkit.exceptions import DobotError
from dobotkit.go.client import DobotLinkClient
from dobotkit.go.magiciango import MagicianGO
from dobotkit.go.navigation import PreciseMover, WaypointNav

__all__ = ["GoController"]

#: Result of a command method: ``ok`` plus a human-readable status message.
Result = Tuple[bool, str]

#: Default drive-speed magnitude used by the ``drive_*`` helpers until
#: :meth:`GoController.set_speed` overrides it.
DEFAULT_SPEED: float = 30.0


class GoController:
    """Logic layer over :class:`MagicianGO` + navigation for the GUI.

    Holds an optional :class:`DobotLinkClient` and :class:`MagicianGO`. Both are
    ``None`` until :meth:`connect` succeeds; either may be injected up front (for
    a demo/offline mode or tests) via the constructor, in which case
    :attr:`is_connected` reflects the injected GO's ``connected`` flag.

    Args:
        client: A pre-built :class:`DobotLinkClient` to reuse (optional).
        go: A pre-built :class:`MagicianGO` (or compatible fake) to drive
            (optional). When supplied, the controller treats itself as connected
            if the object reports a truthy ``connected`` attribute.
        default_speed: Initial stored drive speed for the ``drive_*`` helpers.
    """

    def __init__(
        self,
        client: Optional[DobotLinkClient] = None,
        go: Optional[MagicianGO] = None,
        default_speed: float = DEFAULT_SPEED,
    ) -> None:
        self.client: Optional[DobotLinkClient] = client
        self.go: Optional[MagicianGO] = go
        self.speed: float = float(default_speed)
        # A WaypointNav/PreciseMover are lazily built the first time nav is used
        # so an injected GO is picked up correctly.
        self._nav: Optional[WaypointNav] = None
        self._mover: Optional[PreciseMover] = None

    # ---- connection --------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Whether a GO is present and reports itself connected."""
        go = self.go
        return go is not None and bool(getattr(go, "connected", False))

    def connect(
        self,
        host: str = "localhost",
        port: int = 9090,
        port_name: str = "COM5",
    ) -> Result:
        """Open a DobotLink link and connect the GO (verifying the link).

        Builds a :class:`DobotLinkClient` (unless one was injected), connects it,
        builds a :class:`MagicianGO` on ``port_name``, and calls
        ``go.connect(verify=True)`` so a dead power/wireless link surfaces
        immediately.

        Returns:
            ``(True, message)`` on success, else ``(False, reason)``.
        """
        try:
            if self.client is None:
                self.client = DobotLinkClient(host=host, port=port)
            self.client.connect()
            if self.go is None:
                self.go = MagicianGO(self.client, port_name=port_name)
            self.go.connect(verify=True)
            # Rebuild navigation helpers around the (possibly new) GO.
            self._nav = None
            self._mover = None
            return True, f"Connected to GO on {port_name} via {host}:{port}"
        except DobotError as exc:
            return False, f"Connect failed: {exc}"

    def disconnect(self) -> Result:
        """Disconnect the GO (if any) and close the DobotLink socket.

        Best-effort: both steps are attempted and the controller ends up with no
        live device regardless of individual failures.
        """
        messages = []
        go, self.go = self.go, None
        client, self.client = self.client, None
        self._nav = None
        self._mover = None
        if go is not None:
            try:
                go.disconnect_robot()
            except DobotError as exc:
                messages.append(f"GO disconnect: {exc}")
            except AttributeError:
                pass  # injected fake without disconnect_robot
        if client is not None:
            try:
                client.close()
            except Exception as exc:  # noqa: BLE001 - closing must never raise up
                messages.append(f"client close: {exc}")
        if messages:
            return False, "; ".join(messages)
        return True, "Disconnected"

    # ---- internals ---------------------------------------------------------

    def _require_go(self) -> MagicianGO:
        """Return the live GO or raise :class:`DobotError` if none is connected."""
        go = self.go
        if go is None:
            raise DobotError("not connected")
        return go

    def _nav_helper(self) -> WaypointNav:
        """Lazily build (and cache) a :class:`WaypointNav` around the live GO."""
        if self._nav is None:
            self._nav = WaypointNav(self._require_go())
        return self._nav

    def _mover_helper(self) -> PreciseMover:
        """Lazily build (and cache) a :class:`PreciseMover` around the live GO."""
        if self._mover is None:
            self._mover = PreciseMover(self._require_go())
        return self._mover

    # ---- continuous drive --------------------------------------------------

    def set_speed(self, speed: float) -> Result:
        """Store the drive-speed magnitude used by the ``drive_*`` helpers."""
        self.speed = float(speed)
        return True, f"Drive speed set to {self.speed}"

    def _drive(self, action: str, *args: Any) -> Result:
        """Dispatch a GO drive method by name, catching device errors."""
        try:
            go = self._require_go()
            getattr(go, action)(*args)
            return True, f"{action}({', '.join(str(a) for a in args)})"
        except DobotError as exc:
            return False, f"{action} failed: {exc}"

    def drive_forward(self, speed: Optional[float] = None) -> Result:
        """Drive forward at ``speed`` (defaults to the stored drive speed)."""
        return self._drive("forward", self.speed if speed is None else speed)

    def drive_backward(self, speed: Optional[float] = None) -> Result:
        """Drive backward at ``speed`` (defaults to the stored drive speed)."""
        return self._drive("backward", self.speed if speed is None else speed)

    def strafe_left(self, speed: Optional[float] = None) -> Result:
        """Strafe left at ``speed`` (= ``MagicianGO.strafe(+speed)``)."""
        return self._drive("strafe", self.speed if speed is None else speed)

    def strafe_right(self, speed: Optional[float] = None) -> Result:
        """Strafe right at ``speed`` (= ``MagicianGO.strafe(-speed)``)."""
        return self._drive("strafe", -(self.speed if speed is None else speed))

    def spin_left(self, speed: Optional[float] = None) -> Result:
        """Spin CCW (left) at ``speed`` (= ``MagicianGO.spin(+speed)``)."""
        return self._drive("spin", self.speed if speed is None else speed)

    def spin_right(self, speed: Optional[float] = None) -> Result:
        """Spin CW (right) at ``speed`` (= ``MagicianGO.spin(-speed)``)."""
        return self._drive("spin", -(self.speed if speed is None else speed))

    def stop(self) -> Result:
        """Stop driving (blocking ``move(0, 0, 0)``)."""
        return self._drive("stop")

    def emergency_stop(self) -> Result:
        """Stop immediately via the GO's fire-and-forget emergency stop."""
        try:
            self._require_go().emergency_stop()
            return True, "EMERGENCY STOP"
        except DobotError as exc:
            return False, f"emergency_stop failed: {exc}"

    # ---- output: LED / buzzer ----------------------------------------------

    def rgb(
        self,
        channel: Any,
        r: int,
        g: int,
        b: int,
        effect: int = 1,
        cycle: int = 0,
        counts: int = 0,
    ) -> Result:
        """Set an RGB LED ``channel`` to ``(r, g, b)`` (steady by default)."""
        try:
            self._require_go().rgb(channel, effect, r, g, b, cycle, counts)
            return True, f"rgb({channel}, {r}, {g}, {b})"
        except DobotError as exc:
            return False, f"rgb failed: {exc}"

    def buzzer(self, index: int, tone: int, beat: int) -> Result:
        """Sound the buzzer with ``index``/``tone``/``beat``."""
        try:
            self._require_go().buzzer(index, tone, beat)
            return True, f"buzzer({index}, {tone}, {beat})"
        except DobotError as exc:
            return False, f"buzzer failed: {exc}"

    # ---- line-trace --------------------------------------------------------

    def line_trace_start(
        self, speed: float, p: float, i: float, d: float
    ) -> Result:
        """Configure PID + speed and start autonomous line-tracing."""
        try:
            go = self._require_go()
            go.trace_pid(p, i, d)
            go.trace_speed(speed)
            go.auto_trace(True)
            return True, f"line-trace on (speed={speed}, pid=({p},{i},{d}))"
        except DobotError as exc:
            return False, f"line_trace_start failed: {exc}"

    def line_trace_stop(self) -> Result:
        """Stop autonomous line-tracing."""
        try:
            self._require_go().auto_trace(False)
            return True, "line-trace off"
        except DobotError as exc:
            return False, f"line_trace_stop failed: {exc}"

    # ---- navigation --------------------------------------------------------

    def nav_set_start(
        self, x_cm: float, y_cm: float, heading_deg: float = 0.0
    ) -> Dict[str, Any]:
        """Declare the GO's current mat pose as the navigation start.

        Returns the :meth:`WaypointNav.set_start` echo dict, or on device error a
        dict ``{"error": <message>}`` (this method never raises into the UI).
        """
        try:
            return self._nav_helper().set_start(x_cm, y_cm, heading_deg)
        except DobotError as exc:
            return {"error": str(exc)}

    def nav_goto(self, x_cm: float, y_cm: float) -> Dict[str, Any]:
        """Drive to absolute mat coordinate ``(x_cm, y_cm)`` via :class:`WaypointNav`.

        Returns the :meth:`WaypointNav.go_to` result dict, or on device error a
        dict ``{"error": <message>}``.
        """
        try:
            return self._nav_helper().go_to(x_cm, y_cm)
        except DobotError as exc:
            return {"error": str(exc)}

    def precise_forward(self, mm: float, speed: float = 25) -> Dict[str, Any]:
        """Travel ``mm`` straight ahead via :class:`PreciseMover`.

        Returns the :meth:`PreciseMover.goto_distance` result dict, or on device
        error a dict ``{"error": <message>}``.
        """
        try:
            return self._mover_helper().goto_distance(mm, speed=speed, axis="x")
        except DobotError as exc:
            return {"error": str(exc)}

    # ---- safety / camera ---------------------------------------------------

    def clearance_ok(
        self, x: float = 0, y: float = 0, r: float = 0, threshold: float = 20
    ) -> Tuple[bool, Any]:
        """Passthrough to :meth:`MagicianGO.clearance_ok`.

        On device error returns ``(False, <message>)`` rather than raising.
        """
        try:
            return self._require_go().clearance_ok(
                x=x, y=y, r=r, threshold=threshold
            )
        except DobotError as exc:
            return False, str(exc)

    def read_camera(self) -> Any:
        """Return the CAR-camera object detection result, or ``None`` on failure.

        Guarded: a device error (or no connection) yields ``None`` instead of
        raising, so a UI poll can call it unconditionally.
        """
        try:
            return self._require_go().car_camera_obj()
        except DobotError:
            return None

    # ---- snapshot ----------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        """Read all live sensors into one resilient dict for a UI refresh.

        Each sensor is read independently; any failure leaves that section
        ``None`` and records the first error message under ``"error"``. This
        method never raises.

        Returns:
            ``{connected, ultrasonic, odometer, imu, battery, error}`` where each
            sensor section is a dict of the values below or ``None`` when
            unavailable, and ``error`` is a message string or ``None``:

            * ``ultrasonic``: ``{front, back, left, right}``
            * ``odometer``: ``{x, y, yaw}``
            * ``imu``: ``{yaw}``
            * ``battery``: ``{voltage, percentage}``
        """
        snap: Dict[str, Any] = {
            "connected": self.is_connected,
            "ultrasonic": None,
            "odometer": None,
            "imu": None,
            "battery": None,
            "error": None,
        }
        go = self.go
        if go is None:
            return snap

        def _record_error(exc: Exception) -> None:
            if snap["error"] is None:
                snap["error"] = str(exc)

        try:
            u = go.ultrasonic()
            snap["ultrasonic"] = {
                "front": u.get("front"),
                "back": u.get("back"),
                "left": u.get("left"),
                "right": u.get("right"),
            }
        except Exception as exc:  # noqa: BLE001 - snapshot must never raise
            _record_error(exc)

        try:
            o = go.odometer()
            snap["odometer"] = {
                "x": o.get("x"),
                "y": o.get("y"),
                "yaw": o.get("yaw"),
            }
        except Exception as exc:  # noqa: BLE001
            _record_error(exc)

        try:
            imu = go.imu_angle()
            snap["imu"] = {"yaw": imu.get("yaw")}
        except Exception as exc:  # noqa: BLE001
            _record_error(exc)

        try:
            batt = go.battery()
            snap["battery"] = {
                "voltage": batt.get("powerVoltage"),
                "percentage": batt.get("powerPercentage"),
            }
        except Exception as exc:  # noqa: BLE001
            _record_error(exc)

        return snap
