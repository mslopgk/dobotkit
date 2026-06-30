"""Absolute mat-coordinate waypoint navigation for the Dobot Magician GO.

Adapted from the ``magiciango_go/waypoint_nav.py`` reference, rewritten against
:class:`dobotkit.go.navigation.WaypointNav`. The whole coordinate / unit
convention and the safe closed-loop primitives now live inside ``dobotkit`` --
this script just drives a couple of short, safe legs and prints the result dicts.

How it works (see ``dobotkit.go.navigation`` for the full design):

* The GO odometer ``(x, y, yaw)`` is a planar pose frozen at the last
  ``set_odometer`` call, so :meth:`WaypointNav.set_start` zeroes it to a known
  mat start point -- after that the odometer reads out *mat coordinates*.
* :meth:`WaypointNav.go_to` then drives toward absolute mat ``(x, y)`` targets,
  re-measuring the pose each leg to correct odometer drift and turn error.

Coordinate convention: mat coordinates are centimetres; ``x+`` faces forward at
heading ``0deg``, ``y+`` strafes left, and angles increase counter-clockwise.
The cm<->mm conversion happens entirely inside ``WaypointNav`` / ``PreciseMover``.

Safety (a past open-loop test drove into a wall and tripped the power):

* ``go.connect()`` verifies the link with a real ``battery()`` read.
* Every leg goes through ``PreciseMover``, which clearance-checks the intended
  direction *before* moving, caps speed, and has an absolute wall-clock timeout
  -- so it can never spin forever and aborts (rather than ramming) when blocked.
* The demo runs inside ``try/finally`` ending in ``emergency_stop`` +
  ``client.close()``.

IMPORTANT: the declared start pose below is an ASSUMPTION. For navigation to be
correct it must match the GO's *actual* position/heading on the mat -- calibrate
``set_start(...)`` to your real layout or the car will miss its targets.

Prerequisites:

* **DobotLink.exe** running (Python talks to ``ws://localhost:9090``; DobotLink
  relays over the COM port / wireless dongle to the car).
* The **GO powered on** with its wireless dongle connected to the PC.
* The **COM port** the GO is on (defaults to ``COM5``).

Run it::

    python examples/go_waypoint_nav.py            # defaults to COM5
    python examples/go_waypoint_nav.py COM3        # or name the port explicitly
"""
from __future__ import annotations

import sys

from dobotkit import DobotConnectionError, DobotLinkError, MagicianGO
from dobotkit.go.client import DobotLinkClient
from dobotkit.go.navigation import WaypointNav

# Declared start pose (cm, cm, deg). *** ASSUMPTION -- calibrate to your mat. ***
START_X, START_Y, START_H = 100.0, 48.0, 0.0


def print_pose(label: str, nav: WaypointNav) -> None:
    """Print the current mat pose in a fixed, readable layout."""
    p = nav.pose_cm()
    print(
        f"  {label}: x={p['x_cm']:.1f}cm y={p['y_cm']:.1f}cm "
        f"heading={p['heading_deg']:.1f}deg"
    )


def main(port: str = "COM5") -> None:
    print("=" * 60)
    print(" Magician GO - absolute mat-coordinate waypoint navigation demo")
    print("=" * 60)
    print("[assume] units: mat = cm, internal motion = mm (x10 conversion).")
    print("[assume] heading 0deg faces +X, counter-clockwise positive (+).")
    print(f"[assume] start pose declared as (x,y)=({START_X:.0f},{START_Y:.0f})cm, "
          f"heading={START_H:.0f}deg.")
    print("         *** This is arbitrary. Calibrate set_start(...) to the GO's")
    print("             real mat coordinate/heading or it WILL miss. ***")
    print(f"port: {port} | only short legs (~10-15cm) are driven.\n")

    # Connect to DobotLink first; a failure here almost always means DobotLink.exe
    # is not running.
    client = DobotLinkClient(host="localhost", port=9090, timeout=10.0)
    try:
        client.connect()
    except DobotConnectionError as exc:
        print(f"[FAIL] cannot reach DobotLink: {exc}")
        print("       Start DobotLink.exe and try again.")
        return

    go = MagicianGO(client, port_name=port)
    nav = WaypointNav(go)

    try:
        # Verify the link -- the connect handshake can lie, so connect() reads the
        # battery back to confirm the GO actually responds.
        try:
            batt = go.connect()
        except DobotLinkError as exc:
            print(f"[FAIL] GO did not respond (battery read timed out): {exc}")
            print("       Check GO power / wireless dongle. Aborting.")
            return
        print(f"battery: {batt}")

        # Declare the start pose (assumed; calibrate to reality), zeroing the
        # odometer to the mat frame.
        nav.set_start(START_X, START_Y, START_H)
        print_pose("start", nav)

        # Two short, safe absolute-coordinate legs near the start point.
        waypoints = (
            (START_X + 12.0, START_Y),          # +X by 12cm
            (START_X + 12.0, START_Y + 10.0),   # then +Y by 10cm
        )
        for wx, wy in waypoints:
            print(f"\n-> go_to({wx:.1f}, {wy:.1f}) cm")
            res = nav.go_to(wx, wy, arrive_tol_cm=2.0)
            print_pose("arrived", nav)
            # The result dict carries the full per-leg detail; print the summary.
            print(
                f"   residual={res['residual_cm']:.2f}cm  "
                f"iters={res['iters']}  arrived={res['arrived']}"
            )

        print("\n[done] check residual for accuracy. If it misses, calibrate the "
              "start coordinate/heading first.")
    finally:
        # Always end stopped, on every exit path.
        try:
            go.emergency_stop()
        except Exception:  # noqa: BLE001 - teardown must not raise
            pass
        client.close()


if __name__ == "__main__":
    # First CLI arg (if any) is the COM port; default to COM5.
    main(sys.argv[1] if len(sys.argv) > 1 else "COM5")
