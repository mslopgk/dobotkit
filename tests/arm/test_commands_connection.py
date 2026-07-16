from tests.conftest import FakeClient
from dobotkit.arm.commands import ArmCommands


def test_connect_sends_portname():
    c = FakeClient(results={"Magician.ConnectDobot": {"firmwareName": "Dobot"}})
    cmd = ArmCommands(c, "COM8")
    assert cmd.connect() == {"firmwareName": "Dobot"}
    assert c.find_call("Magician.ConnectDobot") == ("Magician.ConnectDobot", {"portName": "COM8"})


def test_search_sends_no_portname():
    c = FakeClient(results={"Magician.SearchDobot": [{"portName": "COM8"}]})
    assert ArmCommands(c, "COM8").search() == [{"portName": "COM8"}]
    assert c.find_call("Magician.SearchDobot") == ("Magician.SearchDobot", {})


def test_current_index_reads_field():
    c = FakeClient(results={"Magician.GetQueuedCmdCurrentIndex": {"queuedCmdIndex": 7}})
    assert ArmCommands(c, "COM8").current_index() == 7


def test_clear_alarms_sends_rpc():
    c = FakeClient(results={"Magician.ClearAllAlarmsState": True})
    assert ArmCommands(c, "COM8").clear_alarms() is True
    assert c.find_call("Magician.ClearAllAlarmsState") == ("Magician.ClearAllAlarmsState", {"portName": "COM8"})
