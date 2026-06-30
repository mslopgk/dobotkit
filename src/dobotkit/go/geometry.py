"""Pure geometry/units helpers for Magician GO navigation.

Every function here is side-effect-free and hardware-independent: they are the
testable numeric core that ``PreciseMover`` and ``WaypointNav`` build on.

Angle / coordinate conventions (matching the GO research doc, section 2.3):

  * ``0deg`` points along ``+X``; angles increase **counter-clockwise** (CCW),
    so ``+90deg`` points along ``+Y``. This matches ``atan2(dy, dx)`` and the
    GO's ``r+`` = CCW (left-turn) command convention.
  * Signed angle deltas are normalized to the half-open range ``(-180, 180]``:
    a half turn always resolves to ``+180``, never ``-180``.

Unit convention: mat/world coordinates are centimetres (matching the SDK's
position values), while the closed-loop motion primitives work in millimetres.
The ``cm_to_mm`` / ``mm_to_cm`` helpers are the only place that conversion
happens.
"""
from __future__ import annotations

import math

from dobotkit.exceptions import DobotValueError

__all__ = ["yaw_delta", "bearing", "clamp_speed", "cm_to_mm", "mm_to_cm", "MM_PER_CM"]

#: Millimetres per centimetre — the mat(cm) <-> primitive(mm) scale factor.
MM_PER_CM: float = 10.0


def yaw_delta(a: float, b: float) -> float:
    """Return the signed shortest angle ``a - b`` in degrees.

    The result is normalized to the half-open range ``(-180, 180]``, so the
    +-180 wraparound is handled and a half turn resolves to ``+180`` (never
    ``-180``). Inputs need not be normalized; accumulated +-360 offsets give the
    same answer.

    Examples::

        yaw_delta(170, -170) -> -20.0   # not 340
        yaw_delta(-170, 170) -> 20.0
        yaw_delta(90, 0)     -> 90.0
        yaw_delta(180, 0)    -> 180.0
    """
    d = (a - b) % 360.0
    if d > 180.0:
        d -= 360.0
    return d


def bearing(dx: float, dy: float) -> float:
    """Return the direction of the vector ``(dx, dy)`` in degrees.

    ``0deg`` = ``+X`` and angles increase counter-clockwise, so ``+90deg`` =
    ``+Y`` and ``-90deg`` = ``-Y``. The result lies in ``(-180, 180]``. The zero
    vector yields ``0.0``.

    Examples::

        bearing(1, 0) -> 0.0
        bearing(0, 1) -> 90.0
        bearing(5, 5) -> 45.0
    """
    return math.degrees(math.atan2(dy, dx))


def clamp_speed(v: float, lo: float, hi: float) -> float:
    """Clamp the *magnitude* of ``v`` into ``[lo, hi]`` while keeping its sign.

    ``lo``/``hi`` are non-negative magnitude bounds. A magnitude above ``hi`` is
    capped to ``hi``; a non-zero magnitude below ``lo`` is raised to ``lo`` (so a
    crawling command still actually moves). An exact ``0`` is returned unchanged
    so a commanded stop stays a stop.

    Examples::

        clamp_speed(-50, 8, 30) -> -30.0
        clamp_speed(3, 8, 30)   -> 8.0
        clamp_speed(0, 8, 30)   -> 0.0

    Raises:
        DobotValueError: if ``lo > hi`` or either bound is negative.
    """
    if lo < 0 or hi < 0:
        raise DobotValueError(f"speed bounds must be non-negative: lo={lo}, hi={hi}")
    if lo > hi:
        raise DobotValueError(f"speed lower bound {lo} exceeds upper bound {hi}")
    if v == 0:
        return 0.0
    sign = 1.0 if v > 0 else -1.0
    mag = abs(v)
    mag = min(mag, hi)
    mag = max(mag, lo)
    return sign * mag


def cm_to_mm(cm: float) -> float:
    """Convert centimetres to millimetres (``cm * 10``)."""
    return float(cm) * MM_PER_CM


def mm_to_cm(mm: float) -> float:
    """Convert millimetres to centimetres (``mm / 10``)."""
    return float(mm) / MM_PER_CM
