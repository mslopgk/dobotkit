import pytest

from tests.conftest import FakeClient
from dobotkit.arm.magicianlite import MagicianLite
from dobotkit.exceptions import DobotTimeoutError


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


def test_move_to_wait_timeout_raises(monkeypatch):
    """`_wait_for` must raise DobotTimeoutError on deadline, never return silently."""
    calls = {"n": 0}

    def fake_monotonic():
        # First call establishes the deadline; every call after is already past it,
        # so the test never actually sleeps for the (default 30s) timeout.
        calls["n"] += 1
        return 0.0 if calls["n"] == 1 else 999_999.0

    monkeypatch.setattr("dobotkit.arm.magicianlite.time.monotonic", fake_monotonic)
    c = FakeClient(results={
        "Magician.SetPTPCmd": {"queuedCmdIndex": 5},
        # current index never reaches 5.
        "Magician.GetQueuedCmdCurrentIndex": {"queuedCmdIndex": 0},
    })
    arm = MagicianLite(port="COM8", auto_connect=False, _client=c)
    with pytest.raises(DobotTimeoutError):
        arm.move_to(220, 0, 40, 0, wait=True)


def test_home_always_queues_params_and_cmd_even_without_wait():
    """home()'s SetHOMEParams/SetHOMECmd must be isQueued=True regardless of `wait`."""
    c = FakeClient(results={
        "Magician.SetHOMECmd": {"queuedCmdIndex": 1},
        "Magician.GetQueuedCmdCurrentIndex": {"queuedCmdIndex": 1},
    })
    arm = MagicianLite(port="COM8", auto_connect=False, _client=c)
    arm.home(wait=False)
    _, params_call = c.find_call("Magician.SetHOMEParams")
    _, cmd_call = c.find_call("Magician.SetHOMECmd")
    assert params_call["isQueued"] is True
    assert cmd_call["isQueued"] is True


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
