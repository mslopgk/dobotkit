"""High-level Magician GO control layered on a connected ``DobotLinkClient``.

``MagicianGO`` is a thin, typed facade over the DobotLink ``MagicianGO.*``
JSON-RPC surface. Every method (except :meth:`search`) issues
``client.call("MagicianGO.<Func>", portName=self.port_name, **params)`` via the
private :meth:`_call` helper; :meth:`emergency_stop` is the lone command that
uses ``client.notify`` so that stopping the car never blocks on a response.

**Drive model — continuous velocity only.** Motion is commanded as a velocity
vector (:meth:`move`, plus the :meth:`forward`/:meth:`backward`/:meth:`strafe`/
:meth:`spin` helpers and the bounded :meth:`drive_for` pulse): the car drives at
the commanded velocity until told to stop. This is the trusted, hardware-proven
path. For *precise* closed-loop motion (drive an exact distance, turn an exact
angle) build a loop out of continuous :meth:`move` plus sensor feedback with
:class:`dobotkit.go.navigation.PreciseMover` — the firmware's own queued
closed-loop commands are not exposed here because they can hang on this chassis.

**MagicBox peripherals.** The GO carries the same MagicBox hub as the arm; its
sensor/IO reads live on the ``MagicBox.*`` namespace and are exposed through the
:attr:`sensors` and :attr:`io` groups (see :mod:`dobotkit.go.groups`). They
coexist with the native drive/sensor calls on a single ``MagicianGO`` connection
(hardware-verified 2026-07-16).

Safety workflow: after :meth:`connect_robot` always verify the link with a read
such as :meth:`battery` (use :meth:`connect` which does this for you); check
:meth:`clearance_ok` before driving; wrap motion in ``try/finally`` ending in
:meth:`emergency_stop`.
"""
from __future__ import annotations

import math
import time
from typing import Any, Dict, Optional, Tuple, Union, cast

from dobotkit.enums import LEDChannel
from dobotkit.go.groups import GoIOGroup, GoSensorGroup

#: Hard cap (magnitude) applied to every continuous-velocity component. Speed
#: units are firmware-defined and unconfirmed; 8..30 is the empirically safe
#: range on this chassis, so nothing larger is ever put on the wire.
SPEED_CAP: float = 30.0

#: The ultrasonic sensors clamp at this ceiling (hardware-measured): readings
#: of 40 mean "40 cm **or more**".
ULTRA_MAX_CM: float = 40.0

_ULTRA_KEYS: Tuple[str, str, str, str] = ("front", "back", "left", "right")


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

    Attributes:
        sensors: :class:`~dobotkit.go.groups.GoSensorGroup` — MagicBox sensor
            reads (ADC/DI by EIO pin; color/infrared/Seeed by Grove connector),
            guarded so a missing peripheral degrades to ``None``.
        io: :class:`~dobotkit.go.groups.GoIOGroup` — MagicBox digital/analog I/O
            addressed by EIO pin (1..26).
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
        #: MagicBox peripheral sensor reads (guarded -> ``None`` if absent).
        self.sensors = GoSensorGroup(client, port_name)
        #: MagicBox digital/analog I/O, addressed by EIO pin.
        self.io = GoIOGroup(client, port_name)

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
            # <- emergency stop + confirming stop + socket closed, even on error
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

        1. :meth:`emergency_stop` **first** — a fire-and-forget notify that can
           never block, so the car stops instantly even when the link is hung.
        2. :meth:`stop` — a confirming blocking ``SetMoveSpeed(0)``; if it fails
           the emergency stop is re-fired.

        Teardown errors are swallowed — they must never mask the original
        exception. When this instance was created via :meth:`open` the owned
        client socket is closed as the final step.
        """
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

    # ---- diagnostics / alarms ----------------------------------------------

    def get_alarm_info(self) -> Any:
        """Read the active alarm/warning list (``GetAlarmInfo``).

        Returns the firmware result verbatim — expected shape is
        ``{"warning": [...]}`` per the plugin protocol table — read it
        defensively.
        """
        return self._call("GetAlarmInfo")

    def clean_alarm_info(self) -> Any:
        """Clear the active alarms (``CleanAlarmInfo``)."""
        return self._call("CleanAlarmInfo")

    def stall_protection(self) -> Any:
        """Read the stall-protection flag (``GetStallProtection``); ``{"isHappened": int}``."""
        return self._call("GetStallProtection")

    def off_ground(self) -> Any:
        """Read the wheels-off-ground flag (``GetOffGround``); ``{"isHappened": int}``."""
        return self._call("GetOffGround")

    # ---- MagicBox status ----------------------------------------------------
    #
    # Despite their names these are regular ``MagicianGO.*`` methods; the actual
    # MagicBox sensor/IO reads live on the ``MagicBox.*`` namespace via the
    # :attr:`sensors` / :attr:`io` groups.

    def magic_box_mode(self) -> Any:
        """Read the MagicBox mode (``MagicianGO.GetMagicBoxMode``); ``{"mode": int}``."""
        return self._call("GetMagicBoxMode")

    def magic_box_num(self) -> Any:
        """Read the attached-MagicBox count/id (``MagicianGO.GetMagicBoxNum``); read defensively."""
        return self._call("GetMagicBoxNum")
