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
    assert p["isWaitForFinish"] is False


def test_move_to_wait_sends_is_wait_for_finish():
    """`wait=True` must ask DobotLink itself to block via isWaitForFinish;
    there is no more client-side queue-index polling."""
    c = FakeClient(results={"Magician.SetPTPCmd": {"queuedCmdIndex": 2}})
    arm = MagicianLite(port="COM8", auto_connect=False, _client=c)
    arm.move_to(1, 2, 3, wait=True)
    _, p = c.find_call("Magician.SetPTPCmd")
    assert p["isWaitForFinish"] is True
    assert "Magician.GetQueuedCmdCurrentIndex" not in c.methods_called()


def test_home_always_queues_params_and_cmd_even_without_wait():
    """home()'s SetHOMEParams/SetHOMECmd must be isQueued=True regardless of `wait`."""
    c = FakeClient(results={
        "Magician.SetHOMECmd": {"queuedCmdIndex": 1},
    })
    arm = MagicianLite(port="COM8", auto_connect=False, _client=c)
    arm.home(wait=False)
    _, params_call = c.find_call("Magician.SetHOMEParams")
    _, cmd_call = c.find_call("Magician.SetHOMECmd")
    assert params_call["isQueued"] is True
    assert cmd_call["isQueued"] is True
    assert cmd_call["isWaitForFinish"] is False


def test_context_manager_disconnects():
    c = FakeClient()
    with MagicianLite(port="COM8", auto_connect=False, _client=c) as arm:
        arm.connect()
    assert c.find_call("Magician.DisconnectDobot") is not None


def test_exit_swallows_disconnect_error_without_masking():
    """__exit__ must not let a disconnect() failure escape and mask teardown."""
    class Boom(FakeClient):
        def call(self, method, **params):
            if method == "Magician.DisconnectDobot":
                raise RuntimeError("disconnect boom")
            return super().call(method, **params)

    arm = MagicianLite(port="COM8", auto_connect=False, _client=Boom())
    with arm:
        pass  # no exception should propagate from __exit__
