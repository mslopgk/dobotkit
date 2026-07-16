# dobotkit

Complete, pure-Python control for the **Dobot Magician Lite** robotic arm and the
**Dobot Magician GO** mobile robot — one library, no DLLs, no native binaries.

`dobotkit` re-implements the full Dobot SDK surface in clean, type-hinted Python.
It speaks the arm's serial protocol over `pyserial` and the GO's DobotLink
JSON-RPC bridge over `websockets`, so the same code runs on Windows, macOS, and
Linux with nothing more than `pip install`.

```python
import dobotkit

with dobotkit.Magician(port="COM3") as arm:
    arm.home()
    arm.move_to(220, 0, 40, wait=True)
    arm.suck(True)
```

---

## Features

- **Full arm coverage** — all **203/203** official Dobot arm SDK functions are
  mapped to a low-level method (proven by `tests/arm/test_coverage.py`), wrapped
  by an ergonomic high-level `Magician` API (home, move, pick-and-place, IO,
  sensors, end-effectors).
- **Full Magician GO coverage** — the complete DobotLink `MagicianGO.*` surface:
  continuous drive, closed-loop commands, ultrasonic/IMU/odometer sensors, RGB
  LEDs, buzzer, line-tracing, and camera object/tag detection.
- **Pure Python** — only `pyserial` and `websockets` at runtime. No DLL, no
  vendored native code, no DobotDll/DobotRPC dependency. Cross-platform and
  `pip`-installable.
- **Fully type-hinted** — every public symbol is typed and the package ships
  `py.typed`, so editors and `mypy` see real types.
- **Safety-first** — context-manager teardown, optional alarm guards on the arm,
  and a sensor-feedback navigation layer for the GO with absolute wall-clock
  timeouts and pre-move clearance checks.
- **Lazy device imports** — `import dobotkit` never pulls in `pyserial` or
  `websockets`; a program that drives only the arm never pays for the GO's
  WebSocket stack, and vice-versa.
- **pydobot-compatible aliases** — `suck`, `grip`, `speed`, `wait`, `pose`,
  `get_eio`, `set_eio`, and `move_to` mirror `pydobot.Dobot`, so existing
  scripts port with minimal changes.

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

Requires **Python ≥ 3.9**. Runtime dependencies (`pyserial`, `websockets`) are
installed automatically.

한국어 문서: [빠른 시작 quickstart-ko](docs/quickstart-ko.md) ·
[GO API 치트시트](docs/cheatsheet_go.md) (LLM 프롬프트/RAG 접지용 1장 요약)

---

## Quickstart — Magician Lite (arm)

The arm talks over a serial port. Open a `Magician` as a context manager so the
on-device command queue is stopped and the port is closed on every exit path,
including exceptions.

```python
import dobotkit
from dobotkit import PTPMode

# port="auto" picks the first detected serial port; pass "COM3" / "/dev/ttyUSB0"
# to be explicit.
with dobotkit.Magician(port="COM3") as arm:
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
    print(f"final pose: x={pose.x:.1f} y={pose.y:.1f} z={pose.z:.1f}")
```

Pass `check_alarms=True` to a motion call to read the alarm bitmap first and
raise `DobotAlarmError` (carrying `.codes`) instead of driving into a faulted
state.

### MagicBox peripherals (sensors, servo, motors)

Sensors, the external servo, the extended (E-)motors, and the Seeed RGB LED are
reached through the **MagicBox**. If it (or its device) is not connected, the
arm returns no response and these high-level calls **warn and return `None`**
rather than raising — so teaching code keeps running:

```python
reading = arm.sensors.color(port=0)   # RuntimeWarning + None if no MagicBox
if reading is None:
    print("색 센서를 읽지 못했습니다 — 매직박스/센서 연결 확인")
else:
    print(reading)
```

This covers `sensors.*`, `effector.set_servo` / `get_servo`, and
`io.set_motor` / `set_motor_steps`. Arm-native operations (motion, suction cup,
gripper, laser, base digital/analog IO) are unaffected and still raise on error,
as does a genuine connection error (`DobotConnectionError`, e.g. the port was
never opened).

On real hardware (verified 2026-07-16) a missing MagicBox does not time out —
the arm replies with an empty payload, so decoding fails and the facade returns
`None`. Two cases can't be detected (no error is raised), so they warn nothing:

- the **infrared** sensor returns a plausible default (`value=1`), so
  `sensors.infrared(...)` can't tell "no MagicBox" from a real reading;
- MagicBox-routed **writes** (`effector.set_servo`, `io.set_motor` /
  `set_motor_steps`, `sensors.seeed_rgb`) are ACKed by the controller and
  return `None` with **no physical effect** — the servo/motor/LED simply does
  not move.

Treat both as suspect until the MagicBox and its device are confirmed connected.

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

- **Power-on home.** Always `home()` after powering on (and after any
  emergency-stop or alarm) so that absolute coordinates are trustworthy before
  issuing `move_to` / `pick_and_place`.
- **Clearance checks.** Verify the workspace is clear of obstacles, fingers, and
  fixtures along the planned path before commanding a move. Start with the
  illustrative coordinates lowered/slowed and tune to *your* setup.
- **Alarm guard.** Pass `check_alarms=True` to motion calls; on a collision or
  limit fault `DobotAlarmError` is raised with the active `.codes`.
- **Always disconnect.** Use the `Magician` context manager (`with ... as arm:`)
  so the command queue is stopped and the serial port is released on every exit
  path — including exceptions.

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

`dobotkit` aims to cover the **entire** Dobot SDK surface, and the claim is
test-enforced — but read the verification status honestly before relying on any
exact command value against hardware.

- **Full arm SDK coverage: 203/203.** Every official Dobot arm SDK function
  (213 total minus 10 pure DLL-plumbing helpers) maps to a `LowLevelArm` method.
  `tests/arm/test_coverage.py` enumerates the SDK functions and fails if any is
  unmapped — this is the proof of "all features," not a marketing number.
- **Full Magician GO API.** The complete DobotLink `MagicianGO.*` surface is
  wrapped by the typed `MagicianGO` class.
- **Struct byte-layouts are oracle-verified (offline).** Every wire structure's
  packed byte layout is byte-compared against `ctypes` structures from Dobot's
  `DobotDllType` in golden-oracle tests (the oracle is loaded offline, never as a
  runtime dependency, and never requires the DLL). So the *shape and packing* of
  each payload is verified.
- **Command IDs: 84 of 98 verified against the official protocol.** Protocol
  command IDs were cross-checked against the **official Dobot Communication
  Protocol** (V1.1.5 PDF from `download.dobot.cc`) and Dobot's SDK
  `ProtocolID.h` / Magician-Lite `cmd_id.h`. 84/98 IDs are now confirmed
  (73 verified as published, 11 corrected to match the official sources —
  including a genuinely wrong CP-command block and the CAL/angle-sensor block).
  The remaining **14 are tagged `# unverified`**: DLL-name-only calls with no
  public wire ID (motor-mode, speed-ratio, restart-magic-box, fw-ready) and the
  MagicBox/Seeed Grove sensor extensions, which are not in the public protocol
  and need on-hardware or MagicBox-doc confirmation.
- **GO turn direction is unconfirmed.** The GO closed-loop turn direction (yaw
  sign convention) still needs on-hardware confirmation, and the built-in
  closed-loop commands can hang (see **Safety**).

In short: the **coverage is complete**, the **struct layouts are verified
offline**, and **most command IDs are now verified against the official Dobot
protocol**; the few parts that still want hardware confirmation are explicitly
tagged `# unverified` in the code so you know exactly what to check.

---

## Project layout

```
dobotkit/
├── src/dobotkit/
│   ├── __init__.py          # public exports (Magician, MagicianGO, enums, exceptions)
│   ├── enums.py             # PTPMode, JOGMode, GPIOType, EndEffectorType, ... 
│   ├── exceptions.py        # DobotError hierarchy
│   ├── arm/                 # serial arm stack
│   │   ├── protocol.py      # frame + checksum
│   │   ├── ids.py           # protocol command IDs
│   │   ├── structures/      # pack_*/unpack_* wire payloads
│   │   ├── transport.py     # pyserial transport
│   │   ├── queue.py         # on-device command queue + wait helper
│   │   ├── lowlevel/        # LowLevelArm — every SDK function 1:1
│   │   ├── alarms.py        # alarm bitmap decode
│   │   ├── groups.py        # IO / Sensor / Effector facades
│   │   └── magician.py      # high-level Magician API
│   └── go/                  # Magician GO stack (DobotLink WebSocket)
│       ├── geometry.py      # pure helpers (yaw_delta, bearing, clamp_speed)
│       ├── client.py        # DobotLinkClient (JSON-RPC over websockets)
│       ├── magiciango.py    # high-level MagicianGO wrapper
│       └── navigation.py    # PreciseMover + WaypointNav
├── examples/                # runnable demos:
│                            #   arm — pick-and-place, sensors, full API tour
│                            #   GO  — go_teleop, go_waypoint_nav, go_line_trace
├── tests/                   # mirror of src; FakeSerial / FakeWebSocket / oracle
└── docs/                    # API reference
```

## Public API

```python
from dobotkit import Magician, MagicianGO          # device classes
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
