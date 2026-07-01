"""Run a blocking device call off the Tk main thread, then report back on it.

The GUI's control callbacks run on the Tk event-loop thread. A blocking arm
call -- notably a queued move waited on with ``wait=True``, which polls the
command queue for up to its timeout -- would freeze the entire UI (no redraw,
no button responds, telemetry stalls) for the duration of the move. That is the
motion-section "does nothing / frozen" symptom on real hardware.

:func:`run_in_thread` moves such a call onto a short-lived daemon thread and
marshals its outcome back onto the UI thread via a ``schedule`` callback (the
caller passes ``widget.after`` so the result is delivered on the main loop,
where it is safe to touch widgets). Quick, non-blocking actions do not need
this; it is meant for the handful of calls that can block.
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Optional

__all__ = ["run_in_thread"]

# A UI-thread scheduler: given a zero-arg callback, arrange to run it on the
# main loop (e.g. ``lambda cb: widget.after(0, cb)``).
Scheduler = Callable[[Callable[[], None]], Any]
# Completion handler, invoked on the UI thread: (result, error) with exactly one
# meaningful -- error is None on success, else the raised exception.
OnDone = Callable[[Any, Optional[BaseException]], None]


def run_in_thread(
    fn: Callable[[], Any],
    on_done: OnDone,
    schedule: Scheduler,
) -> threading.Thread:
    """Run ``fn()`` on a daemon thread and deliver its outcome via ``schedule``.

    Args:
        fn: The (potentially blocking) callable to run off the UI thread.
        on_done: Called as ``on_done(result, error)`` -- ``error`` is ``None``
            on success (``result`` is ``fn``'s return), otherwise ``result`` is
            ``None`` and ``error`` is the exception ``fn`` raised. It is invoked
            via ``schedule``, i.e. on the UI thread, so it may touch widgets.
        schedule: Posts a zero-arg callback onto the UI thread (pass
            ``lambda cb: widget.after(0, cb)``).

    Returns:
        The started :class:`threading.Thread` (already running; daemon).
    """

    def worker() -> None:
        try:
            result: Any = fn()
            error: Optional[BaseException] = None
        except BaseException as exc:  # noqa: BLE001 - any failure is reported, not raised
            result, error = None, exc
        # Marshal back to the UI thread; never touch widgets from here.
        schedule(lambda: on_done(result, error))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread
