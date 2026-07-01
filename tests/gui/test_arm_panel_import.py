"""Headless import-safety test for :mod:`dobotkit.gui.arm_panel`.

Importing the GUI panel module must only *define* :class:`ArmPanel` -- it must
not construct a ``Tk()`` root or open a window. This lets the module be imported
on CI / no-display runners. The test therefore just imports the module (no widget
construction) and asserts the class is present and is a ``ttk.Frame`` subclass.
"""
from __future__ import annotations

import importlib
from tkinter import ttk


def test_import_arm_panel_is_headless_safe() -> None:
    module = importlib.import_module("dobotkit.gui.arm_panel")
    # The class is defined by import alone -- no Tk() root was created.
    assert hasattr(module, "ArmPanel")
    assert issubclass(module.ArmPanel, ttk.Frame)
