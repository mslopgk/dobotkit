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
4. Line camera — ``trace_angle()``; ``count == 1`` with the car on a line means
   the patrol/vision stack is healthy. Note the ``angle`` value: that is your
   chassis' line-centre constant (``CENTER``) for P-control exercises.
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

        cam = go.trace_angle()
        if cam["count"] > 0:
            print(f"[OK]   line camera  : angle={cam['angle']} count={cam['count']}"
                  f"  <- on-line CENTER constant for P-control")
        else:
            print("[OK]   line camera  : no line in view (count=0) — put the car "
                  "on a floor line to measure CENTER")

        odo = go.odometer()
        imu = go.imu_angle()
        print(f"[OK]   odometer     : x={odo.get('x')} y={odo.get('y')} "
              f"yaw={odo.get('yaw')} (mm/deg, world frame)")
        print(f"[OK]   imu yaw      : {imu.get('yaw')} deg "
              f"(power-on reference — do NOT mix with odometer yaw)")

    print("-" * 60)
    print("All reads completed. The car never moved. You are ready for the")
    print("drive examples (go_line_trace.py / go_waypoint_nav.py).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
