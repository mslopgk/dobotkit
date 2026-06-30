# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

- **Unverified protocol command IDs.** The arm protocol command IDs were
  reconstructed from `pydobot` seed values, `DobotDllType` struct layouts, and
  the documented categorical numbering scheme. IDs that are *not* confirmed by
  the `pydobot` seed are tagged `# unverified` in the source and should be
  confirmed against firmware / official Dobot protocol documentation or on
  hardware. (The struct **byte-layouts** are independently verified offline
  against `DobotDllType` by the golden-oracle tests — the `# unverified` caveat
  applies to *command-ID values*, not to packing.)
- **GO built-in closed-loop commands can hang.** The device-side closed-loop
  commands (`rotate`, `move_dist`, `arc_*`, `*_closed_loop`) may block
  indefinitely; prefer `PreciseMover` / `WaypointNav`, which close the loop in
  software with timeouts.
- **GO closed-loop turn direction (yaw sign) needs on-hardware confirmation.**

[Unreleased]: https://example.com/dobotkit/compare/v0.1.0...HEAD
[0.1.0]: https://example.com/dobotkit/releases/tag/v0.1.0
