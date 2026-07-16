"""Minimal Dobot Magician Lite (arm) demo, driven through DobotLink.

Requires **DobotLink.exe** running. The arm is never opened over a raw serial
port -- Python talks to the **DobotLink** desktop service over a WebSocket
(JSON-RPC 2.0, ``ws://localhost:9090``), and DobotLink relays commands to the
arm over its COM port::

    Python  --(WebSocket JSON-RPC)-->  DobotLink.exe  --(COM port)-->  arm

There is no ``pyserial`` dependency; only ``websockets`` is required at
runtime.

Safety: the arm is opened as a context manager, so its command queue is
stopped and DobotLink is disconnected on every exit path -- even if a call
raises. Home first so absolute coordinates are trustworthy, and keep the
workspace clear before running on real hardware.

Run it::

    python examples/arm_magicianlite.py            # port="auto": first DobotLink port
    python examples/arm_magicianlite.py COM3        # or name the port explicitly

If Korean text prints as garbled characters on Windows, set
``PYTHONIOENCODING=utf-8`` before running.
"""
from __future__ import annotations

import sys

import dobotkit
from dobotkit import DobotConnectionError


def main(port: str = "auto") -> int:
    try:
        # port="auto" resolves to the first port DobotLink's SearchDobot
        # reports; pass a COM name to be explicit.
        with dobotkit.MagicianLite(port=port) as arm:
            # Home first so absolute coordinates are trustworthy (power-on /
            # after any alarm). Blocks until the homing motion completes.
            arm.home()

            # Absolute straight-line move to (x, y, z) in mm; block until done.
            arm.move_to(220, 0, 40, wait=True)

            # Turn the suction cup on (grab).
            arm.suck(True)

            # ADC reads are routed through the MagicBox: a missing MagicBox or
            # sensor degrades to None + a RuntimeWarning instead of raising, so
            # guard the result before using it.
            v = arm.sensors.adc(24)
            if v is None:
                print("매직박스/센서 미연결 -- ADC 값을 읽지 못했습니다")
            else:
                print(f"ADC[24] = {v}")

            print("demo complete")
    except DobotConnectionError as exc:
        print(f"cannot reach the arm via DobotLink: {exc}")
        print("Start DobotLink.exe and try again.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "auto"))
