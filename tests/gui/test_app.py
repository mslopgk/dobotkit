"""Headless-safe tests for :mod:`dobotkit.gui.app` and :mod:`dobotkit.gui._demo`.

Covers three independent layers so the suite passes with *or* without a display:

* **Import safety** -- importing ``app`` / ``_demo`` must not create a ``Tk()``
  root or open a window (only define classes/functions).
* **Demo fakes -> controllers.** A :class:`GoController` / :class:`ArmController`
  built on the ``_demo`` fakes must connect and produce a well-shaped
  ``snapshot()`` -- the exact path the telemetry loop drives.
* **Telemetry queue-drain in isolation.** :class:`TelemetryHub` (the factored-out
  queue/thread plumbing) is pure standard library, so its poll -> queue -> drain
  dispatch is tested with no Tk at all, including the real background threads.
* **App construction, only if a display exists.** ``App()`` is attempted inside a
  ``try/except tk.TclError``; with no display the test skips, otherwise it builds
  the window, pumps one idle cycle, and tears it down via ``on_close``.

Run: ``python -m pytest tests/gui -q``
"""
from __future__ import annotations

import importlib
import time
import tkinter as tk

import pytest

from dobotkit.gui import _demo, app
from dobotkit.gui.app import App, TelemetryHub
from dobotkit.gui.arm_controller import ArmController
from dobotkit.gui.go_controller import GoController


# --------------------------------------------------------------------------- #
# Import safety
# --------------------------------------------------------------------------- #
def test_modules_import_headless_safe() -> None:
    """Importing app / _demo defines the public names without opening a window."""
    importlib.import_module("dobotkit.gui.app")
    importlib.import_module("dobotkit.gui._demo")
    assert hasattr(app, "App")
    assert hasattr(app, "TelemetryHub")
    assert callable(app.main)
    assert hasattr(_demo, "FakeArmDevice")
    assert hasattr(_demo, "FakeGoDevice")


# --------------------------------------------------------------------------- #
# Demo fakes drive the controllers' snapshot() path
# --------------------------------------------------------------------------- #
def test_arm_controller_snapshot_through_demo_fake() -> None:
    """ArmController(device=FakeArmDevice) connects and yields a real snapshot."""
    controller = ArmController(device=_demo.FakeArmDevice())
    ok, _msg = controller.connect("auto")
    assert ok is True
    assert controller.is_connected is True

    snap = controller.snapshot()
    assert snap["connected"] is True
    assert snap["error"] is None
    # Pose is fully populated from the fake's get_pose().
    assert isinstance(snap["pose"], dict)
    for key in ("x", "y", "z", "r", "j1", "j2", "j3", "j4"):
        assert isinstance(snap["pose"][key], (int, float))
    # The demo fake never reports active alarms.
    assert snap["alarms"] == []


def test_arm_demo_move_and_jog_change_pose() -> None:
    """Moving / jogging the demo arm visibly shifts the reported pose."""
    device = _demo.FakeArmDevice()
    controller = ArmController(device=device)
    controller.connect("auto")

    controller.move_to(100.0, 50.0, -20.0, 10.0)
    moved = controller.snapshot()["pose"]
    assert moved["x"] == pytest.approx(100.0, abs=1.0)
    assert moved["y"] == pytest.approx(50.0, abs=1.0)

    # A jog nudges the pose away from where it just was.
    before_x = controller.snapshot()["pose"]["x"]
    controller.jog_start(1, True)  # X positive
    controller.jog_stop()
    after_x = controller.snapshot()["pose"]["x"]
    assert after_x != before_x


def test_arm_demo_device_info() -> None:
    """device_info() reads the fake lowlevel SN/name/version with no error."""
    controller = ArmController(device=_demo.FakeArmDevice())
    controller.connect("auto")
    info = controller.device_info()
    assert info["error"] is None
    assert info["sn"] == "DEMO-SN-0001"
    assert info["name"]
    assert info["version"]


def test_go_controller_snapshot_through_demo_fake() -> None:
    """GoController(go=FakeGoDevice) connects and yields a real snapshot."""
    controller = GoController(client=_demo.FakeLinkClient(), go=_demo.FakeGoDevice())
    ok, _msg = controller.connect(port_name="DEMO")
    assert ok is True
    assert controller.is_connected is True

    snap = controller.snapshot()
    assert snap["connected"] is True
    assert snap["error"] is None
    assert set(snap["ultrasonic"]) == {"front", "back", "left", "right"}
    assert set(snap["odometer"]) == {"x", "y", "yaw"}
    assert snap["imu"]["yaw"] is not None
    assert snap["battery"]["voltage"] is not None
    assert snap["battery"]["percentage"] is not None


def test_go_demo_drive_advances_odometer() -> None:
    """Latching a forward velocity makes successive odometer reads advance."""
    controller = GoController(client=_demo.FakeLinkClient(), go=_demo.FakeGoDevice())
    controller.connect(port_name="DEMO")

    start_x = controller.snapshot()["odometer"]["x"]
    controller.drive_forward(40.0)
    # Each snapshot read advances the sim; take a couple to accumulate motion.
    controller.snapshot()
    moved_x = controller.snapshot()["odometer"]["x"]
    assert moved_x > start_x

    controller.stop()
    stopped_x = controller.snapshot()["odometer"]["x"]
    later_x = controller.snapshot()["odometer"]["x"]
    assert later_x == pytest.approx(stopped_x, abs=0.01)


# --------------------------------------------------------------------------- #
# TelemetryHub queue-drain logic in isolation (no Tk)
# --------------------------------------------------------------------------- #
def test_hub_drain_dispatches_to_registered_handlers() -> None:
    """drain() routes each queued (name, snapshot) to the matching handler."""
    hub = TelemetryHub(sources=[])  # no threads; we feed the queue directly
    received: dict[str, list] = {"arm": [], "go": []}
    hub.on("arm", lambda s: received["arm"].append(s))
    hub.on("go", lambda s: received["go"].append(s))

    hub.queue.put(("arm", {"connected": True}))
    hub.queue.put(("go", {"connected": False}))
    hub.queue.put(("arm", {"connected": False}))

    dispatched = hub.drain()
    assert dispatched == 3
    assert received["arm"] == [{"connected": True}, {"connected": False}]
    assert received["go"] == [{"connected": False}]
    # Queue is emptied; a second drain dispatches nothing.
    assert hub.drain() == 0


def test_hub_drain_swallows_handler_errors() -> None:
    """A raising handler is isolated: drain still processes the rest."""
    hub = TelemetryHub(sources=[])
    seen: list = []

    def boom(_s: object) -> None:
        raise RuntimeError("handler blew up")

    hub.on("bad", boom)
    hub.on("good", lambda s: seen.append(s))
    hub.queue.put(("bad", {"x": 1}))
    hub.queue.put(("good", {"x": 2}))

    assert hub.drain() == 2  # both counted despite the exception
    assert seen == [{"x": 2}]


def test_hub_unknown_source_name_is_ignored() -> None:
    """A snapshot for an unregistered name drains without error (no handler)."""
    hub = TelemetryHub(sources=[])
    hub.queue.put(("nobody", {"x": 1}))
    assert hub.drain() == 1


def test_hub_poll_loop_reads_source_and_stops_cleanly() -> None:
    """A real background thread polls the source, queues snapshots, then stops."""
    calls = {"n": 0}

    def reader() -> dict:
        calls["n"] += 1
        return {"tick": calls["n"]}

    hub = TelemetryHub([("src", reader)], interval=0.01)
    hub.start()
    try:
        # Wait until at least one snapshot lands on the queue.
        deadline = time.monotonic() + 2.0
        while hub.queue.empty() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not hub.queue.empty()
    finally:
        hub.stop(timeout=2.0)

    # After stop() every polling thread has been joined.
    assert all(not t.is_alive() for t in hub._threads) if hub._threads else True

    captured: list = []
    hub.on("src", lambda s: captured.append(s))
    drained = hub.drain()
    assert drained >= 1
    assert captured and captured[0]["tick"] >= 1


def test_hub_poll_loop_survives_reader_exception() -> None:
    """A reader that raises does not kill the thread; the error is queued."""
    def bad_reader() -> dict:
        raise ValueError("sensor offline")

    hub = TelemetryHub([("src", bad_reader)], interval=0.01)
    hub.start()
    try:
        deadline = time.monotonic() + 2.0
        while hub.queue.empty() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not hub.queue.empty()
        _name, snap = hub.queue.get_nowait()
        assert "error" in snap and "sensor offline" in snap["error"]
    finally:
        hub.stop(timeout=2.0)


# --------------------------------------------------------------------------- #
# App construction -- only when a display is available
# --------------------------------------------------------------------------- #
def _make_app() -> App:
    """Build an App on demo controllers, or raise tk.TclError with no display."""
    arm = ArmController(device=_demo.FakeArmDevice())
    go = GoController(client=_demo.FakeLinkClient(), go=_demo.FakeGoDevice())
    # A short drain interval keeps the single update cycle snappy.
    return App(arm, go, poll_interval=0.05, drain_ms=20)


def test_app_constructs_and_tears_down_if_display() -> None:
    """If a display exists, build the window, pump one cycle, and close cleanly."""
    try:
        application = _make_app()
    except tk.TclError:
        pytest.skip("no display available for Tk")

    try:
        # One idle cycle: builds/lays out widgets and runs pending callbacks.
        application.update_idletasks()
        application.update()
        # The three tabs and the status bar are wired up.
        assert application.arm_panel is not None
        assert application.go_panel is not None
        assert application.log_view is not None
    finally:
        # on_close stops the telemetry threads, disconnects, and destroys.
        application.on_close()

    # Idempotent: a second close is a no-op and does not raise.
    application.on_close()
