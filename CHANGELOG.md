# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **MagicBox-routed peripheral calls degrade gracefully when the MagicBox is
  absent.** On the Magician Lite, sensors, the external servo, the extended
  (E-)motors and the Seeed RGB LED are reached through the MagicBox. The
  high-level `SensorGroup` / `EffectorGroup` / `IOGroup` facades now catch a
  missing MagicBox, emit a `RuntimeWarning`, and return `None` instead of
  crashing teaching code. Affected:
  `sensors.color/infrared/seeed_distance/seeed_color/seeed_temp/seeed_light/`
  `seeed_rgb`, `effector.set_servo/get_servo`, `io.set_motor/set_motor_steps`
  (read methods now return `Optional[...]`). Arm-native calls (motion, suction
  cup, gripper, laser, base EIO) and `DobotConnectionError` are **not**
  swallowed.

  Verified on real hardware (Magician Lite, no MagicBox, 2026-07-16): the arm
  answers *reads* (color / seeed_* / servo-angle) *without* a timeout but with
  an **empty/short payload**, so the failure surfaces as `struct.error` inside
  the `unpack_*` decoder (the frame is well-formed, so it is not a
  `DobotProtocolError`). `_guard` therefore catches `DobotTimeoutError`,
  `DobotProtocolError`, **and** `struct.error`. Two undetectable cases remain
  (no error to catch, so no warning): the **infrared** sensor returns a
  plausible default (`value=1`), and MagicBox-routed **writes**
  (`set_servo` / `set_motor` / `set_motor_steps` / `seeed_rgb`) are ACKed
  locally, so they return `None` with no physical effect. Both are returned
  as-is and documented rather than silently pretended to work.

### Fixed

- **Protocol command IDs verified against the official Dobot Communication
  Protocol.** Cross-checked all 98 command IDs against the official protocol
  (V1.1.5 PDF from `download.dobot.cc`) and Dobot's SDK `ProtocolID.h` /
  Magician-Lite `cmd_id.h`. 84/98 are now confirmed (73 verified, 11 corrected).
  Corrected genuinely wrong IDs — a rotated CP-command block
  (CP2 / CPLE / CPCommon / CPRHold values were swapped), the CAL/angle-sensor
  block (211–214 → official 140–143), `DeviceWithL` (6 → 3), `GetUserParams`
  (14 → 220), `GetUART4PeripheralsType` (8 → 181) — and removed two duplicate
  members. The 14 remaining `# unverified` IDs are DLL-name-only calls and
  MagicBox/Seeed Grove extensions with no public wire ID.

## [0.1.0] - 2026-06-30

Initial release of `dobotkit` — a complete, pure-Python control library for the
Dobot Magician Lite robotic arm (serial) and the Dobot Magician GO mobile robot
(DobotLink WebSocket). No DLLs, no native binaries: `pip install` and run on
Windows, macOS, or Linux.

### Added

- **Full arm SDK coverage** — all **203/203** official Dobot arm SDK functions
  are mapped 1:1 to a `LowLevelArm` method, proven by
  `tests/arm/test_coverage.py`. The arm speaks the Dobot serial framing
  (`[0xAA 0xAA][len][id][ctrl][params][checksum]`) directly over `pyserial`;
  there is no dependency on `DobotDll`, `DobotRPC`, or any native code.
- **High-level `Magician` API** — ergonomic arm control: `connect`/`disconnect`
  and context-manager teardown, `home`, `move_to`, `move_relative`,
  `pick_and_place`, `set_speed`, pose access, and `.io` / `.sensors` /
  `.effector` / `.lowlevel` groups. Includes pydobot-compatible aliases
  (`suck`, `grip`, `speed`, `wait`, `pose`, `get_eio`, `set_eio`, `move_to`) so
  existing pydobot scripts port with minimal changes. Optional alarm guards on
  motion raise `DobotAlarmError`.
- **Full Magician GO support** — the complete DobotLink `MagicianGO.*` surface
  via a JSON-RPC `DobotLinkClient` over `websockets`, wrapped by a high-level
  `MagicianGO` API: continuous drive (forward/backward/strafe/spin/move),
  closed-loop commands, ultrasonic / IMU / odometer sensors, RGB LEDs, buzzer,
  line-tracing, and camera object/tag detection.
- **GO sensor-feedback navigation** — `PreciseMover` and `WaypointNav` provide
  closed-loop motion built on odometer/IMU feedback with absolute wall-clock
  timeouts and pre-move clearance checks, as a safer alternative to the
  hang-prone built-in closed-loop commands.
- **Golden-oracle struct verification** — every wire structure's packed
  byte-layout is byte-compared against the official `DobotDllType` ctypes
  structs (loaded offline in tests only, never at runtime), guaranteeing the
  little-endian packed encodings match the vendor SDK exactly.
- **Shared foundation** — a `DobotError` exception hierarchy, an `enums` module
  (`PTPMode`, `JOGMode`, `ContinuousPathMode`, `GPIOType`, `EndEffectorType`,
  `ColorPort`, `LEDChannel`), full type hints, and a shipped `py.typed` marker.
- **Lazy device imports** — `import dobotkit` pulls in neither `pyserial` nor
  `websockets`; each device's dependencies load only when that device class is
  first accessed.
- Runnable `examples/` for both devices: arm (pick-and-place, sensors, full API
  tour) and GO (`go_teleop`, `go_waypoint_nav`, `go_line_trace`), plus
  `README.md` and `docs/api/` reference (`arm.md`, `go.md`).

### Known limitations / caveats

- **A few protocol command IDs remain unverified.** Most command IDs are now
  verified against the official Dobot protocol (see *Unreleased → Fixed*), but
  14 remain tagged `# unverified`: DLL-name-only calls with no public wire ID
  (motor-mode, speed-ratio, restart-magic-box, fw-ready) and the MagicBox/Seeed
  Grove sensor extensions. Confirm these on hardware or against MagicBox-specific
  docs before relying on them. (Struct **byte-layouts** are independently
  verified offline against `DobotDllType` by the golden-oracle tests — this
  caveat applies to *command-ID values*, not to packing.)
- **GO built-in closed-loop commands can hang.** The device-side closed-loop
  commands (`rotate`, `move_dist`, `arc_*`, `*_closed_loop`) may block
  indefinitely; prefer `PreciseMover` / `WaypointNav`, which close the loop in
  software with timeouts.
- **GO closed-loop turn direction (yaw sign) needs on-hardware confirmation.**

[Unreleased]: https://example.com/dobotkit/compare/v0.1.0...HEAD
[0.1.0]: https://example.com/dobotkit/releases/tag/v0.1.0
