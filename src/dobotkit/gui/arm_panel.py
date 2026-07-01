"""The full Dobot Magician arm control panel (:class:`ArmPanel`).

:class:`ArmPanel` is a single :class:`ttk.Frame` that surfaces the *entire* arm
feature set as labelled :class:`~dobotkit.gui.widgets.SectionFrame` blocks and
wires every control to a :class:`~dobotkit.gui.arm_controller.ArmController`.
Nothing here talks to the serial port directly -- each widget callback calls
exactly one controller action, and the ``(ok, message)`` result is written to the
injected ``log`` callable so the surrounding app's log view records the call and
its outcome.

Layout (top-to-bottom):

* **Connection** -- port combobox (populated from
  :meth:`ArmController.available_ports`), Refresh / Connect / Disconnect, a live
  device-info line, and a big red **EMERGENCY STOP** that both stops motion (via
  :meth:`ArmController.jog_stop`) and disconnects the arm.
* **Live Pose** -- a :class:`~dobotkit.gui.widgets.ValueGrid` of x/y/z/r and
  j1..j4, refreshed from :meth:`refresh`.
* **Motion** -- absolute move entries (x/y/z/r) + a :class:`ttk.Combobox` of
  :class:`~dobotkit.enums.PTPMode`, relative-move entries (dx/dy/dz/dr),
  velocity / acceleration sliders driving :meth:`ArmController.set_speed`, and a
  confirmed **Home** button.
* **JOG** -- press-and-hold :class:`~dobotkit.gui.widgets.JogButton` pairs for
  X/Y/Z/R with a Cartesian / joint frame toggle, driving
  :meth:`ArmController.jog_start` / :meth:`ArmController.jog_stop`.
* **End effector** -- suction on/off, gripper open/close, laser on/off, and a
  servo id + angle setter.
* **IO** -- digital-output set, digital-input read, ADC read, PWM set.
* **Sensors** -- color / infrared / Seeed distance / temperature / light reads.
* **Alarms** -- a live alarm list (from the snapshot) + a Clear Alarms button.

Import safety
-------------
Importing this module only *defines* :class:`ArmPanel`; it constructs no
``Tk()`` root and opens no window. A panel is instantiated only when the app
actually builds its window and passes a live ``parent`` widget. This keeps the
module importable headless (CI / no-display test runners).
"""
from __future__ import annotations

import tkinter as tk
from functools import partial
from tkinter import messagebox, ttk
from typing import Any, Callable, Dict, List, Optional

from dobotkit.enums import PTPMode
from dobotkit.gui.arm_controller import ActionResult, ArmController
from dobotkit.gui.widgets import JogButton, SectionFrame, ValueGrid

__all__ = ["ArmPanel"]

# The value-grid fields shown in the Live Pose section, key -> caption.
_POSE_FIELDS: Dict[str, str] = {
    "x": "X (mm)",
    "y": "Y (mm)",
    "z": "Z (mm)",
    "r": "R (deg)",
    "j1": "J1 (deg)",
    "j2": "J2 (deg)",
    "j3": "J3 (deg)",
    "j4": "J4 (deg)",
}

# JOG axis rows: (label, controller axis index). Axis 1..4 == X/Y/Z/R (Cartesian)
# or J1..J4 (joint) -- the frame is selected by the joint-mode toggle.
_JOG_AXES = [("X / J1", 1), ("Y / J2", 2), ("Z / J3", 3), ("R / J4", 4)]


class ArmPanel(ttk.Frame):
    """Full arm control surface bound to an :class:`ArmController`.

    Args:
        parent: The master widget (a live Tk widget). Building a panel requires a
            real master -- this is only done when the app launches, never at
            import time.
        controller: The logic-layer adapter every control drives.
        log: A sink for one human-readable line per action, e.g. the app's log
            view's ``log`` method. Called as ``log(str)``.
    """

    def __init__(
        self,
        parent: tk.Misc,
        controller: ArmController,
        log: Callable[[str], Any],
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, **kwargs)
        self.controller = controller
        self._log = log

        # Widgets that must be disabled while disconnected; populated as the
        # sections are built. Every entry is a widget whose "state" we toggle.
        self._motion_widgets: List[tk.Widget] = []

        # Tk variables (created against this frame, so no global root is needed).
        self._port_var = tk.StringVar(master=self)
        self._info_var = tk.StringVar(master=self, value="Device: -")
        self._joint_mode_var = tk.BooleanVar(master=self, value=False)

        self._abs_vars: Dict[str, tk.StringVar] = {
            k: tk.StringVar(master=self, value="0") for k in ("x", "y", "z", "r")
        }
        self._ptp_mode_var = tk.StringVar(master=self, value=PTPMode.MOVL_XYZ.name)
        self._rel_vars: Dict[str, tk.StringVar] = {
            k: tk.StringVar(master=self, value="0") for k in ("dx", "dy", "dz", "dr")
        }
        self._vel_var = tk.DoubleVar(master=self, value=100.0)
        self._acc_var = tk.DoubleVar(master=self, value=100.0)

        self._servo_id_var = tk.StringVar(master=self, value="0")
        self._servo_angle_var = tk.StringVar(master=self, value="0")

        self._do_addr_var = tk.StringVar(master=self, value="1")
        self._do_level_var = tk.StringVar(master=self, value="1")
        self._di_addr_var = tk.StringVar(master=self, value="1")
        self._adc_addr_var = tk.StringVar(master=self, value="1")
        self._pwm_addr_var = tk.StringVar(master=self, value="1")
        self._pwm_freq_var = tk.StringVar(master=self, value="1000")
        self._pwm_duty_var = tk.StringVar(master=self, value="50")
        self._io_result_var = tk.StringVar(master=self, value="-")

        self._sensor_port_var = tk.StringVar(master=self, value="0")
        self._sensor_result_var = tk.StringVar(master=self, value="-")

        # Build sections top-to-bottom.
        self.columnconfigure(0, weight=1)
        builders = (
            self._build_connection,
            self._build_pose,
            self._build_motion,
            self._build_jog,
            self._build_effector,
            self._build_io,
            self._build_sensors,
            self._build_alarms,
        )
        for row, build in enumerate(builders):
            build(row)

        # Reflect the controller's starting state (typically disconnected).
        self._populate_ports()
        self._set_connected_state(self.controller.is_connected)

    # ------------------------------------------------------------------ #
    # section builders
    # ------------------------------------------------------------------ #
    def _build_connection(self, grid_row: int) -> None:
        sec = SectionFrame(self, "Connection")
        sec.grid(row=grid_row, column=0, sticky="ew", padx=6, pady=4)
        sec.columnconfigure(1, weight=1)

        ttk.Label(sec, text="Port").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self._port_combo = ttk.Combobox(
            sec, textvariable=self._port_var, state="readonly", width=18
        )
        self._port_combo.grid(row=0, column=1, sticky="ew")

        btns = ttk.Frame(sec)
        btns.grid(row=0, column=2, sticky="e", padx=(6, 0))
        ttk.Button(btns, text="Refresh", command=self._populate_ports).grid(
            row=0, column=0, padx=2
        )
        self._connect_btn = ttk.Button(btns, text="Connect", command=self._on_connect)
        self._connect_btn.grid(row=0, column=1, padx=2)
        self._disconnect_btn = ttk.Button(
            btns, text="Disconnect", command=self._on_disconnect
        )
        self._disconnect_btn.grid(row=0, column=2, padx=2)

        ttk.Label(sec, textvariable=self._info_var).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(6, 4)
        )

        # Big red EMERGENCY STOP -- always enabled, even while disconnected.
        style = ttk.Style(self)
        try:
            style.configure(
                "Emergency.TButton", foreground="white", background="red"
            )
        except tk.TclError:
            # Some themes reject background overrides; the button still works.
            pass
        self._estop_btn = ttk.Button(
            sec,
            text="EMERGENCY STOP",
            style="Emergency.TButton",
            command=self._on_emergency_stop,
        )
        self._estop_btn.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(2, 0))

    def _build_pose(self, grid_row: int) -> None:
        sec = SectionFrame(self, "Live Pose")
        sec.grid(row=grid_row, column=0, sticky="ew", padx=6, pady=4)
        self._pose_grid = ValueGrid(sec, _POSE_FIELDS, columns=4, caption_width=10)
        self._pose_grid.grid(row=0, column=0, sticky="w")

    def _build_motion(self, grid_row: int) -> None:
        sec = SectionFrame(self, "Motion")
        sec.grid(row=grid_row, column=0, sticky="ew", padx=6, pady=4)

        # -- absolute move ------------------------------------------------- #
        abs_frame = ttk.Frame(sec)
        abs_frame.grid(row=0, column=0, sticky="w", pady=2)
        for i, key in enumerate(("x", "y", "z", "r")):
            ttk.Label(abs_frame, text=key.upper()).grid(
                row=0, column=2 * i, sticky="e", padx=(6, 2)
            )
            e = ttk.Entry(abs_frame, textvariable=self._abs_vars[key], width=7)
            e.grid(row=0, column=2 * i + 1, sticky="w")
            self._motion_widgets.append(e)
        ttk.Label(abs_frame, text="Mode").grid(row=0, column=8, padx=(8, 2))
        mode_combo = ttk.Combobox(
            abs_frame,
            textvariable=self._ptp_mode_var,
            state="readonly",
            width=16,
            values=[m.name for m in PTPMode],
        )
        mode_combo.grid(row=0, column=9, padx=(0, 6))
        self._motion_widgets.append(mode_combo)
        move_btn = ttk.Button(
            abs_frame, text="Move (wait)", command=self._on_move_to
        )
        move_btn.grid(row=0, column=10, padx=6)
        self._motion_widgets.append(move_btn)

        # -- relative move ------------------------------------------------- #
        rel_frame = ttk.Frame(sec)
        rel_frame.grid(row=1, column=0, sticky="w", pady=2)
        for i, key in enumerate(("dx", "dy", "dz", "dr")):
            ttk.Label(rel_frame, text=key).grid(
                row=0, column=2 * i, sticky="e", padx=(6, 2)
            )
            e = ttk.Entry(rel_frame, textvariable=self._rel_vars[key], width=7)
            e.grid(row=0, column=2 * i + 1, sticky="w")
            self._motion_widgets.append(e)
        rel_btn = ttk.Button(
            rel_frame, text="Move relative", command=self._on_move_relative
        )
        rel_btn.grid(row=0, column=8, padx=6)
        self._motion_widgets.append(rel_btn)

        # -- speed / accel sliders ---------------------------------------- #
        speed_frame = ttk.Frame(sec)
        speed_frame.grid(row=2, column=0, sticky="ew", pady=2)
        speed_frame.columnconfigure(1, weight=1)
        speed_frame.columnconfigure(3, weight=1)
        ttk.Label(speed_frame, text="Velocity").grid(row=0, column=0, padx=(6, 2))
        vel = ttk.Scale(
            speed_frame,
            from_=1,
            to=200,
            variable=self._vel_var,
            command=lambda _v: self._on_set_speed(),
        )
        vel.grid(row=0, column=1, sticky="ew", padx=2)
        self._motion_widgets.append(vel)
        ttk.Label(speed_frame, text="Accel").grid(row=0, column=2, padx=(6, 2))
        acc = ttk.Scale(
            speed_frame,
            from_=1,
            to=200,
            variable=self._acc_var,
            command=lambda _v: self._on_set_speed(),
        )
        acc.grid(row=0, column=3, sticky="ew", padx=2)
        self._motion_widgets.append(acc)

        # -- home (confirmed) --------------------------------------------- #
        home_btn = ttk.Button(sec, text="Home", command=self._on_home)
        home_btn.grid(row=3, column=0, sticky="w", padx=6, pady=(4, 0))
        self._motion_widgets.append(home_btn)

    def _build_jog(self, grid_row: int) -> None:
        sec = SectionFrame(self, "JOG")
        sec.grid(row=grid_row, column=0, sticky="ew", padx=6, pady=4)

        joint_toggle = ttk.Checkbutton(
            sec,
            text="Joint mode (jog J1..J4 instead of X/Y/Z/R)",
            variable=self._joint_mode_var,
        )
        joint_toggle.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        self._motion_widgets.append(joint_toggle)

        for i, (label, axis) in enumerate(_JOG_AXES):
            ttk.Label(sec, text=label, width=8).grid(
                row=i + 1, column=0, sticky="w", padx=6
            )
            minus = JogButton(
                sec,
                text="-",
                on_press=partial(self._on_jog_start, axis, False),
                on_release=self._on_jog_stop,
                width=3,
            )
            minus.grid(row=i + 1, column=1, padx=2, pady=1)
            plus = JogButton(
                sec,
                text="+",
                on_press=partial(self._on_jog_start, axis, True),
                on_release=self._on_jog_stop,
                width=3,
            )
            plus.grid(row=i + 1, column=2, padx=2, pady=1)
            self._motion_widgets.append(minus)
            self._motion_widgets.append(plus)

    def _build_effector(self, grid_row: int) -> None:
        sec = SectionFrame(self, "End effector")
        sec.grid(row=grid_row, column=0, sticky="ew", padx=6, pady=4)

        def _pair(row: int, label: str, on_cmd: Callable[[], Any],
                  off_label: str, off_cmd: Callable[[], Any],
                  on_label: str) -> None:
            ttk.Label(sec, text=label, width=10).grid(
                row=row, column=0, sticky="w", padx=6
            )
            b_on = ttk.Button(sec, text=on_label, command=on_cmd)
            b_on.grid(row=row, column=1, padx=2, pady=1)
            b_off = ttk.Button(sec, text=off_label, command=off_cmd)
            b_off.grid(row=row, column=2, padx=2, pady=1)
            self._motion_widgets.append(b_on)
            self._motion_widgets.append(b_off)

        _pair(0, "Suction", lambda: self._on_suck(True),
              "Off", lambda: self._on_suck(False), "On")
        _pair(1, "Gripper", lambda: self._on_grip(True),
              "Open", lambda: self._on_grip(False), "Close")
        _pair(2, "Laser", lambda: self._on_laser(True),
              "Off", lambda: self._on_laser(False), "On")

        # Servo id + angle setter.
        servo = ttk.Frame(sec)
        servo.grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Label(servo, text="Servo id").grid(row=0, column=0, padx=(6, 2))
        e_id = ttk.Entry(servo, textvariable=self._servo_id_var, width=5)
        e_id.grid(row=0, column=1)
        ttk.Label(servo, text="angle").grid(row=0, column=2, padx=(8, 2))
        e_angle = ttk.Entry(servo, textvariable=self._servo_angle_var, width=7)
        e_angle.grid(row=0, column=3)
        set_btn = ttk.Button(servo, text="Set servo", command=self._on_set_servo)
        set_btn.grid(row=0, column=4, padx=6)
        self._motion_widgets.extend([e_id, e_angle, set_btn])

    def _build_io(self, grid_row: int) -> None:
        sec = SectionFrame(self, "IO")
        sec.grid(row=grid_row, column=0, sticky="ew", padx=6, pady=4)

        # DO addr + level -> set
        ttk.Label(sec, text="DO addr").grid(row=0, column=0, padx=(6, 2), sticky="e")
        e_do_addr = ttk.Entry(sec, textvariable=self._do_addr_var, width=5)
        e_do_addr.grid(row=0, column=1)
        ttk.Label(sec, text="level").grid(row=0, column=2, padx=(8, 2), sticky="e")
        e_do_level = ttk.Entry(sec, textvariable=self._do_level_var, width=5)
        e_do_level.grid(row=0, column=3)
        b_do = ttk.Button(sec, text="Set DO", command=self._on_set_do)
        b_do.grid(row=0, column=4, padx=6)
        self._motion_widgets.extend([e_do_addr, e_do_level, b_do])

        # DI addr -> read
        ttk.Label(sec, text="DI addr").grid(row=1, column=0, padx=(6, 2), sticky="e")
        e_di = ttk.Entry(sec, textvariable=self._di_addr_var, width=5)
        e_di.grid(row=1, column=1)
        b_di = ttk.Button(sec, text="Read DI", command=self._on_get_di)
        b_di.grid(row=1, column=4, padx=6)
        self._motion_widgets.extend([e_di, b_di])

        # ADC addr -> read
        ttk.Label(sec, text="ADC addr").grid(row=2, column=0, padx=(6, 2), sticky="e")
        e_adc = ttk.Entry(sec, textvariable=self._adc_addr_var, width=5)
        e_adc.grid(row=2, column=1)
        b_adc = ttk.Button(sec, text="Read ADC", command=self._on_get_adc)
        b_adc.grid(row=2, column=4, padx=6)
        self._motion_widgets.extend([e_adc, b_adc])

        # PWM addr + freq + duty -> set
        ttk.Label(sec, text="PWM addr").grid(row=3, column=0, padx=(6, 2), sticky="e")
        e_pwm_addr = ttk.Entry(sec, textvariable=self._pwm_addr_var, width=5)
        e_pwm_addr.grid(row=3, column=1)
        ttk.Label(sec, text="freq").grid(row=3, column=2, padx=(8, 2), sticky="e")
        e_pwm_freq = ttk.Entry(sec, textvariable=self._pwm_freq_var, width=7)
        e_pwm_freq.grid(row=3, column=3)
        ttk.Label(sec, text="duty").grid(row=3, column=5, padx=(8, 2), sticky="e")
        e_pwm_duty = ttk.Entry(sec, textvariable=self._pwm_duty_var, width=6)
        e_pwm_duty.grid(row=3, column=6)
        b_pwm = ttk.Button(sec, text="Set PWM", command=self._on_set_pwm)
        b_pwm.grid(row=3, column=7, padx=6)
        self._motion_widgets.extend([e_pwm_addr, e_pwm_freq, e_pwm_duty, b_pwm])

        ttk.Label(sec, text="Result:").grid(row=4, column=0, sticky="e", padx=(6, 2))
        ttk.Label(sec, textvariable=self._io_result_var).grid(
            row=4, column=1, columnspan=7, sticky="w"
        )

    def _build_sensors(self, grid_row: int) -> None:
        sec = SectionFrame(self, "Sensors")
        sec.grid(row=grid_row, column=0, sticky="ew", padx=6, pady=4)

        ttk.Label(sec, text="Port").grid(row=0, column=0, padx=(6, 2), sticky="e")
        e_port = ttk.Entry(sec, textvariable=self._sensor_port_var, width=5)
        e_port.grid(row=0, column=1, sticky="w")
        self._motion_widgets.append(e_port)

        buttons = ttk.Frame(sec)
        buttons.grid(row=1, column=0, columnspan=6, sticky="w", pady=(4, 0))
        specs = [
            ("Color", self._on_read_color),
            ("Infrared", self._on_read_infrared),
            ("Distance", self._on_read_distance),
            ("Temp", self._on_read_temp),
            ("Light", self._on_read_light),
        ]
        for i, (label, cmd) in enumerate(specs):
            b = ttk.Button(buttons, text=label, command=cmd)
            b.grid(row=0, column=i, padx=2)
            self._motion_widgets.append(b)

        ttk.Label(sec, text="Value:").grid(row=2, column=0, sticky="e", padx=(6, 2))
        ttk.Label(sec, textvariable=self._sensor_result_var).grid(
            row=2, column=1, columnspan=5, sticky="w", pady=(4, 0)
        )

    def _build_alarms(self, grid_row: int) -> None:
        sec = SectionFrame(self, "Alarms")
        sec.grid(row=grid_row, column=0, sticky="ew", padx=6, pady=4)
        sec.columnconfigure(0, weight=1)

        self._alarm_list = tk.Listbox(sec, height=4)
        self._alarm_list.grid(row=0, column=0, sticky="ew", padx=6)
        self._clear_alarms_btn = ttk.Button(
            sec, text="Clear Alarms", command=self._on_clear_alarms
        )
        self._clear_alarms_btn.grid(row=0, column=1, sticky="n", padx=6)
        self._motion_widgets.append(self._clear_alarms_btn)

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #
    def refresh(self, snapshot: Dict[str, Any]) -> None:
        """Update the live pose grid + alarm list and control-enable state.

        Args:
            snapshot: A dict shaped like :meth:`ArmController.snapshot` --
                ``{"connected", "port", "pose", "alarms", "error"}``. Missing
                keys are treated as absent/empty; the method never raises.
        """
        connected = bool(snapshot.get("connected", False))
        self._set_connected_state(connected)

        pose = snapshot.get("pose")
        if isinstance(pose, dict):
            self._pose_grid.update_values(
                {k: self._fmt(pose.get(k)) for k in _POSE_FIELDS}
            )
        else:
            self._pose_grid.update_values({k: "-" for k in _POSE_FIELDS})

        alarms = snapshot.get("alarms") or []
        self._alarm_list.delete(0, "end")
        if alarms:
            for name in alarms:
                self._alarm_list.insert("end", str(name))
        else:
            self._alarm_list.insert("end", "(none)")

    # ------------------------------------------------------------------ #
    # enable / disable
    # ------------------------------------------------------------------ #
    def _set_connected_state(self, connected: bool) -> None:
        """Enable motion controls only when connected; toggle connect buttons."""
        motion_state = "normal" if connected else "disabled"
        for w in self._motion_widgets:
            try:
                w.configure(state=motion_state)  # type: ignore[call-arg]
            except tk.TclError:
                pass
        self._connect_btn.configure(state="disabled" if connected else "normal")
        self._disconnect_btn.configure(state="normal" if connected else "disabled")

    # ------------------------------------------------------------------ #
    # connection callbacks
    # ------------------------------------------------------------------ #
    def _populate_ports(self) -> None:
        ports = self.controller.available_ports()
        self._port_combo.configure(values=ports)
        if ports and not self._port_var.get():
            self._port_var.set(ports[0])
        self._log(f"available_ports() -> {ports}")

    def _on_connect(self) -> None:
        port = self._port_var.get() or "auto"
        self._report(f"connect({port!r})", self.controller.connect(port))
        if self.controller.is_connected:
            self._update_device_info()
        self._set_connected_state(self.controller.is_connected)

    def _on_disconnect(self) -> None:
        self._report("disconnect()", self.controller.disconnect())
        self._info_var.set("Device: -")
        self._set_connected_state(self.controller.is_connected)

    def _on_emergency_stop(self) -> None:
        """Stop jog motion and drop the connection -- always available."""
        self._report("EMERGENCY STOP jog_stop()", self.controller.jog_stop())
        self._report("EMERGENCY STOP disconnect()", self.controller.disconnect())
        self._info_var.set("Device: -")
        self._set_connected_state(self.controller.is_connected)

    def _update_device_info(self) -> None:
        info = self.controller.device_info()
        text = (
            f"Device: name={info.get('name')} sn={info.get('sn')} "
            f"version={info.get('version')}"
        )
        if info.get("error"):
            text += f" (error: {info['error']})"
        self._info_var.set(text)
        self._log(f"device_info() -> {info}")

    # ------------------------------------------------------------------ #
    # motion callbacks
    # ------------------------------------------------------------------ #
    def _on_move_to(self) -> None:
        coords = self._read_floats(self._abs_vars, ("x", "y", "z", "r"))
        if coords is None:
            return
        mode = PTPMode[self._ptp_mode_var.get()]
        x, y, z, r = coords
        self._report(
            f"move_to({x}, {y}, {z}, {r}, mode={mode.name})",
            self.controller.move_to(x, y, z, r, mode=mode, wait=True),
        )

    def _on_move_relative(self) -> None:
        offs = self._read_floats(self._rel_vars, ("dx", "dy", "dz", "dr"))
        if offs is None:
            return
        dx, dy, dz, dr = offs
        self._report(
            f"move_relative({dx}, {dy}, {dz}, {dr})",
            self.controller.move_relative(dx, dy, dz, dr, wait=True),
        )

    def _on_set_speed(self) -> None:
        vel = float(self._vel_var.get())
        acc = float(self._acc_var.get())
        self._report(
            f"set_speed({vel:.0f}, {acc:.0f})",
            self.controller.set_speed(vel, acc),
        )

    def _on_home(self) -> None:
        if not messagebox.askokcancel(
            "Home arm", "Run the homing routine? The arm will move to its home pose."
        ):
            self._log("home() cancelled by user")
            return
        self._report("home()", self.controller.home(wait=True))

    # ------------------------------------------------------------------ #
    # jog callbacks
    # ------------------------------------------------------------------ #
    def _on_jog_start(self, axis: int, positive: bool) -> None:
        joint = bool(self._joint_mode_var.get())
        self._report(
            f"jog_start(axis={axis}, positive={positive}, joint={joint})",
            self.controller.jog_start(axis, positive, joint=joint),
        )

    def _on_jog_stop(self) -> None:
        self._report("jog_stop()", self.controller.jog_stop())

    # ------------------------------------------------------------------ #
    # end-effector callbacks
    # ------------------------------------------------------------------ #
    def _on_suck(self, on: bool) -> None:
        self._report(f"suck({on})", self.controller.suck(on))

    def _on_grip(self, on: bool) -> None:
        self._report(f"grip({on})", self.controller.grip(on))

    def _on_laser(self, on: bool) -> None:
        self._report(f"laser({on})", self.controller.laser(on))

    def _on_set_servo(self) -> None:
        servo_id = self._read_int(self._servo_id_var, "servo id")
        angle = self._read_float(self._servo_angle_var, "servo angle")
        if servo_id is None or angle is None:
            return
        self._report(
            f"set_servo({servo_id}, {angle})",
            self.controller.set_servo(servo_id, angle),
        )

    # ------------------------------------------------------------------ #
    # IO callbacks
    # ------------------------------------------------------------------ #
    def _on_set_do(self) -> None:
        addr = self._read_int(self._do_addr_var, "DO addr")
        level = self._read_int(self._do_level_var, "DO level")
        if addr is None or level is None:
            return
        self._report_io(
            f"io_set_do({addr}, {level})", self.controller.io_set_do(addr, level)
        )

    def _on_get_di(self) -> None:
        addr = self._read_int(self._di_addr_var, "DI addr")
        if addr is None:
            return
        self._report_io(f"io_get_di({addr})", self.controller.io_get_di(addr))

    def _on_get_adc(self) -> None:
        addr = self._read_int(self._adc_addr_var, "ADC addr")
        if addr is None:
            return
        self._report_io(f"io_get_adc({addr})", self.controller.io_get_adc(addr))

    def _on_set_pwm(self) -> None:
        addr = self._read_int(self._pwm_addr_var, "PWM addr")
        freq = self._read_float(self._pwm_freq_var, "PWM freq")
        duty = self._read_float(self._pwm_duty_var, "PWM duty")
        if addr is None or freq is None or duty is None:
            return
        self._report_io(
            f"io_set_pwm({addr}, {freq}, {duty})",
            self.controller.io_set_pwm(addr, freq, duty),
        )

    # ------------------------------------------------------------------ #
    # sensor callbacks
    # ------------------------------------------------------------------ #
    def _sensor_port(self) -> Optional[int]:
        return self._read_int(self._sensor_port_var, "sensor port")

    def _on_read_color(self) -> None:
        port = self._sensor_port()
        if port is None:
            return
        self._report_sensor(f"read_color({port})", self.controller.read_color(port))

    def _on_read_infrared(self) -> None:
        port = self._sensor_port()
        if port is None:
            return
        self._report_sensor(
            f"read_infrared({port})", self.controller.read_infrared(port)
        )

    def _on_read_distance(self) -> None:
        port = self._sensor_port()
        if port is None:
            return
        self._report_sensor(
            f"read_seeed_distance({port})", self.controller.read_seeed_distance(port)
        )

    def _on_read_temp(self) -> None:
        port = self._sensor_port()
        if port is None:
            return
        self._report_sensor(
            f"read_seeed_temp({port})", self.controller.read_seeed_temp(port)
        )

    def _on_read_light(self) -> None:
        port = self._sensor_port()
        if port is None:
            return
        self._report_sensor(
            f"read_seeed_light({port})", self.controller.read_seeed_light(port)
        )

    # ------------------------------------------------------------------ #
    # alarm callbacks
    # ------------------------------------------------------------------ #
    def _on_clear_alarms(self) -> None:
        self._report("clear_alarms()", self.controller.clear_alarms())

    # ------------------------------------------------------------------ #
    # reporting + input helpers
    # ------------------------------------------------------------------ #
    def _report(self, call: str, result: ActionResult) -> None:
        """Log ``call`` and its ``(ok, message)`` outcome."""
        status = "OK" if result.ok else "FAIL"
        self._log(f"{call} -> [{status}] {result.message}")

    def _report_io(self, call: str, result: ActionResult) -> None:
        """Like :meth:`_report`, and mirror the result into the IO result label."""
        self._report(call, result)
        self._io_result_var.set(result.message)

    def _report_sensor(self, call: str, result: ActionResult) -> None:
        """Like :meth:`_report`, and mirror the result into the sensor label."""
        self._report(call, result)
        self._sensor_result_var.set(result.message)

    @staticmethod
    def _fmt(value: Any) -> str:
        """Format a pose component for display (numbers to 2 dp)."""
        if isinstance(value, (int, float)):
            return f"{float(value):.2f}"
        return "-" if value is None else str(value)

    def _read_float(self, var: tk.StringVar, label: str) -> Optional[float]:
        raw = var.get().strip()
        try:
            return float(raw)
        except ValueError:
            self._log(f"invalid {label}: {raw!r} (expected a number)")
            return None

    def _read_int(self, var: tk.StringVar, label: str) -> Optional[int]:
        raw = var.get().strip()
        try:
            return int(float(raw))
        except ValueError:
            self._log(f"invalid {label}: {raw!r} (expected an integer)")
            return None

    def _read_floats(
        self, vars_map: Dict[str, tk.StringVar], keys: "tuple[str, ...]"
    ) -> Optional["tuple[float, ...]"]:
        out: List[float] = []
        for k in keys:
            v = self._read_float(vars_map[k], k)
            if v is None:
                return None
            out.append(v)
        return tuple(out)
