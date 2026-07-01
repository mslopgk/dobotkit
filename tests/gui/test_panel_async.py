"""The arm panel must run blocking moves OFF the Tk thread (no UI freeze).

Guarded: skips where no display is available (headless CI). Where a display
exists it builds a real panel, drives a deliberately slow move, and asserts the
button callback returns immediately while the result is delivered later via the
main-thread pump.
"""
from __future__ import annotations

import time

import pytest

tk = pytest.importorskip("tkinter")

from dobotkit.gui._demo import FakeArmDevice  # noqa: E402
from dobotkit.gui.arm_controller import ArmController  # noqa: E402
from dobotkit.gui.arm_panel import ArmPanel  # noqa: E402


class _SlowArm(FakeArmDevice):
    """A demo arm whose move blocks, standing in for a real hardware move."""

    def move_to(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        time.sleep(0.4)
        return super().move_to(*args, **kwargs)


@pytest.fixture(scope="module")
def root():
    # One root for the module: repeatedly creating/destroying Tk() roots in a
    # single process is flaky on Windows, so share one and tear it down once.
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    r.withdraw()
    yield r
    r.destroy()


def test_move_does_not_block_the_ui_thread(root) -> None:
    logs: list = []
    ctrl = ArmController(device=_SlowArm())
    ctrl.connect("DEMO")
    panel = ArmPanel(root, ctrl, log=logs.append)
    panel._set_connected_state(True)
    for k, v in zip(("x", "y", "z", "r"), ("150", "10", "20", "0")):
        panel._abs_vars[k].set(v)

    start = time.monotonic()
    panel._on_move_to()
    # The callback must return promptly; the 0.4 s move runs on a worker thread.
    assert time.monotonic() - start < 0.15
    assert panel._motion_busy is True

    # Pump the event loop so the main-thread queue delivers the result.
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and panel._motion_busy:
        root.update()
        time.sleep(0.02)

    assert panel._motion_busy is False
    assert any("Moved to" in line and "[OK]" in line for line in logs)


def test_overlapping_move_is_rejected_while_busy(root) -> None:
    logs: list = []
    ctrl = ArmController(device=_SlowArm())
    ctrl.connect("DEMO")
    panel = ArmPanel(root, ctrl, log=logs.append)
    panel._set_connected_state(True)

    panel._on_move_to()          # starts a slow move (busy)
    logs.clear()
    panel._on_move_to()          # second click while busy -> rejected, not queued
    assert any("[BUSY]" in line for line in logs)

    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and panel._motion_busy:
        root.update()
        time.sleep(0.02)
    assert panel._motion_busy is False
