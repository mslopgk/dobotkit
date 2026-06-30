"""High-level Magician GO control layered on a connected ``DobotLinkClient``.

``MagicianGO`` is a thin, typed facade over the DobotLink ``MagicianGO.*``
JSON-RPC surface. Every method (except :meth:`search`) issues
``client.call("MagicianGO.<Func>", portName=self.port_name, **params)`` via the
private :meth:`_call` helper; :meth:`emergency_stop` is the lone command that
uses ``client.notify`` so that stopping the car never blocks on a response.

Two classes of drive command exist, and the distinction is a *safety* matter:

* **Continuous velocity control** (:meth:`move`, :meth:`move_direct`,
  :meth:`forward`, :meth:`backward`, :meth:`strafe`, :meth:`spin`, :meth:`stop`)
  is **trusted** — the car drives at the commanded velocity until told to stop.
* **Closed-loop / queued commands** (:meth:`rotate`, :meth:`move_dist`,
  :meth:`arc_rad`, :meth:`arc_cent`, :meth:`coord_closed_loop`,
  :meth:`increment_closed_loop`) are issued with the firmware's
  ``isQueued/isWaitForFinish`` wait flags and **can HANG** on this chassis when
  the completion callback never arrives. They are kept for completeness and
  experimentation only; for reliable precise motion build a closed loop out of
  continuous :meth:`move` plus sensor feedback (see
  ``dobotkit.go.navigation.PreciseMover`` / ``WaypointNav``).

Safety workflow (see research doc §8): after :meth:`connect_robot` always verify
the link with a read such as :meth:`battery` (use :meth:`connect` which does
this for you); check :meth:`clearance_ok` before driving; wrap motion in
``try/finally`` ending in :meth:`emergency_stop`.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple, Union, cast

from dobotkit.enums import LEDChannel

# Wait flags shared by the queued/closed-loop commands. These push the command
# onto the firmware queue and block until a completion callback arrives. On this
# chassis that callback may never come -> the call HANGS until ``timeout`` (here
# ~7 days). Mirrors the proven ``magiciango/go.py`` reference.
_WAIT: Dict[str, Any] = {"isQueued": True, "isWaitForFinish": True, "timeout": 604800000}

# String aliases accepted by :meth:`rgb` ``number``, mapping to firmware LED ids.
_LED_NAMES: Dict[str, int] = {
    "LED_1": 1,
    "LED_2": 2,
    "LED_3": 3,
    "LED_4": 4,
    "LED_ALL": 5,
}

# A connected ``DobotLinkClient`` (or any object exposing ``call``/``notify``).
ClientLike = Any
# Accepted forms for the RGB LED channel selector.
LedSelector = Union[LEDChannel, int, str]


class MagicianGO:
    """Ergonomic, typed wrapper over the DobotLink ``MagicianGO.*`` RPC surface.

    Args:
        client: A connected :class:`~dobotkit.go.client.DobotLinkClient` (or any
            object exposing ``call(method, **params)`` and
            ``notify(method, **params)``).
        port_name: The COM port DobotLink uses to reach the GO. Defaults to
            ``"COM5"``. Sent as ``portName`` on every call except
            :meth:`search`.
    """

    def __init__(self, client: ClientLike, port_name: str = "COM5") -> None:
        self._client = client
        self.port_name = port_name

    # ---- internals ---------------------------------------------------------

    def _call(self, func: str, **params: Any) -> Any:
        """Issue ``MagicianGO.<func>`` with ``portName`` and block for the result."""
        params["portName"] = self.port_name
        return self._client.call(f"MagicianGO.{func}", **params)

    # ---- connection --------------------------------------------------------

    def search(self) -> Any:
        """Search for connectable GO units (``MagicianGO.SearchDobot``).

        Unlike every other method this sends **no** ``portName`` (it runs before
        a port is chosen). The DobotLink response is returned verbatim; its exact
        structure is firmware-defined and not normalised here.
        """
        return self._client.call("MagicianGO.SearchDobot")

    def connect_robot(self) -> Any:
        """Tell DobotLink to connect to the GO on :attr:`port_name`.

        Required before any command. Note: the handshake can report a *false*
        success — always follow it with a real read (:meth:`battery`) to verify
        the link, or simply use :meth:`connect`.
        """
        return self._call("ConnectDobot")

    def disconnect_robot(self) -> Any:
        """Disconnect DobotLink from the GO (``MagicianGO.DisconnectDobot``)."""
        return self._call("DisconnectDobot")

    def set_running_mode(self, mode: int) -> Any:
        """Set the driving mode (``SetRunningMode(runningMode=mode)``).

        ``mode`` is an integer; the concrete meaning of each value is
        firmware-defined and not confirmed from source (examples probe ``0``/``1``).
        """
        return self._call("SetRunningMode", runningMode=mode)

    def connect(self, verify: bool = True) -> Any:
        """Connect to the GO and (by default) verify the link.

        Calls :meth:`connect_robot`, then — unless ``verify`` is ``False`` —
        calls :meth:`battery` so a dead power/wireless link surfaces immediately
        (a hung/timed-out read) rather than silently after a false-success
        handshake.

        Args:
            verify: When ``True`` (default), perform the battery read-back and
                return its result. When ``False``, only connect and return the
                ``connect_robot`` result.

        Returns:
            The :meth:`battery` reading when ``verify`` is ``True``, else the
            :meth:`connect_robot` result.
        """
        result = self.connect_robot()
        if verify:
            return self.battery()
        return result

    # ---- continuous drive (trusted) ----------------------------------------

    def move(self, x: float = 0, y: float = 0, r: float = 0) -> Any:
        """Set a continuous velocity vector (``SetMoveSpeed``).

        Drives until :meth:`stop`/:meth:`emergency_stop`. Convention:
        ``x+`` forward, ``y+`` strafe left, ``r+`` rotate CCW (left).
        """
        return self._call("SetMoveSpeed", x=x, y=y, r=r)

    def move_direct(self, direction: int, speed: int) -> Any:
        """Drive in a fixed ``direction`` at ``speed`` (``SetMoveSpeedDirect``).

        The Python ``direction`` maps to the RPC field ``dir``. ``direction`` is
        an integer enum (``0`` is *presumed* forward) whose value mapping is
        firmware-defined and unconfirmed. Prefer :meth:`forward`/:meth:`move`
        for ordinary driving.
        """
        return self._call("SetMoveSpeedDirect", dir=direction, speed=speed)

    def forward(self, speed: float) -> Any:
        """Drive forward at ``speed`` (= ``move(x=speed)``)."""
        return self.move(x=speed)

    def backward(self, speed: float) -> Any:
        """Drive backward at ``speed`` (= ``move(x=-speed)``)."""
        return self.move(x=-speed)

    def strafe(self, speed: float) -> Any:
        """Strafe left (+) / right (-) at ``speed`` (= ``move(y=speed)``)."""
        return self.move(y=speed)

    def spin(self, speed: float) -> Any:
        """Rotate in place at ``speed`` (``+`` = CCW; = ``move(r=speed)``)."""
        return self.move(r=speed)

    def stop(self) -> Any:
        """Stop driving (= ``move(0, 0, 0)``; waits for the response)."""
        return self.move(0, 0, 0)

    def emergency_stop(self) -> None:
        """Stop immediately via ``notify`` — never blocks, never times out.

        Sends ``SetMoveSpeed(x=0, y=0, r=0)`` as a fire-and-forget JSON-RPC
        notification, so it is safe to call from a ``finally`` block or an
        interrupt path even if the link is degraded.
        """
        self._client.notify(
            "MagicianGO.SetMoveSpeed", portName=self.port_name, x=0, y=0, r=0
        )

    # ---- closed-loop / queued (WARNING: HANG risk) -------------------------

    def rotate(self, r: float, Vr: float) -> Any:
        """Rotate by ``r`` degrees at angular speed ``Vr`` (``SetRotate``).

        .. warning::
            Closed-loop queued command — on this chassis the completion callback
            may never arrive, so this call can **HANG** until the (~7 day)
            timeout. For reliable in-place turns use
            ``dobotkit.go.navigation.PreciseMover.turn_degrees`` (continuous
            :meth:`move` + IMU feedback) instead.
        """
        return self._call("SetRotate", r=r, Vr=Vr, **_WAIT)

    def move_dist(self, x: float, y: float, Vx: float, Vy: float) -> Any:
        """Move a fixed distance ``(x, y)`` at velocities ``(Vx, Vy)`` (``SetMoveDist``).

        .. warning::
            Closed-loop queued command — can **HANG** on this chassis (no
            completion callback). Prefer ``PreciseMover.goto_distance``.
        """
        return self._call("SetMoveDist", x=x, y=y, Vx=Vx, Vy=Vy, **_WAIT)

    def arc_rad(self, velocity: float, radius: float, angle: float, mode: int) -> Any:
        """Drive a radius-based arc (``SetArcRad``).

        ``mode`` is an integer direction/mode flag passed through to firmware
        (meaning per value unconfirmed; examples use ``mode=0``).

        .. warning::
            Closed-loop queued command — can **HANG** on this chassis. Prefer a
            continuous-move + feedback loop.
        """
        return self._call(
            "SetArcRad", velocity=velocity, radius=radius, angle=angle, mode=mode, **_WAIT
        )

    def arc_cent(self, velocity: float, x: float, y: float, angle: float, mode: int) -> Any:
        """Drive a centre-point arc (``SetArcCent``).

        ``mode`` is an integer direction/mode flag passed through to firmware
        (meaning per value unconfirmed; examples use ``mode=0``).

        .. warning::
            Closed-loop queued command — can **HANG** on this chassis. Prefer a
            continuous-move + feedback loop.
        """
        return self._call(
            "SetArcCent", velocity=velocity, x=x, y=y, angle=angle, mode=mode, **_WAIT
        )

    def coord_closed_loop(self, is_enable: bool, angle: float) -> Any:
        """Enable/disable coordinate closed-loop (``SetCoordClosedLoop``).

        Unlike the other closed-loop commands this does **not** send the
        ``isQueued/isWaitForFinish/timeout`` wait flags, so it does not wait for
        a completion callback (different behaviour from :meth:`rotate` et al.).
        """
        return self._call("SetCoordClosedLoop", isEnable=is_enable, angle=angle)

    def increment_closed_loop(self, x: float, y: float, angle: float) -> Any:
        """Incremental closed-loop move (``SetIncrementClosedLoop``).

        .. warning::
            Closed-loop queued command — can **HANG** on this chassis. Prefer
            ``PreciseMover`` (continuous move + sensor feedback).
        """
        return self._call("SetIncrementClosedLoop", x=x, y=y, angle=angle, **_WAIT)

    # ---- safety ------------------------------------------------------------

    def clearance_ok(
        self, x: float = 0, y: float = 0, r: float = 0, threshold: float = 20
    ) -> Tuple[bool, Union[Dict[str, float], str]]:
        """Check ultrasonic clearance in the intended direction of travel.

        Reads :meth:`ultrasonic` and verifies the relevant sensor(s) report at
        least ``threshold`` cm of clearance for the requested motion:

        * ``x > 0`` -> front, ``x < 0`` -> back.
        * ``y != 0`` -> both sides (min of left/right).
        * ``r != 0`` -> all four directions (in-place rotation sweeps a circle).

        Args:
            x: Intended forward/backward velocity sign (only sign matters).
            y: Intended strafe velocity sign (only sign matters).
            r: Intended rotation velocity (any non-zero requires all-around clearance).
            threshold: Minimum acceptable distance in cm. Defaults to ``20``.

        Returns:
            ``(True, distances)`` where ``distances`` is the ultrasonic dict when
            clear, otherwise ``(False, reason)`` with a human-readable reason
            string naming the blocked direction.
        """
        u = self.ultrasonic()
        if x > 0 and u["front"] < threshold:
            return False, f"front={u['front']}<{threshold}"
        if x < 0 and u["back"] < threshold:
            return False, f"back={u['back']}<{threshold}"
        if y != 0 and min(u["left"], u["right"]) < threshold:
            return False, f"side min={min(u['left'], u['right'])}<{threshold}"
        if r != 0 and min(u.values()) < threshold:
            return False, f"around min={min(u.values())}<{threshold}"
        return True, u

    # ---- output: LED / buzzer ----------------------------------------------

    def rgb(
        self,
        number: LedSelector,
        effect: int,
        r: int,
        g: int,
        b: int,
        cycle: int,
        counts: int,
    ) -> Any:
        """Set an RGB LED (``SetLightRGB``).

        Args:
            number: LED channel — a :class:`~dobotkit.enums.LEDChannel`, an int
                ``1..5`` (``5`` = all), or a string name
                (``"LED_1"``..``"LED_4"``, ``"LED_ALL"``).
            effect: ``1`` = on, ``0`` = off.
            r: Red ``0..255``.
            g: Green ``0..255``.
            b: Blue ``0..255``.
            cycle: Blink period (firmware integer; use ``0`` for steady).
            counts: Blink count (firmware integer; use ``0`` for steady).
        """
        if isinstance(number, str):
            number = _LED_NAMES[number]
        else:
            number = int(number)  # LEDChannel or int -> plain int on the wire
        return self._call(
            "SetLightRGB", number=number, effect=effect, r=r, g=g, b=b, cycle=cycle, counts=counts
        )

    def buzzer(self, index: int, tone: int, beat: int) -> Any:
        """Sound the buzzer (``SetBuzzerSound``).

        ``index``/``tone``/``beat`` are integers (note index / pitch / beat);
        their exact ranges and meanings are firmware-defined and unconfirmed.
        """
        return self._call("SetBuzzerSound", index=index, tone=tone, beat=beat)

    # ---- sensors (read-only, motors idle) ----------------------------------

    def ultrasonic(self) -> Dict[str, float]:
        """Read the four ultrasonic distances in cm (``GetUltrasoundData``).

        Returns a dict ``{front, back, left, right}``.
        """
        return cast(Dict[str, float], self._call("GetUltrasoundData"))

    def odometer(self) -> Dict[str, float]:
        """Read accumulated world-frame pose (``GetSpeedometer``).

        Returns ``{x, y, yaw}`` — position in mm, yaw in degrees (zeroed by
        :meth:`set_odometer`). Note the firmware spelling ``Speedometer``.
        """
        return cast(Dict[str, float], self._call("GetSpeedometer"))

    def set_odometer(self, x: float, y: float, yaw: float) -> Any:
        """Force the odometer pose (``SetSpeedometer``) — used to zero coordinates."""
        return self._call("SetSpeedometer", x=x, y=y, yaw=yaw)

    def battery(self) -> Dict[str, float]:
        """Read battery voltage/percentage (``GetBatteryVoltage``).

        Returns ``{powerVoltage, powerPercentage}``. Commonly used as the
        link-verification read after :meth:`connect_robot`.
        """
        return cast(Dict[str, float], self._call("GetBatteryVoltage"))

    def imu_angle(self) -> Dict[str, float]:
        """Read the IMU angle (``GetImuAngle``).

        Returns ``{yaw, ...}`` — an absolute angle referenced to power-on (not
        affected by :meth:`set_odometer`).
        """
        return cast(Dict[str, float], self._call("GetImuAngle"))

    def imu_speed(self) -> Dict[str, float]:
        """Read the IMU angular speed (``GetImuSpeed``)."""
        return cast(Dict[str, float], self._call("GetImuSpeed"))

    # ---- line-trace --------------------------------------------------------

    def auto_trace(self, on: Any) -> Any:
        """Turn line-tracing on/off (``SetTraceLoop`` then ``SetTraceAuto``)."""
        self._call("SetTraceLoop", enable=bool(on))
        return self._call("SetTraceAuto", isTrace=bool(on))

    def trace_speed(self, speed: float) -> Any:
        """Set the line-tracing speed (``SetTraceSpeed``)."""
        return self._call("SetTraceSpeed", speed=speed)

    def trace_pid(self, p: float, i: float, d: float) -> Any:
        """Set the line-following PID gains (``SetTracePid``)."""
        return self._call("SetTracePid", p=p, i=i, d=d)

    def trace_angle(self) -> Any:
        """Read the CAR camera's detected line angle (``GetCarCameraAngle``).

        Returns ``{angle, count}``. Uses the CAR camera, so it is unaffected by
        an inactive ARM camera (405).
        """
        return self._call("GetCarCameraAngle")

    # ---- camera (defensive parsing — see research doc §3.8) ----------------

    def car_camera_obj(self) -> Any:
        """CAR-camera deep-learning object detection (``GetCarCameraObj``).

        Returns the firmware result (e.g. ``{count, dl_obj: [...]}``) verbatim;
        field names vary by firmware/version, so callers should read it
        defensively (prefer ``result.get("count", len(result.get("dl_obj", [])))``).
        """
        return self._call("GetCarCameraObj")

    def arm_camera_obj(self) -> Any:
        """ARM-camera object detection (``GetArmCameraObj``).

        May be inactive on some chassis (firmware error ``405`` / timeout); fall
        back to :meth:`car_camera_obj`. Returned structure is read defensively.
        """
        return self._call("GetArmCameraObj")

    def arm_camera_tag(self) -> Any:
        """ARM-camera AprilTag/marker detection (``GetArmCameraTag``).

        May be inactive on some chassis (``405`` / timeout). Returned structure
        is firmware-defined; read it defensively.
        """
        return self._call("GetArmCameraTag")
