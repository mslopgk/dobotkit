# dobotkit GUI

A Tkinter control panel for the Dobot **Magician** arm and the **Magician GO**
car, built entirely on the `dobotkit` public API and the Python standard-library
`tkinter`/`tkinter.ttk` (no extra pip dependencies).

The window is a tabbed notebook — one tab for the arm, one for the GO, and one
combined log — with a status bar along the bottom and a background telemetry
loop that keeps the live read-outs ticking.

## Launching

### Real hardware

```bash
python -m dobotkit.gui
```

Optional flags let you pre-set the connection defaults the panels use:

| Flag | Default | Meaning |
| --- | --- | --- |
| `--arm-port` | `auto` | Serial port for the arm (e.g. `COM3`, `/dev/ttyUSB0`). `auto` picks the first discovered port. |
| `--go-port` | `COM5` | DobotLink COM port name for the GO. |
| `--dobotlink-host` | `localhost` | DobotLink WebSocket host. |
| `--dobotlink-port` | `9090` | DobotLink WebSocket port. |

The window opens **disconnected**. Use each tab's **Connect** button to open the
link when you are ready. The GO additionally requires the **DobotLink** desktop
service to be running (Python talks to DobotLink over a WebSocket, and DobotLink
relays to the car).

```bash
python -m dobotkit.gui --arm-port COM3 --go-port COM5
```

### Demo mode (no hardware)

```bash
python -m dobotkit.gui --demo
```

`--demo` injects in-memory fake devices, so the whole UI comes up **live** with
nothing plugged in — the arm pose drifts as you move/jog it, and the GO's
ultrasonic/odometer/battery read-outs change over time. Great for trying the
interface, screenshots, or teaching, and it never touches a serial port or
DobotLink. In demo mode both tabs auto-connect on launch.

## The tabs

- **Arm** — full Magician control surface: connection (port picker + a big red
  **EMERGENCY STOP**), a live pose grid (X/Y/Z/R and J1–J4), absolute and
  relative moves with a PTP-mode selector, velocity/acceleration sliders, a
  confirmed **Home**, press-and-hold **JOG** buttons (Cartesian or joint frame),
  the end effector (suction / gripper / laser / servo), digital & analog **IO**,
  the **sensors** (color / infrared / Seeed distance / temp / light), and a live
  **alarm** list with a Clear button.
- **GO** — full Magician GO control surface: connection (host / port / port-name
  + an armed **EMERGENCY STOP**), a directional press-and-hold **drive** pad with
  a speed slider and clearance check, a **live telemetry** grid (ultrasonic,
  odometer, IMU, battery), RGB LED + buzzer **output**, **line-trace** with PID,
  **navigation** (set-start, go-to waypoint, precise-forward), and a **camera**
  read-out.
- **Log** — a scrolling, timestamped record of every action and its result. Each
  control on the other two tabs logs the call it makes and the outcome here, so
  you can see exactly what was sent to the device.

The status bar shows the connection state of each device.

## System requirement: Tk

The GUI uses `tkinter`, which needs the Tk runtime present:

- **Windows / macOS** — the official python.org installers bundle Tk; nothing
  extra to install.
- **Linux** — Tk is usually a separate package. On Debian/Ubuntu:
  `sudo apt install python3-tk`. You also need a graphical session (an X/Wayland
  display). Running with no display prints a clear message and exits cleanly
  rather than crashing.

## Safety notes

- **EMERGENCY STOP is always available while connected.** On the arm it stops
  any jog motion and drops the connection; on the GO it fires a non-blocking
  stop that halts the car even if the link is degraded. Reach for it first if
  anything looks wrong.
- **Start slow.** Bring the velocity/acceleration sliders (arm) and the speed
  slider (GO) down before your first moves, then raise them once you trust the
  motion. Keep the workspace clear.
- **Check clearance before driving the GO.** Use the **Check clearance** button;
  the navigation primitives also verify ultrasonic clearance in the intended
  direction before each motion and abort if blocked.
- **Home carefully.** The arm's **Home** button asks for confirmation because
  the arm sweeps to its home pose — make sure the area around it is clear first.
- Some of the GO's built-in closed-loop commands can hang on this chassis, so
  the panel drives via continuous velocity + sensor feedback (the `PreciseMover`
  / `WaypointNav` primitives) for reliable precise motion.
