"""dobotkit.arm -- Magician Lite (4-axis arm) control over a pure-Python serial protocol.

This subpackage reimplements the full Dobot serial command set (no DLL) and
layers an ergonomic, safety-first API on top of it. The exported names are:

* :class:`~dobotkit.arm.magician.Magician` -- the high-level, Pythonic API
  (context manager, ``move_to``/``home``/``pick_and_place``, ``.io``/
  ``.sensors``/``.effector`` groups, pydobot-compatible aliases).
* :class:`~dobotkit.arm.lowlevel.LowLevelArm` -- the complete 1:1 mapping of
  every official SDK function, for niche commands the high-level API does not
  wrap.
* :class:`~dobotkit.arm.transport.SerialTransport` -- the raw serial transport.

Names are resolved through a module-level :func:`__getattr__` (PEP 562) so that
merely importing :mod:`dobotkit.arm` does not eagerly pull in ``pyserial``; the
``serial`` dependency is imported only when one of these classes is first
accessed.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - for type checkers only, not imported at runtime
    from .lowlevel import LowLevelArm
    from .magician import Magician
    from .transport import SerialTransport

# Public name -> (submodule, attribute). Deferred to first access so importing
# this subpackage never eagerly imports ``serial``.
_LAZY = {
    "Magician": ("dobotkit.arm.magician", "Magician"),
    "LowLevelArm": ("dobotkit.arm.lowlevel", "LowLevelArm"),
    "SerialTransport": ("dobotkit.arm.transport", "SerialTransport"),
}

__all__ = ["LowLevelArm", "Magician", "SerialTransport"]


def __getattr__(name: str) -> Any:
    """Lazily resolve the arm classes on first access (PEP 562)."""
    target = _LAZY.get(name)
    if target is not None:
        import importlib

        module_name, attr = target
        value = getattr(importlib.import_module(module_name), attr)
        globals()[name] = value  # cache so repeat access skips the import machinery
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> "list[str]":
    return sorted(set(globals()) | set(__all__))
