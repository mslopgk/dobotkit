# dobotkit

Complete, pure-Python control for the **Dobot Magician Lite** robotic arm and the
**Dobot Magician GO** mobile robot — one library, no DLLs, no native binaries.

`dobotkit` wraps both devices' **DobotLink** JSON-RPC bridge in clean,
type-hinted Python over `websockets`, so the same code runs on Windows, macOS,
and Linux with nothing more than `pip install`. **DobotLink.exe must be
running** for either device -- neither is driven over a raw serial port.

```python
import dobotkit

with dobotkit.MagicianLite(port="auto") as arm:
    arm.home()
    arm.move_to(220, 0, 40, wait=True)
    arm.suck(True)
```

---

## Features

- **Magician Lite arm over DobotLink** — an ergonomic high-level `MagicianLite`
  API (home, move, pick-and-place, IO, sensors, end-effectors) wraps the arm's
  `Magician.*` DobotLink JSON-RPC surface. No serial port, no serial-library
  runtime dependency.
- **Full Magician GO coverage** — the complete DobotLink `MagicianGO.*` surface:
  continuous drive, closed-loop commands, ultrasonic/IMU/odometer sensors, RGB
  LEDs, buzzer, line-tracing, and camera object/tag detection.
- **Pure Python** — only `websockets` at runtime. No DLL, no vendored native
  code, no DobotDll/DobotRPC dependency. Cross-platform and `pip`-installable.
- **Fully type-hinted** — every public symbol is typed and the package ships
  `py.typed`, so editors and `mypy` see real types.
- **Safety-first** — context-manager teardown for both devices (queue stop +
  disconnect on every exit path, including exceptions), and a sensor-feedback
  navigation layer for the GO with absolute wall-clock timeouts and pre-move
  clearance checks.
- **Lazy device imports** — `import dobotkit` never pulls in `websockets`; it
  is imported only when you first access `MagicianLite` or `MagicianGO`.
- **Ergonomic pydobot-flavoured API** — `suck`, `grip`, `move_to`, and
  `move_relative` read like `pydobot.Dobot`, so the everyday arm workflow
  (home -> move -> grab -> move -> release) needs no protocol knowledge.

## Installation

> **Not yet published to PyPI** — install from a local checkout for now:

```bash
pip install -e path/to/dobotkit
```

For development (editable install with the test/lint toolchain):

```bash
git clone <repo-url> dobotkit
cd dobotkit
pip install -e ".[dev]"
```

Requires **Python ≥ 3.9**. The only runtime dependency, `websockets` (used to
talk to DobotLink for both the arm and the GO), is installed automatically.

한국어 문서: [빠른 시작 quickstart-ko](docs/quickstart-ko.md) ·
[GO API 치트시트](docs/cheatsheet_go.md) (LLM 프롬프트/RAG 접지용 1장 요약)

---

## Quickstart — Magician Lite (arm)

The arm is not driven over a serial port: Python talks to the **DobotLink**
desktop service over a WebSocket (JSON-RPC 2.0), and DobotLink relays commands
to the arm over its COM port. **DobotLink.exe must be running.** Open a
`MagicianLite` as a context manager so the on-device command queue is stopped
and DobotLink is disconnected on every exit path, including exceptions.

```python
import dobotkit
from dobotkit import PTPMode

# port="auto" picks the first port DobotLink reports; pass "COM3" to be explicit.
with dobotkit.MagicianLite(port="auto") as arm:
    # Home first so absolute coordinates are trustworthy (blocks until done).
    arm.home(wait=True)

    # Set a gentle speed/acceleration (percentages; pydobot-compatible).
    arm.set_speed(velocity=100, acceleration=100)

    # Absolute straight-line move to (x, y, z, r) in mm/degrees; wait for finish.
    arm.move_to(220, 0, 40, 0, mode=PTPMode.MOVL_XYZ, wait=True)

    # Toggle the suction cup directly...
    arm.suck(True)
    arm.move_relative(dz=-20, wait=True)
    arm.suck(False)

    # ...or run the whole eight-step pick-and-place cycle as one queued program.
    # Waypoints are (x, y, z) in mm; z_safe is the travel clearance between them.
    arm.pick_and_place(
        src=(200.0, 0.0, -30.0),
        dst=(100.0, 150.0, -30.0),
        z_safe=50.0,
        settle_ms=300,
    )

    pose = arm.get_pose()
    print(f"final pose: x={pose['x']:.1f} y={pose['y']:.1f} z={pose['z']:.1f}")
```

`wait=True` polls the on-device queue until the command finishes and raises
`DobotTimeoutError` if it never does -- treat that as "something is stuck,"
not a silent success.

### MagicBox peripherals (sensors, ADC/DI reads)

Every `sensors.*` read (`adc`, `di`, `color`, `infrared`, `distance`, `temp`,
`light`, `rgb`) and the read-only `io.get_di` / `io.get_adc` are routed
through the **MagicBox**. If it (or its device) is not connected, these calls
**warn and return `None`** rather than raising, so teaching code keeps
running:

```python
reading = arm.sensors.color(port=0)   # RuntimeWarning + None if no MagicBox
if reading is None:
    print("색 센서를 읽지 못했습니다 — 매직박스/센서 연결 확인")
else:
    print(reading)

v = arm.sensors.adc(24)               # RuntimeWarning + None if no MagicBox
if v is None:
    print("매직박스/센서 미연결")
```

Arm-native operations (motion, `effector.suck` / `grip` / `servo`, `io.set_do`
/ `set_pwm` / `set_multiplexing`) are unaffected and still raise on error, as
does a genuine connection error (`DobotConnectionError`, e.g. DobotLink is not
running).

## Quickstart — Magician GO (mobile robot)

The GO is not driven directly: Python talks to the **DobotLink** desktop service
over a WebSocket (JSON-RPC 2.0), and DobotLink relays commands to the car.
DobotLink must be running.

```
Python  --(WebSocket JSON-RPC)-->  DobotLink  --(COM/wireless)-->  GO
```

```python
from dobotkit import MagicianGO
from dobotkit.link import DobotLinkClient
from dobotkit.go.navigation import WaypointNav

# Connect to DobotLink (default ws://localhost:9090) as a context manager.
with DobotLinkClient() as client:
    go = MagicianGO(client, port_name="COM5")

    # connect() verifies the link with a battery read-back so a dead
    # power/wireless link surfaces immediately.
    go.connect()

    try:
        # Continuous velocity control is reliable: check clearance, then drive.
        ok, info = go.clearance_ok(x=1, threshold=20)
        if ok:
            go.forward(20)   # drive forward at speed 20 until told to stop
        # ... do work ...
    finally:
        go.stop()            # always halt
        go.emergency_stop()  # fire-and-forget safety stop (never blocks)

    # For precise, reliable motion use the sensor-feedback navigation layer
    # instead of the built-in closed-loop commands (which can HANG, see below).
    nav = WaypointNav(go)
    nav.set_start(x_cm=0, y_cm=0, heading_deg=0)   # zero the odometer to the mat
    result = nav.go_to(x_cm=50, y_cm=30, arrive_tol_cm=2.0)
    print("arrived:", result["arrived"], "residual_cm:", result["residual_cm"])
```

---

## Safety

Robot hardware moves under power and can collide, pinch, or topple. `dobotkit` is
built to fail safe, but you must still operate it responsibly. The guidance below
comes from the Dobot Magician Lite and Magician GO operating notes.

**Arm (Magician Lite)**

- **Power-on home.** Always `home()` after powering on so that absolute
  coordinates are trustworthy before issuing `move_to` / `pick_and_place`.
- **Clearance checks.** Verify the workspace is clear of obstacles, fingers, and
  fixtures along the planned path before commanding a move. Start with the
  illustrative coordinates lowered/slowed and tune to *your* setup.
- **Wait timeouts, not silent success.** `wait=True` raises `DobotTimeoutError`
  if the queued command never finishes, instead of returning as if it had.
- **Always disconnect.** Use the `MagicianLite` context manager
  (`with ... as arm:`) so the command queue is stopped and DobotLink is
  disconnected on every exit path — including exceptions.

**GO (Magician GO)**

- **Verify the link.** Use `go.connect()` (it follows the connect handshake with
  a real battery read), because the raw handshake can report a *false* success.
- **Clearance before driving.** Call `clearance_ok(...)` for the intended
  direction of travel and only drive when it returns `True`.
- **Timeouts everywhere.** The `PreciseMover` / `WaypointNav` control loops use
  absolute wall-clock timeouts (`time.monotonic`) so they can never spin forever,
  and every path ends in `emergency_stop`.
- **Always stop.** Wrap motion in `try/finally` ending in `go.stop()` and
  `go.emergency_stop()` (the latter is a non-blocking notify, safe from a
  `finally` block or interrupt path even if the link is degraded).
- **Avoid the built-in closed-loop commands.** `rotate`, `move_dist`, `arc_rad`,
  `arc_cent`, and `increment_closed_loop` are issued with the firmware's
  wait flags and **can HANG** on this chassis if the completion callback never
  arrives. Use `PreciseMover` / `WaypointNav` (continuous move + sensor feedback)
  for reliable precise motion.

---

## Feature coverage & verification

- **Magician Lite arm via DobotLink.** The ergonomic `MagicianLite` API (and
  its `effector` / `sensors` / `io` groups) wraps the arm's `Magician.*`
  DobotLink JSON-RPC surface. DobotLink owns the wire protocol, struct
  packing, and command IDs -- there is no serial transport or wire-level code
  in this library.
- **Full Magician GO API.** The complete DobotLink `MagicianGO.*` surface is
  wrapped by the typed `MagicianGO` class.
- **GO turn direction is unconfirmed.** The GO closed-loop turn direction (yaw
  sign convention) still needs on-hardware confirmation, and the built-in
  closed-loop commands can hang (see **Safety**).

---

## Project layout

```
dobotkit/
├── src/dobotkit/
│   ├── __init__.py          # public exports (MagicianLite, MagicianGO, enums, exceptions)
│   ├── enums.py             # PTPMode, JOGMode, GPIOType, EndEffectorType, ... 
│   ├── exceptions.py        # DobotError hierarchy
│   ├── link.py              # DobotLinkClient (JSON-RPC over websockets) -- shared by arm + GO
│   ├── arm/                 # Magician Lite arm, via DobotLink
│   │   ├── commands/        # ArmCommands: Magician.* RPC wrapper mixins
│   │   ├── groups.py        # IO / Sensor / Effector facades
│   │   └── magicianlite.py  # high-level MagicianLite API
│   └── go/                  # Magician GO stack, via DobotLink
│       ├── geometry.py      # pure helpers (yaw_delta, bearing, clamp_speed)
│       ├── magiciango.py    # high-level MagicianGO wrapper
│       └── navigation.py    # PreciseMover + WaypointNav
├── examples/                # runnable demos:
│                            #   arm — arm_magicianlite
│                            #   GO  — go_teleop, go_waypoint_nav, go_line_trace
├── tests/                   # mirror of src; FakeWebSocket / FakeClient doubles
└── docs/                    # API reference
```

## Public API

```python
from dobotkit import MagicianLite, MagicianGO       # device classes
from dobotkit import (                              # enums
    PTPMode, JOGMode, ContinuousPathMode, GPIOType,
    EndEffectorType, ColorPort, LEDChannel,
)
from dobotkit import (                              # exceptions
    DobotError, DobotConnectionError, DobotTimeoutError,
    DobotProtocolError, DobotAlarmError, DobotLinkError, DobotValueError,
)
from dobotkit.link import DobotLinkClient
from dobotkit.go.navigation import PreciseMover, WaypointNav
```

## License

MIT — see [LICENSE](LICENSE).
