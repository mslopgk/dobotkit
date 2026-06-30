"""dobotkit.go -- Magician GO control over the DobotLink WebSocket (JSON-RPC).

This subpackage wraps the DobotLink ``MagicianGO.*`` RPC surface and layers
sensor-feedback navigation on top of it. It talks to ``ws://localhost:9090``
via the ``websockets`` library; nothing here touches the arm's serial stack.

Exported names:

* :class:`~dobotkit.go.client.DobotLinkClient` -- the WebSocket JSON-RPC client.
* :class:`~dobotkit.go.magiciango.MagicianGO` -- the high-level GO wrapper
  (continuous drive, sensors, camera, LED/buzzer, line-trace).
* :class:`~dobotkit.go.navigation.PreciseMover` /
  :class:`~dobotkit.go.navigation.WaypointNav` -- sensor-feedback closed-loop
  motion and absolute mat-coordinate navigation.

Names are resolved through a module-level :func:`__getattr__` (PEP 562) so that
merely importing :mod:`dobotkit.go` stays light (no ``websockets`` import, no
socket); the dependency is pulled in only when one of these classes is first
accessed. A program controlling only the arm never imports the GO stack.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - for type checkers only, not imported at runtime
    from .client import DobotLinkClient
    from .magiciango import MagicianGO
    from .navigation import PreciseMover, WaypointNav

# Public name -> (submodule, attribute). Deferred to first access so importing
# this subpackage never eagerly imports ``websockets``.
_LAZY = {
    "DobotLinkClient": ("dobotkit.go.client", "DobotLinkClient"),
    "MagicianGO": ("dobotkit.go.magiciango", "MagicianGO"),
    "PreciseMover": ("dobotkit.go.navigation", "PreciseMover"),
    "WaypointNav": ("dobotkit.go.navigation", "WaypointNav"),
}

__all__ = ["DobotLinkClient", "MagicianGO", "PreciseMover", "WaypointNav"]


def __getattr__(name: str) -> Any:
    """Lazily resolve the GO classes on first access (PEP 562)."""
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
