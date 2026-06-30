"""Hardware-free unit tests for ``dobotkit.go.geometry`` pure functions.

These functions carry no I/O and are the testable core of the GO navigation
stack. Conventions (matching the GO research doc and the implementation plan):

  * ``yaw_delta(a, b)`` returns the signed shortest angle ``a - b`` normalized
    to the half-open range ``(-180, 180]`` (handles +-180 wraparound).
  * ``bearing(dx, dy)`` returns the direction of vector ``(dx, dy)`` in degrees
    with ``0deg = +X`` and counter-clockwise positive (``+90deg = +Y``).
  * ``clamp_speed(v, lo, hi)`` clamps the *magnitude* into ``[lo, hi]`` while
    preserving the sign of ``v``.
  * ``cm_to_mm`` / ``mm_to_cm`` convert between mat (cm) and primitive (mm) units.
"""
import pytest

from dobotkit.go.geometry import (
    bearing,
    clamp_speed,
    cm_to_mm,
    mm_to_cm,
    yaw_delta,
)


# --------------------------------------------------------------------------
# yaw_delta(a, b) -> signed shortest a - b, normalized to (-180, 180]
# --------------------------------------------------------------------------
def test_yaw_delta_simple_positive():
    assert yaw_delta(90, 0) == pytest.approx(90.0)


def test_yaw_delta_simple_negative():
    assert yaw_delta(0, 90) == pytest.approx(-90.0)


def test_yaw_delta_zero():
    assert yaw_delta(45, 45) == pytest.approx(0.0)


def test_yaw_delta_plan_authoritative_example():
    # PLAN Task 4.1 Step 1: yaw_delta(170, -170) == -20 (approx)
    assert yaw_delta(170, -170) == pytest.approx(-20.0)


def test_yaw_delta_wraparound_other_direction():
    assert yaw_delta(-170, 170) == pytest.approx(20.0)


def test_yaw_delta_exactly_180_is_positive():
    # (-180, 180] convention: exactly opposite resolves to +180, never -180.
    assert yaw_delta(180, 0) == pytest.approx(180.0)
    assert yaw_delta(-180, 0) == pytest.approx(180.0)


def test_yaw_delta_small_steps():
    assert yaw_delta(30, 10) == pytest.approx(20.0)
    assert yaw_delta(10, 30) == pytest.approx(-20.0)


def test_yaw_delta_handles_unnormalized_inputs():
    # Accumulated +-360 inputs must give the same answer.
    assert yaw_delta(370, 350) == pytest.approx(20.0)
    assert yaw_delta(450, 0) == pytest.approx(90.0)


def test_yaw_delta_near_360_wrap():
    assert yaw_delta(1, 359) == pytest.approx(2.0)
    assert yaw_delta(359, 1) == pytest.approx(-2.0)


# --------------------------------------------------------------------------
# bearing(dx, dy) -> deg, 0=+X, CCW+
# --------------------------------------------------------------------------
def test_bearing_east_is_zero():
    assert bearing(10, 0) == pytest.approx(0.0)


def test_bearing_north_is_90():
    # PLAN Task 4.1 Step 1: bearing(0, 1) == 90
    assert bearing(0, 1) == pytest.approx(90.0)


def test_bearing_west_is_180():
    assert abs(bearing(-10, 0)) == pytest.approx(180.0)


def test_bearing_south_is_minus_90():
    assert bearing(0, -10) == pytest.approx(-90.0)


def test_bearing_diagonal_45():
    assert bearing(5, 5) == pytest.approx(45.0)


def test_bearing_zero_vector_is_zero():
    assert bearing(0, 0) == pytest.approx(0.0)


# --------------------------------------------------------------------------
# clamp_speed(v, lo, hi) -> magnitude into [lo, hi], sign preserved
# --------------------------------------------------------------------------
def test_clamp_speed_plan_authoritative_example():
    # PLAN Task 4.1 Step 1: clamp_speed(-50, 8, 30) == -30
    assert clamp_speed(-50, 8, 30) == pytest.approx(-30.0)


def test_clamp_speed_caps_positive_to_high():
    assert clamp_speed(50, 8, 30) == pytest.approx(30.0)


def test_clamp_speed_raises_small_magnitude_to_low():
    assert clamp_speed(3, 8, 30) == pytest.approx(8.0)
    assert clamp_speed(-3, 8, 30) == pytest.approx(-8.0)


def test_clamp_speed_passes_through_in_band():
    assert clamp_speed(20, 8, 30) == pytest.approx(20.0)
    assert clamp_speed(-20, 8, 30) == pytest.approx(-20.0)


def test_clamp_speed_zero_stays_zero():
    # A commanded stop must remain a stop, not be forced up to lo.
    assert clamp_speed(0, 8, 30) == pytest.approx(0.0)


def test_clamp_speed_bad_bounds_raises():
    from dobotkit.exceptions import DobotValueError

    with pytest.raises(DobotValueError):
        clamp_speed(10, 30, 8)  # lo > hi


# --------------------------------------------------------------------------
# cm <-> mm conversions (mat=cm, primitives=mm; x10 / /10)
# --------------------------------------------------------------------------
def test_cm_to_mm_basic():
    assert cm_to_mm(0) == pytest.approx(0.0)
    assert cm_to_mm(1) == pytest.approx(10.0)
    assert cm_to_mm(25) == pytest.approx(250.0)
    assert cm_to_mm(4.8) == pytest.approx(48.0)


def test_mm_to_cm_basic():
    assert mm_to_cm(0) == pytest.approx(0.0)
    assert mm_to_cm(10) == pytest.approx(1.0)
    assert mm_to_cm(250) == pytest.approx(25.0)
    assert mm_to_cm(100) == pytest.approx(10.0)


def test_cm_mm_round_trip():
    for v in (0, 1, 5.3, 48, 250, -12.5):
        assert mm_to_cm(cm_to_mm(v)) == pytest.approx(float(v))
        assert cm_to_mm(mm_to_cm(v)) == pytest.approx(float(v))
