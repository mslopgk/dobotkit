"""First-connection diagnostic for the Dobot Magician GO — READ-ONLY, no motion.

The recommended first script to run in a classroom or on a new setup: it
connects, verifies the link, and reads every sensor once, printing a short
health report. **No motor command is ever issued**, so it is safe to run with
the car on a desk.

What it checks, in order:

1. DobotLink reachable (``ws://localhost:9090`` — is DobotLink.exe running?).
2. GO link alive — ``MagicianGO.open()`` verifies with a real ``battery()``
   read, because the connect handshake can report a *false* success.
3. Ultrasonic sanity — validated read (``None`` means a malformed response;
   values clamp at the hardware's 40 cm ceiling).
4. MagicBox — ``magic_box_num()`` / ``magic_box_mode()`` report whether a
   MagicBox peripheral hub is attached. Its sensors read through ``go.sensors``
   (``go.sensors.adc(22)`` for a potentiometer on EIO pin 22; ``color``/
   ``infrared`` take a Grove connector 1..6) and ``go.io``; a missing
   MagicBox/sensor degrades to ``None`` + a ``RuntimeWarning``.
5. Odometer / IMU — both yaw sources printed side by side (they use different
   references and must never be mixed).

Run it::

    python examples/go_discover.py            # default port COM5
    python examples/go_discover.py COM3       # explicit port
"""
from __future__ import annotations

import sys

from dobotkit import DobotConnectionError, DobotLinkError, MagicianGO

DEFAULT_PORT = "COM5"  # COM port the GO's wireless dongle enumerates on


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PORT
    print("=" * 60)
    print(f" Magician GO discovery (READ-ONLY)  port={port}")
    print("=" * 60)

    try:
        go = MagicianGO.open(port_name=port)
    except DobotConnectionError as exc:
        print(f"[FAIL] DobotLink unreachable: {exc}")
        print("       -> Start DobotLink.exe (or DobotLab) and retry.")
        return 1
    except DobotLinkError as exc:
        print(f"[FAIL] GO link dead on {port}: {exc}")
        print("       -> Check the GO power switch and the wireless dongle.")
        return 1

    with go:  # read-only from here on; teardown still guarantees a safe state
        batt = go.battery()
        # powerPercentage scale differs by firmware: the reference chassis
        # reports a 0..1 fraction (measured 0.9999... = full), but 0..100 has
        # been seen documented — normalise defensively.
        pct = float(batt.get("powerPercentage", 0))
        pct = pct * 100 if pct <= 1.0 else pct
        print(f"[OK]   battery      : {batt.get('powerVoltage', '?')} V "
              f"({round(pct)}%)")

        ultra = go.ultrasonic()
        if ultra is None:
            print("[WARN] ultrasonic   : malformed response (treat as unknown -> "
                  "any drive code must stop)")
        else:
            note = " (40 = 40 cm OR MORE — hardware ceiling)" \
                if max(ultra.values()) >= 40 else ""
            print(f"[OK]   ultrasonic   : {ultra}{note}")

        mbox = go.magic_box_num()
        n = mbox.get("num", 0) if isinstance(mbox, dict) else 0
        if n:
            print(f"[OK]   magicbox     : {n} device(s) {mbox} — read sensors via "
                  f"go.sensors.* / go.io.* (adc/di by EIO pin, color/infrared by Grove 1-6)")
        else:
            print("[OK]   magicbox     : none detected (attach one for Grove sensors)")

        odo = go.odometer()
        imu = go.imu_angle()
        print(f"[OK]   odometer     : x={odo.get('x')} y={odo.get('y')} "
              f"yaw={odo.get('yaw')} (mm/deg, world frame)")
        print(f"[OK]   imu yaw      : {imu.get('yaw')} deg "
              f"(power-on reference — do NOT mix with odometer yaw)")

    print("-" * 60)
    print("All reads completed. The car never moved. You are ready for the")
    print("drive example (go_teleop.py) and PreciseMover feedback motion.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
