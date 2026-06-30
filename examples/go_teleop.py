"""Keyboard teleop for the Dobot Magician GO with an ultrasonic interlock.

Adapted from the ``magiciango_go/monitor.py`` reference, rewritten against the
ergonomic :class:`dobotkit.MagicianGO` API. It drives the car under continuous
velocity control (the reliable command class) while a live telemetry line and a
clearance interlock keep it from driving into anything.

Controls::

    W / S   forward / backward
    A / D   strafe left / right
    J / L   spin CCW / CW (in place)
    SPACE   stop
    Q       quit

Safety (mirrors the GO research doc; a past open-loop test drove into a wall and
tripped the power, so this matters):

* ``go.connect()`` follows the connect handshake with a real ``battery()`` read,
  because the raw handshake can report a *false* success.
* Every key command is gated by :meth:`MagicianGO.clearance_ok` for the intended
  direction of travel; a blocked direction is refused and the car is stopped.
* Because the drive is a *continuous* velocity command, every loop re-checks the
  current direction of travel and auto-stops if it becomes blocked.
* The control loop runs inside ``try/finally`` ending in ``emergency_stop`` (a
  non-blocking notify, safe even if the link is degraded) and ``client.close()``.

Prerequisites:

* **DobotLink.exe** running (Python talks to ``ws://localhost:9090``; DobotLink
  relays over the COM port / wireless dongle to the car).
* The **GO powered on** with its wireless dongle connected to the PC.
* The **COM port** the GO is on (defaults to ``COM5``).

Keyboard input uses ``msvcrt``, which is Windows-only. The import is guarded so
the module still imports cleanly on other platforms; running the teleop there
prints a clear message and exits.

Run it::

    python examples/go_teleop.py            # defaults to COM5
    python examples/go_teleop.py COM3        # or name the port explicitly
"""
from __future__ import annotations

import sys
import time
from typing import Dict, Optional, Tuple

from dobotkit import DobotConnectionError, DobotLinkError, MagicianGO
from dobotkit.go.client import DobotLinkClient

# Windows-only keyboard polling. Guarded so the file imports on any platform;
# main() checks for it and bails out with a clear message if unavailable.
try:
    import msvcrt
except ImportError:  # pragma: no cover - non-Windows fallback
    msvcrt = None  # type: ignore[assignment]

DRIVE_SPEED = 20  # conservative low speed
THRESHOLD = 15  # minimum clearance (cm) before a move is allowed
LOOP_DT = 0.1  # control-loop period (s)

# Key -> (x, y, r) continuous velocity command.
KEY_CMD: Dict[str, Tuple[int, int, int]] = {
    "W": (DRIVE_SPEED, 0, 0),
    "S": (-DRIVE_SPEED, 0, 0),
    "A": (0, DRIVE_SPEED, 0),
    "D": (0, -DRIVE_SPEED, 0),
    "J": (0, 0, DRIVE_SPEED),
    "L": (0, 0, -DRIVE_SPEED),
}


def safe_read(fn):
    """Run a sensor read, returning an ``err:...`` string instead of raising.

    Telemetry should never crash the teleop loop, so a degraded read is shown in
    the status line rather than propagated.
    """
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - telemetry must never kill the loop
        return f"err:{exc}"


def blocked(cmd: Tuple[float, float, float], u: Dict[str, float], threshold: float) -> Optional[str]:
    """Return the blocked direction for command ``cmd`` given ultrasonic dict ``u``.

    Mirrors :meth:`MagicianGO.clearance_ok`'s logic over an already-read distance
    dict (so the live loop can reuse one read for both display and the check):
    ``x > 0`` -> front, ``x < 0`` -> back, ``y != 0`` -> sides, ``r != 0`` -> all
    around. Returns ``None`` when clear.
    """
    x, y, r = cmd
    if x > 0 and u["front"] < threshold:
        return "front"
    if x < 0 and u["back"] < threshold:
        return "back"
    if y != 0 and min(u["left"], u["right"]) < threshold:
        return "side"
    if r != 0 and min(u.values()) < threshold:
        return "around"
    return None


def main(port: str = "COM5") -> None:
    if msvcrt is None:
        print("keyboard teleop requires msvcrt (Windows only); cannot run here.")
        return

    # Connect to DobotLink first; a failure here almost always means DobotLink.exe
    # is not running.
    client = DobotLinkClient()
    try:
        client.connect()
    except DobotConnectionError as exc:
        print(f"cannot reach DobotLink: {exc}")
        print("Start DobotLink.exe and try again.")
        return

    go = MagicianGO(client, port_name=port)
    try:
        # connect() verifies the link with a battery read so a dead power/wireless
        # link surfaces immediately rather than after a false-success handshake.
        try:
            go.connect()
        except DobotLinkError as exc:
            print(f"GO did not respond on {port}: {exc}")
            print("Check GO power / wireless dongle (confirm it connects in DobotLab first).")
            return

        print("Controls: W/S fwd-back, A/D strafe, J/L spin, SPACE stop, Q quit")
        print(f"Low speed ({DRIVE_SPEED}). Interlock {THRESHOLD}cm. Keep the area clear!\n")

        moving: Tuple[int, int, int] = (0, 0, 0)  # current continuous velocity command
        while True:
            u = safe_read(go.ultrasonic)
            batt = safe_read(go.battery)
            imu = safe_read(go.imu_angle)
            print(f"\rBatt:{batt} | IMU:{imu} | US:{u}        ", end="", flush=True)

            # While moving, re-check the current direction every loop and auto-stop
            # if it has become blocked (continuous velocity keeps going otherwise).
            if isinstance(u, dict) and moving != (0, 0, 0):
                why = blocked(moving, u, THRESHOLD)
                if why:
                    go.emergency_stop()
                    moving = (0, 0, 0)
                    print(f"\n[auto-stop] obstacle ahead in travel direction: {why}")

            if msvcrt.kbhit():
                key = msvcrt.getch().decode("utf-8", "ignore").upper()
                if key == "Q":
                    break
                elif key == " ":
                    go.emergency_stop()
                    moving = (0, 0, 0)
                elif key in KEY_CMD:
                    cmd = KEY_CMD[key]
                    why = blocked(cmd, u, THRESHOLD) if isinstance(u, dict) else None
                    if why:
                        go.emergency_stop()
                        moving = (0, 0, 0)
                        print(f"\n[blocked] that direction is too close: {why}")
                    else:
                        go.move(x=cmd[0], y=cmd[1], r=cmd[2])
                        moving = cmd
            time.sleep(LOOP_DT)
    finally:
        # Always end stopped, on every exit path (quit, blocked, or exception).
        print("\nstopping and disconnecting...")
        try:
            go.emergency_stop()
        except Exception:  # noqa: BLE001 - teardown must not raise
            pass
        client.close()


if __name__ == "__main__":
    # First CLI arg (if any) is the COM port; default to COM5.
    main(sys.argv[1] if len(sys.argv) > 1 else "COM5")
