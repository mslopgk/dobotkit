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
* **Closed-loop / queued commands** (:meth:`unsafe_rotate`,
  :meth:`unsafe_move_dist`, :meth:`unsafe_arc_rad`, :meth:`unsafe_arc_cent`,
  :meth:`unsafe_increment_closed_loop`; :meth:`coord_closed_loop` is the lone
  non-waiting exception) are issued with the firmware's
  ``isQueued/isWaitForFinish`` wait flags and **can HANG** on this chassis when
  the completion callback never arrives (hardware-measured). Their canonical
  names carry the ``unsafe_`` prefix so they cannot be picked up by accident;
  the old bare names remain as deprecated aliases that emit a ``UserWarning``.
  For reliable precise motion build a closed loop out of continuous
  :meth:`move` plus sensor feedback (see
  ``dobotkit.go.navigation.PreciseMover`` / ``WaypointNav``).

Safety workflow (see research doc §8): after :meth:`connect_robot` always verify
the link with a read such as :meth:`battery` (use :meth:`connect` which does
this for you); check :meth:`clearance_ok` before driving; wrap motion in
``try/finally`` ending in :meth:`emergency_stop`.

Beyond the hardware-verified core above, the class also exposes the *extended*
RPC surface mined from the official DobotLink sources (DobotEDU wrapper, CHM
help, plugin protocol tables) on 2026-07-04: diagnostics/alarms, firmware
trace configuration, absolute drive, extended CAR/ARM camera reads and
calibration, firmware command-queue control, MagicBox stop-point service
(``MagicBox.*`` namespace), light prompt, and device identity/maintenance.
Those methods are **hardware-unverified (2026-07-04)** — each docstring says
so — and follow the same safety split: the lone queued motion command,
:meth:`unsafe_move_pos`, carries the ``unsafe_`` prefix and HANG warning.
"""
from __future__ import annotations

import math
import time
import warnings
from typing import Any, Dict, Optional, Tuple, Union, cast

from dobotkit.enums import LEDChannel

# Wait flags shared by the queued/closed-loop commands. These push the command
# onto the firmware queue and block until a completion callback arrives. On this
# chassis that callback may never come -> the call HANGS until ``timeout`` (here
# ~7 days). Mirrors the proven ``magiciango/go.py`` reference.
_WAIT: Dict[str, Any] = {"isQueued": True, "isWaitForFinish": True, "timeout": 604800000}

#: Hard cap (magnitude) applied to every continuous-velocity component. Speed
#: units are firmware-defined and unconfirmed; 8..30 is the empirically safe
#: range on this chassis, so nothing larger is ever put on the wire.
SPEED_CAP: float = 30.0

#: The ultrasonic sensors clamp at this ceiling (hardware-measured): readings
#: of 40 mean "40 cm **or more**".
ULTRA_MAX_CM: float = 40.0

_ULTRA_KEYS: Tuple[str, str, str, str] = ("front", "back", "left", "right")

# Deprecation text for the queued closed-loop commands (measured HANG risk).
_HANG_WARNING = (
    "MagicianGO.{name}() is a queued closed-loop command that can HANG on this "
    "chassis (the completion callback never arrives) — prefer {alt}. "
    "이 명령은 이 기체에서 멈춤(HANG)이 실측되었습니다. {alt} 를 사용하세요. "
    "To acknowledge the risk explicitly, call unsafe_{name}() instead."
)


def _cap(value: float) -> float:
    """Clamp a velocity component's magnitude to the :data:`SPEED_CAP` safety cap.

    Non-finite input (NaN/inf from broken control math) maps to **0.0** — an
    undefined velocity must refuse to move, never drive. Naive
    ``max(min(...))`` clamping would turn NaN into +SPEED_CAP (full speed)
    because NaN comparisons are always False.
    """
    v = float(value)
    if not math.isfinite(v):
        return 0.0
    return max(-SPEED_CAP, min(SPEED_CAP, v))

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
        client: A connected :class:`~dobotkit.link.DobotLinkClient` (or any
            object exposing ``call(method, **params)`` and
            ``notify(method, **params)``).
        port_name: The COM port DobotLink uses to reach the GO. Defaults to
            ``"COM5"``. Sent as ``portName`` on every call except
            :meth:`search`.
    """

    def __init__(self, client: ClientLike, port_name: str = "COM5") -> None:
        self._client = client
        self.port_name = port_name
        self._owns_client = False  # True only when built via :meth:`open`
        #: Connection lifecycle flag: ``True`` after a successful
        #: :meth:`connect_robot`/:meth:`connect`, ``False`` initially and after
        #: :meth:`disconnect_robot` or context-manager exit. Consumers (e.g.
        #: GUI controllers) read this to gate device features.
        self.connected: bool = False

    # ---- lifecycle ----------------------------------------------------------

    @classmethod
    def open(
        cls,
        port_name: str = "COM5",
        host: str = "localhost",
        port: int = 9090,
        timeout: float = 10.0,
    ) -> "MagicianGO":
        """One-line entry point: connect DobotLink, wrap it, verify the GO link.

        Equivalent to ``DobotLinkClient(host, port, timeout).connect()`` +
        ``MagicianGO(client, port_name)`` + :meth:`connect` (which includes the
        battery link-verification read). The returned instance *owns* its
        client, so using it as a context manager closes the socket too::

            with MagicianGO.open(port_name="COM5") as go:
                go.forward(15)
                ...
            # <- line-trace OFF + emergency stop + socket closed, even on error
        """
        from dobotkit.link import DobotLinkClient

        client = DobotLinkClient(host=host, port=port, timeout=timeout).connect()
        go = cls(client, port_name=port_name)
        go._owns_client = True
        try:
            go.connect()
        except Exception:
            client.close()
            raise
        return go

    def __enter__(self) -> "MagicianGO":
        return self

    def __exit__(self, *exc: object) -> None:
        """Best-effort safety teardown so a crashed script never leaves the car driving.

        Order matters on a degraded link:

        1. :meth:`emergency_stop` **first** — a fire-and-forget notify that can
           never block, so the manual-drive case stops instantly even when the
           link is hung (a blocking call here could stall the stop by the full
           client timeout).
        2. ``auto_trace(False)`` — blocking, but required: while firmware
           patrol is active it overrides ``SetMoveSpeed``, so the notify alone
           does not stop a patrolling car.
        3. :meth:`cmd_queue_force_stop` — blocking, best-effort: a queued
           motion command (e.g. an escaped :meth:`unsafe_move_pos`) keeps
           executing **in firmware** and ``SetMoveSpeed(0)`` does not stop
           queue execution; DobotLab's own emergency sequence issues this
           queue force-stop first. hardware-unverified (2026-07-04) — do not
           rely on it as the only stop.
        4. :meth:`emergency_stop` again — re-assert zero velocity after the
           patrol/queue controllers let go.

        Teardown errors are swallowed — they must never mask the original
        exception. When this instance was created via :meth:`open` the owned
        client socket is closed as the final step.
        """
        try:
            self.emergency_stop()
        except Exception:  # noqa: BLE001 - teardown must never raise
            pass
        try:
            self.auto_trace(False)
        except Exception:  # noqa: BLE001 - teardown must never raise
            pass
        try:
            self.cmd_queue_force_stop()
        except Exception:  # noqa: BLE001 - teardown must never raise
            pass
        try:
            self.emergency_stop()
        except Exception:  # noqa: BLE001 - teardown must never raise
            pass
        self.connected = False  # the session is over either way
        if self._owns_client:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001 - teardown must never raise
                pass

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

        Required before any command. Sets :attr:`connected` on success. Note:
        the handshake can report a *false* success — always follow it with a
        real read (:meth:`battery`) to verify the link, or simply use
        :meth:`connect` (which resets :attr:`connected` if verification fails).
        """
        result = self._call("ConnectDobot")
        self.connected = True
        return result

    def disconnect_robot(self) -> Any:
        """Disconnect DobotLink from the GO (``MagicianGO.DisconnectDobot``)."""
        self.connected = False
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
            try:
                return self.battery()
            except Exception:
                # Handshake succeeded but the link is dead (false success) —
                # the device is NOT usable, so don't report it as connected.
                self.connected = False
                raise
        return result

    # ---- continuous drive (trusted) ----------------------------------------

    def move(self, x: float = 0, y: float = 0, r: float = 0) -> Any:
        """Set a continuous velocity vector (``SetMoveSpeed``).

        Drives **until told to stop** — prefer :meth:`drive_for` when a bounded
        pulse is all you need. Convention: ``x+`` forward, ``y+`` strafe left,
        ``r+`` rotate CCW (left). Each component's magnitude is clamped to
        :data:`SPEED_CAP` (±30); speed units are firmware-defined and
        unconfirmed — 8..30 is the practical range on this chassis.
        """
        return self._call("SetMoveSpeed", x=_cap(x), y=_cap(y), r=_cap(r))

    def move_direct(self, direction: int, speed: float) -> Any:
        """Drive in a fixed ``direction`` at ``speed`` (``SetMoveSpeedDirect``).

        The Python ``direction`` maps to the RPC field ``dir``. ``direction`` is
        an integer enum (``0`` is *presumed* forward) whose value mapping is
        firmware-defined and unconfirmed. ``speed`` magnitude is clamped to
        :data:`SPEED_CAP` like every other continuous-velocity command. Prefer
        :meth:`forward`/:meth:`move` for ordinary driving.
        """
        return self._call("SetMoveSpeedDirect", dir=direction, speed=_cap(speed))

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

    def drive_for(
        self, x: float = 0, y: float = 0, r: float = 0, seconds: float = 0.5
    ) -> None:
        """Dead-man drive: :meth:`move` for ``seconds`` (clamped to 5 s), then stop.

        The safe, bounded alternative to a bare :meth:`move` — even if the
        caller is interrupted mid-pulse, the ``finally`` still stops the car
        (fire-and-forget :meth:`emergency_stop`, then a confirming
        :meth:`stop`; if that confirming read fails the emergency stop is
        re-fired).
        """
        duration = max(0.0, min(5.0, float(seconds)))
        try:
            self.move(x=x, y=y, r=r)
            time.sleep(duration)
        finally:
            # Teardown must never raise (e.g. replace an in-flight
            # KeyboardInterrupt with a socket error) — same convention as
            # __exit__. Every stop attempt is individually guarded.
            try:
                self.emergency_stop()
            except Exception:  # noqa: BLE001 - teardown must never raise
                pass
            try:
                self.stop()
            except Exception:  # noqa: BLE001 - any link error -> re-fire safe stop
                try:
                    self.emergency_stop()
                except Exception:  # noqa: BLE001 - teardown must never raise
                    pass

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
    #
    # The canonical names carry an ``unsafe_`` prefix so autocompletion and
    # LLM-generated code cannot pick up a hang-prone command by accident. The
    # old bare names are kept as deprecated aliases that emit a ``UserWarning``
    # and delegate.

    def unsafe_rotate(self, r: float, Vr: float) -> Any:
        """Rotate by ``r`` degrees at angular speed ``Vr`` (``SetRotate``).

        .. warning::
            Closed-loop queued command — on this chassis the completion callback
            may never arrive, so this call can **HANG** until the (~7 day)
            timeout. For reliable in-place turns use
            ``dobotkit.go.navigation.PreciseMover.turn_degrees`` (continuous
            :meth:`move` + IMU feedback) instead.
        """
        return self._call("SetRotate", r=r, Vr=Vr, **_WAIT)

    def rotate(self, r: float, Vr: float) -> Any:
        """Deprecated alias of :meth:`unsafe_rotate` (measured HANG risk)."""
        warnings.warn(
            _HANG_WARNING.format(name="rotate", alt="PreciseMover.turn_degrees"),
            UserWarning,
            stacklevel=2,
        )
        return self.unsafe_rotate(r=r, Vr=Vr)

    def unsafe_move_dist(self, x: float, y: float, Vx: float, Vy: float) -> Any:
        """Move a fixed distance ``(x, y)`` at velocities ``(Vx, Vy)`` (``SetMoveDist``).

        .. warning::
            Closed-loop queued command — can **HANG** on this chassis (no
            completion callback). Prefer ``PreciseMover.goto_distance``.
        """
        return self._call("SetMoveDist", x=x, y=y, Vx=Vx, Vy=Vy, **_WAIT)

    def move_dist(self, x: float, y: float, Vx: float, Vy: float) -> Any:
        """Deprecated alias of :meth:`unsafe_move_dist` (measured HANG risk)."""
        warnings.warn(
            _HANG_WARNING.format(name="move_dist", alt="PreciseMover.goto_distance"),
            UserWarning,
            stacklevel=2,
        )
        return self.unsafe_move_dist(x=x, y=y, Vx=Vx, Vy=Vy)

    def unsafe_arc_rad(self, velocity: float, radius: float, angle: float, mode: int) -> Any:
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

    def arc_rad(self, velocity: float, radius: float, angle: float, mode: int) -> Any:
        """Deprecated alias of :meth:`unsafe_arc_rad` (measured HANG risk)."""
        warnings.warn(
            _HANG_WARNING.format(name="arc_rad", alt="a continuous-move feedback loop"),
            UserWarning,
            stacklevel=2,
        )
        return self.unsafe_arc_rad(velocity=velocity, radius=radius, angle=angle, mode=mode)

    def unsafe_arc_cent(
        self, velocity: float, x: float, y: float, angle: float, mode: int
    ) -> Any:
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

    def arc_cent(self, velocity: float, x: float, y: float, angle: float, mode: int) -> Any:
        """Deprecated alias of :meth:`unsafe_arc_cent` (measured HANG risk)."""
        warnings.warn(
            _HANG_WARNING.format(name="arc_cent", alt="a continuous-move feedback loop"),
            UserWarning,
            stacklevel=2,
        )
        return self.unsafe_arc_cent(velocity=velocity, x=x, y=y, angle=angle, mode=mode)

    def coord_closed_loop(self, is_enable: bool, angle: float) -> Any:
        """Enable/disable coordinate closed-loop (``SetCoordClosedLoop``).

        Unlike the other closed-loop commands this does **not** send the
        ``isQueued/isWaitForFinish/timeout`` wait flags, so it does not wait for
        a completion callback (different behaviour from :meth:`unsafe_rotate`
        et al.) and is not hang-prone.
        """
        return self._call("SetCoordClosedLoop", isEnable=is_enable, angle=angle)

    def unsafe_increment_closed_loop(self, x: float, y: float, angle: float) -> Any:
        """Incremental closed-loop move (``SetIncrementClosedLoop``).

        .. warning::
            Closed-loop queued command — can **HANG** on this chassis. Prefer
            ``PreciseMover`` (continuous move + sensor feedback).
        """
        return self._call("SetIncrementClosedLoop", x=x, y=y, angle=angle, **_WAIT)

    def increment_closed_loop(self, x: float, y: float, angle: float) -> Any:
        """Deprecated alias of :meth:`unsafe_increment_closed_loop` (measured HANG risk)."""
        warnings.warn(
            _HANG_WARNING.format(name="increment_closed_loop", alt="PreciseMover"),
            UserWarning,
            stacklevel=2,
        )
        return self.unsafe_increment_closed_loop(x=x, y=y, angle=angle)

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
            string naming the blocked direction. A malformed ultrasonic read
            (``None``) is itself a blocking reason — unknown means stop.
        """
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

        Hardware-verified (2026-07-03): with ``cycle=0, counts=0`` the LEDs
        stay dim/dark regardless of ``effect`` — send ``cycle=1, counts>=1``
        (or more) for a visible light. ``effect=0`` turns off; effects 1..3
        all light up (3 is what DobotLab's own quick-test sends).

        Args:
            number: LED channel — a :class:`~dobotkit.enums.LEDChannel`, an int
                ``1..5`` (``5`` = all), or a string name
                (``"LED_1"``..``"LED_4"``, ``"LED_ALL"``).
            effect: ``0`` = off; ``1..3`` = lit (mode enum, DobotLab uses 3).
            r: Red ``0..255``.
            g: Green ``0..255``.
            b: Blue ``0..255``.
            cycle: Blink period (use ``1`` — ``0`` renders dark, measured).
            counts: Blink count (use ``>=1`` — ``0`` renders dark, measured).
        """
        if isinstance(number, str):
            number = _LED_NAMES[number]
        else:
            number = int(number)  # LEDChannel or int -> plain int on the wire
        return self._call(
            "SetLightRGB", number=number, effect=effect, r=r, g=g, b=b, cycle=cycle, counts=counts
        )

    def buzzer(self, index: int = 5, tone: int = 0, beat: int = 0) -> Any:
        """Sound the buzzer (``SetBuzzerSound``).

        Hardware-verified (2026-07-03): ``index=5, tone=0, beat=0`` — the
        exact combo DobotLab's own beep uses — produces a clean beep. Other
        combos (e.g. ``index=1, tone=5, beat=1``) produce a rattling buzz or
        nothing; full range semantics remain firmware-defined.
        """
        return self._call("SetBuzzerSound", index=index, tone=tone, beat=beat)

    # ---- sensors (read-only, motors idle) ----------------------------------

    def ultrasonic(self) -> Optional[Dict[str, float]]:
        """Read the four ultrasonic distances in cm, validated (``GetUltrasoundData``).

        Returns ``{front, back, left, right}`` with every value clamped to the
        hardware's measured :data:`ULTRA_MAX_CM` (40 cm) ceiling — a reading of
        40 means "40 cm **or more**". Returns ``None`` when the response is
        malformed: missing keys, non-numeric, or ``<= 0`` sentinel values from
        an absent/failed sensor. Callers must treat ``None`` as
        "unknown -> stop" (as :meth:`clearance_ok` does). Use
        :meth:`ultrasonic_raw` for the untouched firmware response.
        """
        raw = self.ultrasonic_raw()
        if not isinstance(raw, dict):
            return None
        out: Dict[str, float] = {}
        for key in _ULTRA_KEYS:
            value = raw.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return None
            v = float(value)
            # NaN would sail through <=0 (NaN comparisons are False) and then
            # defeat clearance_ok the same way — require a finite positive value.
            if not math.isfinite(v) or v <= 0:
                return None
            out[key] = min(v, ULTRA_MAX_CM)
        return out

    def ultrasonic_raw(self) -> Any:
        """Raw ``GetUltrasoundData`` response, unvalidated (advanced/diagnostic use)."""
        return self._call("GetUltrasoundData")

    def odometer(self) -> Dict[str, float]:
        """Read accumulated world-frame pose (``GetSpeedometer``).

        Returns ``{x, y, yaw}`` — position nominally in mm, yaw in degrees
        (zeroed by :meth:`set_odometer`). Note the firmware spelling
        ``Speedometer``.

        .. caution::
            The mm scale is **suspect** (2026-07-03 measurement: a drive whose
            odometer counted ~110 covered roughly 370-470 real millimetres —
            a 3-4x undercount). Treat odometer distances as *relative* progress
            until the scale is calibrated with a ruler on your chassis.
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
        """Read raw IMU accel/gyro (``GetImuSpeed``).

        Hardware-verified (2026-07-03): returns ``{ax, ay, az, gx, gy, gz}`` —
        accelerometer in g (``az ~= -0.95`` at rest = gravity) plus gyro rates,
        **not** an angular-speed ``{yaw}`` dict as the RPC name suggests.
        """
        return cast(Dict[str, float], self._call("GetImuSpeed"))

    # ---- line-trace --------------------------------------------------------

    def auto_trace(self, on: Any) -> Any:
        """Turn line-tracing on/off (``SetTraceLoop`` then ``SetTraceAuto``).

        Hardware-verified wire format (2026-07-02): the DobotLink plugin
        declares ``isTrace`` as **int**, so sending a JSON bool is parsed as 0
        and the command is silently ignored — patrol neither starts *nor
        stops*. ``type=0`` is also required. DobotLab's own patrol button sends
        exactly ``SetTraceAuto{isTrace: 1, type: 0}``.
        """
        self._call("SetTraceLoop", enable=bool(on))
        return self._call("SetTraceAuto", isTrace=int(bool(on)), type=0)

    def trace_speed(self, speed: float) -> Any:
        """Set the line-tracing speed (``SetTraceSpeed``)."""
        return self._call("SetTraceSpeed", speed=speed)

    def trace_pid(self, p: float, i: float, d: float) -> Any:
        """Set the line-following PID gains (``SetTracePid``)."""
        return self._call("SetTracePid", p=p, i=i, d=d)

    def trace_angle(self) -> Dict[str, int]:
        """Read the CAR camera's detected line angle (``GetCarCameraAngle``).

        Returns a normalised ``{"angle": int, "count": int}``; a malformed
        firmware response degrades to ``{"angle": 0, "count": 0}`` ("no line")
        rather than raising. Uses the CAR camera, so it is unaffected by an
        inactive ARM camera (405). ``count == 0`` means no line is seen.
        See also :meth:`firmware_trace_angle` — a *different*, unconfirmed RPC.
        """
        raw = self._call("GetCarCameraAngle")
        if not isinstance(raw, dict):
            return {"angle": 0, "count": 0}
        try:
            return {"angle": int(raw.get("angle", 0)), "count": int(raw.get("count", 0))}
        except (TypeError, ValueError):
            return {"angle": 0, "count": 0}

    def line_error(self, center: float) -> Optional[float]:
        """Line-following error ``angle - center`` in camera units, or ``None``.

        The teaching primitive for a P-controller: read the error, steer with
        ``move(x=speed, r=-kp * error)`` (steering sign is chassis-dependent —
        verify on hardware by nudging the car off-line and watching the sign).
        ``center`` is the measured on-line angle (~245 on the reference
        chassis). Returns ``None`` when the camera reports no line
        (``count == 0``) — treat that as "stop and search", not as error 0.
        """
        cam = self.trace_angle()
        if cam["count"] <= 0:
            return None
        return float(cam["angle"]) - float(center)

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

    # ---- diagnostics (extended, hardware-unverified) -------------------------

    def get_alarm_info(self) -> Any:
        """Read the active alarm/warning list (``GetAlarmInfo``).

        Returns the firmware result verbatim — expected shape is
        ``{"warning": [...]}`` per the plugin protocol table, but read it
        defensively. hardware-unverified (2026-07-04).
        """
        return self._call("GetAlarmInfo")

    def clean_alarm_info(self) -> Any:
        """Clear the active alarms (``CleanAlarmInfo``). hardware-unverified (2026-07-04)."""
        return self._call("CleanAlarmInfo")

    def running_state(self) -> Any:
        """Read the running state (``GetRunningState``).

        Expected shape ``{"runningState": int}`` is *presumed* from the plugin
        string table only (no JS call site, and the CHM page for this name
        documents a different RPC) — read the result defensively.
        hardware-unverified (2026-07-04).
        """
        return self._call("GetRunningState")

    def stall_protection(self) -> Any:
        """Read the stall-protection flag (``GetStallProtection``).

        Returns ``{"isHappened": int}`` per CHM/plugin table.
        hardware-unverified (2026-07-04).
        """
        return self._call("GetStallProtection")

    def off_ground(self) -> Any:
        """Read the wheels-off-ground flag (``GetOffGround``).

        Returns ``{"isHappened": int}`` per CHM/plugin table.
        hardware-unverified (2026-07-04).
        """
        return self._call("GetOffGround")

    def get_move_speed(self) -> Any:
        """Read the current velocity vector (``GetMoveSpeed``).

        Returns ``{x, y, r}`` — ``x``/``y`` in cm/s (0..100 per CHM), ``r`` in
        deg/s. The read-back counterpart of :meth:`move` (``SetMoveSpeed``).
        hardware-unverified (2026-07-04).
        """
        return self._call("GetMoveSpeed")

    def get_running_mode(self) -> Any:
        """Read the driving mode (``GetRunningMode``).

        The counterpart of :meth:`set_running_mode`. Expected shape is
        ``{"runningMode": int}`` (0 NORMAL / 1 SAFE), but the CHM keyword table
        contradicts itself (``runningState``) — read the result defensively.
        hardware-unverified (2026-07-04).
        """
        return self._call("GetRunningMode")

    # ---- trace (firmware, hardware-unverified) -------------------------------

    def firmware_trace_angle(self, **params: Any) -> Any:
        """Firmware line-trace angle (``GetTraceAngle``) — wire params unconfirmed.

        .. caution::
            This RPC **may not exist on the wire**: it is absent from the
            DobotLink plugin method table and the JS SDK, and the CHM only
            carries the file name (the page body documents ``GetImuAngle``).
            Expect an error from DobotLink. Any keyword arguments are passed
            through verbatim (wire params unconfirmed).

        Not the same thing as :meth:`trace_angle`, which calls
        ``GetCarCameraAngle`` — the CAR-camera line angle that DobotEDU's own
        ``get_trace_angle`` actually uses. Prefer :meth:`trace_angle` for line
        following. hardware-unverified (2026-07-04).
        """
        return self._call("GetTraceAngle", **params)

    def set_trace_line_info(self, lineInfo: int) -> Any:
        """Configure the trace line info (``SetTraceLineInfo(lineInfo=...)``).

        ``lineInfo`` is an integer whose per-value meaning is firmware-defined
        (CHM documents only the parameter name/type).
        hardware-unverified (2026-07-04).
        """
        return self._call("SetTraceLineInfo", lineInfo=lineInfo)

    # ---- absolute drive (extended, hardware-unverified) ----------------------

    def unsafe_move_pos(self, x: float, y: float, s: float) -> Any:
        """Move to absolute world position ``(x, y)`` cm at speed ``s`` (``SetMovePos``).

        ``x``/``y`` are target world coordinates in cm (odometer frame — see
        :meth:`odometer`/:meth:`set_odometer`), ``s`` is the travel speed in
        cm/s (0..100 per CHM). DobotEDU aligns heading first (``SetRotate`` by
        ``-yaw``) before issuing this; raw calls translate without turning.

        .. warning::
            Closed-loop queued command (sent with the ``isQueued`` /
            ``isWaitForFinish`` wait flags) — on this chassis the completion
            callback may never arrive, so this call can **HANG** until the
            (~7 day) timeout. Escaping a hung call (e.g. Ctrl-C) does **not**
            cancel the queued move — it keeps executing in firmware, and
            ``SetMoveSpeed(0)`` alone does not stop queue execution. The
            context-manager teardown issues a best-effort
            :meth:`cmd_queue_force_stop` (hardware-unverified) but do not
            rely on it; call :meth:`cmd_queue_force_stop` /
            :meth:`clean_cmd_queue` yourself when escaping. For reliable
            point-to-point motion use
            ``dobotkit.go.navigation.WaypointNav`` / ``PreciseMover``
            (continuous :meth:`move` + sensor feedback) instead.

        hardware-unverified (2026-07-04).
        """
        return self._call("SetMovePos", x=x, y=y, s=s, **_WAIT)

    def move_speed_time(
        self, time: float, x: float = 0, y: float = 0, r: float = 0, isAck: bool = False
    ) -> Any:
        """Drive at velocity ``(x, y, r)`` for ``time`` seconds (``SetMoveSpeedTime``).

        A firmware-side timed drive: unlike :meth:`drive_for` the stop happens
        in firmware, not in Python. **Not** a queued action command (DobotLab's
        own jog uses it with no queue flags and ``isAck=false``), so it does not
        carry HANG risk. Each velocity component's magnitude is clamped to
        :data:`SPEED_CAP` like every other continuous-velocity command; ``x``/
        ``y`` in cm/s, ``r`` in deg/s per CHM.

        .. caution::
            Because the drive runs **in firmware**, it outlives a crashed
            script — a typo like ``time=600`` would command a 10-minute drive
            with nothing in Python left to stop it. ``time`` is therefore
            clamped to **0..5 s**, mirroring :meth:`drive_for`. (The parameter
            keeps the wire name ``time``; it shadows the :mod:`time` module
            inside this method only.)

        hardware-unverified (2026-07-04).
        """
        duration = max(0.0, min(5.0, float(time)))
        return self._call(
            "SetMoveSpeedTime", time=duration, x=_cap(x), y=_cap(y), r=_cap(r), isAck=isAck
        )

    def set_origin_point(self, enable: int) -> Any:
        """Enable/disable the origin point (``SetOriginPoint(enable=...)``).

        ``enable``: ``1`` use / ``0`` don't use (CHM). Not a queued action
        command. hardware-unverified (2026-07-04).
        """
        return self._call("SetOriginPoint", enable=enable)

    # ---- camera extended (hardware-unverified; defensive parsing) ------------

    def car_camera_color(self) -> Any:
        """CAR-camera colour-block detection (``GetCarCameraColor``).

        Expected shape ``{count, color_obj: [{x, y, w, h, id}]}`` (count up to
        5) per CHM — like :meth:`car_camera_obj`, the array key may be absent
        when ``count == 0``, so read the result defensively (prefer
        ``result.get("count", len(result.get("color_obj", [])))``).
        hardware-unverified (2026-07-04).
        """
        return self._call("GetCarCameraColor")

    def car_camera_tag(self) -> Any:
        """CAR-camera AprilTag detection (``GetCarCameraTag``).

        Expected shape ``{count, aptag_obj: [{x, y, w, h, id, rot}]}`` (count up
        to 5) per CHM — the array key may be absent when ``count == 0``, so
        read the result defensively. hardware-unverified (2026-07-04).
        """
        return self._call("GetCarCameraTag")

    def get_car_camera_model(self) -> Any:
        """Read the CAR-camera run model (``GetCarCameraRunModel``).

        Returns ``{"runModelIndex": int}`` per the DobotEDU wrapper.
        hardware-unverified (2026-07-04).
        """
        return self._call("GetCarCameraRunModel")

    def set_car_camera_model(self, runModelIndex: int) -> Any:
        """Select the CAR-camera run model (``SetCarCameraRunModel``).

        hardware-unverified (2026-07-04).
        """
        return self._call("SetCarCameraRunModel", runModelIndex=runModelIndex)

    def get_car_camera_calibration_mode(self) -> Any:
        """Read CAR-camera calibration mode (``GetCarCameraCalibrationMode``).

        Expected shape ``{"isEnableCali": int}`` is *presumed* from the plugin
        table — read the result defensively. (The CHM example misspells the
        method without ``Car``; the plugin table carries the full name.)
        hardware-unverified (2026-07-04).
        """
        return self._call("GetCarCameraCalibrationMode")

    def set_car_camera_calibration_mode(self, isEnableCali: int) -> Any:
        """Enter/exit CAR-camera calibration mode (``SetCarCameraCalibrationMode``).

        ``isEnableCali``: ``1`` enter / ``0`` exit (CHM).
        hardware-unverified (2026-07-04).
        """
        return self._call("SetCarCameraCalibrationMode", isEnableCali=isEnableCali)

    def camera_calibration_data(self, april_list: str, device_list: str) -> Any:
        """Fit camera calibration from 9-point data (``GetCameraCalibrationData``).

        Despite the ``Get`` name this takes inputs: ``april_list`` and
        ``device_list`` are JSON-encoded strings of nine ``[x, y]`` points
        (AprilTag pixel coords and matching machine coords) — DobotLink feeds
        them to its ``fit_homography`` tool and returns an error-report string
        such as ``{"data": "max_x_err:0.44,..."}``. Read defensively.
        hardware-unverified (2026-07-04).
        """
        return self._call(
            "GetCameraCalibrationData", april_list=april_list, device_list=device_list
        )

    def arm_camera_color(self) -> Any:
        """ARM-camera colour-block detection (``GetArmCameraColor``).

        Expected shape ``{count, color_obj: [{x, y, w, h, id}]}`` (count up to
        5) per CHM — the array key may be absent when ``count == 0``, so read
        the result defensively. May be inactive on some chassis (``405`` /
        timeout) like the other ARM-camera reads. hardware-unverified (2026-07-04).
        """
        return self._call("GetArmCameraColor")

    def arm_camera_angle(self) -> Any:
        """ARM-camera detected angle (``GetArmCameraAngle``).

        Expected shape ``{"angle": int}`` per CHM; read defensively. May be
        inactive on some chassis (``405`` / timeout).
        hardware-unverified (2026-07-04).
        """
        return self._call("GetArmCameraAngle")

    def get_arm_camera_model(self) -> Any:
        """Read the ARM-camera run model (``GetArmCameraRunModel``).

        Returns ``{"runModelIndex": int}`` per the DobotEDU wrapper.
        hardware-unverified (2026-07-04).
        """
        return self._call("GetArmCameraRunModel")

    def set_arm_camera_model(self, runModelIndex: int) -> Any:
        """Select the ARM-camera run model (``SetArmCameraRunModel``).

        hardware-unverified (2026-07-04).
        """
        return self._call("SetArmCameraRunModel", runModelIndex=runModelIndex)

    def get_arm_camera_calibration_mode(self) -> Any:
        """Read ARM-camera calibration mode (``GetArmCameraCalibrationMode``).

        Expected shape ``{"isEnableCali": int}`` is *presumed* from the plugin
        table — read the result defensively. hardware-unverified (2026-07-04).
        """
        return self._call("GetArmCameraCalibrationMode")

    def set_arm_camera_calibration_mode(self, isEnableCali: int) -> Any:
        """Enter/exit ARM-camera calibration mode (``SetArmCameraCalibrationMode``).

        ``isEnableCali``: ``1`` enter / ``0`` exit (CHM).
        hardware-unverified (2026-07-04).
        """
        return self._call("SetArmCameraCalibrationMode", isEnableCali=isEnableCali)

    # ---- cmd queue (hardware-unverified) --------------------------------------

    def clean_cmd_queue(self) -> Any:
        """Clear the firmware command queue (``CleanCmdQueue``).

        hardware-unverified (2026-07-04).
        """
        return self._call("CleanCmdQueue")

    def cmd_queue_start(self) -> Any:
        """Start executing the firmware command queue (``SetCmdQueueStart``).

        hardware-unverified (2026-07-04).
        """
        return self._call("SetCmdQueueStart")

    def cmd_queue_stop(self) -> Any:
        """Stop the firmware command queue after the current command
        (``SetCmdQueueStop``). hardware-unverified (2026-07-04)."""
        return self._call("SetCmdQueueStop")

    def cmd_queue_force_stop(self) -> Any:
        """Force-stop the firmware command queue (``SetCmdQueueForcelyStop``).

        DobotLab's own emergency sequence issues this first. Note this stops
        the *queue*, not a continuous :meth:`move` — pair with
        :meth:`emergency_stop` for velocity commands.
        hardware-unverified (2026-07-04).
        """
        return self._call("SetCmdQueueForcelyStop")

    def queued_cmd_current_index(self) -> Any:
        """Read the executing queue index (``GetQueuedCmdCurrentIndex``).

        Returns ``{"queueCmdCurrentIndex": int}`` — note the result key spells
        ``queue``, not ``Queued`` (JS SDK-confirmed). The CHM documents this
        RPC under the older name ``GetCmdQueueCurrentIndex``; the wire name is
        ``GetQueuedCmdCurrentIndex``. hardware-unverified (2026-07-04).
        """
        return self._call("GetQueuedCmdCurrentIndex")

    def cmd_queue_available_space(self) -> Any:
        """Read the free command-queue slots (``GetCmdQueueAvailableSpace``).

        Returns ``{"space": int}`` per CHM/plugin table.
        hardware-unverified (2026-07-04).
        """
        return self._call("GetCmdQueueAvailableSpace")

    # ---- MagicBox (hardware-unverified) ---------------------------------------
    #
    # Only the stop-point RPCs live in the ``MagicBox.*`` JSON-RPC namespace;
    # despite their names, GetMagicBoxMode/GetMagicBoxNum/SetRunningState are
    # regular ``MagicianGO.*`` methods (JS call sites + CHM INPUT examples).

    def magic_box_mode(self) -> Any:
        """Read the MagicBox mode (``MagicianGO.GetMagicBoxMode``).

        Returns ``{"mode": int}`` (JS-confirmed field). Note: MagicianGO
        namespace despite the name. hardware-unverified (2026-07-04).
        """
        return self._call("GetMagicBoxMode")

    def magic_box_num(self) -> Any:
        """Read the MagicBox device number (``MagicianGO.GetMagicBoxNum``).

        Result field is *presumed* ``{"num": int}`` (plugin table); the CHM
        instead documents a ``device`` hex id (lite ``0x02``, GO ``0x04``,
        K210 car ``0x20``, K210 arm ``0x21``) — read the result defensively.
        MagicianGO namespace despite the name. hardware-unverified (2026-07-04).
        """
        return self._call("GetMagicBoxNum")

    def stop_point_state(self) -> Any:
        """Read whether the stop point was reached (``MagicBox.GetStopPointState``).

        Sent on the **MagicBox** JSON-RPC namespace (not ``MagicianGO``).
        Returns ``{"result": bool}`` — ``True`` when arrived/stopped.
        hardware-unverified (2026-07-04).
        """
        return self._client.call("MagicBox.GetStopPointState", portName=self.port_name)

    def set_stop_point_param(self, scopeErr: int, stopErr: int) -> Any:
        """Set stop-point tolerances (``MagicBox.SetStopPointParam``).

        Sent on the **MagicBox** JSON-RPC namespace (not ``MagicianGO``).
        ``scopeErr`` is the approach-range radius (default 40 cm), ``stopErr``
        the stop precision (default 2 cm). hardware-unverified (2026-07-04).
        """
        return self._client.call(
            "MagicBox.SetStopPointParam",
            portName=self.port_name,
            scopeErr=scopeErr,
            stopErr=stopErr,
        )

    def set_stop_point_server(self, PointX: int, PointY: int) -> Any:
        """Set the stop-point target (``MagicBox.SetStopPointServer``).

        Sent on the **MagicBox** JSON-RPC namespace (not ``MagicianGO``). Wire
        parameter names are capitalised ``PointX``/``PointY`` (source-confirmed
        — keep the capital P). The coordinate **unit is unconfirmed** (cm vs
        mm; the official docs never say — inherited from ``stop_point_test.py``).
        hardware-unverified (2026-07-04).
        """
        return self._client.call(
            "MagicBox.SetStopPointServer",
            portName=self.port_name,
            PointX=PointX,
            PointY=PointY,
        )

    def set_running_state(self, **params: Any) -> Any:
        """Set the running state (``MagicianGO.SetRunningState``) — wire params unconfirmed.

        Only the method name is attested (plugin string table); no JS call site
        or CHM page exists (the CHM file of this name documents a different
        RPC). The parameter is *presumed* ``runningState: int`` — keyword
        arguments are passed through verbatim. MagicianGO namespace despite
        the MagicBox-flavoured context. hardware-unverified (2026-07-04).
        """
        return self._call("SetRunningState", **params)

    # ---- output (extended, hardware-unverified) -------------------------------

    def set_light_prompt(self, index: int) -> Any:
        """Select the light prompt (``SetLightPrompt(index=...)``).

        ``index``: ``0`` none, ``1`` USB, ``2`` low battery, ``3`` handle,
        ``4`` script (CHM). hardware-unverified (2026-07-04).
        """
        return self._call("SetLightPrompt", index=index)

    # ---- device info (hardware-unverified) ------------------------------------

    def product_name(self) -> Any:
        """Read the product name (``GetProductName``).

        Returns ``{"productName": str}`` — DobotLab treats ``"MagicianGo"`` as
        the valid-device marker. hardware-unverified (2026-07-04).
        """
        return self._call("GetProductName")

    def device_fw_software_version(self) -> Any:
        """Read the firmware software version (``GetDeviceFwSoftwareVersion``).

        JS consumers read ``{majorVersionNum, secondVersionNum,
        revisionVersionNum, previousVersionNum}`` and format
        ``V{major}.{second}.{revision}.{previous}``; the CHM example shows
        older field names — read the result defensively.
        hardware-unverified (2026-07-04).
        """
        return self._call("GetDeviceFwSoftwareVersion")

    def device_fw_hardware_version(self) -> Any:
        """Read the firmware hardware version (``GetDeviceFwHardwareVersion``).

        Field names are *presumed* to match
        :meth:`device_fw_software_version` (the CHM example shows older
        names) — read the result defensively. hardware-unverified (2026-07-04).
        """
        return self._call("GetDeviceFwHardwareVersion")

    def device_id(self) -> Any:
        """Read the device id (``GetDeviceID``).

        Returns ``{"deviceID": [int, ...]}`` per CHM (whose example method
        string carries a ``MagicBox.`` misprint — the plugin table places it
        in MagicianGO). hardware-unverified (2026-07-04).
        """
        return self._call("GetDeviceID")

    def get_device_name(self) -> Any:
        """Read the device name (``GetDeviceName``).

        Returns ``{"deviceName": str}``. hardware-unverified (2026-07-04).
        """
        return self._call("GetDeviceName")

    def set_device_name(self, deviceName: str) -> Any:
        """Set the device name (``SetDeviceName``; CHM example ``"MgoNO.1"``).

        hardware-unverified (2026-07-04).
        """
        return self._call("SetDeviceName", deviceName=deviceName)

    def get_device_sn(self) -> Any:
        """Read the device serial number (``GetDeviceSN``).

        Returns ``{"deviceSN": str}``. hardware-unverified (2026-07-04).
        """
        return self._call("GetDeviceSN")

    def set_device_sn(self, deviceSN: str) -> Any:
        """Set the device serial number (``SetDeviceSN``).

        CHM example ``"SNMGO20200821000061"``. hardware-unverified (2026-07-04).
        """
        return self._call("SetDeviceSN", deviceSN=deviceSN)

    def device_time(self) -> Any:
        """Read the device uptime clock (``GetDeviceTime``).

        Returns ``{"gSystick": int, "passtime": "hh:mm:ss.z"}`` per CHM/plugin
        table. hardware-unverified (2026-07-04).
        """
        return self._call("GetDeviceTime")

    def device_reboot(self) -> Any:
        """Reboot the device (``DeviceReboot``).

        .. warning::
            The GO **reboots immediately** — the DobotLink connection drops and
            every subsequent call fails until the device is back up and
            reconnected (:meth:`connect`). Do not call mid-motion.

        The response (if any arrives before the link drops) is returned
        verbatim. hardware-unverified (2026-07-04).
        """
        return self._call("DeviceReboot")

    def heartbeat(self) -> Any:
        """Keep-alive ping (``HeartBeat``).

        DobotLab calls this on a 2000 ms client-side timeout and treats more
        than 3 consecutive failures as a lost connection.
        hardware-unverified (2026-07-04).
        """
        return self._call("HeartBeat")
