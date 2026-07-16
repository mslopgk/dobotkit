"""Read a MagicBox sensor on the Magician GO — READ-ONLY, no motion.

The GO carries the same **MagicBox** peripheral hub as the arm. Connect the car
once with ``MagicianGO`` and its MagicBox sensors read through ``go.sensors`` /
``go.io`` on a single connection (no separate MagicBox connect step).

Two addressing schemes (from the official DobotLab apiBook):

* **ADC / DI / DO / PWM** -> a raw **EIO pin (1..26)**. The rotary
  potentiometer shipped with the teaching kit, plugged into Grove connector 4,
  reads on EIO pin **22** -> ``go.sensors.adc(22)``.
* **color / infrared / Seeed** -> the labelled **Grove connector (1..6)**.

A missing MagicBox or unplugged sensor degrades to ``None`` + a
``RuntimeWarning`` instead of raising, so a classroom script keeps running.

Run it (turn the knob and watch the value change)::

    python examples/go_magicbox_sensor.py            # default port COM5, EIO 22
    python examples/go_magicbox_sensor.py COM3 22    # explicit port + EIO pin
"""
from __future__ import annotations

import sys
import time

from dobotkit import DobotConnectionError, DobotLinkError, MagicianGO

DEFAULT_PORT = "COM5"
DEFAULT_EIO = 22  # teaching-kit potentiometer on Grove connector 4


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PORT
    eio = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_EIO

    try:
        go = MagicianGO.open(port_name=port)
    except DobotConnectionError as exc:
        print(f"[FAIL] DobotLink unreachable: {exc}  -> start DobotLink.exe")
        return 1
    except DobotLinkError as exc:
        print(f"[FAIL] GO link dead on {port}: {exc}  -> check GO power + dongle")
        return 1

    with go:  # read-only; teardown still guarantees a safe (stopped) state
        mbox = go.magic_box_num()
        print(f"MagicBox: {mbox}")
        print(f"Reading analog on EIO pin {eio} for ~10 s — turn the knob...")
        for _ in range(20):
            value = go.sensors.adc(eio)  # None (+warning) if unplugged/absent
            bar = "#" * (int(value) * 40 // 4096) if value is not None else ""
            print(f"  adc({eio}) = {value!s:>5}  {bar}")
            time.sleep(0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
