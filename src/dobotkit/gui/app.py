"""The dobotkit GUI application -- window, tabs, telemetry loop, and ``main()``.

This module ties the pieces together into a runnable app:

* :class:`App` -- a :class:`tkinter.Tk` root holding a :class:`ttk.Notebook` with
  three tabs (**Arm** = :class:`~dobotkit.gui.arm_panel.ArmPanel`,
  **GO** = :class:`~dobotkit.gui.go_panel.GoPanel`, **Log** = a
  :class:`~dobotkit.gui.widgets.LogView`), a :class:`~dobotkit.gui.widgets.StatusBar`
  along the bottom, and a shared thread-safe ``log`` routed to the Log tab.
* A **telemetry loop**: one background daemon thread per controller periodically
  calls ``controller.snapshot()`` and pushes ``(name, snapshot)`` onto a
  :class:`queue.Queue`. The Tk side drains that queue from a ``self.after(...)``
  callback and hands each snapshot to the matching panel's ``refresh(...)``.
  Worker threads *never* touch a Tk widget -- all widget mutation happens on the
  main thread inside the ``after`` drain, as Tkinter requires. The threads are
  stopped cleanly (and the controllers disconnected) on window close.
* :func:`main` -- argument parsing (``--demo`` / ``--arm-port`` / ``--go-port`` /
  ``--dobotlink-host`` / ``--dobotlink-port``), controller construction (with the
  :mod:`dobotkit.gui._demo` fakes injected under ``--demo``), and the mainloop.
  If ``Tk()`` cannot initialise (no display), it prints a clear message and
  exits ``0`` rather than crashing.

Import safety
-------------
Importing this module only *defines* the classes/functions below and pulls in
``tkinter`` (which is import-safe -- importing ``tkinter`` does not open a
display). No ``Tk()`` root is created until :func:`main` (or :class:`App`) is
actually invoked, so importing ``dobotkit.gui.app`` is safe headless. The
telemetry plumbing that carries the interesting logic lives in
:class:`TelemetryHub`, which is pure standard-library (queue + threads) and
testable without a display.
"""
from __future__ import annotations

import argparse
import queue
import threading
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Sequence, Tuple, cast

from dobotkit.gui.arm_controller import ArmController
from dobotkit.gui.arm_panel import ArmPanel
from dobotkit.gui.go_controller import GoController
from dobotkit.gui.go_panel import GoPanel
from dobotkit.gui.widgets import LogView, StatusBar

if TYPE_CHECKING:
    # Only needed to name the injection-boundary cast targets below; kept behind
    # TYPE_CHECKING so importing the app never eagerly pulls the device modules
    # (serial/websockets stay lazy).
    from dobotkit.arm.magician import Magician
    from dobotkit.go.client import DobotLinkClient
    from dobotkit.go.magiciango import MagicianGO

__all__ = ["App", "TelemetryHub", "main"]

#: One telemetry item on the queue: the source controller name + its snapshot.
Snapshot = Dict[str, Any]
TelemetryItem = Tuple[str, Snapshot]

#: A source the hub polls: a name and a zero-arg snapshot reader.
SnapshotSource = Tuple[str, Callable[[], Snapshot]]

#: Default telemetry poll period (seconds). One read per source per period.
DEFAULT_POLL_INTERVAL: float = 0.3

#: Default Tk-side drain period (milliseconds) for ``self.after`` loops.
DEFAULT_DRAIN_MS: int = 100


class TelemetryHub:
    """Background poller + thread-safe queue feeding the Tk refresh loop.

    Owns one daemon thread per registered source. Each thread repeatedly calls
    its source's ``snapshot()`` and pushes ``(name, snapshot)`` onto a shared
    queue, sleeping ``interval`` seconds between reads (interruptibly, so
    :meth:`stop` returns promptly). The Tk side calls :meth:`drain` from an
    ``after`` callback to pull queued items and dispatch each to the matching
    panel -- keeping every widget touch on the main thread.

    This class is deliberately free of any Tkinter dependency so the queue/drain
    logic can be unit-tested headless.

    Args:
        sources: ``(name, snapshot_callable)`` pairs to poll. ``name`` routes the
            snapshot to a handler registered via :meth:`on`.
        interval: Seconds between successive reads of each source.
    """

    def __init__(
        self,
        sources: Sequence[SnapshotSource],
        *,
        interval: float = DEFAULT_POLL_INTERVAL,
    ) -> None:
        self._sources: List[SnapshotSource] = list(sources)
        self._interval = float(interval)
        self._queue: "queue.Queue[TelemetryItem]" = queue.Queue()
        self._stop = threading.Event()
        self._threads: List[threading.Thread] = []
        self._handlers: Dict[str, Callable[[Snapshot], None]] = {}

    # -- wiring ------------------------------------------------------------ #
    def on(self, name: str, handler: Callable[[Snapshot], None]) -> None:
        """Register the handler that receives ``name``'s snapshots on :meth:`drain`."""
        self._handlers[name] = handler

    @property
    def queue(self) -> "queue.Queue[TelemetryItem]":
        """The shared telemetry queue (exposed for tests)."""
        return self._queue

    # -- lifecycle --------------------------------------------------------- #
    def start(self) -> None:
        """Spawn one daemon polling thread per source (idempotent)."""
        if self._threads:
            return
        self._stop.clear()
        for name, reader in self._sources:
            thread = threading.Thread(
                target=self._poll_loop,
                args=(name, reader),
                name=f"telemetry-{name}",
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

    def _poll_loop(self, name: str, reader: Callable[[], Snapshot]) -> None:
        """Poll one source until stopped; never let a read error kill the thread."""
        while not self._stop.is_set():
            try:
                snap = reader()
            except Exception as exc:  # noqa: BLE001 -- a bad read must not kill polling
                snap = {"error": str(exc)}
            self._queue.put((name, snap))
            # Interruptible sleep: wake immediately when stop is signalled.
            self._stop.wait(self._interval)

    def stop(self, *, timeout: float = 1.0) -> None:
        """Signal all polling threads to stop and join them (best-effort)."""
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=timeout)
        self._threads = []

    # -- draining ---------------------------------------------------------- #
    def drain(self) -> int:
        """Dispatch every queued snapshot to its handler. Call on the Tk thread.

        Returns the number of items dispatched. A handler exception is swallowed
        (so one panel's refresh error can never stall the drain loop) but still
        counts as dispatched.
        """
        dispatched = 0
        while True:
            try:
                name, snap = self._queue.get_nowait()
            except queue.Empty:
                break
            dispatched += 1
            handler = self._handlers.get(name)
            if handler is not None:
                try:
                    handler(snap)
                except Exception:  # noqa: BLE001 -- a refresh error must not stall drain
                    pass
        return dispatched


class App(tk.Tk):
    """The main application window: notebook of Arm / GO / Log tabs + status bar.

    Args:
        arm_controller: The arm logic adapter driving the Arm tab.
        go_controller: The GO logic adapter driving the GO tab.
        poll_interval: Telemetry poll period (seconds) per controller.
        drain_ms: Tk-side queue-drain period (milliseconds).
    """

    def __init__(
        self,
        arm_controller: ArmController,
        go_controller: GoController,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        drain_ms: int = DEFAULT_DRAIN_MS,
    ) -> None:
        super().__init__()
        self.title("dobotkit control panel")
        self.geometry("900x720")

        self.arm_controller = arm_controller
        self.go_controller = go_controller
        self._drain_ms = int(drain_ms)
        self._drain_after_id: Optional[str] = None
        self._closing = False

        # -- layout: notebook (top) + status bar (bottom) ----------------- #
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(self)
        notebook.grid(row=0, column=0, sticky="nsew")

        # Log tab first so a shared log(...) sink exists before the panels build.
        self.log_view = LogView(notebook, height=20, width=90)
        self.arm_panel = ArmPanel(notebook, arm_controller, self.log)
        self.go_panel = GoPanel(notebook, go_controller, self.log)

        notebook.add(self.arm_panel, text="Arm")
        notebook.add(self.go_panel, text="GO")
        notebook.add(self.log_view, text="Log")

        self.status = StatusBar(self, initial="Ready")
        self.status.grid(row=1, column=0, sticky="ew")

        # -- telemetry hub ------------------------------------------------- #
        self._hub = TelemetryHub(
            [
                ("arm", self.arm_controller.snapshot),
                ("go", self.go_controller.snapshot),
            ],
            interval=poll_interval,
        )
        self._hub.on("arm", self._refresh_arm)
        self._hub.on("go", self._refresh_go)

        self.log("dobotkit GUI started")
        self._hub.start()
        self._schedule_drain()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # -- shared log -------------------------------------------------------- #
    def log(self, msg: str) -> None:
        """Thread-safe shared log sink: queue a line for the Log tab.

        Safe to call from any thread -- :meth:`LogView.log` only enqueues; the
        text widget is written on the Tk thread by :meth:`_schedule_drain`.
        """
        self.log_view.log(msg)

    # -- telemetry refresh handlers (run on the Tk thread via drain) ------- #
    def _refresh_arm(self, snap: Snapshot) -> None:
        self.arm_panel.refresh(snap)
        self._update_status()

    def _refresh_go(self, snap: Snapshot) -> None:
        self.go_panel.refresh(snap)
        self._update_status()

    def _update_status(self) -> None:
        arm = "connected" if self.arm_controller.is_connected else "off"
        go = "connected" if self.go_controller.is_connected else "off"
        self.status.set(f"Arm: {arm}   |   GO: {go}")

    # -- Tk-thread drain loop ---------------------------------------------- #
    def _schedule_drain(self) -> None:
        """Drain the telemetry queue + log queue, then reschedule (Tk thread)."""
        if self._closing:
            return
        self._hub.drain()
        self.log_view.drain()
        self._drain_after_id = self.after(self._drain_ms, self._schedule_drain)

    # -- teardown ---------------------------------------------------------- #
    def on_close(self) -> None:
        """Stop threads, disconnect controllers, and destroy the window cleanly."""
        if self._closing:
            return
        self._closing = True
        # Cancel the pending drain so no after-callback fires post-destroy.
        if self._drain_after_id is not None:
            try:
                self.after_cancel(self._drain_after_id)
            except tk.TclError:
                pass
            self._drain_after_id = None
        # Stop background polling before touching the controllers.
        self._hub.stop()
        # Best-effort disconnect -- a controller never raises out of disconnect().
        for controller in (self.arm_controller, self.go_controller):
            try:
                controller.disconnect()
            except Exception:  # noqa: BLE001 -- teardown must not raise
                pass
        self.destroy()


# --------------------------------------------------------------------------- #
# main entry point
# --------------------------------------------------------------------------- #
def _build_parser() -> argparse.ArgumentParser:
    """Build the ``dobotkit.gui`` command-line parser."""
    parser = argparse.ArgumentParser(
        prog="python -m dobotkit.gui",
        description="Tkinter control panel for the Dobot Magician arm and GO car.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run against in-memory fake devices (no hardware, no DobotLink).",
    )
    parser.add_argument(
        "--arm-port",
        default="auto",
        help="Serial port for the arm (e.g. COM3, /dev/ttyUSB0). Default: auto.",
    )
    parser.add_argument(
        "--go-port",
        default="COM5",
        help="DobotLink COM port name for the GO. Default: COM5.",
    )
    parser.add_argument(
        "--dobotlink-host",
        default="localhost",
        help="DobotLink WebSocket host. Default: localhost.",
    )
    parser.add_argument(
        "--dobotlink-port",
        type=int,
        default=9090,
        help="DobotLink WebSocket port. Default: 9090.",
    )
    return parser


def _build_controllers(
    args: argparse.Namespace,
) -> Tuple[ArmController, GoController]:
    """Construct the arm + GO controllers, injecting demo fakes under ``--demo``.

    In ``--demo`` mode the controllers are seeded with the
    :mod:`dobotkit.gui._demo` fakes so the whole UI runs with no hardware. In a
    real run they are built empty and connect lazily from the panels' Connect
    buttons (using the ports parsed here as the panels' defaults where relevant).
    """
    if args.demo:
        # Import here so a real (non-demo) run never imports the demo module.
        from dobotkit.gui._demo import FakeArmDevice, FakeGoDevice, FakeLinkClient

        # The fakes are structural stand-ins (duck-typed to the real devices'
        # public surface, not subclasses), so cast at this injection boundary to
        # satisfy the controllers' nominal parameter types.
        arm = ArmController(device=cast("Magician", FakeArmDevice()))
        # Inject a no-op link client too: the GO controller opens/closes a
        # DobotLink client alongside the GO, which must not hit a real socket.
        go = GoController(
            client=cast("DobotLinkClient", FakeLinkClient()),
            go=cast("MagicianGO", FakeGoDevice()),
        )
        return arm, go

    arm = ArmController()
    go = GoController()
    return arm, go


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Parse args, build the app, and run the Tk mainloop.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]`` when ``None``).

    Returns:
        Process exit code. ``0`` on a clean run, and also ``0`` (with a clear
        message) when no display is available so headless CI never fails here.
    """
    args = _build_parser().parse_args(argv)
    arm_controller, go_controller = _build_controllers(args)

    try:
        app = App(arm_controller, go_controller)
    except tk.TclError as exc:
        # No display / no Tk -- report clearly and exit success (headless-safe).
        print(
            "dobotkit.gui: cannot open a window (no display available). "
            f"Tk error: {exc}\n"
            "On Linux install the Tk runtime (e.g. 'sudo apt install python3-tk') "
            "and run in a graphical session."
        )
        return 0

    if args.demo:
        app.log("--demo: running against in-memory fake devices (no hardware).")
        # Auto-connect the demo devices so the tabs come up live immediately.
        app.arm_controller.connect(args.arm_port)
        app.go_controller.connect(
            host=args.dobotlink_host,
            port=args.dobotlink_port,
            port_name=args.go_port,
        )

    app.mainloop()
    return 0


if __name__ == "__main__":  # pragma: no cover -- exercised via -m, not imported
    raise SystemExit(main())
