"""Tkinter control panel for the Magician GO, wired to :class:`GoController`.

``GoPanel`` is a :class:`ttk.Frame` exposing the *full* GO feature set as a set
of :class:`~dobotkit.gui.widgets.SectionFrame` groups:

* **Connection** -- host/port/port-name entries, Connect (verifying the link) /
  Disconnect, a live battery read-out and an always-armed **EMERGENCY STOP**.
* **Drive** -- a directional pad of press-and-hold :class:`JogButton`\\ s that
  ``drive_*`` on press and :meth:`GoController.stop` on release, a speed slider,
  a plain STOP button and a clearance-check indicator.
* **Live Telemetry** -- a :class:`ValueGrid` of ultrasonic front/back/left/right,
  odometer x/y/yaw, IMU yaw and battery V/%, refreshed from a snapshot dict.
* **Output** -- an RGB LED channel + r/g/b sliders and a buzzer index/tone/beat.
* **Line trace** -- speed + P/I/D entries with Start/Stop.
* **Navigation** -- set-start x/y/heading, go-to x/y (``WaypointNav``) and a
  precise-forward mm + speed (``PreciseMover``); result dicts are logged.
* **Camera** -- a Read-camera button showing the detection count / objects.

Every user action is routed through the injected :class:`GoController` (never
the device directly), and both the *call* and its *result* are written to the
``log`` callback.

Import safety / headless
------------------------
Importing this module only imports ``tkinter``/``tkinter.ttk`` and *defines*
:class:`GoPanel`; it constructs **no** ``Tk()`` root and opens no window. A panel
is instantiated only when the running app supplies a live master widget, which
happens at launch, not at import time. This keeps the module importable on CI
and in a headless test.

The widget layer is only lightly typed (per the project's ``dobotkit.gui.*``
mypy relaxation); the logic it drives lives fully-typed in
:class:`~dobotkit.gui.go_controller.GoController`.
"""
from __future__ import annotations

import queue
import tkinter as tk
from functools import partial
from tkinter import ttk
from typing import Any, Callable, Dict, Optional

from dobotkit.enums import LEDChannel
from dobotkit.gui._async import run_in_thread
from dobotkit.gui.go_controller import GoController
from dobotkit.gui.widgets import JogButton, SectionFrame, ValueGrid

__all__ = ["GoPanel"]

#: A logging sink: called with one human-readable line per action + result.
LogFn = Callable[[str], object]

#: Telemetry grid fields: key -> caption. Keys are what :meth:`GoPanel.refresh`
#: writes to; captions are what the user reads.
_TELEMETRY_FIELDS: Dict[str, str] = {
    "us_front": "Ultrasonic front (cm)",
    "us_back": "Ultrasonic back (cm)",
    "us_left": "Ultrasonic left (cm)",
    "us_right": "Ultrasonic right (cm)",
    "odo_x": "Odometer x (mm)",
    "odo_y": "Odometer y (mm)",
    "odo_yaw": "Odometer yaw (deg)",
    "imu_yaw": "IMU yaw (deg)",
    "batt_v": "Battery (V)",
    "batt_pct": "Battery (%)",
}


def _fmt(value: Any) -> str:
    """Format a possibly-``None`` numeric telemetry value for display."""
    if value is None:
        return "-"
    if isinstance(value, (int, float)):
        return f"{value:.1f}"
    return str(value)


class GoPanel(ttk.Frame):
    """Full-feature Magician GO control surface bound to a :class:`GoController`.

    Args:
        parent: The master widget (a live ``Tk`` root or another widget).
        controller: The :class:`GoController` all actions are routed through.
        log: A callback taking one string; each action logs its call and result
            through it (e.g. :meth:`dobotkit.gui.widgets.LogView.log`).
    """

    def __init__(
        self,
        parent: tk.Misc,
        controller: GoController,
        log: LogFn,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, **kwargs)
        self.controller = controller
        self._log = log

        # Widgets that toggle with connection state (all disabled until Connect,
        # except the emergency stop which is armed whenever connected).
        self._connect_gated: list[tk.Widget] = []
        self._estop_button: Optional[tk.Widget] = None
        self._disconnect_button: Optional[tk.Widget] = None
        self._connect_button: Optional[tk.Widget] = None

        # Tk variables (created against this frame so no implicit default root).
        self._host = tk.StringVar(master=self, value="localhost")
        self._port = tk.StringVar(master=self, value="9090")
        self._port_name = tk.StringVar(master=self, value="COM5")
        self._battery = tk.StringVar(master=self, value="battery: -")
        self._clearance = tk.StringVar(master=self, value="clearance: ?")
        self._speed = tk.DoubleVar(master=self, value=float(controller.speed))
        self._rgb_channel = tk.IntVar(master=self, value=int(LEDChannel.LED_ALL))
        self._rgb_r = tk.IntVar(master=self, value=0)
        self._rgb_g = tk.IntVar(master=self, value=0)
        self._rgb_b = tk.IntVar(master=self, value=0)
        self._buz_index = tk.StringVar(master=self, value="1")
        self._buz_tone = tk.StringVar(master=self, value="1")
        self._buz_beat = tk.StringVar(master=self, value="1")
        self._trace_speed = tk.StringVar(master=self, value="15")
        self._trace_p = tk.StringVar(master=self, value="1.0")
        self._trace_i = tk.StringVar(master=self, value="0.0")
        self._trace_d = tk.StringVar(master=self, value="0.0")
        self._nav_start_x = tk.StringVar(master=self, value="0")
        self._nav_start_y = tk.StringVar(master=self, value="0")
        self._nav_start_h = tk.StringVar(master=self, value="0")
        self._nav_goto_x = tk.StringVar(master=self, value="0")
        self._nav_goto_y = tk.StringVar(master=self, value="0")
        self._pf_mm = tk.StringVar(master=self, value="100")
        self._pf_speed = tk.StringVar(master=self, value="25")
        self._camera = tk.StringVar(master=self, value="camera: -")

        self._telemetry: Optional[ValueGrid] = None

        # Off-thread dispatch for blocking navigation (WaypointNav / PreciseMover
        # loop with timeouts and would otherwise freeze the UI). Worker threads
        # push completion callbacks onto this queue; a main-thread ``after`` pump
        # drains it. ``_nav_busy`` prevents overlapping navigation runs.
        self._ui_queue: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self._nav_busy: bool = False

        self._build()
        self._set_connected_state(self.controller.is_connected)
        self._pump_ui_queue()

    # ------------------------------------------------------------------ #
    # worker-result pump (main thread)
    # ------------------------------------------------------------------ #
    def _pump_ui_queue(self) -> None:
        """Drain worker-thread callbacks on the Tk main thread; self-reschedules."""
        try:
            while True:
                callback = self._ui_queue.get_nowait()
                try:
                    callback()
                except Exception as exc:  # noqa: BLE001 -- never kill the pump
                    self._emit(f"UI callback error: {exc}")
        except queue.Empty:
            pass
        try:
            self.after(60, self._pump_ui_queue)
        except tk.TclError:
            pass  # widget destroyed; stop pumping

    def _run_async(self, label: str, action: Callable[[], Any]) -> None:
        """Run a BLOCKING controller call off the Tk thread, then log the result.

        Used for navigation (``nav_goto`` / ``precise_forward``) which polls with
        timeouts; running it inline would freeze the window. Only one navigation
        runs at a time (``_nav_busy``).
        """
        if self._nav_busy:
            self._emit(f"{label} -> [BUSY] navigation already running")
            return
        self._nav_busy = True
        self._emit(f"{label} ... (running)")

        def done(result: Any, error: Optional[BaseException]) -> None:
            self._nav_busy = False
            if error is not None:
                self._emit(f"{label} -> EXCEPTION: {error}")
            else:
                self._emit(f"{label} -> {result!r}")

        run_in_thread(action, done, self._ui_queue.put)

    # ------------------------------------------------------------------ #
    # Logging helpers
    # ------------------------------------------------------------------ #
    def _emit(self, msg: str) -> None:
        """Send a line to the log sink, swallowing any sink failure."""
        try:
            self._log(msg)
        except Exception:  # noqa: BLE001 -- logging must never break the UI
            pass

    def _run(self, label: str, action: Callable[[], Any]) -> Any:
        """Run ``action`` (a controller call), log ``label`` + its result, return it.

        The controller never raises the dobotkit error hierarchy into the UI, but
        this still guards defensively so a stray error can never crash the panel.
        """
        try:
            result = action()
        except Exception as exc:  # noqa: BLE001 -- surface, never crash the UI
            self._emit(f"{label} -> EXCEPTION: {exc}")
            return None
        self._emit(f"{label} -> {result!r}")
        return result

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        """Construct all section frames and lay them out in a two-column grid."""
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        conn = self._build_connection()
        drive = self._build_drive()
        telem = self._build_telemetry()
        output = self._build_output()
        trace = self._build_line_trace()
        nav = self._build_navigation()
        camera = self._build_camera()

        conn.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=4)
        drive.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        telem.grid(row=1, column=1, sticky="nsew", padx=4, pady=4)
        output.grid(row=2, column=0, sticky="nsew", padx=4, pady=4)
        trace.grid(row=2, column=1, sticky="nsew", padx=4, pady=4)
        nav.grid(row=3, column=0, sticky="nsew", padx=4, pady=4)
        camera.grid(row=3, column=1, sticky="nsew", padx=4, pady=4)

    def _entry(self, master: tk.Misc, var: tk.StringVar, width: int = 7) -> ttk.Entry:
        """A small entry bound to ``var`` (registered as connect-gated)."""
        e = ttk.Entry(master, textvariable=var, width=width)
        self._connect_gated.append(e)
        return e

    # ---- Connection ---------------------------------------------------- #
    def _build_connection(self) -> SectionFrame:
        f = SectionFrame(self, "Connection")
        # host / port / port_name entries (NOT connect-gated -- editable to set up
        # a connection, then locked once connected below via disable).
        ttk.Label(f, text="host").grid(row=0, column=0, sticky="w")
        self._host_entry = ttk.Entry(f, textvariable=self._host, width=12)
        self._host_entry.grid(row=0, column=1, sticky="w", padx=(0, 8))
        ttk.Label(f, text="port").grid(row=0, column=2, sticky="w")
        self._port_entry = ttk.Entry(f, textvariable=self._port, width=7)
        self._port_entry.grid(row=0, column=3, sticky="w", padx=(0, 8))
        ttk.Label(f, text="port_name").grid(row=0, column=4, sticky="w")
        self._port_name_entry = ttk.Entry(f, textvariable=self._port_name, width=8)
        self._port_name_entry.grid(row=0, column=5, sticky="w", padx=(0, 8))

        self._connect_button = ttk.Button(f, text="Connect", command=self._on_connect)
        self._connect_button.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._disconnect_button = ttk.Button(
            f, text="Disconnect", command=self._on_disconnect
        )
        self._disconnect_button.grid(row=1, column=2, columnspan=2, sticky="ew", pady=(6, 0))

        ttk.Label(f, textvariable=self._battery).grid(
            row=1, column=4, columnspan=2, sticky="w", padx=(8, 0)
        )

        # Big red EMERGENCY STOP -- armed whenever connected; spans the row.
        style = ttk.Style(self)
        try:
            style.configure("Emergency.TButton", foreground="red", font=("", 12, "bold"))
        except tk.TclError:  # pragma: no cover -- some minimal Tk builds
            pass
        self._estop_button = ttk.Button(
            f,
            text="EMERGENCY STOP",
            style="Emergency.TButton",
            command=self._on_emergency_stop,
        )
        self._estop_button.grid(row=2, column=0, columnspan=6, sticky="ew", pady=(8, 0))
        return f

    # ---- Drive --------------------------------------------------------- #
    def _build_drive(self) -> SectionFrame:
        f = SectionFrame(self, "Drive")

        # Directional pad. Press = drive; release = stop.
        def jog(text: str, drive: Callable[[], Any], r: int, c: int) -> None:
            btn = JogButton(
                f,
                text,
                on_press=partial(self._on_jog_press, text, drive),
                on_release=self._on_jog_release,
                width=8,
            )
            btn.grid(row=r, column=c, padx=2, pady=2, sticky="ew")
            self._connect_gated.append(btn)

        jog("Forward", self.controller.drive_forward, 0, 1)
        jog("Strafe L", self.controller.strafe_left, 1, 0)
        jog("Spin L", self.controller.spin_left, 1, 1)
        jog("Strafe R", self.controller.strafe_right, 1, 2)
        jog("Back", self.controller.drive_backward, 2, 1)
        jog("Spin R", self.controller.spin_right, 2, 2)

        # Speed slider.
        ttk.Label(f, text="speed").grid(row=3, column=0, sticky="w", pady=(8, 0))
        scale = ttk.Scale(
            f,
            from_=0,
            to=100,
            orient="horizontal",
            variable=self._speed,
            command=self._on_speed,
        )
        scale.grid(row=3, column=1, columnspan=2, sticky="ew", pady=(8, 0))
        self._connect_gated.append(scale)

        # Plain STOP + clearance check.
        stop_btn = ttk.Button(f, text="STOP", command=self._on_stop)
        stop_btn.grid(row=4, column=1, sticky="ew", pady=(6, 0))
        self._connect_gated.append(stop_btn)

        check_btn = ttk.Button(f, text="Check clearance", command=self._on_clearance)
        check_btn.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._connect_gated.append(check_btn)
        ttk.Label(f, textvariable=self._clearance).grid(
            row=5, column=2, sticky="w", padx=(6, 0), pady=(6, 0)
        )
        return f

    # ---- Telemetry ----------------------------------------------------- #
    def _build_telemetry(self) -> SectionFrame:
        f = SectionFrame(self, "Live Telemetry")
        self._telemetry = ValueGrid(f, _TELEMETRY_FIELDS, columns=2, caption_width=20)
        self._telemetry.grid(row=0, column=0, sticky="nsew")
        return f

    # ---- Output (RGB / buzzer) ---------------------------------------- #
    def _build_output(self) -> SectionFrame:
        f = SectionFrame(self, "Output")

        ttk.Label(f, text="RGB channel").grid(row=0, column=0, sticky="w")
        chan = ttk.Combobox(
            f,
            state="readonly",
            width=8,
            values=[c.name for c in LEDChannel],
        )
        chan.set(LEDChannel.LED_ALL.name)
        chan.grid(row=0, column=1, sticky="w", padx=(0, 8))
        chan.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._rgb_channel.set(int(LEDChannel[chan.get()])),
        )
        self._connect_gated.append(chan)

        for i, (label, var) in enumerate(
            (("R", self._rgb_r), ("G", self._rgb_g), ("B", self._rgb_b))
        ):
            ttk.Label(f, text=label).grid(row=1 + i, column=0, sticky="w")
            s = ttk.Scale(f, from_=0, to=255, orient="horizontal", variable=var)
            s.grid(row=1 + i, column=1, sticky="ew", padx=(0, 8))
            self._connect_gated.append(s)

        set_rgb = ttk.Button(f, text="Set RGB", command=self._on_rgb)
        set_rgb.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._connect_gated.append(set_rgb)

        ttk.Separator(f, orient="horizontal").grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=6
        )

        ttk.Label(f, text="buzzer index/tone/beat").grid(
            row=6, column=0, columnspan=2, sticky="w"
        )
        row = ttk.Frame(f)
        row.grid(row=7, column=0, columnspan=2, sticky="w")
        self._entry(row, self._buz_index, width=5).grid(row=0, column=0, padx=2)
        self._entry(row, self._buz_tone, width=5).grid(row=0, column=1, padx=2)
        self._entry(row, self._buz_beat, width=5).grid(row=0, column=2, padx=2)
        buz = ttk.Button(f, text="Buzz", command=self._on_buzzer)
        buz.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._connect_gated.append(buz)
        return f

    # ---- Line trace ---------------------------------------------------- #
    def _build_line_trace(self) -> SectionFrame:
        f = SectionFrame(self, "Line trace")
        fields = (
            ("speed", self._trace_speed),
            ("P", self._trace_p),
            ("I", self._trace_i),
            ("D", self._trace_d),
        )
        for i, (label, var) in enumerate(fields):
            ttk.Label(f, text=label).grid(row=i, column=0, sticky="w")
            self._entry(f, var).grid(row=i, column=1, sticky="w", pady=1)

        start = ttk.Button(f, text="Start", command=self._on_trace_start)
        start.grid(row=len(fields), column=0, sticky="ew", pady=(6, 0))
        self._connect_gated.append(start)
        stop = ttk.Button(f, text="Stop", command=self._on_trace_stop)
        stop.grid(row=len(fields), column=1, sticky="ew", pady=(6, 0))
        self._connect_gated.append(stop)
        return f

    # ---- Navigation ---------------------------------------------------- #
    def _build_navigation(self) -> SectionFrame:
        f = SectionFrame(self, "Navigation")

        ttk.Label(f, text="set start x/y/heading").grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        srow = ttk.Frame(f)
        srow.grid(row=1, column=0, columnspan=3, sticky="w")
        self._entry(srow, self._nav_start_x, width=6).grid(row=0, column=0, padx=2)
        self._entry(srow, self._nav_start_y, width=6).grid(row=0, column=1, padx=2)
        self._entry(srow, self._nav_start_h, width=6).grid(row=0, column=2, padx=2)
        set_start = ttk.Button(f, text="Set start", command=self._on_nav_set_start)
        set_start.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self._connect_gated.append(set_start)

        ttk.Separator(f, orient="horizontal").grid(
            row=3, column=0, columnspan=3, sticky="ew", pady=6
        )

        ttk.Label(f, text="go to x/y").grid(row=4, column=0, columnspan=3, sticky="w")
        grow = ttk.Frame(f)
        grow.grid(row=5, column=0, columnspan=3, sticky="w")
        self._entry(grow, self._nav_goto_x, width=6).grid(row=0, column=0, padx=2)
        self._entry(grow, self._nav_goto_y, width=6).grid(row=0, column=1, padx=2)
        go_to = ttk.Button(f, text="Go to", command=self._on_nav_goto)
        go_to.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self._connect_gated.append(go_to)

        ttk.Separator(f, orient="horizontal").grid(
            row=7, column=0, columnspan=3, sticky="ew", pady=6
        )

        ttk.Label(f, text="precise forward mm/speed").grid(
            row=8, column=0, columnspan=3, sticky="w"
        )
        prow = ttk.Frame(f)
        prow.grid(row=9, column=0, columnspan=3, sticky="w")
        self._entry(prow, self._pf_mm, width=6).grid(row=0, column=0, padx=2)
        self._entry(prow, self._pf_speed, width=6).grid(row=0, column=1, padx=2)
        pf = ttk.Button(f, text="Precise forward", command=self._on_precise_forward)
        pf.grid(row=10, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self._connect_gated.append(pf)
        return f

    # ---- Camera -------------------------------------------------------- #
    def _build_camera(self) -> SectionFrame:
        f = SectionFrame(self, "Camera")
        read = ttk.Button(f, text="Read camera", command=self._on_read_camera)
        read.grid(row=0, column=0, sticky="ew")
        self._connect_gated.append(read)
        ttk.Label(f, textvariable=self._camera).grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        return f

    # ------------------------------------------------------------------ #
    # Value parsing (entries are strings; keep the panel crash-proof)
    # ------------------------------------------------------------------ #
    def _num(self, var: tk.StringVar, label: str, default: float = 0.0) -> float:
        """Parse ``var`` as float, logging + falling back to ``default`` on error."""
        raw = var.get().strip()
        try:
            return float(raw)
        except (TypeError, ValueError):
            self._emit(f"{label}: invalid number {raw!r}, using {default}")
            return default

    def _int(self, var: tk.StringVar, label: str, default: int = 0) -> int:
        """Parse ``var`` as int, logging + falling back to ``default`` on error."""
        raw = var.get().strip()
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            self._emit(f"{label}: invalid integer {raw!r}, using {default}")
            return default

    # ------------------------------------------------------------------ #
    # Connection actions
    # ------------------------------------------------------------------ #
    def _on_connect(self) -> None:
        host = self._host.get().strip() or "localhost"
        port = self._int(self._port, "port", 9090)
        port_name = self._port_name.get().strip() or "COM5"
        result = self._run(
            f"connect(host={host!r}, port={port}, port_name={port_name!r})",
            lambda: self.controller.connect(host=host, port=port, port_name=port_name),
        )
        self._set_connected_state(self.controller.is_connected)
        # Prime the battery/telemetry read-out right after a connect.
        if result is not None:
            self.refresh(self.controller.snapshot())

    def _on_disconnect(self) -> None:
        self._run("disconnect()", self.controller.disconnect)
        self._set_connected_state(self.controller.is_connected)
        self._battery.set("battery: -")

    def _on_emergency_stop(self) -> None:
        self._run("EMERGENCY STOP", self.controller.emergency_stop)

    # ------------------------------------------------------------------ #
    # Drive actions
    # ------------------------------------------------------------------ #
    def _on_speed(self, _value: Any = None) -> None:
        self._run(
            f"set_speed({self._speed.get():.1f})",
            lambda: self.controller.set_speed(self._speed.get()),
        )

    def _on_jog_press(self, label: str, drive: Callable[[], Any]) -> None:
        self._run(f"drive {label}", drive)

    def _on_jog_release(self) -> None:
        self._run("stop (release)", self.controller.stop)

    def _on_stop(self) -> None:
        self._run("stop()", self.controller.stop)

    def _on_clearance(self) -> None:
        result = self._run("clearance_ok()", self.controller.clearance_ok)
        if result is not None:
            ok, info = result
            self._clearance.set(f"clearance: {'OK' if ok else 'BLOCKED'} ({info})")

    # ------------------------------------------------------------------ #
    # Output actions
    # ------------------------------------------------------------------ #
    def _on_rgb(self) -> None:
        channel = self._rgb_channel.get()
        r, g, b = self._rgb_r.get(), self._rgb_g.get(), self._rgb_b.get()
        self._run(
            f"rgb({channel}, {r}, {g}, {b})",
            lambda: self.controller.rgb(channel, r, g, b),
        )

    def _on_buzzer(self) -> None:
        index = self._int(self._buz_index, "buzzer index", 1)
        tone = self._int(self._buz_tone, "buzzer tone", 1)
        beat = self._int(self._buz_beat, "buzzer beat", 1)
        self._run(
            f"buzzer({index}, {tone}, {beat})",
            lambda: self.controller.buzzer(index, tone, beat),
        )

    # ------------------------------------------------------------------ #
    # Line-trace actions
    # ------------------------------------------------------------------ #
    def _on_trace_start(self) -> None:
        speed = self._num(self._trace_speed, "trace speed", 15.0)
        p = self._num(self._trace_p, "trace P", 1.0)
        i = self._num(self._trace_i, "trace I", 0.0)
        d = self._num(self._trace_d, "trace D", 0.0)
        self._run(
            f"line_trace_start(speed={speed}, p={p}, i={i}, d={d})",
            lambda: self.controller.line_trace_start(speed, p, i, d),
        )

    def _on_trace_stop(self) -> None:
        self._run("line_trace_stop()", self.controller.line_trace_stop)

    # ------------------------------------------------------------------ #
    # Navigation actions (result dicts land in the log)
    # ------------------------------------------------------------------ #
    def _on_nav_set_start(self) -> None:
        x = self._num(self._nav_start_x, "start x")
        y = self._num(self._nav_start_y, "start y")
        h = self._num(self._nav_start_h, "start heading")
        self._run(
            f"nav_set_start(x={x}, y={y}, heading={h})",
            lambda: self.controller.nav_set_start(x, y, h),
        )

    def _on_nav_goto(self) -> None:
        x = self._num(self._nav_goto_x, "goto x")
        y = self._num(self._nav_goto_y, "goto y")
        self._run_async(
            f"nav_goto(x={x}, y={y})",
            lambda: self.controller.nav_goto(x, y),
        )

    def _on_precise_forward(self) -> None:
        mm = self._num(self._pf_mm, "precise mm", 100.0)
        speed = self._num(self._pf_speed, "precise speed", 25.0)
        self._run_async(
            f"precise_forward(mm={mm}, speed={speed})",
            lambda: self.controller.precise_forward(mm, speed=speed),
        )

    # ------------------------------------------------------------------ #
    # Camera action
    # ------------------------------------------------------------------ #
    def _on_read_camera(self) -> None:
        result = self._run("read_camera()", self.controller.read_camera)
        if result is None:
            self._camera.set("camera: none / unavailable")
            return
        if isinstance(result, dict):
            objs = result.get("dl_obj", [])
            count = result.get("count", len(objs) if isinstance(objs, list) else 0)
            self._camera.set(f"camera: {count} object(s) {objs!r}")
        else:
            self._camera.set(f"camera: {result!r}")

    # ------------------------------------------------------------------ #
    # Refresh + connection-gated enable/disable
    # ------------------------------------------------------------------ #
    def refresh(self, snapshot: Dict[str, Any]) -> None:
        """Update the telemetry grid + battery display from a controller snapshot.

        ``snapshot`` is the dict returned by :meth:`GoController.snapshot`:
        ``{connected, ultrasonic, odometer, imu, battery, error}``. Missing /
        ``None`` sections render as ``"-"``. Also re-applies the connection-gated
        enable/disable using ``snapshot["connected"]``.
        """
        us = snapshot.get("ultrasonic") or {}
        odo = snapshot.get("odometer") or {}
        imu = snapshot.get("imu") or {}
        batt = snapshot.get("battery") or {}

        if self._telemetry is not None:
            self._telemetry.update_values(
                {
                    "us_front": _fmt(us.get("front")),
                    "us_back": _fmt(us.get("back")),
                    "us_left": _fmt(us.get("left")),
                    "us_right": _fmt(us.get("right")),
                    "odo_x": _fmt(odo.get("x")),
                    "odo_y": _fmt(odo.get("y")),
                    "odo_yaw": _fmt(odo.get("yaw")),
                    "imu_yaw": _fmt(imu.get("yaw")),
                    "batt_v": _fmt(batt.get("voltage")),
                    "batt_pct": _fmt(batt.get("percentage")),
                }
            )

        v = batt.get("voltage")
        pct = batt.get("percentage")
        if v is None and pct is None:
            self._battery.set("battery: -")
        else:
            self._battery.set(f"battery: {_fmt(v)} V / {_fmt(pct)} %")

        self._set_connected_state(bool(snapshot.get("connected")))

    def _set_connected_state(self, connected: bool) -> None:
        """Enable/disable widgets by connection state.

        All feature widgets are enabled only when ``connected``. The Connect
        button + connection entries are the inverse (usable only while
        *disconnected*), Disconnect follows ``connected``, and the EMERGENCY STOP
        is armed whenever ``connected`` (always available to halt the car).
        """
        feature_state = "normal" if connected else "disabled"
        for w in self._connect_gated:
            self._set_state(w, feature_state)

        # Connect + connection entries: usable only while disconnected.
        conn_setup_state = "disabled" if connected else "normal"
        self._set_state(self._connect_button, conn_setup_state)
        for entry in (self._host_entry, self._port_entry, self._port_name_entry):
            self._set_state(entry, conn_setup_state)

        # Disconnect + emergency stop track the connected flag.
        self._set_state(self._disconnect_button, feature_state)
        self._set_state(self._estop_button, feature_state)

    @staticmethod
    def _set_state(widget: Optional[tk.Widget], state: str) -> None:
        """Best-effort widget enable/disable (works for ``ttk`` + classic Tk)."""
        if widget is None:
            return
        try:
            widget.configure(state=state)  # type: ignore[call-arg]
        except tk.TclError:  # pragma: no cover -- widget without a state option
            pass
