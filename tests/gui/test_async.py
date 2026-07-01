"""Unit tests for the off-main-thread action runner (headless, no Tk)."""
from __future__ import annotations

import threading
import time

from dobotkit.gui._async import run_in_thread


def _drain(scheduled: list) -> None:
    """Run every callback a fake ``schedule`` captured (mimics the UI thread)."""
    while scheduled:
        scheduled.pop(0)()


def test_runs_fn_and_reports_result_off_the_calling_thread() -> None:
    scheduled: list = []
    caller = threading.get_ident()
    ran_on: dict = {}
    done: dict = {}

    def fn() -> int:
        ran_on["ident"] = threading.get_ident()
        return 42

    def on_done(result, error) -> None:
        done["result"], done["error"] = result, error

    t = run_in_thread(fn, on_done, schedule=scheduled.append)
    t.join(timeout=2)
    _drain(scheduled)  # the UI thread would run the scheduled callback

    assert done == {"result": 42, "error": None}
    assert ran_on["ident"] != caller, "fn must run OFF the calling thread"


def test_captures_exception_instead_of_raising() -> None:
    scheduled: list = []
    done: dict = {}

    def fn() -> None:
        raise RuntimeError("boom")

    def on_done(result, error) -> None:
        done["result"], done["error"] = result, error

    run_in_thread(fn, on_done, schedule=scheduled.append).join(timeout=2)
    _drain(scheduled)

    assert done["result"] is None
    assert isinstance(done["error"], RuntimeError)
    assert "boom" in str(done["error"])


def test_does_not_block_the_caller() -> None:
    scheduled: list = []
    started = time.monotonic()

    def slow() -> str:
        time.sleep(0.3)
        return "ok"

    t = run_in_thread(slow, lambda r, e: None, schedule=scheduled.append)
    # Control returns essentially immediately, well before slow() finishes.
    assert time.monotonic() - started < 0.2
    t.join(timeout=2)
