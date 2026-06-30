"""Pick-and-place demo for the Dobot Magician (Lite) arm.

Adapted from the pick-and-place example in the Dobot Lite API research doc, but
written against the ergonomic :class:`dobotkit.Magician` API instead of the raw
``DobotDllType`` calls. The whole cycle is queued on the device and executed as
one motion program, so it runs smoothly without per-step round-trips.

Run it::

    python examples/arm_pick_and_place.py            # auto-detect the serial port
    python examples/arm_pick_and_place.py COM3        # or name the port explicitly

Safety: the arm is opened as a context manager, so the queue is stopped and the
port closed on exit -- even if a move raises. Adjust the coordinates below to
match YOUR workspace before running on real hardware; the defaults are
illustrative only.
"""
from __future__ import annotations

import sys

import dobotkit
from dobotkit import DobotAlarmError


def main(port: str = "auto") -> None:
    # Opening as a context manager guarantees a clean teardown (queue stop +
    # disconnect) on every exit path, including exceptions.
    with dobotkit.Magician(port=port) as arm:
        # Home first so absolute coordinates are trustworthy, then set a gentle
        # speed/acceleration for the demo (percentages, pydobot-compatible).
        arm.home(wait=True)
        arm.set_speed(velocity=100, acceleration=100)

        # Waypoints are (x, y, z) in millimetres. ``src``/``dst`` give the grab
        # and release heights; ``z_safe`` is the travel clearance between them.
        source = (200.0, 0.0, -30.0)
        destination = (100.0, 150.0, -30.0)
        z_safe = 50.0

        try:
            # One call performs the full eight-step cycle (approach, descend,
            # suck, lift, travel, descend, release, lift) -- all queued, then
            # waited on until the final lift completes.
            arm.pick_and_place(source, destination, z_safe=z_safe, settle_ms=300)
        except DobotAlarmError as exc:
            # A collision / limit fault during the move surfaces here with the
            # active alarm codes.
            print(f"motion stopped by an active alarm: {exc.codes}")
            raise

        # Report where we ended up.
        pose = arm.get_pose()
        print(f"done -- final pose: x={pose.x:.1f} y={pose.y:.1f} z={pose.z:.1f}")


if __name__ == "__main__":
    # First CLI arg (if any) is the serial port; default to auto-detection.
    main(sys.argv[1] if len(sys.argv) > 1 else "auto")
