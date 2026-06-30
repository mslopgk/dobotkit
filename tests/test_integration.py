"""Top-level integration tests for the public ``dobotkit`` API (Task 5.1).

These guard two contracts of the package's front door:

1. **Complete public surface.** The names a user reaches for -- the two device
   classes (:class:`Magician`, :class:`MagicianGO`), the enums, and the
   exception hierarchy -- are all importable straight from ``dobotkit``.

2. **Lazy device imports.** Merely ``import dobotkit`` must stay cheap: it must
   *not* eagerly import the heavy device dependencies (``serial`` for the arm,
   ``websockets`` for the GO). Those are pulled in only when the corresponding
   device class is first *accessed* (which triggers the module ``__getattr__``
   lazy import). This is verified in a clean subprocess so the result is not
   polluted by other tests that already imported those modules.
"""
from __future__ import annotations

import subprocess
import sys


def test_public_api_imports():
    """Every advertised public name imports from the top-level package."""
    from dobotkit import (  # noqa: F401  (import *is* the assertion)
        DobotAlarmError,
        DobotError,
        Magician,
        MagicianGO,
        PTPMode,
    )

    # The device classes are real classes (the lazy __getattr__ resolved them).
    assert isinstance(Magician, type)
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
    assert "Magician" in dobotkit.__all__
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


def test_bare_import_does_not_pull_in_serial_or_websockets():
    """``import dobotkit`` alone must not import ``serial`` or ``websockets``."""
    mods = _modules_after("import dobotkit")
    assert "serial" not in mods, "import dobotkit eagerly imported serial"
    assert "websockets" not in mods, "import dobotkit eagerly imported websockets"


def test_importing_enums_and_exceptions_stays_light():
    """Reaching the enums/exceptions through the package keeps it light."""
    mods = _modules_after(
        "import dobotkit; _ = (dobotkit.PTPMode, dobotkit.DobotError)"
    )
    assert "serial" not in mods
    assert "websockets" not in mods


def test_accessing_magician_imports_serial_lazily():
    """Touching ``dobotkit.Magician`` triggers the (lazy) ``serial`` import."""
    mods = _modules_after("import dobotkit; _ = dobotkit.Magician")
    assert "serial" in mods, "accessing Magician should lazily import serial"
