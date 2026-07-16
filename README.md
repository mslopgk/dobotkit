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
- **Magician GO over DobotLink** — a clean `MagicianGO` core: continuous drive
  (forward/strafe/spin + bounded `drive_for`), ultrasonic/IMU/odometer/battery
  sensors, RGB LEDs, buzzer, alarms, and `PreciseMover` sensor-feedback motion
  (drive an exact distance / turn an exact angle). Its **MagicBox** peripherals
  read through `go.sensors` / `go.io` (ADC/DI by EIO pin, color/infrared/Seeed
  by Grove connector) on the same connection.
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

```bash
pip install dobotkit
```

For development (editable install with the test/lint toolchain):

```bash
git clone https://github.com/mslopgk/dobotkit
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

`wait=True` sends `isWaitForFinish=true`, so DobotLink blocks until the move
physically completes before returning (raising `DobotTimeoutError` only if the
per-call deadline elapses). Keep targets inside the workspace — a target that
drives a joint near its travel limit can fault.

> **If the arm accepts commands but does not move**, its controller has an
> active alarm (motion is silently blocked while sensors/IO/effector still
> work). This is not reliably clearable from software — **power-cycle the arm**
> to clear it, then reconnect.

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
from dobotkit.go.navigation import PreciseMover

# open() connects DobotLink + verifies the GO link with a battery read-back,
# and (as a context manager) stops the car + closes the socket on every exit.
with MagicianGO.open(port_name="COM5") as go:
    try:
        # Continuous velocity control is reliable: check clearance, then drive.
        ok, info = go.clearance_ok(x=1, threshold=20)
        if ok:
            go.drive_for(x=20, seconds=1.0)   # bounded forward pulse, auto-stops
    finally:
        go.emergency_stop()  # fire-and-forget safety stop (never blocks)

    # For precise motion use the sensor-feedback layer (continuous move + IMU/
    # odometer feedback) — drive an exact distance or turn an exact angle.
    mover = PreciseMover(go)
    mover.goto_distance(300, speed=20)   # ~300 mm forward, then stop
    mover.turn_degrees(90, speed=20)     # +90 deg (CCW), IMU-closed-loop

    # MagicBox peripherals ride the same connection (guarded -> None if absent):
    knob = go.sensors.adc(22)            # potentiometer on EIO pin 22 (0..4095)
    print("knob:", knob)
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
- **Timeouts everywhere.** The `PreciseMover` control loops use absolute
  wall-clock timeouts (`time.monotonic`) so they can never spin forever, and
  every path ends in `emergency_stop`.
- **Always stop.** Wrap motion in `try/finally` ending in `go.emergency_stop()`
  (a non-blocking notify, safe from a `finally` block or interrupt path even if
  the link is degraded); the `MagicianGO` context manager also stops on exit.
- **Precise motion = continuous move + feedback.** For exact distances/turns use
  `PreciseMover` (continuous `move()` sampled against the odometer/IMU). The
  firmware's own built-in closed-loop commands were removed from this library
  because they can hang indefinitely on this chassis.

---

## Feature coverage & verification

- **Magician Lite arm via DobotLink.** The ergonomic `MagicianLite` API (and
  its `effector` / `sensors` / `io` groups) wraps the arm's `Magician.*`
  DobotLink JSON-RPC surface. DobotLink owns the wire protocol, struct
  packing, and command IDs -- there is no serial transport or wire-level code
  in this library.
- **Magician GO core, hardware-verified.** The typed `MagicianGO` class wraps a
  clean, generally-used slice of the `MagicianGO.*` surface (drive, native
  sensors, RGB/buzzer, alarms) plus `PreciseMover` feedback motion. Turn
  direction is confirmed: `r+` = CCW (`PreciseMover.turn_degrees(+90)` verified).
- **GO MagicBox peripherals, hardware-verified (2026-07-16).** `go.sensors` /
  `go.io` read the GO's MagicBox on the `MagicBox.*` namespace over the same
  connection. ADC/DI/DO/PWM address an **EIO pin (1..26)**; color/infrared/Seeed
  address a **Grove connector (1..6)**. Reads degrade to `None` + a warning when
  the MagicBox or sensor is absent. (Verified: potentiometer on Grove 4 = EIO 22.)

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
│       ├── groups.py        # MagicBox sensor/IO facades (go.sensors / go.io)
│       ├── magiciango.py    # high-level MagicianGO wrapper
│       └── navigation.py    # PreciseMover (sensor-feedback motion)
├── examples/                # runnable demos:
│                            #   arm — arm_magicianlite
│                            #   GO  — go_discover, go_teleop, go_magicbox_sensor
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
from dobotkit.go.navigation import PreciseMover, NavigationAborted
```

## License

MIT — see [LICENSE](LICENSE).
