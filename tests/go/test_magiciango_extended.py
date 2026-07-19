"""Offline wire-format tests for MagicianGO diagnostics/alarms + MagicBox status.

After the GO cleanup the class keeps a small set of extended getters beyond the
hardware-verified drive/sensor core: alarm info, running state, stall / wheels-
off-ground flags, and the MagicBox mode/count status reads (which, despite their
names, are regular ``MagicianGO.*`` methods — the actual MagicBox sensor/IO
reads live on the ``MagicBox.*`` namespace via ``go.sensors`` / ``go.io``, tested
in ``test_groups.py``). Each test pins the exact ``(method, params)`` recorded
by the ``FakeClient`` double; nothing here touches hardware.
"""
from __future__ import annotations

from typing import Any, Tuple

from dobotkit.go.magiciango import MagicianGO

from .conftest import FakeClient


def make_go(result: Any = None, results: Any = None,
            port_name: str = "COM5") -> Tuple[MagicianGO, FakeClient]:
    fc = FakeClient(result=result, results=results)
    return MagicianGO(fc, port_name=port_name), fc


# ---- diagnostics / state getters (MagicianGO, portName only) ----------------

def test_get_alarm_info():
    go, fc = make_go(results={"MagicianGO.GetAlarmInfo": {"warning": []}})
    assert go.get_alarm_info() == {"warning": []}
    assert fc.calls[0] == ("MagicianGO.GetAlarmInfo", {"portName": "COM5"})


def test_clean_alarm_info():
    go, fc = make_go()
    go.clean_alarm_info()
    assert fc.calls[0] == ("MagicianGO.CleanAlarmInfo", {"portName": "COM5"})


def test_stall_protection():
    go, fc = make_go(results={"MagicianGO.GetStallProtection": {"isHappened": 0}})
    assert go.stall_protection() == {"isHappened": 0}
    assert fc.calls[0] == ("MagicianGO.GetStallProtection", {"portName": "COM5"})


def test_off_ground():
    go, fc = make_go(results={"MagicianGO.GetOffGround": {"isHappened": 1}})
    assert go.off_ground() == {"isHappened": 1}
    assert fc.calls[0] == ("MagicianGO.GetOffGround", {"portName": "COM5"})


# ---- MagicBox status (MagicianGO namespace despite the names) ---------------

def test_magic_box_mode_is_magiciango_namespace():
    go, fc = make_go(results={"MagicianGO.GetMagicBoxMode": {"mode": 2}})
    assert go.magic_box_mode() == {"mode": 2}
    assert fc.calls[0] == ("MagicianGO.GetMagicBoxMode", {"portName": "COM5"})


def test_magic_box_num_is_magiciango_namespace():
    go, fc = make_go(results={"MagicianGO.GetMagicBoxNum": {"num": 1}})
    assert go.magic_box_num() == {"num": 1}
    assert fc.calls[0] == ("MagicianGO.GetMagicBoxNum", {"portName": "COM5"})


def test_diagnostics_use_configured_port_name():
    go, fc = make_go(port_name="COM9")
    go.get_alarm_info()
    go.magic_box_mode()
    assert all(params["portName"] == "COM9" for _method, params in fc.calls)
