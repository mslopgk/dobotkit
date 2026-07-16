"""dobotkit.arm -- Magician Lite (4-axis arm) control over DobotLink.

This subpackage wraps the DobotLink ``Magician.*`` RPC surface
(:mod:`dobotkit.arm.commands`) and layers an ergonomic, safety-first API on
top of it. The exported name is:

* :class:`~dobotkit.arm.magicianlite.MagicianLite` -- the high-level,
  Pythonic API (context manager, ``move_to``/``home``/``pick_and_place``,
  ``.io``/``.sensors``/``.effector`` groups).

Names are resolved through a module-level :func:`__getattr__` (PEP 562) so
that merely importing :mod:`dobotkit.arm` does not eagerly pull in
``websockets``; that dependency is imported only when the class is first
accessed.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - for type checkers only, not imported at runtime
    from .magicianlite import MagicianLite

# Public name -> (submodule, attribute). Deferred to first access so importing
# this subpackage never eagerly imports ``websockets``.
_LAZY = {
    "MagicianLite": ("dobotkit.arm.magicianlite", "MagicianLite"),
}

__all__ = ["MagicianLite"]


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
