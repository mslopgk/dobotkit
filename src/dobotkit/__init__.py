"""dobotkit -- complete pure-Python control for Dobot Magician Lite and Magician GO.

This module is the single public front door to the library. What it exposes:

* **Eager, light-weight symbols** -- the full exception hierarchy
  (:mod:`dobotkit.exceptions`), every enum (:mod:`dobotkit.enums`), and
  :data:`__version__`. These are pure-Python and pull in **no** device
  dependencies, so ``import dobotkit`` stays cheap.

* **Lazy device classes** -- :class:`~dobotkit.arm.magicianlite.MagicianLite`
  (DobotLink-mediated arm) and :class:`~dobotkit.go.magiciango.MagicianGO`
  (DobotLink WebSocket car) are resolved through a module-level
  :func:`__getattr__` (PEP 562). They are imported only on first *access*
  (``dobotkit.MagicianLite``), so merely importing the package never drags in
  ``websockets``. A program that drives only the arm never pays for the GO's
  navigation stack, and vice-versa.

The set of eager names re-exported here is kept in lock-step with the
``enums`` / ``exceptions`` modules by ``tests/test_integration.py``, which fails
if either module grows a public symbol that is not listed in :data:`__all__`.

Example::

    import dobotkit                       # light: no websockets yet

    with dobotkit.MagicianLite(port="COM3") as arm:   # now DobotLink is contacted
        arm.home()
        arm.move_to(220, 0, 40, 0, wait=True)
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._version import __version__
from .enums import (
    ColorPort,
    ContinuousPathMode,
    EndEffectorType,
    GPIOType,
    JOGMode,
    LEDChannel,
    PTPMode,
)
from .exceptions import (
    DobotAlarmError,
    DobotConnectionError,
    DobotError,
    DobotLinkError,
    DobotProtocolError,
    DobotTimeoutError,
    DobotValueError,
)

if TYPE_CHECKING:  # pragma: no cover - import only for type checkers, not at runtime
    from .arm.magicianlite import MagicianLite
    from .go.magiciango import MagicianGO

# Lazily-imported device classes -> (submodule, attribute). Kept in a table so
# __getattr__ and __dir__ agree and adding a device is a one-liner. Importing
# their modules is deferred to first attribute access (see __getattr__) so a
# bare ``import dobotkit`` never pulls in ``websockets``.
_LAZY = {
    "MagicianLite": ("dobotkit.arm.magicianlite", "MagicianLite"),
    "MagicianGO": ("dobotkit.go.magiciango", "MagicianGO"),
}

__all__ = [
    "__version__",
    # enums (dobotkit.enums)
    "ColorPort",
    "ContinuousPathMode",
    "EndEffectorType",
    "GPIOType",
    "JOGMode",
    "LEDChannel",
    "PTPMode",
    # exceptions (dobotkit.exceptions)
    "DobotAlarmError",
    "DobotConnectionError",
    "DobotError",
    "DobotLinkError",
    "DobotProtocolError",
    "DobotTimeoutError",
    "DobotValueError",
    # lazy device classes
    "MagicianLite",
    "MagicianGO",
]


def __getattr__(name: str) -> Any:
    """Lazily resolve the device classes on first access (PEP 562).

    Importing the device's module here -- rather than at the top of this file --
    is what keeps ``import dobotkit`` from eagerly importing ``websockets``.
    Any other unknown attribute raises ``AttributeError`` as usual.
    """
    target = _LAZY.get(name)
    if target is not None:
        import importlib

        module_name, attr = target
        value = getattr(importlib.import_module(module_name), attr)
        # Cache on the package so repeat access skips the import machinery.
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> "list[str]":
    """Include the lazy device names in ``dir(dobotkit)`` / tab-completion."""
    return sorted(set(globals()) | set(__all__))
