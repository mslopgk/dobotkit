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


def test_ids_fit_single_byte():
    # The wire frame stores the command id in ONE byte (Message: bytes([id, ...])),
    # so every ProtocolId must be in range(0, 256).
    out_of_range = [m.name for m in ProtocolId if not (0 <= m.value < 256)]
    assert not out_of_range, f"protocol IDs outside 0..255: {out_of_range}"
