from tests.conftest import FakeClient
from dobotkit.arm.magicianlite import MagicianLite


def _arm(**results):
    return MagicianLite(port="COM8", auto_connect=False, _client=FakeClient(results=results))


def test_move_to_sends_ptp_no_wait():
    c = FakeClient(results={"Magician.SetPTPCmd": {"queuedCmdIndex": 5}})
    arm = MagicianLite(port="COM8", auto_connect=False, _client=c)
    arm.move_to(220, 0, 40, 0, wait=False)
    _, p = c.find_call("Magician.SetPTPCmd")
    assert p["x"] == 220 and p["ptpMode"] == 2 and p["portName"] == "COM8"


def test_move_to_wait_polls_current_index():
    c = FakeClient(results={"Magician.SetPTPCmd": {"queuedCmdIndex": 2},
                            "Magician.GetQueuedCmdCurrentIndex": {"queuedCmdIndex": 2}})
    arm = MagicianLite(port="COM8", auto_connect=False, _client=c)
    arm.move_to(1, 2, 3, wait=True)
    assert "Magician.GetQueuedCmdCurrentIndex" in c.methods_called()


def test_context_manager_disconnects():
    c = FakeClient()
    with MagicianLite(port="COM8", auto_connect=False, _client=c) as arm:
        arm.connect()
    assert c.find_call("Magician.DisconnectDobot") is not None
