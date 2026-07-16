"""Tests for the high-level :class:`~dobotkit.arm.magician.Magician` API (Task 3.3).

``Magician`` is an ergonomic facade over :class:`~dobotkit.arm.lowlevel.LowLevelArm`
(itself driven by a :class:`~dobotkit.arm.transport.SerialTransport`). These tests
exercise it two ways, neither of which touches real hardware:

* a **fake LowLevelArm** (a :class:`unittest.mock.MagicMock` wired with a real
  :class:`~dobotkit.arm.queue.CommandQueue` mock) injected via the
  ``_transport`` seam plus monkeypatching, OR
* the in-memory ``FakeSerial`` double from ``tests/conftest.py`` plugged into a
  real ``SerialTransport`` through its ``_serial_factory`` hook.

The behaviours under test (per the plan):

* ``move_to(..., wait=True)`` issues a queued PTP, starts the queue, and waits
  for the returned index;
* the context manager stops + disconnects on ``__exit__`` even when the body
  raised;
* the pydobot-compat aliases (``suck`` / ``grip`` / ``speed`` / ``wait`` /
  ``pose`` / ``get_eio`` / ``set_eio``) delegate to the right low-level calls;
* ``pick_and_place`` sequences the safe-height moves and the suction toggles.
"""
from __future__ import annotations

import struct
from unittest.mock import MagicMock

import pytest

from dobotkit.arm.magician import Magician
from dobotkit.arm.protocol import Message
from dobotkit.arm.ids import ProtocolId
from dobotkit.arm.structures import Pose
from dobotkit.enums import PTPMode
from dobotkit.exceptions import DobotAlarmError


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def make_magician_with_fake_ll() -> tuple[Magician, MagicMock]:
    """Build a Magician backed by a fake (Mock) LowLevelArm.

    The fake exposes a ``queue`` attribute (also a Mock) so that ``wait=True``
    paths (``queue.start`` / ``queue.wait_for``) are observable. ``auto_connect``
    is off so no transport work happens at construction.
    """
    ll = MagicMock(name="LowLevelArm")
    ll.queue = MagicMock(name="CommandQueue")
    m = Magician(_lowlevel=ll, auto_connect=False)
    return m, ll


# --------------------------------------------------------------------------- #
# Construction / lifecycle
# --------------------------------------------------------------------------- #
def test_init_does_not_autoconnect_when_disabled():
    ll = MagicMock()
    Magician(_lowlevel=ll, auto_connect=False)
    ll.connect.assert_not_called()


def test_init_autoconnects_by_default():
    ll = MagicMock()
    Magician(_lowlevel=ll, auto_connect=True)
    ll.connect.assert_called_once_with()


def test_port_auto_resolves_via_search(monkeypatch):
    captured: dict = {}

    # A single stand-in for the SerialTransport symbol: callable as a
    # constructor AND carrying a .search() classmethod, mirroring the real type.
    def fake_transport_ctor(port, baudrate, **kwargs):
        captured["port"] = port
        captured["baudrate"] = baudrate
        return MagicMock(name="SerialTransport")

    fake_transport_ctor.search = staticmethod(  # type: ignore[attr-defined]
        lambda: ["COM7", "COM9"]
    )

    monkeypatch.setattr(
        "dobotkit.arm.magician.SerialTransport", fake_transport_ctor
    )
    # The LowLevelArm built on top of the transport is also faked so connect()
    # is a no-op.
    monkeypatch.setattr(
        "dobotkit.arm.magician.LowLevelArm", lambda transport: MagicMock()
    )

    Magician(port="auto", auto_connect=False)
    assert captured["port"] == "COM7"  # first search hit


def test_connect_disconnect_delegate_to_lowlevel():
    m, ll = make_magician_with_fake_ll()
    m.connect()
    ll.connect.assert_called_once_with()
    m.disconnect()
    ll.disconnect.assert_called_once_with()


def test_connect_starts_queue_so_standalone_queued_aliases_execute():
    # Mirrors pydobot, which starts the on-device queue at construction. Without
    # this, a standalone arm.suck(True) / grip / wait would be enqueued but never
    # execute until a later waited motion started the queue.
    m, ll = make_magician_with_fake_ll()
    m.connect()
    ll.queue.start.assert_called_once_with()


# --------------------------------------------------------------------------- #
# Context manager
# --------------------------------------------------------------------------- #
def test_context_manager_stops_and_disconnects_on_clean_exit():
    m, ll = make_magician_with_fake_ll()
    with m as entered:
        assert entered is m
    ll.queue.stop.assert_called_once_with()
    ll.disconnect.assert_called_once_with()


def test_context_manager_disconnects_even_after_exception():
    m, ll = make_magician_with_fake_ll()
    with pytest.raises(RuntimeError):
        with m:
            raise RuntimeError("boom in the body")
    # Cleanup must still have happened.
    ll.queue.stop.assert_called_once_with()
    ll.disconnect.assert_called_once_with()


def test_context_manager_does_not_suppress_exception():
    m, _ = make_magician_with_fake_ll()
    with pytest.raises(ValueError):
        with m:
            raise ValueError("not suppressed")


# --------------------------------------------------------------------------- #
# Motion: move_to
# --------------------------------------------------------------------------- #
def test_move_to_immediate_when_wait_false():
    m, ll = make_magician_with_fake_ll()
    ll.set_ptp_cmd.return_value = None

    m.move_to(200, 0, 50, 0)

    ll.set_ptp_cmd.assert_called_once_with(
        PTPMode.MOVL_XYZ, 200, 0, 50, 0, queued=False
    )
    ll.queue.start.assert_not_called()
    ll.queue.wait_for.assert_not_called()


def test_move_to_wait_true_queues_starts_and_waits():
    m, ll = make_magician_with_fake_ll()
    ll.set_ptp_cmd.return_value = 7  # queued index

    m.move_to(200, 0, 50, 0, wait=True)

    ll.set_ptp_cmd.assert_called_once_with(
        PTPMode.MOVL_XYZ, 200, 0, 50, 0, queued=True
    )
    ll.queue.start.assert_called_once_with()
    ll.queue.wait_for.assert_called_once_with(7)


def test_move_to_honours_mode_argument():
    m, ll = make_magician_with_fake_ll()
    m.move_to(1, 2, 3, 4, mode=PTPMode.MOVJ_XYZ)
    ll.set_ptp_cmd.assert_called_once_with(
        PTPMode.MOVJ_XYZ, 1, 2, 3, 4, queued=False
    )


def test_move_relative_uses_inc_mode_and_waits():
    m, ll = make_magician_with_fake_ll()
    ll.set_ptp_cmd.return_value = 11

    m.move_relative(dx=10, dy=-5, dz=2, dr=1, wait=True)

    ll.set_ptp_cmd.assert_called_once_with(
        PTPMode.MOVL_XYZ_INC, 10, -5, 2, 1, queued=True
    )
    ll.queue.start.assert_called_once_with()
    ll.queue.wait_for.assert_called_once_with(11)


# --------------------------------------------------------------------------- #
# Alarm checking
# --------------------------------------------------------------------------- #
def test_move_to_check_alarms_raises_when_active():
    m, ll = make_magician_with_fake_ll()
    # bit 0 set -> COMMON_RESET alarm active.
    ll.get_alarms_state.return_value = bytes([0x01])

    with pytest.raises(DobotAlarmError) as excinfo:
        m.move_to(200, 0, 50, 0, check_alarms=True)
    assert 0 in excinfo.value.codes


def test_move_to_check_alarms_passes_when_clear():
    m, ll = make_magician_with_fake_ll()
    ll.get_alarms_state.return_value = bytes([0x00, 0x00])
    m.move_to(200, 0, 50, 0, check_alarms=True)  # must not raise
    ll.set_ptp_cmd.assert_called_once()


# --------------------------------------------------------------------------- #
# Home / speed / pose
# --------------------------------------------------------------------------- #
def test_home_sets_params_runs_cmd_and_waits():
    m, ll = make_magician_with_fake_ll()
    ll.set_home_cmd.return_value = 3

    m.home(x=200, y=0, z=0, r=0, wait=True)

    ll.set_home_params.assert_called_once_with(200, 0, 0, 0, queued=True)
    ll.set_home_cmd.assert_called_once_with(queued=True)
    ll.queue.start.assert_called_once_with()
    ll.queue.wait_for.assert_called_once_with(3)


def test_set_speed_sets_common_and_coordinate_params():
    m, ll = make_magician_with_fake_ll()
    m.set_speed(150, 80)
    ll.set_ptp_common_params.assert_called_once_with(150, 80)
    ll.set_ptp_coordinate_params.assert_called_once_with(150, 150, 80, 80)


def test_get_pose_delegates():
    m, ll = make_magician_with_fake_ll()
    pose = Pose(1, 2, 3, 4, 5, 6, 7, 8)
    ll.get_pose.return_value = pose
    assert m.get_pose() == pose
    assert m.pose_obj == pose  # property accessor


# --------------------------------------------------------------------------- #
# Groups
# --------------------------------------------------------------------------- #
def test_group_properties_wrap_lowlevel():
    from dobotkit.arm._legacy_groups import EffectorGroup, IOGroup, SensorGroup

    m, ll = make_magician_with_fake_ll()
    assert isinstance(m.effector, EffectorGroup)
    assert isinstance(m.io, IOGroup)
    assert isinstance(m.sensors, SensorGroup)
    assert m.effector.lowlevel is ll
    assert m.lowlevel is ll


# --------------------------------------------------------------------------- #
# pydobot-compat aliases
# --------------------------------------------------------------------------- #
def test_suck_alias_delegates_to_effector():
    m, ll = make_magician_with_fake_ll()
    m.suck(True)
    ll.set_end_effector_suction_cup.assert_called_once_with(
        enable_ctrl=True, on=True, queued=True
    )


def test_grip_alias_delegates_to_effector():
    m, ll = make_magician_with_fake_ll()
    m.grip(True)
    ll.set_end_effector_gripper.assert_called_once_with(
        enable_ctrl=True, on=True, queued=True
    )


def test_speed_alias_matches_set_speed():
    m, ll = make_magician_with_fake_ll()
    m.speed(120, 60)
    ll.set_ptp_common_params.assert_called_once_with(120, 60)
    ll.set_ptp_coordinate_params.assert_called_once_with(120, 120, 60, 60)


def test_wait_alias_issues_queued_wait_cmd():
    m, ll = make_magician_with_fake_ll()
    m.wait(1000)
    ll.set_wait_cmd.assert_called_once_with(1000, queued=True)


def test_pose_callable_returns_pydobot_tuple():
    m, ll = make_magician_with_fake_ll()
    ll.get_pose.return_value = Pose(1, 2, 3, 4, 5, 6, 7, 8)
    assert m.pose() == (1, 2, 3, 4, 5, 6, 7, 8)


def test_get_eio_reads_digital_output():
    # pydobot's get_eio issues protocol 131 (GetIODO, rw=0): it reads back the
    # digital-OUTPUT register that set_eio writes, not a digital input.
    m, ll = make_magician_with_fake_ll()
    ll.get_io_do.return_value = MagicMock(level=1)
    assert m.get_eio(5) == 1
    ll.get_io_do.assert_called_once_with(5)
    ll.get_io_di.assert_not_called()


def test_set_eio_writes_digital_output():
    m, ll = make_magician_with_fake_ll()
    m.set_eio(5, 1)
    # Delegates through IOGroup.set_do, which issues an immediate (non-queued)
    # digital-output write.
    ll.set_io_do.assert_called_once_with(5, 1, queued=False)


# --------------------------------------------------------------------------- #
# pick_and_place
# --------------------------------------------------------------------------- #
def test_pick_and_place_sequences_moves_and_suction():
    m, ll = make_magician_with_fake_ll()
    # Every queued set returns an incrementing index so wait_for sees real ints.
    counter = {"i": 0}

    def _next_index(*_a, **_k):
        counter["i"] += 1
        return counter["i"]

    ll.set_ptp_cmd.side_effect = _next_index
    ll.set_end_effector_suction_cup.side_effect = _next_index
    ll.set_wait_cmd.side_effect = _next_index

    src = (200, 0, -40)
    dst = (100, 150, -40)
    m.pick_and_place(src, dst, z_safe=50, settle_ms=200)

    # Build the ordered list of (method, positional-args) actually issued.
    moves = [
        c.args[:4] for c in ll.set_ptp_cmd.call_args_list
    ]  # (mode, x, y, z)
    # Expect: above-src, down-to-src, (suck on), up, above-dst, down-to-dst,
    # (suck off), up. Verify the XY/Z waypoints in order.
    xyz = [(x, y, z) for (_mode, x, y, z) in moves]
    assert xyz == [
        (200, 0, 50),    # 1. travel above source
        (200, 0, -40),   # 2. descend to source
        (200, 0, 50),    # 3. lift back to safe height
        (100, 150, 50),  # 4. travel above destination
        (100, 150, -40), # 5. descend to destination
        (100, 150, 50),  # 6. lift back to safe height
    ]

    # Suction: ON after descending to source, OFF after descending to dest.
    suction_states = [
        c.kwargs.get("on") for c in ll.set_end_effector_suction_cup.call_args_list
    ]
    assert suction_states == [True, False]

    # The queue is started and the final waypoint is waited on.
    ll.queue.start.assert_called()
    assert ll.queue.wait_for.called


def test_pick_and_place_all_moves_are_queued():
    m, ll = make_magician_with_fake_ll()
    ll.set_ptp_cmd.return_value = 1
    ll.set_end_effector_suction_cup.return_value = 1
    ll.set_wait_cmd.return_value = 1

    m.pick_and_place((200, 0, -40), (100, 150, -40), z_safe=50)

    for call in ll.set_ptp_cmd.call_args_list:
        assert call.kwargs.get("queued") is True
    for call in ll.set_end_effector_suction_cup.call_args_list:
        assert call.kwargs.get("queued") is True


# --------------------------------------------------------------------------- #
# End-to-end through a real SerialTransport + FakeSerial
# --------------------------------------------------------------------------- #
def _pose_response() -> bytes:
    """A GetPose response frame carrying eight float pose components."""
    params = struct.pack("<8f", 200.0, 0.0, 50.0, 0.0, 1.0, 2.0, 3.0, 4.0)
    return Message(id=ProtocolId.GET_POSE, ctrl=0, params=params).to_bytes()


def test_get_pose_through_fakeserial(monkeypatch):
    """Drive the full stack: Magician -> LowLevelArm -> SerialTransport -> FakeSerial."""
    from tests.conftest import FakeSerial

    fake = FakeSerial([_pose_response()])

    # Build a real SerialTransport over the fake serial, then a real LowLevelArm.
    from dobotkit.arm.transport import SerialTransport
    from dobotkit.arm.lowlevel import LowLevelArm

    tx = SerialTransport(port="FAKE", _serial_factory=lambda *a, **k: fake)
    ll = LowLevelArm(tx)
    m = Magician(_lowlevel=ll, auto_connect=False)

    pose = m.get_pose()
    assert (pose.x, pose.y, pose.z, pose.r) == (200.0, 0.0, 50.0, 0.0)
    assert (pose.j1, pose.j2, pose.j3, pose.j4) == (1.0, 2.0, 3.0, 4.0)
    # The request frame for GetPose was written to the fake serial.
    assert fake.written == Message(id=ProtocolId.GET_POSE, ctrl=0).to_bytes()
