# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-07-24

### Added

- **`pump_off()` on the arm** — `MagicianLite.pump_off()` (and
  `effector.pump_off()`). Cuts power to the shared air pump (`enable=False` on
  both the suction cup and the gripper) so it stops running and goes quiet.
  `suck(False)` / `grip(False)` only flip the valve to *release* and leave the
  pump running (so a re-grab is instant); `pump_off()` powers it down. It runs
  on the motion queue, so it sequences after any pending `suck`/`grip`.
  `disconnect()` / `with`-block teardown now calls it automatically
  (immediately, bypassing the queue), so the pump never keeps running after a
  program ends.

### Changed (BREAKING)

- **The arm is rewritten on DobotLink; the serial stack is gone.**
  `dobotkit.Magician` (`pyserial`-based) is replaced by
  `dobotkit.arm.magicianlite.MagicianLite` (exported as `dobotkit.MagicianLite`),
  which speaks the arm's `Magician.*` RPC surface through the same DobotLink
  JSON-RPC bridge (`ws://localhost:9090`) already used by the GO. **DobotLink.exe
  is now required to drive the arm** — there is no more direct serial
  connection. `pyserial` is dropped from `dependencies`; `websockets` is now
  the library's only runtime dependency.

  The old serial-only surface is gone entirely: `arm.lowlevel` / `LowLevelArm`,
  `arm/protocol.py`, `arm/ids.py`, `arm/structures/`, `arm/transport.py`,
  `arm/queue.py`, and `arm/alarms.py` no longer exist, and neither does the
  `check_alarms=` motion-call argument. The now-dead serial test
  infrastructure (`tests/conftest.py`'s `oracle` fixture/`_load_oracle` helper
  and the `FakeSerial` double, plus the tests that exercised them) is removed.

  `MagicianLite`'s high-level surface keeps the same shape as before:
  `connect`/`disconnect`, context-manager teardown, `home`, `move_to`,
  `move_relative`, `pick_and_place`, `set_speed`, `get_pose`, `suck`, `grip`,
  and the `effector` / `sensors` / `io` device groups (see `groups.py`).

- **MagicBox-routed peripheral calls degrade gracefully when the MagicBox is
  absent.** `sensors.adc/di/color/infrared/distance/temp/light/rgb` and
  `io.get_di`/`io.get_adc` catch a missing MagicBox (or its attached sensor)
  answering with `DobotTimeoutError` / `DobotProtocolError`, emit a
  `RuntimeWarning`, and return `None` instead of crashing teaching code.
  Arm-native calls (motion, `effector.suck`/`grip`/`servo`,
  `io.set_do`/`set_pwm`/`set_multiplexing`) and a genuine
  `DobotConnectionError` are **not** swallowed.

- **The Magician GO stack is trimmed to a clean core and now reads its MagicBox
  peripherals.** `MagicianGO` keeps continuous drive (`move`/`forward`/
  `backward`/`strafe`/`spin`/`stop`/`drive_for`/`emergency_stop`),
  `clearance_ok`, native sensors (`ultrasonic`/`ultrasonic_raw`/`odometer`/
  `set_odometer`/`battery`/`imu_angle`), `rgb`/`buzzer`, alarms/state
  (`get_alarm_info`/`clean_alarm_info`/`stall_protection`/`off_ground`), and
  `magic_box_mode`/`magic_box_num`. **New:** `go.sensors`
  (`GoSensorGroup`) and `go.io` (`GoIOGroup`) read the GO's MagicBox on the
  DobotLink `MagicBox.*` namespace over the *same* `MagicianGO` connection —
  ADC/DI/DO/PWM address an **EIO pin (1..26)**, color/infrared/Seeed address a
  **Grove connector (1..6)** — and every `go.sensors` read degrades to `None` +
  a `RuntimeWarning` when the MagicBox/sensor is absent (hardware-verified
  2026-07-16: the teaching-kit potentiometer on Grove connector 4 reads on EIO
  pin 22 via `go.sensors.adc(22)`).

  Removed (BREAKING): all firmware closed-loop / queued motion
  (`rotate`/`move_dist`/`arc_rad`/`arc_cent`/`coord_closed_loop`/
  `increment_closed_loop` and their `unsafe_` variants, `unsafe_move_pos`,
  `move_speed_time`, `set_origin_point`, `move_direct`, `set_running_mode`);
  line-tracing (`auto_trace`/`trace_speed`/`trace_pid`/`trace_angle`/
  `line_error`/`firmware_trace_angle`/`set_trace_line_info`); cameras
  (`car_camera_*`/`arm_camera_*`/`camera_calibration_data`); firmware
  command-queue internals; MagicBox stop-point RPCs; device-management RPCs
  (`product_name`, fw versions, `device_id`, name/SN, `device_time`,
  `device_reboot`, `heartbeat`); `set_running_state`; `set_light_prompt`;
  `imu_speed`; `get_move_speed`; `get_running_mode`. The `WaypointNav`
  navigation class is removed — `PreciseMover` (continuous move + odometer/IMU
  feedback) remains for precise motion. `MagicianGO.__exit__` teardown is
  simplified to `emergency_stop` + a confirming `stop` (+ socket close when it
  owns the client). Examples `go_line_trace.py`/`go_waypoint_nav.py` are
  removed; `go_magicbox_sensor.py` is added.

### Fixed

- **The suction cup and gripper now actually actuate.** The DobotLink parameter
  for pump power is `enable` (bool), not the Dobot SDK's `enableCtrl` — DobotLink
  silently ignores the unknown key (the RPC returns success but the pump never
  powers), so `suck`/`grip` did nothing on hardware. `set_suction_cup` /
  `set_gripper` now send `enable`, so `arm.suck(True)` / `arm.grip(True)` grip as
  expected (the `on` state key was already correct). Verified live via the
  `GetEndEffectorSuctionCup` / `GetEndEffectorGripper` readback
  (`enable=True, on=True → {isEnabled: True, isOn: True}`). The FakeClient unit
  tests only asserted the *sent* params, so they could not catch a key that
  DobotLink does not accept.
- **`home()` always queues `SetHOMEParams`/`SetHOMECmd`.** Previously
  `queued=wait` meant `wait=False` sent them unqueued, which could desync the
  on-device queue index; `wait` now only controls whether `home()` blocks
  until the queue catches up, matching `move_to`'s always-queued behavior.
- **Motion blocks on DobotLink's `isWaitForFinish`, not client-side polling.**
  `move_to` / `move_relative` / `home` / `pick_and_place` with `wait=True` send
  `isWaitForFinish=true` (with a generous per-call timeout) so DobotLink blocks
  until the move physically completes — matching DobotLab. This replaced an
  unreliable queued-command-index poll that returned before the move finished,
  which let moves overlap and made DobotLink report `action timeout` (verified
  on hardware). `pick_and_place` now runs its eight steps sequentially this way.
- **Context-manager teardown (`__exit__`) no longer lets a `disconnect()`
  failure escape.** Both `queue_stop()` and `disconnect()` are now
  independently best-effort during teardown, so neither can mask the `with`
  body's original exception.
- **`DobotTimeoutError` messages are device-neutral.** They used to say "GO
  power/wireless link may be down" even when raised for the arm; the shared
  `DobotLinkClient` now says the device may be unresponsive or DobotLink lost
  the link.

### Known limitations

- **A controller alarm silently blocks arm motion.** If the Magician Lite
  controller has an active alarm (`GetAlarmsState` non-zero — observed as a
  recurring `byte12` fault on the test unit), DobotLink accepts motion commands
  (returns success) but the arm does not move; sensors / IO / effector still
  work. The alarm is **not reliably clearable in software** (issuing
  `ClearAllAlarmsState` was observed to *trigger* it on the test unit), so the
  library does not call it automatically. **Power-cycle the arm to clear it.**
  Motion is reliable once the controller is alarm-free and targets stay within
  the workspace (a target that drives a joint near its travel limit can fault).

- **A GO left powered on for a long time drops its wireless link.**
  `ConnectDobot` then returns a *false success* (`{firmwareName: "Dobot",
  firmwareVersion: "", productName: ""}` — the empty version/name is the tell)
  and every subsequent read times out. `MagicianGO.open`/`connect`'s built-in
  battery read-back surfaces this immediately. **Power-cycle the car to
  recover.**

## [0.1.1] - 2026-07-19

### Removed

- **`MagicianGO.running_state()` (`GetRunningState`).** The GO firmware never
  answers this call — a reproducible ~10 s `DobotTimeoutError` on the test unit
  — while every neighbouring read (`battery`, `ultrasonic`, `imu_angle`,
  `odometer`, `off_ground`, `stall_protection`, `magic_box_mode`/`num`,
  `get_alarm_info`) works. A method that only ever hangs has no place in the
  clean core, so it was dropped (hardware-verified 2026-07-19). Use
  `get_alarm_info()` / `stall_protection()` / `off_ground()` for GO status.

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

- **A few protocol command IDs remain unverified.** 14 remain tagged
  `# unverified`: DLL-name-only calls with no public wire ID
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

[0.2.0]: https://example.com/dobotkit/compare/v0.1.1...v0.2.0
[0.1.1]: https://example.com/dobotkit/compare/v0.1.0...v0.1.1
[0.1.0]: https://example.com/dobotkit/releases/tag/v0.1.0
