"""Tests for the sensor category — structures (Task 2.8) + SensorMixin.

The sensor command set has **no** dedicated ``DobotDllType`` ``Structure``
classes (the golden SDK builds every sensor payload inline from scalar C
arguments), so there is nothing of the form ``bytes(oracle.StructX(...))`` to
compare against. The struct tests therefore byte-match against explicit
little-endian ``struct.pack`` literals whose field widths are derived directly
from the oracle ``api.Set*`` / ``api.Get*`` C call signatures
(``c_uint8`` / ``c_ubyte`` / ``c_ushort`` / ``c_float``). See the module
docstring of ``dobotkit.arm.structures.sensor`` for the per-struct derivation.

Method tests drive a real :class:`SerialTransport` over the in-memory
``FakeSerial`` double, asserting the frame written by each method (id + rw /
queued ctrl bits) and that GET methods decode their response payloads.
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
def make_arm(responses):
    """Build a LowLevelArm over a FakeSerial preloaded with response frames."""
    fake = FakeSerial(responses)
    tx = SerialTransport(port="FAKE", _serial_factory=lambda *a, **k: fake)
    return LowLevelArm(tx), fake


def written_frame(fake):
    """Parse the single frame the arm wrote to the fake serial port."""
    return Message.from_bytes(bytes(fake.written))


# --------------------------------------------------------------------------- #
# Structures: byte-layout (vs struct.pack literals; widths from the oracle)
# --------------------------------------------------------------------------- #
def test_color_sensor_params_pack_unpack():
    raw = S.pack_ColorSensorParams(enable=1, port=2, version=3)
    assert raw == struct.pack("<BBB", 1, 2, 3)
    assert len(raw) == 3
    p = S.unpack_ColorSensorParams(raw)
    assert (p.enable, p.port, p.version) == (1, 2, 3)
    # enable is coerced to a 0/1 bool byte (oracle uses c_bool).
    assert S.pack_ColorSensorParams(enable=5, port=0) == struct.pack("<BBB", 1, 0, 0)


def test_color_sensor_reading_pack_unpack():
    raw = S.pack_ColorSensorReading(r=10, g=20, b=30)
    assert raw == struct.pack("<BBB", 10, 20, 30)
    assert len(raw) == 3
    p = S.unpack_ColorSensorReading(raw)
    assert (p.r, p.g, p.b) == (10, 20, 30)


def test_infrared_sensor_params_pack_unpack():
    raw = S.pack_InfraredSensorParams(enable=1, port=1, version=0)
    assert raw == struct.pack("<BBB", 1, 1, 0)
    p = S.unpack_InfraredSensorParams(raw)
    assert (p.enable, p.port, p.version) == (1, 1, 0)


def test_infrared_sensor_reading_pack_unpack():
    raw = S.pack_InfraredSensorReading(value=1)
    assert raw == struct.pack("<B", 1)
    assert len(raw) == 1
    assert S.unpack_InfraredSensorReading(raw).value == 1


def test_seeed_color_reading_pack_unpack():
    raw = S.pack_SeeedColorReading(r=1000, g=2000, b=3000, cct=4000)
    assert raw == struct.pack("<HHHH", 1000, 2000, 3000, 4000)
    assert len(raw) == 8
    p = S.unpack_SeeedColorReading(raw)
    assert (p.r, p.g, p.b, p.cct) == (1000, 2000, 3000, 4000)


def test_seeed_temp_reading_pack_unpack():
    raw = S.pack_SeeedTempReading(temperature=250, humidity=600)
    assert raw == struct.pack("<HH", 250, 600)
    assert len(raw) == 4
    p = S.unpack_SeeedTempReading(raw)
    assert (p.temperature, p.humidity) == (250, 600)


def test_seeed_light_reading_pack_unpack():
    raw = S.pack_SeeedLightReading(lux=12345)
    assert raw == struct.pack("<H", 12345)
    assert len(raw) == 2
    assert S.unpack_SeeedLightReading(raw).lux == 12345


def test_seeed_distance_reading_pack_unpack():
    raw = S.pack_SeeedDistanceReading(distance=42)
    assert raw == struct.pack("<B", 42)
    assert len(raw) == 1
    assert S.unpack_SeeedDistanceReading(raw).distance == 42


def test_seeed_rgb_params_pack_unpack():
    raw = S.pack_SeeedRgbParams(port=1, rgb=3.5)
    assert raw == struct.pack("<Bf", 1, 3.5)
    assert len(raw) == 5
    p = S.unpack_SeeedRgbParams(raw)
    assert (p.port, p.rgb) == (1, 3.5)


# --------------------------------------------------------------------------- #
# Color sensor  ->  SET_GET_COLOR_SENSOR (137)
# --------------------------------------------------------------------------- #
def test_set_color_sensor_immediate_writes_frame():
    resp = Message(
        id=ProtocolId.SET_GET_COLOR_SENSOR, ctrl=0b01, params=b""
    ).to_bytes()
    arm, fake = make_arm([resp])
    out = arm.set_color_sensor(enable=1, port=2, version=0)
    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_COLOR_SENSOR
    assert frame.ctrl & 0b01 == 0b01  # write
    assert frame.ctrl & 0b10 == 0  # not queued
    assert frame.params == S.pack_ColorSensorParams(enable=1, port=2, version=0)
    assert out is None


def test_set_color_sensor_queued_returns_index():
    resp = Message(
        id=ProtocolId.SET_GET_COLOR_SENSOR, ctrl=0b11, params=struct.pack("<Q", 17)
    ).to_bytes()
    arm, fake = make_arm([resp])
    idx = arm.set_color_sensor(enable=1, port=0, queued=True)
    frame = written_frame(fake)
    assert frame.ctrl & 0b11 == 0b11  # rw + queued
    assert idx == 17


def test_get_color_sensor_decodes_rgb():
    payload = struct.pack("<BBB", 11, 22, 33)
    resp = Message(
        id=ProtocolId.SET_GET_COLOR_SENSOR, ctrl=0, params=payload
    ).to_bytes()
    arm, fake = make_arm([resp])
    reading = arm.get_color_sensor()
    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_COLOR_SENSOR
    assert frame.ctrl & 0b01 == 0  # read
    assert (reading.r, reading.g, reading.b) == (11, 22, 33)


def test_color_sensor_ext_delegates_to_base():
    resp = Message(
        id=ProtocolId.SET_GET_COLOR_SENSOR, ctrl=0b01, params=b""
    ).to_bytes()
    arm, fake = make_arm([resp])
    arm.set_color_sensor_ext(enable=1, port=1)
    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_COLOR_SENSOR
    assert frame.ctrl & 0b01 == 0b01


# --------------------------------------------------------------------------- #
# Infrared sensor  ->  SET_GET_IR_SWITCH (138)
# --------------------------------------------------------------------------- #
def test_set_infrared_sensor_immediate():
    resp = Message(
        id=ProtocolId.SET_GET_IR_SWITCH, ctrl=0b01, params=b""
    ).to_bytes()
    arm, fake = make_arm([resp])
    arm.set_infrared_sensor(enable=1, port=1, version=0)
    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_IR_SWITCH
    assert frame.ctrl & 0b01 == 0b01
    assert frame.params == S.pack_InfraredSensorParams(enable=1, port=1, version=0)


def test_get_infrared_sensor_decodes_value():
    payload = struct.pack("<B", 1)
    resp = Message(
        id=ProtocolId.SET_GET_IR_SWITCH, ctrl=0, params=payload
    ).to_bytes()
    arm, fake = make_arm([resp])
    reading = arm.get_infrared_sensor(port=1)
    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_IR_SWITCH
    assert frame.ctrl & 0b01 == 0  # read
    # GET request carries the port byte.
    assert frame.params == struct.pack("<B", 1)
    assert reading.value == 1


def test_set_infrared_sensor_ext_ex_queued_returns_index():
    resp = Message(
        id=ProtocolId.SET_GET_IR_SWITCH, ctrl=0b11, params=struct.pack("<Q", 5)
    ).to_bytes()
    arm, fake = make_arm([resp])
    idx = arm.set_infrared_sensor_ext_ex(enable=0, port=2, queued=True)
    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_GET_IR_SWITCH
    assert frame.ctrl & 0b11 == 0b11
    assert idx == 5


# --------------------------------------------------------------------------- #
# Seeed distance sensor  (PLAN: "returns float mm" — wire is c_ubyte; see issues)
# --------------------------------------------------------------------------- #
def test_get_seeed_distance_sensor_decodes():
    payload = struct.pack("<B", 99)
    resp = Message(
        id=ProtocolId.SET_GET_COLOR_SENSOR, ctrl=0, params=payload
    ).to_bytes()
    arm, fake = make_arm([resp])
    reading = arm.get_seeed_distance_sensor(port=1)
    frame = written_frame(fake)
    assert frame.ctrl & 0b01 == 0  # read
    assert frame.params == struct.pack("<B", 1)  # port byte
    assert reading.distance == 99


# --------------------------------------------------------------------------- #
# Seeed color sensor
# --------------------------------------------------------------------------- #
def test_set_seeed_color_sensor_queued_returns_index():
    resp = Message(
        id=ProtocolId.SET_GET_COLOR_SENSOR, ctrl=0b11, params=struct.pack("<Q", 8)
    ).to_bytes()
    arm, fake = make_arm([resp])
    idx = arm.set_seeed_color_sensor(port=1, queued=True)
    frame = written_frame(fake)
    assert frame.ctrl & 0b11 == 0b11
    assert frame.params == struct.pack("<B", 1)
    assert idx == 8


def test_get_seeed_color_sensor_decodes():
    payload = struct.pack("<HHHH", 100, 200, 300, 400)
    resp = Message(
        id=ProtocolId.SET_GET_COLOR_SENSOR, ctrl=0, params=payload
    ).to_bytes()
    arm, fake = make_arm([resp])
    reading = arm.get_seeed_color_sensor()
    frame = written_frame(fake)
    assert frame.ctrl & 0b01 == 0  # read
    assert (reading.r, reading.g, reading.b, reading.cct) == (100, 200, 300, 400)


# --------------------------------------------------------------------------- #
# Seeed temp sensor  ->  returns (temperature, humidity)
# --------------------------------------------------------------------------- #
def test_get_seeed_temp_sensor_decodes_pair():
    payload = struct.pack("<HH", 250, 600)
    resp = Message(
        id=ProtocolId.SET_GET_COLOR_SENSOR, ctrl=0, params=payload
    ).to_bytes()
    arm, fake = make_arm([resp])
    reading = arm.get_seeed_temp_sensor()
    frame = written_frame(fake)
    assert frame.ctrl & 0b01 == 0  # read
    assert (reading.temperature, reading.humidity) == (250, 600)


def test_set_seeed_temp_sensor_immediate():
    resp = Message(
        id=ProtocolId.SET_GET_COLOR_SENSOR, ctrl=0b01, params=b""
    ).to_bytes()
    arm, fake = make_arm([resp])
    out = arm.set_seeed_temp_sensor(port=1)
    frame = written_frame(fake)
    assert frame.ctrl & 0b01 == 0b01
    assert out is None


# --------------------------------------------------------------------------- #
# Seeed light sensor
# --------------------------------------------------------------------------- #
def test_get_seeed_light_sensor_decodes():
    payload = struct.pack("<H", 4242)
    resp = Message(
        id=ProtocolId.SET_GET_COLOR_SENSOR, ctrl=0, params=payload
    ).to_bytes()
    arm, fake = make_arm([resp])
    reading = arm.get_seeed_light_sensor()
    assert written_frame(fake).ctrl & 0b01 == 0
    assert reading.lux == 4242


# --------------------------------------------------------------------------- #
# Seeed RGB LED
# --------------------------------------------------------------------------- #
def test_set_seeed_rgb_immediate_writes_frame():
    resp = Message(
        id=ProtocolId.SET_GET_COLOR_SENSOR, ctrl=0b01, params=b""
    ).to_bytes()
    arm, fake = make_arm([resp])
    out = arm.set_seeed_rgb(port=1, rgb=2.0)
    frame = written_frame(fake)
    assert frame.id == ProtocolId.SET_SEEED_RGB
    assert frame.ctrl & 0b01 == 0b01  # write
    assert frame.params == S.pack_SeeedRgbParams(port=1, rgb=2.0)
    assert out is None


def test_set_seeed_rgb_ext_ex_queued_returns_index():
    resp = Message(
        id=ProtocolId.SET_GET_COLOR_SENSOR, ctrl=0b11, params=struct.pack("<Q", 21)
    ).to_bytes()
    arm, fake = make_arm([resp])
    idx = arm.set_seeed_rgb_ext_ex(port=0, rgb=1.0, queued=True)
    frame = written_frame(fake)
    assert frame.ctrl & 0b11 == 0b11
    assert idx == 21
