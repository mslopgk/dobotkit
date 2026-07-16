"""High-level Magician Lite arm over DobotLink.

:class:`MagicianLite` is the ergonomic, intent-revealing front door to the
DobotLink-mediated Magician Lite arm. It wraps a
:class:`~dobotkit.arm.commands.ArmCommands` (which speaks the DobotLink
JSON-RPC surface through a :class:`~dobotkit.link.DobotLinkClient`) and
exposes the everyday operations directly -- connect, home, move,
pick-and-place -- plus the effector/sensor/IO
:mod:`~dobotkit.arm.groups` facades.

Design highlights
------------------
* **Queued motion.** Motion commands are always queued on-device;
  ``connect()`` clears and starts the queue so anything sent afterwards
  actually executes. ``wait=True`` polls
  :meth:`~dobotkit.arm.commands.ArmCommands.current_index` until the
  returned queued-command index has executed.
* **Safe teardown.** Used as a context manager, ``__exit__`` always stops
  the queue and disconnects -- even if the ``with`` body raised -- and
  never suppresses the original exception.
* **``port="auto"``.** Resolves to the first port DobotLink's
  ``SearchDobot`` reports, at :meth:`connect` time.
"""
from __future__ import annotations

import time
from typing import Any, Optional, Tuple

from dobotkit.arm.commands import ArmCommands
from dobotkit.arm.groups import EffectorGroup, IOGroup, SensorGroup
from dobotkit.enums import PTPMode
from dobotkit.exceptions import DobotConnectionError, DobotTimeoutError

__all__ = ["MagicianLite"]

# A 3-component Cartesian waypoint (x, y, z).
Point = Tuple[float, float, float]


class MagicianLite:
    """Ergonomic high-level control of a Dobot Magician Lite arm via DobotLink."""

    def __init__(
        self,
        port: str = "auto",
        *,
        host: str = "localhost",
        ws_port: int = 9090,
        timeout: float = 10.0,
        auto_connect: bool = True,
        _client: Optional[Any] = None,
    ) -> None:
        """Create a MagicianLite.

        Args:
            port: DobotLink port name (e.g. ``"COM3"``). The special value
                ``"auto"`` resolves to the first port reported by
                :meth:`~dobotkit.arm.commands.ArmCommands.search` when
                :meth:`connect` runs.
            host: DobotLink WebSocket host.
            ws_port: DobotLink WebSocket port.
            timeout: Seconds to wait for the DobotLink connection and each RPC
                response.
            auto_connect: When ``True`` (default), :meth:`connect` is called
                during construction.
            _client: Test/advanced seam -- inject a ready (or fake)
                DobotLink client instead of opening a real
                :class:`~dobotkit.link.DobotLinkClient`.
        """
        self._owns_client = _client is None
        if _client is None:
            from dobotkit.link import DobotLinkClient

            _client = DobotLinkClient(host=host, port=ws_port, timeout=timeout).connect()
        self._client = _client
        self._port = port
        self.cmds = ArmCommands(_client, port if port != "auto" else "")
        self.effector = EffectorGroup(self.cmds)
        self.sensors = SensorGroup(self.cmds)
        self.io = IOGroup(self.cmds)

        if auto_connect:
            self.connect()

    # -- lifecycle -----------------------------------------------------------

    def connect(self) -> None:
        """Resolve ``port="auto"``, connect the arm, clear alarms, and start its queue.

        Alarms are cleared here because an active controller alarm makes the arm
        **silently refuse all PTP motion** (commands are accepted but nothing
        moves); clearing on connect makes motion work out of the box.
        """
        if self._port == "auto":
            ports = self.cmds.search() or []
            if not ports:
                raise DobotConnectionError("no Dobot ports found via DobotLink")
            self.cmds.port_name = ports[0]["portName"]
        self.cmds.connect()
        self.cmds.clear_alarms()
        self.cmds.queue_clear()
        self.cmds.queue_start()

    def clear_alarms(self) -> Any:
        """Clear all active controller alarms (unblocks motion). See :meth:`connect`."""
        return self.cmds.clear_alarms()

    def disconnect(self) -> None:
        """Disconnect the arm and, if this instance owns it, close the client."""
        try:
            self.cmds.disconnect()
        finally:
            if self._owns_client:
                self._client.close()

    def __enter__(self) -> "MagicianLite":
        return self

    def __exit__(self, *exc: object) -> None:
        """Stop the queue and disconnect, always; never suppress an exception."""
        try:
            self.cmds.queue_stop()
        except Exception:  # pragma: no cover - teardown must not mask body errors
            pass
        try:
            self.disconnect()
        except Exception:  # pragma: no cover - teardown must not mask body errors
            pass

    # -- internal motion -------------------------------------------------------

    def _wait_for(
        self, index: Optional[int], wait: bool, timeout_s: float = 30.0
    ) -> Optional[int]:
        """Poll ``current_index()`` until it reaches ``index``.

        Raises:
            DobotTimeoutError: if ``timeout_s`` elapses before the queue's
                current index reaches ``index``.
        """
        if wait and index is not None:
            deadline = time.monotonic() + timeout_s
            while True:
                if self.cmds.current_index() >= index:
                    break
                if time.monotonic() >= deadline:
                    raise DobotTimeoutError(
                        f"timed out after {timeout_s}s waiting for queued command "
                        f"index {index} to complete"
                    )
                time.sleep(0.05)
        return index

    # -- pose / speed ------------------------------------------------------

    def get_pose(self) -> Any:
        """Read the current Cartesian + joint pose."""
        return self.cmds.get_pose()

    def set_speed(self, velocity: float, acceleration: float) -> None:
        """Set the PTP velocity / acceleration for Cartesian moves."""
        self.cmds.set_ptp_common_params(velocity, acceleration)
        self.cmds.set_ptp_coordinate_params(velocity, acceleration)

    # -- homing --------------------------------------------------------------

    def home(
        self, x: float = 200, y: float = 0, z: float = 0, r: float = 0, *, wait: bool = True
    ) -> Optional[int]:
        """Run the homing routine, targeting the given pose."""
        self.cmds.set_home_params(x, y, z, r, queued=True)
        return self._wait_for(self.cmds.set_home_cmd(queued=True), wait)

    # -- moves -----------------------------------------------------------------

    def move_to(
        self, x: float, y: float, z: float, r: float = 0, *,
        mode: int = PTPMode.MOVL_XYZ, wait: bool = False,
    ) -> Optional[int]:
        """Move to an absolute Cartesian pose (defaults to a straight-line move)."""
        return self._wait_for(self.cmds.set_ptp_cmd(mode, x, y, z, r, queued=True), wait)

    def move_relative(
        self, dx: float = 0, dy: float = 0, dz: float = 0, dr: float = 0, *, wait: bool = False
    ) -> Optional[int]:
        """Move by a relative Cartesian offset (straight-line increment)."""
        return self._wait_for(
            self.cmds.set_ptp_cmd(PTPMode.MOVL_XYZ_INC, dx, dy, dz, dr, queued=True), wait
        )

    # -- effector aliases --------------------------------------------------

    def suck(self, on: bool) -> Optional[int]:
        """Turn the suction cup on (grab) or off (release)."""
        return self.effector.suck(bool(on))

    def grip(self, on: bool) -> Optional[int]:
        """Close the gripper (``on=True``) or open it."""
        return self.effector.grip(bool(on))

    # -- pick and place --------------------------------------------------------

    def pick_and_place(
        self, src: Point, dst: Point, z_safe: float, settle_ms: int = 200
    ) -> None:
        """Pick an object at ``src`` and place it at ``dst``.

        The classic eight-step cycle, all queued so it runs as one program:
        travel above the source at ``z_safe``, descend to the source, turn
        the suction cup ON and settle, lift back to ``z_safe``, travel above
        the destination, descend, turn the suction cup OFF and settle, lift
        back to ``z_safe``. Blocks until the final move completes.
        """
        sx, sy, sz = src
        dx, dy, dz = dst
        m = PTPMode.MOVL_XYZ
        self.cmds.set_ptp_cmd(m, sx, sy, z_safe, 0)
        self.cmds.set_ptp_cmd(m, sx, sy, sz, 0)
        self.cmds.set_suction_cup(True, True)
        self.cmds.set_wait_cmd(settle_ms)
        self.cmds.set_ptp_cmd(m, sx, sy, z_safe, 0)
        self.cmds.set_ptp_cmd(m, dx, dy, z_safe, 0)
        self.cmds.set_ptp_cmd(m, dx, dy, dz, 0)
        self.cmds.set_suction_cup(True, False)
        self.cmds.set_wait_cmd(settle_ms)
        last = self.cmds.set_ptp_cmd(m, dx, dy, z_safe, 0)
        self._wait_for(last, True)
