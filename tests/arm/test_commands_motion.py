"""Tests for motion command RPC wrappers (PTP, CP, ARC, jog, ...)."""
from tests.conftest import FakeClient
from dobotkit.arm.commands.motion import MotionMixin


class _Cmds(MotionMixin):
    """Compose MotionMixin for testing (avoids importing concurrent sibling edits)."""
    pass


def test_set_ptp_cmd_maps_params_and_returns_index():
    c = FakeClient(results={"Magician.SetPTPCmd": {"queuedCmdIndex": 12}})
    idx = _Cmds(c, "COM8").set_ptp_cmd(2, 220.0, 0.0, 40.0, 0.0, queued=True)
    assert idx == 12
    m, p = c.find_call("Magician.SetPTPCmd")
    assert p == {"portName": "COM8", "ptpMode": 2, "x": 220.0, "y": 0.0,
                 "z": 40.0, "r": 0.0, "isQueued": True}


def test_get_pose_passthrough():
    pose = {"x": 214.0, "y": 0.0, "z": 0.0, "r": 0.0, "jointAngle": [0, 25, 67, 0]}
    c = FakeClient(results={"Magician.GetPose": pose})
    assert _Cmds(c, "COM8").get_pose() == pose


def test_set_wait_cmd_maps_timeout():
    c = FakeClient(results={"Magician.SetWAITCmd": {"queuedCmdIndex": 3}})
    assert _Cmds(c, "COM8").set_wait_cmd(200, queued=True) == 3
    _, p = c.find_call("Magician.SetWAITCmd")
    assert p == {"portName": "COM8", "timeout": 200, "isQueued": True}
