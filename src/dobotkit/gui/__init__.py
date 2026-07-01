"""dobotkit.gui -- a Tkinter control-panel front end for the arm and the GO.

This subpackage hosts the graphical control surface layered on top of the
:mod:`dobotkit.arm` and :mod:`dobotkit.go` public APIs. It is split into three
layers:

* **widgets** (:mod:`dobotkit.gui.widgets`) -- reusable, generic ``ttk`` helpers
  (section frames, live value grids, press-and-hold jog buttons, a thread-safe
  log view, a status bar). Pure view code with no device knowledge.
* **controllers** -- thin, fully-typed adapters that translate widget events
  into calls on :class:`~dobotkit.arm.magician.Magician` /
  :class:`~dobotkit.go.magiciango.MagicianGO` and push readings back to the
  view. These carry the logic and are held to the full type gate.
* **app** -- the window/layout wiring and ``main()`` entry point.

Import safety
-------------
Every module in this package is import-safe **headless**: importing it only
*defines* classes and functions and never constructs a ``Tk()`` root or opens a
window. A real root is created only when the application actually launches (see
:mod:`dobotkit.gui.__main__` / ``app.main``). This keeps the package importable
on CI and in tests that have no display.

Submodules are intentionally **not** imported eagerly here, so ``import
dobotkit.gui`` stays cheap and pulls in ``tkinter`` only when a submodule that
needs it is imported explicitly.
"""
from __future__ import annotations

__all__: list[str] = []
