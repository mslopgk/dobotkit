import pytest
from dobotkit.exceptions import (
    DobotError, DobotConnectionError, DobotTimeoutError, DobotProtocolError,
    DobotAlarmError, DobotLinkError, DobotValueError,
)

@pytest.mark.parametrize("cls", [
    DobotConnectionError, DobotTimeoutError, DobotProtocolError,
    DobotLinkError, DobotValueError,
])
def test_subclasses_of_base(cls):
    assert issubclass(cls, DobotError)
    with pytest.raises(DobotError):
        raise cls("boom")

def test_alarm_error_carries_codes():
    err = DobotAlarmError(codes=[1, 7], message="planning error")
    assert issubclass(DobotAlarmError, DobotError)
    assert err.codes == [1, 7]
    assert "planning error" in str(err)
