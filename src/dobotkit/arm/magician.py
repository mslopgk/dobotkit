"""High-level Dobot Magician (Lite) arm API (Task 3.3).

:class:`Magician` is the ergonomic, intent-revealing front door to the arm. It
wraps a :class:`~dobotkit.arm.lowlevel.LowLevelArm` (which in turn speaks the
serial protocol through a :class:`~dobotkit.arm.transport.SerialTransport`) and
exposes the everyday operations directly -- connect, home, move, pick-and-place,
plus the actuator/sensor/IO :mod:`~dobotkit.arm.groups`.

Design highlights
-----------------
* **Queued, waited motion.** When a motion is issued with ``wait=True`` it is
  appended to the on-device queue, the queue is started, and the call blocks
  until the returned index has executed (via
  :meth:`~dobotkit.arm.queue.CommandQueue.wait_for`). With ``wait=False`` the
  command is sent immediately (non-queued) and the call returns at once.
* **Safe teardown.** Used as a context manager, ``__exit__`` always stops the
  queue and disconnects -- even if the ``with`` body raised -- and never
  suppresses the original exception.
* **Optional alarm guard.** Pass ``check_alarms=True`` to a motion call to read
  the alarm bitmap first and raise :class:`~dobotkit.exceptions.DobotAlarmError`
  when any fault is active, rather than driving the arm into a faulted state.
* **pydobot compatibility.** ``suck`` / ``grip`` / ``speed`` / ``wait`` /
  ``pose`` / ``get_eio`` / ``set_eio`` / ``move_to`` mirror ``pydobot.Dobot`` so
  existing scripts port with minimal changes.
"""
from __future__ import annotations

from typing import Optional, Tuple

from dobotkit.arm.alarms import decode_alarms
from dobotkit.arm.groups import EffectorGroup, IOGroup, SensorGroup
from dobotkit.arm.lowlevel import LowLevelArm
from dobotkit.arm.structures import Pose
from dobotkit.arm.transport import SerialTransport
from dobotkit.enums import PTPMode
from dobotkit.exceptions import DobotAlarmError, DobotConnectionError

__all__ = ["Magician"]

# A 3-component Cartesian waypoint (x, y, z).
Point = Tuple[float, float, float]


class Magician:
    """Ergonomic high-level control of a Dobot Magician (Lite) arm."""

    def __init__(
        self,
        port: str = "auto",
        baudrate: int = 115200,
        *,
        auto_connect: bool = True,
        _transport: Optional[SerialTransport] = None,
        _lowlevel: Optional[LowLevelArm] = None,
    ) -> None:
        """Create a Magician.

        Args:
            port: Serial port name (e.g. ``"COM3"`` / ``"/dev/ttyUSB0"``). The
                special value ``"auto"`` resolves to the first port returned by
                :meth:`SerialTransport.search`.
            baudrate: Serial baud rate (the Dobot default is ``115200``).
            auto_connect: When ``True`` (default), :meth:`connect` is called
                during construction.
            _transport: Test/advanced seam -- inject a ready
                :class:`~dobotkit.arm.transport.SerialTransport` instead of
                opening ``port``.
            _lowlevel: Test/advanced seam -- inject a ready (or fake)
                :class:`~dobotkit.arm.lowlevel.LowLevelArm`; when given, ``port``,
                ``baudrate`` and ``_transport`` are ignored.

        Raises:
            DobotConnectionError: ``port="auto"`` but no serial ports were found.
        """
        if _lowlevel is not None:
            self._ll: LowLevelArm = _lowlevel
        else:
            transport = _transport
            if transport is None:
                resolved = self._resolve_port(port)
                transport = SerialTransport(resolved, baudrate)
            self._ll = LowLevelArm(transport)

        self._effector = EffectorGroup(self._ll)
        self._sensors = SensorGroup(self._ll)
        self._io = IOGroup(self._ll)

        if auto_connect:
            self.connect()

    @staticmethod
    def _resolve_port(port: str) -> str:
        """Resolve ``"auto"`` to the first discovered serial port."""
        if port != "auto":
            return port
        ports = SerialTransport.search()
        if not ports:
            raise DobotConnectionError(
                "no serial ports found for port='auto'; pass an explicit port"
            )
        return ports[0]

    # -- lifecycle ---------------------------------------------------------

    def connect(self) -> None:
        """Open the connection to the arm."""
        self._ll.connect()

    def disconnect(self) -> None:
        """Close the connection to the arm."""
        self._ll.disconnect()

    def __enter__(self) -> "Magician":
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Stop the queue and disconnect, always; never suppress an exception.

        Runs on both clean and exceptional exits. The queue stop is best-effort
        (a transport error during teardown must not mask the body's exception),
        but the disconnect always runs.
        """
        try:
            self._ll.queue.stop()
        except Exception:  # pragma: no cover - teardown must not mask body errors
            pass
        finally:
            self.disconnect()
        # Return None -> the context manager does not suppress exceptions.

    # -- groups ------------------------------------------------------------

    @property
    def lowlevel(self) -> LowLevelArm:
        """The underlying :class:`~dobotkit.arm.lowlevel.LowLevelArm`."""
        return self._ll

    @property
    def effector(self) -> EffectorGroup:
        """End-effector group (suction cup, gripper, laser, servo)."""
        return self._effector

    @property
    def sensors(self) -> SensorGroup:
        """Sensor group (color, infrared, Seeed distance/temp/light)."""
        return self._sensors

    @property
    def io(self) -> IOGroup:
        """IO group (digital/analog IO, PWM, extended motors)."""
        return self._io

    # -- alarms ------------------------------------------------------------

    def _raise_if_alarms(self) -> None:
        """Read the alarm bitmap and raise if any fault is active."""
        codes = decode_alarms(self._ll.get_alarms_state())
        if codes:
            raise DobotAlarmError(
                [int(c) for c in codes],
                f"active alarms before motion: {[int(c) for c in codes]}",
            )

    # -- internal motion ---------------------------------------------------

    def _run_motion(self, index: Optional[int], wait: bool) -> Optional[int]:
        """Start the queue and wait for ``index`` when ``wait`` and queued.

        ``index`` is the queued-command index returned by the low-level setter
        (``None`` for an immediate, non-queued command). Returns it unchanged so
        callers can chain further waits.
        """
        if wait and index is not None:
            self._ll.queue.start()
            self._ll.queue.wait_for(index)
        return index

    # -- homing ------------------------------------------------------------

    def home(
        self,
        x: float = 200,
        y: float = 0,
        z: float = 0,
        r: float = 0,
        *,
        wait: bool = True,
    ) -> Optional[int]:
        """Run the homing routine, targeting the given pose.

        Sets the home parameters then executes the home command. When ``wait``
        the command is queued, the queue is started, and the call blocks until
        homing completes.
        """
        self._ll.set_home_params(x, y, z, r, queued=wait)
        index = self._ll.set_home_cmd(queued=wait)
        return self._run_motion(index, wait)

    # -- speed -------------------------------------------------------------

    def set_speed(self, velocity: float, acceleration: float) -> None:
        """Set the PTP velocity / acceleration for Cartesian moves.

        Mirrors ``pydobot``: applies the values to both the common ratios and
        the coordinate-mode params so every subsequent move honours them.
        """
        self._ll.set_ptp_common_params(velocity, acceleration)
        self._ll.set_ptp_coordinate_params(
            velocity, velocity, acceleration, acceleration
        )

    # -- pose --------------------------------------------------------------

    def get_pose(self) -> Pose:
        """Read the current Cartesian + joint pose."""
        return self._ll.get_pose()

    @property
    def pose_obj(self) -> Pose:
        """The current pose as a :class:`~dobotkit.arm.structures.Pose`."""
        return self._ll.get_pose()

    # -- moves -------------------------------------------------------------

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
        """Move to an absolute Cartesian pose.

        Defaults to a straight-line ``MOVL_XYZ`` move. With ``wait=True`` the
        move is queued, the queue started, and the call blocks until it
        completes. With ``check_alarms=True`` the alarm bitmap is read first and
        :class:`~dobotkit.exceptions.DobotAlarmError` is raised if any fault is
        active.
        """
        if check_alarms:
            self._raise_if_alarms()
        index = self._ll.set_ptp_cmd(mode, x, y, z, r, queued=wait)
        return self._run_motion(index, wait)

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
        """Move by a relative Cartesian offset (straight-line increment).

        Uses ``MOVL_XYZ_INC`` so the offsets are added to the current pose.
        """
        if check_alarms:
            self._raise_if_alarms()
        index = self._ll.set_ptp_cmd(
            PTPMode.MOVL_XYZ_INC, dx, dy, dz, dr, queued=wait
        )
        return self._run_motion(index, wait)

    # -- pick and place ----------------------------------------------------

    def pick_and_place(
        self,
        src: Point,
        dst: Point,
        z_safe: float,
        settle_ms: int = 200,
    ) -> None:
        """Pick an object at ``src`` and place it at ``dst``.

        The classic eight-step cycle, all queued so it runs as one program:

        1. travel above the source at ``z_safe``;
        2. descend to the source;
        3. turn the suction cup ON and let it settle (``settle_ms``);
        4. lift back to ``z_safe``;
        5. travel above the destination at ``z_safe``;
        6. descend to the destination;
        7. turn the suction cup OFF and let it settle;
        8. lift back to ``z_safe``.

        ``src`` / ``dst`` are ``(x, y, z)`` waypoints (the grab/release heights);
        ``z_safe`` is the clearance height used between waypoints. The whole
        sequence is queued, the queue is started, and the call blocks until the
        final move completes.
        """
        sx, sy, sz = src
        dx, dy, dz = dst
        mode = PTPMode.MOVL_XYZ
        last_index: Optional[int] = None

        # 1-2: above source, then down to grab.
        self._ll.set_ptp_cmd(mode, sx, sy, z_safe, 0, queued=True)
        self._ll.set_ptp_cmd(mode, sx, sy, sz, 0, queued=True)
        # 3: suction ON + settle.
        self._ll.set_end_effector_suction_cup(enable_ctrl=True, on=True, queued=True)
        self._ll.set_wait_cmd(settle_ms, queued=True)
        # 4: lift to safe height.
        self._ll.set_ptp_cmd(mode, sx, sy, z_safe, 0, queued=True)
        # 5-6: above destination, then down to release.
        self._ll.set_ptp_cmd(mode, dx, dy, z_safe, 0, queued=True)
        self._ll.set_ptp_cmd(mode, dx, dy, dz, 0, queued=True)
        # 7: suction OFF + settle.
        self._ll.set_end_effector_suction_cup(enable_ctrl=True, on=False, queued=True)
        self._ll.set_wait_cmd(settle_ms, queued=True)
        # 8: final lift -- this index is the one we wait on.
        last_index = self._ll.set_ptp_cmd(mode, dx, dy, z_safe, 0, queued=True)

        self._ll.queue.start()
        if last_index is not None:
            self._ll.queue.wait_for(last_index)

    # ===================================================================== #
    # pydobot-compatible aliases
    # ===================================================================== #

    def suck(self, on: bool) -> Optional[int]:
        """pydobot alias: turn the suction cup on (grab) or off (release)."""
        return self._effector.suck(bool(on))

    def grip(self, on: bool) -> Optional[int]:
        """pydobot alias: close the gripper (``on=True``) or open it."""
        return self._effector.grip(bool(on))

    def speed(self, velocity: float = 100.0, acceleration: float = 100.0) -> None:
        """pydobot alias for :meth:`set_speed`."""
        self.set_speed(velocity, acceleration)

    def wait(self, ms: int) -> Optional[int]:
        """pydobot alias: queue a wait command (pause the queue ``ms`` ms)."""
        return self._ll.set_wait_cmd(ms, queued=True)

    def pose(self) -> Tuple[float, float, float, float, float, float, float, float]:
        """pydobot alias: current pose as ``(x, y, z, r, j1, j2, j3, j4)``."""
        p = self._ll.get_pose()
        return (p.x, p.y, p.z, p.r, p.j1, p.j2, p.j3, p.j4)

    def get_eio(self, addr: int) -> int:
        """pydobot alias: read the digital-input level of IO pin ``addr``."""
        return self._io.get_di(addr)

    def set_eio(self, addr: int, val: int) -> Optional[int]:
        """pydobot alias: set the digital-output level of IO pin ``addr``."""
        return self._io.set_do(addr, val)
