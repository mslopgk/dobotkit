"""Read the Magician arm's sensors via the ergonomic ``Magician.sensors`` group.

Adapted from the IO / sensor API section of the Dobot Lite API research doc. The
low-level "set the port, then read" two-step is collapsed into a single call by
the :class:`~dobotkit.arm.groups.SensorGroup` helpers exposed as ``arm.sensors``.

Most Seeed Grove sensors and the servo path require a Magic Box and are wired to
its Grove ports (1-6). The color / infrared sensors plug into the GP ports
(``ColorPort.GP1`` = 0 .. ``GP5`` = 3).

Run it::

    python examples/arm_sensors.py             # auto-detect the serial port
    python examples/arm_sensors.py COM3 2      # port + Grove/GP port number
"""
from __future__ import annotations

import sys

import dobotkit
from dobotkit import ColorPort


def main(port: str = "auto", grove_port: int = 1) -> None:
    with dobotkit.Magician(port=port) as arm:
        sensors = arm.sensors

        # Every sensor read is MagicBox-routed: if the MagicBox (or the sensor)
        # is not connected it returns ``None`` (with a warning) instead of
        # raising, so guard each reading before using it.

        # --- color sensor (GP port) --------------------------------------- #
        # ``color`` enables the sensor on the given port then reads (r, g, b).
        rgb = sensors.color(ColorPort.GP1)
        if rgb is None:
            print("color sensor: 읽지 못함 (매직박스/센서 연결 확인)")
        else:
            print(f"color sensor RGB: r={rgb.r} g={rgb.g} b={rgb.b}")

        # --- infrared sensor (GP port) ------------------------------------ #
        ir = sensors.infrared(ColorPort.GP2)
        if ir is None:
            print("infrared: 읽지 못함 (매직박스/센서 연결 확인)")
        else:
            print(f"infrared value: {ir.value}")

        # --- Seeed Grove sensors (Magic Box ports 1-6) -------------------- #
        # Distance takes the port directly; the read returns millimetres.
        distance = sensors.seeed_distance(grove_port)
        if distance is None:
            print("distance: 읽지 못함 (매직박스/센서 연결 확인)")
        else:
            print(f"distance: {distance.distance} mm")

        # Temp/humidity: select the port, then read (temperature, humidity).
        th = sensors.seeed_temp(grove_port)
        if th is None:
            print("temp/humidity: 읽지 못함 (매직박스/센서 연결 확인)")
        else:
            print(f"temperature: {th.temperature} C, humidity: {th.humidity} %")

        # Color (Seeed): returns (r, g, b, cct).
        sc = sensors.seeed_color(grove_port)
        if sc is None:
            print("seeed color: 읽지 못함 (매직박스/센서 연결 확인)")
        else:
            print(f"seeed color: r={sc.r} g={sc.g} b={sc.b} cct={sc.cct}")

        # Light: returns a lux value.
        light = sensors.seeed_light(grove_port)
        if light is None:
            print("light: 읽지 못함 (매직박스/센서 연결 확인)")
        else:
            print(f"light: {light.lux} lux")

        # --- alarms -------------------------------------------------------- #
        # Read the active alarm bitmap and decode it to human-readable codes.
        from dobotkit.arm.alarms import decode_alarms

        codes = decode_alarms(arm.lowlevel.get_alarms_state())
        print(f"active alarms: {[c.name for c in codes] or 'none'}")


if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "auto"
    grove = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    main(port, grove)
