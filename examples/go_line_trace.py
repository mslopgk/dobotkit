"""Line-tracing demo for the Dobot Magician GO with an obstacle interlock.

Adapted from the ``magiciango_go/line_trace.py`` reference, rewritten against the
ergonomic :class:`dobotkit.MagicianGO` API. The GO follows a physical floor line
under its built-in PID line follower while a safety loop watches the ultrasonic
sensors and stops the instant anything gets too close.

A physical FLOOR LINE is required to actually follow a path. With no line the GO
just attempts the tracing motion in place. If any ultrasonic distance drops below
the threshold, tracing is disabled and the car is emergency-stopped immediately.

Safety (a past open-loop test drove into a wall and tripped the power):

* ``go.connect()`` verifies the link with a real ``battery()`` read, because the
  connect handshake can report a *false* success.
* Each loop reads all four ultrasonic distances; if the nearest is below the
  obstacle threshold, tracing is turned off and an ``emergency_stop`` is fired.
* The loop has a duration cap, ``Ctrl-C`` is handled, and everything runs inside
  ``try/finally`` that disables tracing, emergency-stops, and closes the client
  no matter how the run ends.

Prerequisites:

* **DobotLink.exe** running (Python talks to ``ws://localhost:9090``; DobotLink
  relays over the COM port / wireless dongle to the car).
* The **GO powered on** with its wireless dongle connected to the PC.
* The **COM port** the GO is on (defaults to ``COM5``), and a floor line to trace.

Run it::

    python examples/go_line_trace.py                  # defaults: COM5, 20s
    python examples/go_line_trace.py COM3 30           # port + duration (seconds)
"""
from __future__ import annotations

import sys
import time
from typing import Tuple

from dobotkit import DobotConnectionError, DobotLinkError, MagicianGO
from dobotkit.link import DobotLinkClient

# Easily tunable constants (safety / drive tuning).
DEFAULT_PORT = "COM5"  # COM port the GO is connected on
DEFAULT_DURATION = 20.0  # default run time (seconds)

TRACE_SPEED = 20  # official patrol speed (matches DobotLab's patrol button)
TRACE_P = 0.5  # PID proportional gain (official demo value; hardware-measured:
TRACE_I = 0    # values like 50 are ~100x too hot -> violent oscillation and
TRACE_D = 0.5  # the car flies off the line)

OBSTACLE_THRESHOLD_CM = 15  # below this (cm) -> obstacle -> stop immediately
LOOP_DT = 0.1  # control-loop period (seconds)

HOST = "localhost"
WS_PORT = 9090
WS_TIMEOUT = 10.0


def parse_args(argv: list) -> Tuple[str, float]:
    """Parse ``[port] [duration]`` from CLI args, falling back to the defaults."""
    port = argv[1] if len(argv) >= 2 and argv[1] else DEFAULT_PORT
    duration = DEFAULT_DURATION
    if len(argv) >= 3 and argv[2]:
        try:
            duration = float(argv[2])
        except ValueError:
            print(f"[warn] could not parse duration '{argv[2]}', "
                  f"using default {DEFAULT_DURATION}s.")
    return port, duration


def main() -> None:
    port, duration = parse_args(sys.argv)

    print("=" * 64)
    print("Dobot Magician GO line-tracing demo")
    print(f"  port={port}  duration={duration}s")
    print(f"  speed={TRACE_SPEED}  PID=({TRACE_P},{TRACE_I},{TRACE_D})")
    print(f"  obstacle threshold={OBSTACLE_THRESHOLD_CM}cm")
    print("=" * 64)

    # 1) Connect to DobotLink; a failure here almost always means DobotLink.exe
    #    is not running.
    try:
        client = DobotLinkClient(host=HOST, port=WS_PORT, timeout=WS_TIMEOUT).connect()
    except DobotConnectionError as exc:
        print(f"[error] cannot reach DobotLink (ws://{HOST}:{WS_PORT}). "
              f"Is DobotLink.exe running?\n        {exc}")
        sys.exit(1)

    go = MagicianGO(client, port_name=port)

    try:
        # 2) Connect + verify the link. connect() follows the handshake with a
        #    battery read so a dead power/wireless link surfaces immediately.
        try:
            batt = go.connect()
        except DobotLinkError as exc:
            print(f"[error] connect/battery failed on {port} -- GO power/link may be "
                  f"down. Aborting.\n        {exc}")
            return
        print(f"[ok] link verified. battery={batt}")

        # 3) Warn the user, then configure tracing.
        print("")
        print("!! NOTICE: a FLOOR LINE is required. The GO will START MOVING shortly.")
        print("!! Press Ctrl-C at any time to stop.\n")

        go.trace_speed(TRACE_SPEED)
        go.trace_pid(TRACE_P, TRACE_I, TRACE_D)

        # 4) Start tracing + run the safety loop.
        go.auto_trace(True)
        print(f"[start] line tracing started (up to {duration}s).\n")

        start = time.monotonic()
        while time.monotonic() - start < duration:
            u = go.ultrasonic()
            angle_info = go.trace_angle()

            # ultrasonic() returns None on a malformed/failed read — unknown
            # means STOP, exactly like a detected obstacle.
            if u is None:
                go.auto_trace(False)
                go.emergency_stop()
                print("\n[safe-stop] ultrasonic read invalid (unknown -> stop) "
                      "-> tracing stopped.")
                break

            elapsed = time.monotonic() - start
            line = (
                f"\r[{elapsed:5.1f}s] ultrasonic(cm) F={u['front']:>4} B={u['back']:>4} "
                f"L={u['left']:>4} R={u['right']:>4} | line angle={angle_info.get('angle')} "
                f"count={angle_info.get('count')}   "
            )
            sys.stdout.write(line)
            sys.stdout.flush()

            # Safety interlock: any direction under the threshold -> stop now.
            nearest_dir = min(u, key=u.get)
            nearest = u[nearest_dir]
            if nearest < OBSTACLE_THRESHOLD_CM:
                go.auto_trace(False)
                go.emergency_stop()
                print(f"\n[safe-stop] obstacle detected: {nearest_dir}={nearest}cm "
                      f"< {OBSTACLE_THRESHOLD_CM}cm -> tracing stopped.")
                break

            time.sleep(LOOP_DT)
        else:
            print(f"\n[done] duration ({duration}s) elapsed -> normal stop.")

    except KeyboardInterrupt:
        print("\n[interrupt] Ctrl-C -> stopping.")
    except DobotLinkError as exc:
        print(f"\n[error] DobotLink communication error -> stopping.\n        {exc}")
    except Exception as exc:  # noqa: BLE001 - any failure must still stop the car
        print(f"\n[error] unexpected error -> stopping.\n        {exc}")
    finally:
        # 5) No matter what happened, the car must end stopped.
        print("[cleanup] disabling trace, emergency stop, closing connection.")
        try:
            go.auto_trace(False)
        except Exception:  # noqa: BLE001 - teardown must not raise
            pass
        try:
            go.emergency_stop()
        except Exception:  # noqa: BLE001 - teardown must not raise
            pass
        try:
            client.close()
        except Exception:  # noqa: BLE001 - teardown must not raise
            pass
        print("[exit] shut down safely.")


if __name__ == "__main__":
    main()
