"""The arm/go subpackages expose their public classes and stay import-light.

``from dobotkit.arm import Magician`` and ``from dobotkit.go import
DobotLinkClient`` must work, while merely importing a subpackage must not
eagerly drag in the heavy device dependency (``serial`` / ``websockets``).
"""
from __future__ import annotations

import subprocess
import sys


def test_arm_subpackage_exports():
    from dobotkit.arm import LowLevelArm, Magician, SerialTransport

    assert Magician.__name__ == "Magician"
    assert LowLevelArm.__name__ == "LowLevelArm"
    assert SerialTransport.__name__ == "SerialTransport"


def test_go_subpackage_exports():
    from dobotkit.go import DobotLinkClient, MagicianGO, PreciseMover, WaypointNav

    assert DobotLinkClient.__name__ == "DobotLinkClient"
    assert MagicianGO.__name__ == "MagicianGO"
    assert PreciseMover.__name__ == "PreciseMover"
    assert WaypointNav.__name__ == "WaypointNav"


def test_arm_unknown_attr_raises():
    import dobotkit.arm as arm

    try:
        arm.NoSuchThing  # noqa: B018 - exercising __getattr__
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected AttributeError for unknown arm attribute")


def test_importing_subpackages_is_lazy():
    """`import dobotkit.arm` / `import dobotkit.go` must not import the heavy deps."""
    code = (
        "import sys, dobotkit.arm, dobotkit.go;"
        "print('serial' in sys.modules, 'websockets' in sys.modules)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert out == "False False", f"subpackage import was not lazy: {out!r}"
