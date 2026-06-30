"""Tests for the system low-level category (Task 2.9).

Two kinds of tests:

* **Struct byte-match** vs the golden oracle (``DobotDllType``) for each new
  structure: ``AlarmsState``, ``WIFIIPAddress``, ``WIFINetmask``,
  ``WIFIGateway``, ``WIFIDNS``, ``UpgradeFWReadyCmd``. These ``pytest.skip()``
  (via the ``oracle`` fixture) when the oracle is not importable.
* **FakeSerial-backed** encode/decode tests for representative ``SystemMixin``
  methods: assert the written frame's ``id`` + ``rw``/``queued`` ctrl bits and
  that GET methods decode their response correctly.
"""
import struct

from dobotkit.arm import structures as S
from dobotkit.arm.ids import ProtocolId
from dobotkit.arm.lowlevel import LowLevelArm
from dobotkit.arm.protocol import Message
from dobotkit.arm.transport import SerialTransport
from tests.conftest import FakeSerial


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def make_arm(responses=None):
    """Build a LowLevelArm over a FakeSerial via the injectable factory."""
    fake = FakeSerial(responses or [])
    tx = SerialTransport(port="FAKE", _serial_factory=lambda *a, **k: fake)
    return LowLevelArm(tx), fake


def written_frame(fake):
    """Parse the single frame the arm wrote to the fake serial."""
    return Message.from_bytes(bytes(fake.written))


def resp(id_, params=b""):
    """A response frame (ctrl=0) the device would send back."""
    return Message(id=id_, ctrl=0, params=params).to_bytes()


# ===================================================================== #
# Struct byte-match vs oracle
# ===================================================================== #
def test_alarmsstate_pack_and_unpack():
    raw = S.pack_AlarmsState(0x12345678)
    assert raw == struct.pack("<i", 0x12345678)
    assert S.unpack_AlarmsState(raw).alarms_state == 0x12345678


def test_alarmsstate_matches_oracle(oracle):
    o = oracle.AlarmsState()
    o.alarmsState = 0x12345678
    assert S.pack_AlarmsState(0x12345678) == bytes(o)


def test_wifiipaddress_pack_and_unpack():
    raw = S.pack_WIFIIPAddress(1, 192, 168, 1, 100)
    assert raw == struct.pack("<5B", 1, 192, 168, 1, 100)
    p = S.unpack_WIFIIPAddress(raw)
    assert (p.dhcp, p.addr1, p.addr2, p.addr3, p.addr4) == (1, 192, 168, 1, 100)


def test_wifiipaddress_matches_oracle(oracle):
    o = oracle.WIFIIPAddress()
    o.dhcp = 1
    o.addr1 = 192
    o.addr2 = 168
    o.addr3 = 1
    o.addr4 = 100
    assert S.pack_WIFIIPAddress(1, 192, 168, 1, 100) == bytes(o)


def test_wifinetmask_pack_and_unpack():
    raw = S.pack_WIFINetmask(255, 255, 255, 0)
    assert raw == struct.pack("<4B", 255, 255, 255, 0)
    p = S.unpack_WIFINetmask(raw)
    assert (p.addr1, p.addr2, p.addr3, p.addr4) == (255, 255, 255, 0)


def test_wifinetmask_matches_oracle(oracle):
    o = oracle.WIFINetmask()
    o.addr1 = 255
    o.addr2 = 255
    o.addr3 = 255
    o.addr4 = 0
    assert S.pack_WIFINetmask(255, 255, 255, 0) == bytes(o)


def test_wifigateway_matches_oracle(oracle):
    o = oracle.WIFIGateway()
    o.addr1 = 192
    o.addr2 = 168
    o.addr3 = 1
    o.addr4 = 1
    assert S.pack_WIFIGateway(192, 168, 1, 1) == bytes(o)


def test_wifidns_matches_oracle(oracle):
    o = oracle.WIFIDNS()
    o.addr1 = 8
    o.addr2 = 8
    o.addr3 = 8
    o.addr4 = 8
    assert S.pack_WIFIDNS(8, 8, 8, 8) == bytes(o)


def test_upgradefw_pack_size_and_fwsize_prefix():
    md5 = "0123456789abcdef0123456789abcdef"
    raw = S.pack_UpgradeFWReadyCmd(4096, bytes.fromhex(md5))
    # fwSize (uint32 LE) + 16-byte digest.
    assert len(raw) == 20
    assert raw[:4] == struct.pack("<I", 4096)
    assert raw[4:] == bytes.fromhex(md5)
    p = S.unpack_UpgradeFWReadyCmd(raw)
    assert p.fw_size == 4096
    assert p.md5 == bytes.fromhex(md5)


def test_upgradefw_fwsize_matches_oracle(oracle):
    # The oracle declares md5 as a c_char_p *pointer*, so only the leading
    # uint32 fwSize is meaningful inline data; match that prefix.
    o = oracle.UpgradeFWReadyCmd()
    o.fwSize = 4096
    raw = S.pack_UpgradeFWReadyCmd(4096, bytes.fromhex("00" * 16))
    assert raw[:4] == bytes(o)[:4]


# ===================================================================== #
# FakeSerial-backed method tests
# ===================================================================== #
def test_clear_all_alarms_state_sets_rw_bit():
    arm, fake = make_arm([resp(ProtocolId.CLEAR_ALL_ALARMS_STATE)])
    arm.clear_all_alarms_state()
    f = written_frame(fake)
    assert f.id == ProtocolId.CLEAR_ALL_ALARMS_STATE
    assert f.ctrl & 0b01  # rw set
    assert not (f.ctrl & 0b10)  # not queued


def test_get_alarms_state_returns_raw_bitmap():
    bitmap = b"\x01\x00\x80\x00"
    arm, fake = make_arm([resp(ProtocolId.GET_ALARMS_STATE, bitmap)])
    out = arm.get_alarms_state()
    assert out == bitmap
    f = written_frame(fake)
    assert f.id == ProtocolId.GET_ALARMS_STATE
    assert not (f.ctrl & 0b01)  # read (rw=0)


def test_set_arm_speed_ratio_immediate_writes_params():
    arm, fake = make_arm([resp(ProtocolId.SET_GET_ARM_SPEED_RATIO)])
    ret = arm.set_arm_speed_ratio(params_mode=1, speed_ratio=50)
    assert ret is None
    f = written_frame(fake)
    assert f.id == ProtocolId.SET_GET_ARM_SPEED_RATIO
    assert f.ctrl & 0b01  # rw set
    assert f.params == struct.pack("<BB", 1, 50)


def test_set_arm_speed_ratio_queued_returns_index():
    idx = 7
    arm, fake = make_arm(
        [resp(ProtocolId.SET_GET_ARM_SPEED_RATIO, struct.pack("<Q", idx))]
    )
    ret = arm.set_arm_speed_ratio(params_mode=0, speed_ratio=80, queued=True)
    assert ret == idx
    f = written_frame(fake)
    assert f.ctrl & 0b11 == 0b11  # rw and queued both set


def test_get_arm_speed_ratio_decodes_byte():
    arm, fake = make_arm(
        [resp(ProtocolId.SET_GET_ARM_SPEED_RATIO, struct.pack("<B", 42))]
    )
    assert arm.get_arm_speed_ratio(params_mode=0) == 42
    f = written_frame(fake)
    assert not (f.ctrl & 0b01)  # rw=0 (get)
    assert f.params == struct.pack("<B", 0)


def test_set_motor_mode_and_get_motor_mode():
    arm, fake = make_arm([resp(ProtocolId.SET_GET_MOTOR_MODE)])
    arm.set_motor_mode(2)
    f = written_frame(fake)
    assert f.id == ProtocolId.SET_GET_MOTOR_MODE
    assert f.ctrl & 0b01
    assert f.params == struct.pack("<i", 2)

    arm2, _ = make_arm(
        [resp(ProtocolId.SET_GET_MOTOR_MODE, struct.pack("<i", 3))]
    )
    assert arm2.get_motor_mode() == 3


def test_set_lost_step_params_queued_index():
    idx = 11
    arm, fake = make_arm(
        [resp(ProtocolId.SET_GET_LOST_STEP_PARAMS, struct.pack("<Q", idx))]
    )
    ret = arm.set_lost_step_params(threshold=5.0, queued=True)
    assert ret == idx
    f = written_frame(fake)
    assert f.id == ProtocolId.SET_GET_LOST_STEP_PARAMS
    assert f.params == struct.pack("<f", 5.0)
    assert f.ctrl & 0b11 == 0b11


def test_get_lost_step_enable_and_params_decodes():
    arm, fake = make_arm([resp(_lost_step_id(), struct.pack("<Bf", 1, 3.5))])
    enabled, threshold = arm.get_lost_step_enable_and_params()
    assert enabled is True
    assert threshold == 3.5
    f = written_frame(fake)
    assert not (f.ctrl & 0b01)  # rw=0


def test_set_lost_step_enable_and_params_encodes():
    arm, fake = make_arm([resp(_lost_step_id())])
    ret = arm.set_lost_step_enable_and_params(enable=True, threshold=2.0)
    assert ret is None
    f = written_frame(fake)
    assert f.params == struct.pack("<Bf", 1, 2.0)
    assert f.ctrl & 0b01


def test_hht_trig_mode_roundtrip():
    arm, fake = make_arm([resp(ProtocolId.SET_GET_HHTTRIG_MODE)])
    arm.set_hht_trig_mode(1)
    f = written_frame(fake)
    assert f.id == ProtocolId.SET_GET_HHTTRIG_MODE
    assert f.params == struct.pack("<i", 1)

    arm2, _ = make_arm(
        [resp(ProtocolId.SET_GET_HHTTRIG_MODE, struct.pack("<i", 2))]
    )
    assert arm2.get_hht_trig_mode() == 2


def test_get_hht_trig_output_true():
    arm, _ = make_arm([resp(ProtocolId.GET_HHTTRIG_OUTPUT, b"\x01")])
    assert arm.get_hht_trig_output() is True


def test_angle_sensor_static_error_roundtrip():
    arm, fake = make_arm([resp(ProtocolId.SET_GET_ANGLE_SENSOR_STATIC_ERROR)])
    arm.set_angle_sensor_static_error(0.5, -0.25)
    f = written_frame(fake)
    assert f.id == ProtocolId.SET_GET_ANGLE_SENSOR_STATIC_ERROR
    assert f.params == struct.pack("<ff", 0.5, -0.25)

    arm2, _ = make_arm(
        [
            resp(
                ProtocolId.SET_GET_ANGLE_SENSOR_STATIC_ERROR,
                struct.pack("<ff", 1.0, 2.0),
            )
        ]
    )
    assert arm2.get_angle_sensor_static_error() == (1.0, 2.0)


def test_get_base_decoder_static_error_decodes():
    arm, _ = make_arm(
        [
            resp(
                ProtocolId.SET_GET_BASE_DECODER_STATIC_ERROR,
                struct.pack("<f", 0.75),
            )
        ]
    )
    assert arm.get_base_decoder_static_error() == 0.75


def test_set_wifi_ssid_encodes_and_get_decodes():
    arm, fake = make_arm([resp(ProtocolId.SET_GET_WIFI_SSID)])
    arm.set_wifi_ssid("dobot-net")
    f = written_frame(fake)
    assert f.id == ProtocolId.SET_GET_WIFI_SSID
    assert f.ctrl & 0b01
    assert f.params.split(b"\x00", 1)[0] == b"dobot-net"

    arm2, _ = make_arm(
        [resp(ProtocolId.SET_GET_WIFI_SSID, b"my-ssid\x00garbage")]
    )
    assert arm2.get_wifi_ssid() == "my-ssid"


def test_set_wifi_ip_address_encodes():
    arm, fake = make_arm([resp(ProtocolId.SET_GET_WIFI_IP_ADDRESS)])
    arm.set_wifi_ip_address(1, 192, 168, 1, 100)
    f = written_frame(fake)
    assert f.id == ProtocolId.SET_GET_WIFI_IP_ADDRESS
    assert f.params == S.pack_WIFIIPAddress(1, 192, 168, 1, 100)


def test_get_wifi_ip_address_decodes():
    arm, _ = make_arm(
        [
            resp(
                ProtocolId.SET_GET_WIFI_IP_ADDRESS,
                S.pack_WIFIIPAddress(0, 10, 0, 0, 5),
            )
        ]
    )
    p = arm.get_wifi_ip_address()
    assert (p.dhcp, p.addr1, p.addr2, p.addr3, p.addr4) == (0, 10, 0, 0, 5)


def test_get_wifi_connect_status():
    arm, _ = make_arm([resp(ProtocolId.GET_WIFI_CONNECT_STATUS, b"\x01")])
    assert arm.get_wifi_connect_status() is True


def test_set_wifi_config_mode_and_get():
    arm, fake = make_arm([resp(ProtocolId.SET_GET_WIFI_CONFIG_MODE)])
    arm.set_wifi_config_mode(True)
    f = written_frame(fake)
    assert f.params == struct.pack("<?", True)
    assert f.ctrl & 0b01

    arm2, _ = make_arm(
        [resp(ProtocolId.SET_GET_WIFI_CONFIG_MODE, b"\x01")]
    )
    assert arm2.get_wifi_config_mode() is True


def test_queue_passthroughs_emit_correct_ids():
    # clear
    arm, fake = make_arm([resp(ProtocolId.SET_QUEUED_CMD_CLEAR)])
    arm.queued_cmd_clear()
    assert written_frame(fake).id == ProtocolId.SET_QUEUED_CMD_CLEAR

    # start
    arm, fake = make_arm([resp(ProtocolId.SET_QUEUED_CMD_START_EXEC)])
    arm.queued_cmd_start_exec()
    assert written_frame(fake).id == ProtocolId.SET_QUEUED_CMD_START_EXEC

    # stop
    arm, fake = make_arm([resp(ProtocolId.SET_QUEUED_CMD_STOP_EXEC)])
    arm.queued_cmd_stop_exec()
    assert written_frame(fake).id == ProtocolId.SET_QUEUED_CMD_STOP_EXEC

    # force stop
    arm, fake = make_arm([resp(ProtocolId.SET_QUEUED_CMD_FORCE_STOP_EXEC)])
    arm.queued_cmd_force_stop_exec()
    assert written_frame(fake).id == ProtocolId.SET_QUEUED_CMD_FORCE_STOP_EXEC


def test_get_queued_cmd_current_index_decodes_uint64():
    arm, _ = make_arm(
        [resp(ProtocolId.GET_QUEUED_CMD_CURRENT_INDEX, struct.pack("<Q", 99))]
    )
    assert arm.get_queued_cmd_current_index() == 99


def test_get_queued_cmd_motion_finish_decodes_bool():
    arm, _ = make_arm(
        [resp(ProtocolId.GET_QUEUED_CMD_MOTION_FINISH, struct.pack("<?", True))]
    )
    assert arm.get_queued_cmd_motion_finish() is True


def test_queued_cmd_start_download_encodes_params():
    arm, fake = make_arm([resp(243)])
    arm.queued_cmd_start_download(total_loop=3, line_per_loop=10)
    f = written_frame(fake)
    assert f.id == 243
    assert f.params == struct.pack("<II", 3, 10)
    assert f.ctrl & 0b01


def test_set_upgrade_fw_ready_encodes():
    arm, fake = make_arm([resp(250)])
    md5 = "0123456789abcdef0123456789abcdef"
    arm.set_upgrade_fw_ready(fw_size=2048, md5=md5)
    f = written_frame(fake)
    assert f.id == 250
    assert f.params == S.pack_UpgradeFWReadyCmd(2048, bytes.fromhex(md5))
    assert f.ctrl & 0b01


def _lost_step_id():
    """The protocol id used by set/get_lost_step_enable_and_params."""
    from dobotkit.arm.lowlevel.system import _SET_LOST_STEP_ENABLE_AND_PARAMS

    return _SET_LOST_STEP_ENABLE_AND_PARAMS
