"""Logic layer between the GUI and the Dobot Magician arm (Task: GUI arm controller).

:class:`ArmController` is the thin, fully-typed adapter the Tkinter view talks to.
It owns an optional :class:`~dobotkit.arm.magician.Magician` (``None`` until a
connection is opened) and turns every widget event into exactly one high-level
arm call. Two rules make it safe to drive straight from UI callbacks:

* **Never raise into the UI.** Every action catches
  :class:`~dobotkit.exceptions.DobotError` (and, for the resilient
  :meth:`snapshot`, any per-read failure) and reports it as an
  :class:`ActionResult` ``(ok, message)`` pair instead of propagating. A UI
  callback can therefore call an action and simply show ``result.message``.
* **Injectable device.** The arm is supplied either as a ready ``device`` (used
  by tests with a fake) or lazily built by a ``device_factory`` on
  :meth:`connect` (used by ``--demo`` / real runs). Nothing here constructs a
  ``Tk()`` root, so importing this module is headless-safe.

This module deliberately imports only :mod:`dobotkit` APIs and the standard
library -- no ``tkinter`` -- so the logic layer is unit-testable without a
display.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, NamedTuple, Optional

from dobotkit.arm.alarms import decode_alarms
from dobotkit.arm.magician import Magician
from dobotkit.arm.transport import SerialTransport
from dobotkit.enums import JOGMode, PTPMode
from dobotkit.exceptions import DobotError

__all__ = ["ActionResult", "ArmController"]

# A factory that builds (and typically connects) a Magician for a given port.
DeviceFactory = Callable[[str], Magician]


class ActionResult(NamedTuple):
    """Outcome of a controller action.

    A 2-tuple ``(ok, message)`` so callers may unpack it (``ok, msg = ...``) or
    read the fields by name. ``ok`` is ``True`` on success; ``message`` is a
    short human-readable line suitable for a status bar or log.
    """

    ok: bool
    message: str


class ArmController:
    """Stateful, exception-swallowing adapter over :class:`Magician`.

    Args:
        device: An already-built arm (or fake) to drive. When given, it is used
            directly and :meth:`connect` just calls its ``connect()``. Its
            ``connected`` flag (if present) seeds :attr:`is_connected`.
        device_factory: Builds a Magician from a port name on demand. Used when
            no ``device`` is injected -- e.g. real runs (default factory) or a
            ``--demo`` fake factory. Called once per successful :meth:`connect`.
    """

    def __init__(
        self,
        device: Optional[Magician] = None,
        *,
        device_factory: Optional[DeviceFactory] = None,
    ) -> None:
        self._device: Optional[Magician] = device
        self._factory: DeviceFactory = device_factory or self._default_factory
        self._port: Optional[str] = None
        # An injected device may already be connected; reflect that.
        self._connected: bool = bool(getattr(device, "connected", False))
        # Remember the JOG frame in use so jog_stop sends the matching idle cmd.
        self._jog_is_joint: int = 0

    # -- default device construction -------------------------------------- #

    @staticmethod
    def _default_factory(port: str) -> Magician:
        """Build and connect a real Magician on ``port`` (deferred connect)."""
        arm = Magician(port, auto_connect=False)
        arm.connect()
        return arm

    # -- discovery -------------------------------------------------------- #

    def available_ports(self) -> List[str]:
        """Return the currently available serial ports (``[]`` on any failure)."""
        try:
            return list(SerialTransport.search())
        except Exception:
            # Port enumeration must never break the UI, even on a driver error.
            return []

    # -- connection state ------------------------------------------------- #

    @property
    def is_connected(self) -> bool:
        """Whether a device is present and believed to be connected."""
        if self._device is None:
            return False
        # Prefer the device's own view when it exposes one.
        return bool(getattr(self._device, "connected", self._connected))

    @property
    def port(self) -> Optional[str]:
        """The port last connected to (``None`` if never connected)."""
        return self._port

    @property
    def device(self) -> Optional[Magician]:
        """The underlying arm, or ``None`` when not connected."""
        return self._device

    def connect(self, port: str = "auto") -> ActionResult:
        """Open the connection (build the device via the factory if needed)."""
        try:
            if self._device is None:
                self._device = self._factory(port)
            else:
                self._device.connect()
            self._connected = True
            self._port = port
            return ActionResult(True, f"Connected ({port})")
        except DobotError as exc:
            return ActionResult(False, f"Connect failed: {exc}")

    def disconnect(self) -> ActionResult:
        """Close the connection; safe to call when already disconnected."""
        if self._device is None:
            self._connected = False
            return ActionResult(True, "Already disconnected")
        try:
            self._device.disconnect()
            self._connected = False
            return ActionResult(True, "Disconnected")
        except DobotError as exc:
            return ActionResult(False, f"Disconnect failed: {exc}")

    # -- guard helper ----------------------------------------------------- #

    def _require_device(self) -> Magician:
        """Return the device or raise :class:`DobotError` when disconnected."""
        if self._device is None:
            raise DobotError("not connected")
        return self._device

    # -- motion ----------------------------------------------------------- #

    def home(self, *, wait: bool = True) -> ActionResult:
        """Run the homing routine."""
        try:
            self._require_device().home(wait=wait)
            return ActionResult(True, "Homing complete" if wait else "Homing started")
        except DobotError as exc:
            return ActionResult(False, f"Home failed: {exc}")

    def move_to(
        self,
        x: float,
        y: float,
        z: float,
        r: float = 0.0,
        *,
        mode: PTPMode = PTPMode.MOVL_XYZ,
        wait: bool = True,
    ) -> ActionResult:
        """Move to an absolute Cartesian pose."""
        try:
            self._require_device().move_to(x, y, z, r, mode=mode, wait=wait)
            return ActionResult(True, f"Moved to ({x}, {y}, {z}, {r})")
        except DobotError as exc:
            return ActionResult(False, f"Move failed: {exc}")

    def move_relative(
        self,
        dx: float = 0.0,
        dy: float = 0.0,
        dz: float = 0.0,
        dr: float = 0.0,
        *,
        wait: bool = True,
    ) -> ActionResult:
        """Move by a relative Cartesian offset."""
        try:
            self._require_device().move_relative(dx, dy, dz, dr, wait=wait)
            return ActionResult(True, f"Moved by ({dx}, {dy}, {dz}, {dr})")
        except DobotError as exc:
            return ActionResult(False, f"Relative move failed: {exc}")

    def set_speed(self, velocity: float, acceleration: float) -> ActionResult:
        """Set the PTP velocity / acceleration for Cartesian moves."""
        try:
            self._require_device().set_speed(velocity, acceleration)
            return ActionResult(True, f"Speed set (v={velocity}, a={acceleration})")
        except DobotError as exc:
            return ActionResult(False, f"Set speed failed: {exc}")

    # -- jogging ---------------------------------------------------------- #

    @staticmethod
    def _jog_cmd(axis: int, positive: bool) -> JOGMode:
        """Map a 1-based ``axis`` + direction to a :class:`JOGMode` command.

        Axis ``n`` uses cmd ``2n-1`` for the positive direction and ``2n`` for
        the negative one (axis 1 -> AP/AN=1/2, ... axis 4 -> DP/DN=7/8).
        """
        if axis < 1 or axis > 4:
            raise DobotError(f"jog axis out of range: {axis}")
        base = 2 * axis - 1
        return JOGMode(base if positive else base + 1)

    def jog_start(
        self, axis: int, positive: bool, *, joint: bool = False
    ) -> ActionResult:
        """Begin a continuous JOG on ``axis`` in the given direction.

        ``joint=False`` (default) jogs in the Cartesian frame; ``joint=True``
        jogs the corresponding joint. The frame is remembered so :meth:`jog_stop`
        sends the matching idle command.
        """
        try:
            self._jog_is_joint = 1 if joint else 0
            cmd = self._jog_cmd(axis, positive)
            self._require_device().lowlevel.set_jog_cmd(self._jog_is_joint, int(cmd))
            direction = "+" if positive else "-"
            return ActionResult(True, f"Jog axis {axis}{direction}")
        except DobotError as exc:
            return ActionResult(False, f"Jog failed: {exc}")

    def jog_stop(self) -> ActionResult:
        """Stop any active JOG motion (sends the idle command)."""
        try:
            self._require_device().lowlevel.set_jog_cmd(
                self._jog_is_joint, int(JOGMode.IDLE)
            )
            return ActionResult(True, "Jog stopped")
        except DobotError as exc:
            return ActionResult(False, f"Jog stop failed: {exc}")

    # -- end effector ----------------------------------------------------- #

    def suck(self, on: bool, *, enable: bool = True) -> ActionResult:
        """Drive the suction cup.

        ``on`` is the vacuum state (grab vs release); ``enable`` powers the air
        pump. Pass ``enable=False`` to switch the pump off entirely.
        """
        try:
            self._require_device().effector.suck(bool(on), enable=bool(enable))
            if not enable:
                return ActionResult(True, "Suction pump off")
            return ActionResult(True, f"Suction {'on' if on else 'released'}")
        except DobotError as exc:
            return ActionResult(False, f"Suck failed: {exc}")

    def grip(self, on: bool, *, enable: bool = True) -> ActionResult:
        """Drive the gripper.

        ``on`` closes (``True``) / opens (``False``) it; ``enable`` powers the
        air pump. Pass ``enable=False`` to switch the pump off entirely.
        """
        try:
            self._require_device().effector.grip(bool(on), enable=bool(enable))
            if not enable:
                return ActionResult(True, "Gripper pump off")
            return ActionResult(True, f"Gripper {'closed' if on else 'open'}")
        except DobotError as exc:
            return ActionResult(False, f"Grip failed: {exc}")

    def laser(self, on: bool, *, enable: bool = True) -> ActionResult:
        """Switch the laser on or off (``enable`` powers the control circuit)."""
        try:
            self._require_device().effector.laser(bool(on), enable=bool(enable))
            return ActionResult(True, f"Laser {'on' if on else 'off'}")
        except DobotError as exc:
            return ActionResult(False, f"Laser failed: {exc}")

    def set_servo(self, servo_id: int, angle: float) -> ActionResult:
        """Set the angle of a servo on the end effector."""
        try:
            self._require_device().effector.set_servo(servo_id, angle)
            return ActionResult(True, f"Servo {servo_id} -> {angle}")
        except DobotError as exc:
            return ActionResult(False, f"Set servo failed: {exc}")

    # -- IO --------------------------------------------------------------- #

    def io_set_do(self, addr: int, level: int) -> ActionResult:
        """Set the digital-output level of IO pin ``addr``."""
        try:
            self._require_device().io.set_do(addr, level)
            return ActionResult(True, f"DO[{addr}] = {level}")
        except DobotError as exc:
            return ActionResult(False, f"IO set DO failed: {exc}")

    def io_get_di(self, addr: int) -> ActionResult:
        """Read the digital-input level of IO pin ``addr``."""
        try:
            value = self._require_device().io.get_di(addr)
            return ActionResult(True, f"DI[{addr}] = {value}")
        except DobotError as exc:
            return ActionResult(False, f"IO get DI failed: {exc}")

    def io_get_adc(self, addr: int) -> ActionResult:
        """Read the ADC value of IO pin ``addr``."""
        try:
            value = self._require_device().io.get_adc(addr)
            return ActionResult(True, f"ADC[{addr}] = {value}")
        except DobotError as exc:
            return ActionResult(False, f"IO get ADC failed: {exc}")

    def io_set_pwm(self, addr: int, freq: float, duty: float) -> ActionResult:
        """Configure PWM (frequency Hz, duty cycle %) on IO pin ``addr``."""
        try:
            self._require_device().io.set_pwm(addr, freq, duty)
            return ActionResult(True, f"PWM[{addr}] freq={freq} duty={duty}")
        except DobotError as exc:
            return ActionResult(False, f"IO set PWM failed: {exc}")

    # -- sensors ---------------------------------------------------------- #

    def read_color(self, port: int = 0) -> ActionResult:
        """Enable and read the color sensor on ``port``."""
        try:
            value = self._require_device().sensors.color(port)
            return ActionResult(True, f"Color = {value}")
        except DobotError as exc:
            return ActionResult(False, f"Read color failed: {exc}")

    def read_infrared(self, port: int) -> ActionResult:
        """Enable and read the infrared sensor on ``port``."""
        try:
            value = self._require_device().sensors.infrared(port)
            return ActionResult(True, f"Infrared[{port}] = {value}")
        except DobotError as exc:
            return ActionResult(False, f"Read infrared failed: {exc}")

    def read_seeed_distance(self, port: int) -> ActionResult:
        """Read the Seeed distance sensor on ``port``."""
        try:
            value = self._require_device().sensors.seeed_distance(port)
            return ActionResult(True, f"Distance[{port}] = {value}")
        except DobotError as exc:
            return ActionResult(False, f"Read distance failed: {exc}")

    def read_seeed_temp(self, port: int) -> ActionResult:
        """Read the Seeed temperature/humidity sensor on ``port``."""
        try:
            value = self._require_device().sensors.seeed_temp(port)
            return ActionResult(True, f"Temp[{port}] = {value}")
        except DobotError as exc:
            return ActionResult(False, f"Read temp failed: {exc}")

    def read_seeed_light(self, port: int) -> ActionResult:
        """Read the Seeed light sensor on ``port``."""
        try:
            value = self._require_device().sensors.seeed_light(port)
            return ActionResult(True, f"Light[{port}] = {value}")
        except DobotError as exc:
            return ActionResult(False, f"Read light failed: {exc}")

    # -- alarms ----------------------------------------------------------- #

    def clear_alarms(self) -> ActionResult:
        """Clear all active alarms on the arm."""
        try:
            self._require_device().lowlevel.clear_all_alarms_state()
            return ActionResult(True, "Alarms cleared")
        except DobotError as exc:
            return ActionResult(False, f"Clear alarms failed: {exc}")

    # -- device info ------------------------------------------------------ #

    def device_info(self) -> Dict[str, Any]:
        """Return ``{sn, name, version, error}`` -- each field guarded.

        Never raises: a read that fails leaves its field ``None`` and records
        the first failure under ``error``.
        """
        info: Dict[str, Any] = {"sn": None, "name": None, "version": None, "error": None}
        device = self._device
        if device is None:
            info["error"] = "not connected"
            return info
        ll = getattr(device, "lowlevel", None)

        def _guard(key: str, read: Callable[[], Any]) -> None:
            try:
                info[key] = read()
            except Exception as exc:  # resilient: any read may fail independently
                if info["error"] is None:
                    info["error"] = str(exc)

        if ll is None:
            info["error"] = "device exposes no lowlevel"
            return info
        _guard("sn", ll.get_device_sn)
        _guard("name", ll.get_device_name)
        _guard("version", ll.get_device_version)
        return info

    # -- snapshot --------------------------------------------------------- #

    def snapshot(self) -> Dict[str, Any]:
        """Return a resilient status snapshot for the live status view.

        Shape::

            {
                "connected": bool,
                "port": str | None,
                "pose": {"x", "y", "z", "r", "j1", "j2", "j3", "j4"} | None,
                "alarms": [alarm-name, ...],   # empty when none / unavailable
                "error": str | None,           # first per-read failure, if any
            }

        Every read is guarded independently; the method never raises. A failed
        read leaves its field at the empty default and records the first error
        message under ``"error"``.
        """
        snap: Dict[str, Any] = {
            "connected": self.is_connected,
            "port": self._port,
            "pose": None,
            "alarms": [],
            "error": None,
        }
        device = self._device
        if device is None:
            return snap

        def _note(exc: Exception) -> None:
            if snap["error"] is None:
                snap["error"] = str(exc)

        # -- pose --------------------------------------------------------- #
        try:
            pose = device.get_pose()
            snap["pose"] = {
                "x": pose.x,
                "y": pose.y,
                "z": pose.z,
                "r": pose.r,
                "j1": pose.j1,
                "j2": pose.j2,
                "j3": pose.j3,
                "j4": pose.j4,
            }
        except Exception as exc:  # resilient: a pose read failure must not raise
            _note(exc)

        # -- alarms ------------------------------------------------------- #
        try:
            ll = getattr(device, "lowlevel", None)
            get_alarms = getattr(ll, "get_alarms_state", None)
            if callable(get_alarms):
                codes = decode_alarms(get_alarms())
                snap["alarms"] = [c.name for c in codes]
        except Exception as exc:  # resilient: alarm read failure must not raise
            _note(exc)

        return snap
