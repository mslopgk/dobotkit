"""Top-level integration tests for the public ``dobotkit`` API (Task 5.1).

These guard two contracts of the package's front door:

1. **Complete public surface.** The names a user reaches for -- the two device
   classes (:class:`MagicianLite`, :class:`MagicianGO`), the enums, and the
   exception hierarchy -- are all importable straight from ``dobotkit``.

2. **Lazy device imports.** Merely ``import dobotkit`` must stay cheap: it must
   *not* eagerly import the heavy device dependency (``websockets``, used by
   both the arm and the GO). It is pulled in only when a device actually opens
   a connection, never merely by *accessing* the class (which only triggers
   the module ``__getattr__`` lazy import). This is verified in a clean
   subprocess so the result is not polluted by other tests that already
   imported those modules.
"""
from __future__ import annotations

import subprocess
import sys


def test_public_api_imports():
    """Every advertised public name imports from the top-level package."""
    from dobotkit import (  # noqa: F401  (import *is* the assertion)
        DobotAlarmError,
        DobotError,
        MagicianGO,
        MagicianLite,
        PTPMode,
    )

    # The device classes are real classes (the lazy __getattr__ resolved them).
    assert isinstance(MagicianLite, type)
    assert isinstance(MagicianGO, type)
    # Enum + exception sanity.
    assert PTPMode.MOVL_XYZ == 2
    assert issubclass(DobotAlarmError, DobotError)


def test_all_enums_and_exceptions_exported():
    """Each symbol in ``dobotkit.enums`` / ``dobotkit.exceptions`` is re-exported."""
    import dobotkit
    import dobotkit.enums as enums
    import dobotkit.exceptions as exceptions

    for name in ("PTPMode", "JOGMode", "ContinuousPathMode", "GPIOType",
                 "EndEffectorType", "ColorPort", "LEDChannel"):
        assert hasattr(enums, name), f"enums missing {name}"
        assert getattr(dobotkit, name) is getattr(enums, name)
        assert name in dobotkit.__all__

    for name in ("DobotError", "DobotConnectionError", "DobotTimeoutError",
                 "DobotProtocolError", "DobotValueError", "DobotLinkError",
                 "DobotAlarmError"):
        assert hasattr(exceptions, name), f"exceptions missing {name}"
        assert getattr(dobotkit, name) is getattr(exceptions, name)
        assert name in dobotkit.__all__


def test_version_exported():
    import dobotkit

    assert isinstance(dobotkit.__version__, str)
    assert dobotkit.__version__.count(".") >= 1
    assert "MagicianLite" in dobotkit.__all__
    assert "MagicianGO" in dobotkit.__all__


def test_unknown_attribute_raises_attribute_error():
    import dobotkit

    try:
        dobotkit.NoSuchThing  # noqa: B018  (attribute access is the test)
    except AttributeError:
        pass
    else:  # pragma: no cover - the access above must raise
        raise AssertionError("expected AttributeError for unknown attribute")


def _modules_after(snippet: str) -> set:
    """Run ``snippet`` in a clean interpreter; return its final ``sys.modules`` keys.

    A fresh subprocess is essential: the in-process test session has very
    likely already imported ``serial``/``websockets`` via other tests, so only
    a pristine interpreter can prove that *this* import path stays lazy.
    """
    code = snippet + "\nimport sys, json; print(json.dumps(sorted(sys.modules)))"
    out = subprocess.check_output([sys.executable, "-c", code], text=True)
    import json

    return set(json.loads(out.strip().splitlines()[-1]))


def test_bare_import_does_not_pull_in_websockets():
    """``import dobotkit`` alone must not import ``websockets``."""
    mods = _modules_after("import dobotkit")
    assert "websockets" not in mods, "import dobotkit eagerly imported websockets"


def test_importing_enums_and_exceptions_stays_light():
    """Reaching the enums/exceptions through the package keeps it light."""
    mods = _modules_after(
        "import dobotkit; _ = (dobotkit.PTPMode, dobotkit.DobotError)"
    )
    assert "websockets" not in mods


def test_accessing_device_classes_stays_light():
    """Merely resolving ``dobotkit.MagicianLite``/``MagicianGO`` (the lazy
    ``__getattr__``) must not import ``websockets`` -- only actually opening a
    connection does."""
    mods = _modules_after(
        "import dobotkit; _ = (dobotkit.MagicianLite, dobotkit.MagicianGO)"
    )
    assert "websockets" not in mods, "resolving the device classes should not import websockets"


def test_connecting_magicianlite_imports_websockets_lazily():
    """Actually attempting to connect a ``MagicianLite`` triggers the (lazy)
    ``websockets`` import -- whether the attempt itself succeeds or fails.

    Uses an unlikely port and a short timeout so this stays fast and does not
    depend on whether some other service happens to be listening on the
    default DobotLink port in the test environment.
    """
    code = (
        "import dobotkit\n"
        "try:\n"
        "    dobotkit.MagicianLite(port='COM8', host='127.0.0.1', ws_port=19099, timeout=0.5)\n"
        "except dobotkit.DobotError:\n"
        "    pass\n"
    )
    mods = _modules_after(code)
    assert "websockets" in mods, "connecting MagicianLite should lazily import websockets"
