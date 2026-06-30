from dobotkit.arm.ids import ProtocolId


def test_known_ids_match_pydobot():
    assert ProtocolId.GET_POSE == 10
    assert ProtocolId.GET_ALARMS_STATE == 20
    assert ProtocolId.SET_HOME_CMD == 31
    assert ProtocolId.SET_PTP_CMD == 84
    assert ProtocolId.SET_CP_CMD == 91
    assert ProtocolId.SET_QUEUED_CMD_CLEAR == 245
    assert ProtocolId.GET_QUEUED_CMD_CURRENT_INDEX == 246


def test_ids_unique():
    values = [m.value for m in ProtocolId]
    assert len(values) == len(set(values)), "duplicate protocol IDs"
