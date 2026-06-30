"""Tests for the ``io`` low-level category (Task 2.7).

Covers:
(a) byte-match of every new struct (IOMultiplexing, IODO, IOPWM, IODI, IOADC,
    EMotor, EMotorS, WAITCmd, TRIGCmd) against the golden oracle.
(b) FakeSerial-backed encode/decode tests for representative ``IoMixin``
    methods: the written frame's id + rw/queued ctrl bits are asserted, GET
    methods decode their response, and the ``_ext`` / ``_ext_ex`` wrappers are
    shown to reuse the base id while flagging MagicBox routing.
"""
import struct


from dobotkit.arm import structures as S
from dobotkit.arm.ids import ProtocolId
from dobotkit.arm.protocol import Message
from dobotkit.arm.lowlevel import LowLevelArm
from dobotkit.arm.transport import SerialTransport
from tests.conftest import FakeSerial


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _make_arm(responses):
    fake = FakeSerial(responses)
    tx = SerialTransport(port="FAKE", _serial_factory=lambda *a, **k: fake)
    return LowLevelArm(tx), fake


def _resp(id_, params=b""):
    """A response frame (rw=0) carrying ``params`` for command ``id_``."""
    return Message(id=int(id_), ctrl=0, params=params).to_bytes()


def _written(fake):
    return Message.from_bytes(bytes(fake.written))


# --------------------------------------------------------------------------- #
# (a) struct byte-match vs oracle
# --------------------------------------------------------------------------- #
def test_io_multiplexing_pack_and_oracle(oracle):
    raw = S.pack_IOMultiplexing(address=2, multiplex=1)
    assert raw == struct.pack("<bb", 2, 1)
    o = oracle.IOMultiplexing()
    o.address = 2
    o.multiplex = 1
    assert raw == bytes(o)
    u = S.unpack_IOMultiplexing(raw)
    assert (u.address, u.multiplex) == (2, 1)


def test_io_do_pack_and_oracle(oracle):
    raw = S.pack_IODO(address=2, level=1)
    assert raw == struct.pack("<bb", 2, 1)
    o = oracle.IODO()
    o.address = 2
    o.level = 1
    assert raw == bytes(o)
    assert S.unpack_IODO(raw).level == 1


def test_io_pwm_pack_and_oracle(oracle):
    raw = S.pack_IOPWM(address=4, frequency=10000.0, duty_cycle=50.0)
    assert raw == struct.pack("<bff", 4, 10000.0, 50.0)
    o = oracle.IOPWM()
    o.address = 4
    o.frequency = 10000.0
    o.dutyCycle = 50.0
    assert raw == bytes(o)
    u = S.unpack_IOPWM(raw)
    assert (u.address, u.frequency, u.duty_cycle) == (4, 10000.0, 50.0)


def test_io_di_pack_and_oracle(oracle):
    raw = S.pack_IODI(address=3, level=1)
    assert raw == struct.pack("<bb", 3, 1)
    o = oracle.IODI()
    o.address = 3
    o.level = 1
    assert raw == bytes(o)
    assert S.unpack_IODI(raw).level == 1


def test_io_adc_pack_and_oracle(oracle):
    raw = S.pack_IOADC(address=5, value=1234)
    assert raw == struct.pack("<bi", 5, 1234)
    o = oracle.IOADC()
    o.address = 5
    o.value = 1234
    assert raw == bytes(o)
    assert S.unpack_IOADC(raw).value == 1234


def test_emotor_pack_and_oracle(oracle):
    raw = S.pack_EMotor(index=0, is_enabled=1, speed=10000)
    assert raw == struct.pack("<bbi", 0, 1, 10000)
    o = oracle.EMotor()
    o.index = 0
    o.isEnabled = 1
    o.speed = 10000
    assert raw == bytes(o)
    u = S.unpack_EMotor(raw)
    assert (u.index, u.is_enabled, u.speed) == (0, 1, 10000)


def test_emotors_pack_and_oracle(oracle):
    raw = S.pack_EMotorS(index=1, is_enabled=1, speed=-5000, distance=12345)
    assert raw == struct.pack("<bbiI", 1, 1, -5000, 12345)
    o = oracle.EMotorS()
    o.index = 1
    o.isEnabled = 1
    o.speed = -5000
    o.distance = 12345
    assert raw == bytes(o)
    u = S.unpack_EMotorS(raw)
    assert (u.index, u.is_enabled, u.speed, u.distance) == (1, 1, -5000, 12345)


def test_wait_cmd_pack_and_oracle(oracle):
    raw = S.pack_WAITCmd(wait_time=1000)
    assert raw == struct.pack("<I", 1000)
    o = oracle.WAITCmd()
    o.waitTime = 1000
    assert raw == bytes(o)
    assert S.unpack_WAITCmd(raw).wait_time == 1000


def test_trig_cmd_pack_and_oracle(oracle):
    raw = S.pack_TRIGCmd(address=1, mode=0, condition=0, threshold=512)
    assert raw == struct.pack("<bbbH", 1, 0, 0, 512)
    o = oracle.TRIGCmd()
    o.address = 1
    o.mode = 0
    o.condition = 0
    o.threshold = 512
    assert raw == bytes(o)
    u = S.unpack_TRIGCmd(raw)
    assert (u.address, u.mode, u.condition, u.threshold) == (1, 0, 0, 512)


def test_all_exports_present():
    for name in (
        "IOMultiplexing", "IODO", "IOPWM", "IODI", "IOADC",
        "EMotor", "EMotorS", "WAITCmd", "TRIGCmd",
    ):
        assert hasattr(S, f"pack_{name}")
        assert hasattr(S, f"unpack_{name}")
        assert name in S.__dict__ or hasattr(S, name)


# --------------------------------------------------------------------------- #
# (b) IoMixin encode/decode via FakeSerial
# --------------------------------------------------------------------------- #
def test_set_io_multiplexing_writes_rw_frame():
    arm, fake = _make_arm([_resp(ProtocolId.SET_GET_IO_MULTIPLEXING)])
    out = arm.set_io_multiplexing(address=2, multiplex=1)
    w = _written(fake)
    assert w.id == ProtocolId.SET_GET_IO_MULTIPLEXING
    assert w.ctrl & 0b01  # rw set (a "set")
    assert not (w.ctrl & 0b10)  # not queued
    assert w.params == struct.pack("<bb", 2, 1)
    assert out is None


def test_set_io_multiplexing_queued_returns_index():
    arm, fake = _make_arm(
        [_resp(ProtocolId.SET_GET_IO_MULTIPLEXING, struct.pack("<Q", 7))]
    )
    idx = arm.set_io_multiplexing(address=2, multiplex=1, queued=True)
    w = _written(fake)
    assert w.id == ProtocolId.SET_GET_IO_MULTIPLEXING
    assert w.ctrl & 0b11 == 0b11  # rw + queued
    assert idx == 7


def test_get_io_multiplexing_decodes():
    arm, fake = _make_arm(
        [_resp(ProtocolId.SET_GET_IO_MULTIPLEXING, struct.pack("<bb", 2, 4))]
    )
    res = arm.get_io_multiplexing(address=2)
    w = _written(fake)
    assert w.id == ProtocolId.SET_GET_IO_MULTIPLEXING
    assert not (w.ctrl & 0b01)  # rw=0 (a "get")
    assert res.multiplex == 4


def test_set_io_do_frame():
    arm, fake = _make_arm([_resp(ProtocolId.SET_GET_IO_DO)])
    arm.set_io_do(address=2, level=1)
    w = _written(fake)
    assert w.id == ProtocolId.SET_GET_IO_DO
    assert w.ctrl & 0b01
    assert w.params == struct.pack("<bb", 2, 1)


def test_get_io_do_decodes():
    arm, fake = _make_arm(
        [_resp(ProtocolId.SET_GET_IO_DO, struct.pack("<bb", 2, 1))]
    )
    assert arm.get_io_do(address=2).level == 1
    assert not (_written(fake).ctrl & 0b01)


def test_set_io_pwm_frame():
    arm, fake = _make_arm([_resp(ProtocolId.SET_GET_IO_PWM)])
    arm.set_io_pwm(address=4, frequency=10000.0, duty_cycle=50.0)
    w = _written(fake)
    assert w.id == ProtocolId.SET_GET_IO_PWM
    assert w.ctrl & 0b01
    assert w.params == struct.pack("<bff", 4, 10000.0, 50.0)


def test_get_io_pwm_decodes():
    arm, fake = _make_arm(
        [_resp(ProtocolId.SET_GET_IO_PWM, struct.pack("<bff", 4, 10000.0, 50.0))]
    )
    p = arm.get_io_pwm(address=4)
    assert (p.frequency, p.duty_cycle) == (10000.0, 50.0)


def test_get_io_di_decodes():
    arm, fake = _make_arm(
        [_resp(ProtocolId.GET_IO_DI, struct.pack("<bb", 3, 1))]
    )
    res = arm.get_io_di(address=3)
    w = _written(fake)
    assert w.id == ProtocolId.GET_IO_DI
    assert not (w.ctrl & 0b01)
    assert res.level == 1


def test_get_io_adc_decodes():
    arm, fake = _make_arm(
        [_resp(ProtocolId.GET_IO_ADC, struct.pack("<bi", 5, 2048))]
    )
    res = arm.get_io_adc(address=5)
    w = _written(fake)
    assert w.id == ProtocolId.GET_IO_ADC
    assert not (w.ctrl & 0b01)
    assert res.value == 2048


def test_set_e_motor_frame():
    arm, fake = _make_arm([_resp(ProtocolId.SET_EMOTOR)])
    arm.set_e_motor(index=0, is_enabled=1, speed=10000)
    w = _written(fake)
    assert w.id == ProtocolId.SET_EMOTOR
    assert w.ctrl & 0b01
    assert w.params == struct.pack("<bbi", 0, 1, 10000)


def test_set_e_motor_queued_returns_index():
    arm, fake = _make_arm([_resp(ProtocolId.SET_EMOTOR, struct.pack("<Q", 11))])
    idx = arm.set_e_motor(index=0, is_enabled=1, speed=10000, queued=True)
    w = _written(fake)
    assert w.ctrl & 0b10  # queued bit
    assert idx == 11


def test_set_e_motors_frame():
    arm, fake = _make_arm([_resp(ProtocolId.SET_EMOTOR_S)])
    arm.set_e_motors(index=1, is_enabled=1, speed=-5000, distance=12345)
    w = _written(fake)
    assert w.id == ProtocolId.SET_EMOTOR_S
    assert w.ctrl & 0b01
    assert w.params == struct.pack("<bbiI", 1, 1, -5000, 12345)


def test_set_wait_cmd_frame():
    arm, fake = _make_arm([_resp(ProtocolId.SET_WAIT_CMD, struct.pack("<Q", 3))])
    idx = arm.set_wait_cmd(wait_time=1000, queued=True)
    w = _written(fake)
    assert w.id == ProtocolId.SET_WAIT_CMD
    assert w.ctrl & 0b01
    assert w.params == struct.pack("<I", 1000)
    assert idx == 3


def test_set_trig_cmd_frame():
    arm, fake = _make_arm([_resp(ProtocolId.SET_TRIG_CMD)])
    arm.set_trig_cmd(address=1, mode=0, condition=0, threshold=512)
    w = _written(fake)
    assert w.id == ProtocolId.SET_TRIG_CMD
    assert w.ctrl & 0b01
    assert w.params == struct.pack("<bbbH", 1, 0, 0, 512)


# --------------------------------------------------------------------------- #
# (b) _ext / _ext_ex wrappers: reuse the base id, set MagicBox routing flag
# --------------------------------------------------------------------------- #
def test_ext_methods_exist():
    arm, _ = _make_arm([])
    for base in (
        "io_multiplexing", "io_do", "io_pwm", "io_di", "io_adc",
        "e_motor", "e_motors",
    ):
        # the GET-only ones (di/adc) expose get_*_ext; the others expose set_*_ext
        has_set = hasattr(arm, f"set_{base}_ext")
        has_get = hasattr(arm, f"get_{base}_ext")
        assert has_set or has_get, f"missing _ext wrapper for {base}"
        has_set_ex = hasattr(arm, f"set_{base}_ext_ex")
        has_get_ex = hasattr(arm, f"get_{base}_ext_ex")
        assert has_set_ex or has_get_ex, f"missing _ext_ex wrapper for {base}"


def test_set_io_multiplexing_ext_reuses_id_and_flags_routing():
    arm, fake = _make_arm([_resp(ProtocolId.SET_GET_IO_MULTIPLEXING)])
    arm.set_io_multiplexing_ext(address=2, multiplex=1)
    w = _written(fake)
    # _ext reuses the SAME id as the base command.
    assert w.id == ProtocolId.SET_GET_IO_MULTIPLEXING
    assert w.ctrl & 0b01
    assert w.params == struct.pack("<bb", 2, 1)
    # routing flag is reset after the call (not left dangling).
    assert getattr(arm, "_routed_to_magicbox", False) is False


def test_set_io_multiplexing_ext_ex_reuses_id():
    arm, fake = _make_arm([_resp(ProtocolId.SET_GET_IO_MULTIPLEXING)])
    arm.set_io_multiplexing_ext_ex(address=2, multiplex=1)
    w = _written(fake)
    assert w.id == ProtocolId.SET_GET_IO_MULTIPLEXING
    assert w.params == struct.pack("<bb", 2, 1)


def test_get_io_adc_ext_decodes():
    arm, fake = _make_arm(
        [_resp(ProtocolId.GET_IO_ADC, struct.pack("<bi", 5, 99))]
    )
    res = arm.get_io_adc_ext(address=5)
    assert _written(fake).id == ProtocolId.GET_IO_ADC
    assert res.value == 99


def test_set_e_motor_ext_queued_returns_index():
    arm, fake = _make_arm([_resp(ProtocolId.SET_EMOTOR, struct.pack("<Q", 21))])
    idx = arm.set_e_motor_ext(index=0, is_enabled=1, speed=10000, queued=True)
    w = _written(fake)
    assert w.id == ProtocolId.SET_EMOTOR
    assert w.ctrl & 0b10
    assert idx == 21


def test_routing_flag_does_not_leak_between_calls():
    arm, fake = _make_arm(
        [
            _resp(ProtocolId.SET_GET_IO_DO),
            _resp(ProtocolId.SET_GET_IO_DO),
        ]
    )
    arm.set_io_do_ext(address=2, level=1)  # routed
    assert getattr(arm, "_routed_to_magicbox", False) is False
    arm.set_io_do(address=2, level=0)  # base, not routed
    assert getattr(arm, "_routed_to_magicbox", False) is False
