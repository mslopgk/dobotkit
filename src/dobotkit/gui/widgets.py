"""Reusable ``ttk`` building blocks for the dobotkit GUI.

These are generic, device-agnostic view helpers. Importing this module only
imports ``tkinter``/``tkinter.ttk`` and *defines* the classes below; it never
constructs a ``Tk()`` root or opens a window. Every widget is a subclass of a
``tkinter``/``ttk`` widget and therefore requires a live master (a ``Tk`` root or
another widget) to be *instantiated* -- but that only happens when the app runs,
not at import time.

Provided widgets:

* :class:`SectionFrame` -- a titled ``ttk.LabelFrame`` wrapper.
* :class:`LabeledValue` -- a caption label beside a live-updatable value label.
* :class:`ValueGrid` -- a grid of :class:`LabeledValue` addressed by key, with a
  bulk :meth:`~ValueGrid.update_values` from a dict.
* :class:`JogButton` -- a press-and-hold button firing a callback on
  ``<ButtonPress>`` and another on ``<ButtonRelease>`` (for continuous jog).
* :class:`LogView` -- a scrolled, read-only ``Text`` with a thread-safe,
  timestamped :meth:`~LogView.log`; messages are queued and drained on the Tk
  thread by the owner via :meth:`~LogView.drain`.
* :class:`StatusBar` -- a one-line status label pinned along the bottom.
"""
from __future__ import annotations

import queue
import time
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, Mapping, Optional

__all__ = [
    "SectionFrame",
    "LabeledValue",
    "ValueGrid",
    "JogButton",
    "LogView",
    "StatusBar",
]


class SectionFrame(ttk.LabelFrame):
    """A titled container -- a thin ``ttk.LabelFrame`` wrapper.

    Groups related controls under a bordered, captioned box. Extra keyword
    arguments are forwarded to :class:`ttk.LabelFrame`.
    """

    def __init__(
        self, master: tk.Misc, title: str = "", *, padding: Any = 8, **kwargs: Any
    ) -> None:
        super().__init__(master, text=title, padding=padding, **kwargs)


class LabeledValue(ttk.Frame):
    """A caption label next to a value label whose text can be updated live.

    Use :meth:`set` to replace the displayed value at runtime. The current text
    is also readable via :attr:`value`.
    """

    def __init__(
        self,
        master: tk.Misc,
        caption: str,
        value: str = "-",
        *,
        caption_width: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, **kwargs)
        self._var = tk.StringVar(master=self, value=value)
        cap_kwargs: Dict[str, Any] = {}
        if caption_width:
            cap_kwargs["width"] = caption_width
        self.caption_label = ttk.Label(self, text=caption, **cap_kwargs)
        self.value_label = ttk.Label(self, textvariable=self._var)
        self.caption_label.grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.value_label.grid(row=0, column=1, sticky="w")

    def set(self, text: object) -> None:
        """Set the displayed value (stringified)."""
        self._var.set(str(text))

    @property
    def value(self) -> str:
        """The currently displayed value text."""
        return self._var.get()


class ValueGrid(ttk.Frame):
    """A grid of :class:`LabeledValue` rows addressed by string key.

    Build it from an ordered mapping of ``key -> caption``; read values back and
    update them in bulk with :meth:`update_values`.
    """

    def __init__(
        self,
        master: tk.Misc,
        fields: Mapping[str, str],
        *,
        columns: int = 1,
        caption_width: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, **kwargs)
        self._rows: Dict[str, LabeledValue] = {}
        cols = max(1, int(columns))
        for i, (key, caption) in enumerate(fields.items()):
            row, col = divmod(i, cols)
            lv = LabeledValue(self, caption, caption_width=caption_width)
            lv.grid(row=row, column=col, sticky="w", padx=6, pady=2)
            self._rows[key] = lv

    def set_value(self, key: str, text: object) -> None:
        """Set a single field by key (ignored if the key is unknown)."""
        row = self._rows.get(key)
        if row is not None:
            row.set(text)

    def update_values(self, values: Mapping[str, object]) -> None:
        """Bulk-update fields from a mapping; unknown keys are ignored."""
        for key, text in values.items():
            self.set_value(key, text)

    def keys(self) -> "list[str]":
        """The field keys, in insertion order."""
        return list(self._rows)


class JogButton(ttk.Button):
    """A press-and-hold button for continuous ("jog") actions.

    Fires ``on_press`` on ``<ButtonPress-1>`` (start moving) and ``on_release``
    on ``<ButtonRelease-1>`` (stop). Either callback may be ``None``. This is the
    natural control for velocity-style commands where holding the button drives
    the device and letting go halts it.
    """

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        on_press: Optional[Callable[[], object]] = None,
        on_release: Optional[Callable[[], object]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, text=text, **kwargs)
        self._on_press = on_press
        self._on_release = on_release
        self.bind("<ButtonPress-1>", self._handle_press)
        self.bind("<ButtonRelease-1>", self._handle_release)

    def _handle_press(self, _event: "tk.Event[tk.Misc]") -> None:
        if self._on_press is not None:
            self._on_press()

    def _handle_release(self, _event: "tk.Event[tk.Misc]") -> None:
        if self._on_release is not None:
            self._on_release()


class LogView(ttk.Frame):
    """A scrolled, read-only text log with a thread-safe writer.

    :meth:`log` may be called from any thread: it timestamps the message and
    pushes it onto an internal :class:`queue.Queue`. The owner (running on the Tk
    thread) periodically calls :meth:`drain` -- e.g. from a ``root.after`` loop --
    to move queued lines into the ``Text`` widget. This keeps all Tk mutation on
    the main thread, which Tkinter requires.
    """

    def __init__(
        self,
        master: tk.Misc,
        *,
        height: int = 10,
        width: int = 60,
        max_lines: int = 1000,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, **kwargs)
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._max_lines = max_lines

        self.text = tk.Text(
            self, height=height, width=width, state="disabled", wrap="word"
        )
        self._scroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=self._scroll.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        self._scroll.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    def log(self, msg: str) -> None:
        """Queue a timestamped message. Safe to call from any thread."""
        stamp = time.strftime("%H:%M:%S")
        self._queue.put(f"[{stamp}] {msg}")

    def drain(self) -> int:
        """Flush queued messages into the widget. Call on the Tk thread.

        Returns the number of lines appended.
        """
        lines = []
        while True:
            try:
                lines.append(self._queue.get_nowait())
            except queue.Empty:
                break
        if not lines:
            return 0
        self.text.configure(state="normal")
        for line in lines:
            self.text.insert("end", line + "\n")
        self._trim()
        self.text.see("end")
        self.text.configure(state="disabled")
        return len(lines)

    def clear(self) -> None:
        """Erase all displayed text (does not touch pending queued lines)."""
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def _trim(self) -> None:
        """Drop the oldest lines when the buffer exceeds ``max_lines``."""
        if self._max_lines <= 0:
            return
        # Text indices are 1-based lines; the trailing newline yields one extra.
        line_count = int(self.text.index("end-1c").split(".")[0])
        excess = line_count - self._max_lines
        if excess > 0:
            self.text.delete("1.0", f"{excess + 1}.0")


class StatusBar(ttk.Frame):
    """A one-line status label, meant to sit pinned along the window bottom.

    Update the shown text with :meth:`set`.
    """

    def __init__(
        self, master: tk.Misc, initial: str = "Ready", **kwargs: Any
    ) -> None:
        super().__init__(master, **kwargs)
        self._var = tk.StringVar(master=self, value=initial)
        self.label = ttk.Label(
            self, textvariable=self._var, anchor="w", relief="sunken", padding=(6, 2)
        )
        self.label.grid(row=0, column=0, sticky="ew")
        self.columnconfigure(0, weight=1)

    def set(self, text: str) -> None:
        """Set the status text."""
        self._var.set(text)

    @property
    def text(self) -> str:
        """The current status text."""
        return self._var.get()
