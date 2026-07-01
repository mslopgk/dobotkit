"""Import-safety tests for :mod:`dobotkit.gui.go_panel`.

The GUI package is contractually import-safe **headless**: importing any gui
module must only *define* classes/functions and must never construct a ``Tk()``
root or open a window. These tests verify that ``dobotkit.gui.go_panel``:

* imports cleanly (``import dobotkit.gui.go_panel``);
* does so **without** creating a ``Tk`` root -- checked out-of-process so an
  unrelated in-process ``tkinter`` import by another test cannot mask a
  regression (the panel must not build a default root at import time);
* exposes the expected public surface (:class:`GoPanel`).
"""
from __future__ import annotations

import importlib
import subprocess
import sys


def test_import_go_panel() -> None:
    """`import dobotkit.gui.go_panel` succeeds and exposes GoPanel."""
    mod = importlib.import_module("dobotkit.gui.go_panel")
    assert hasattr(mod, "GoPanel")
    assert "GoPanel" in getattr(mod, "__all__", [])


def test_import_creates_no_tk_root() -> None:
    """Importing the module must not construct a Tk default root.

    Run out-of-process: import the module, then assert that tkinter (if pulled in
    at all) has no live default root. This proves the module only *defines*
    ``GoPanel`` and never instantiates a window at import time.
    """
    code = (
        "import importlib\n"
        "importlib.import_module('dobotkit.gui.go_panel')\n"
        "import tkinter\n"
        "assert tkinter._default_root is None, 'a Tk root was created at import'\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        "importing go_panel must not create a Tk root; "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
