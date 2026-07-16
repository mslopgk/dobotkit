"""매직박스 미장착 시 주변장치 그룹의 우아한 처리 (design 2026-07-16).

매직박스를 거치는 주변장치 명령(센서 읽기/서보/E-motor/Seeed RGB)이 무응답으로
``DobotTimeoutError`` / ``DobotProtocolError``를 만나면, 그룹 파사드는 예외를
전파하는 대신 ``RuntimeWarning``을 내고 ``None``을 반환해야 한다. 팔 컨트롤러
직결 명령(석션컵/그리퍼/레이저/base EIO)은 그대로 예외를 전파해야 한다.
"""
import struct
from unittest.mock import MagicMock

import pytest

from dobotkit.arm._legacy_groups import EffectorGroup, IOGroup, SensorGroup
from dobotkit.exceptions import (
    DobotConnectionError,
    DobotProtocolError,
    DobotTimeoutError,
)

# 매직박스 경유 → 미연결 시 None+경고로 감싸야 하는 대상.
# (label, group_cls, 예외를 낼 저수준 메서드명, 그룹 메서드 호출)
WRAPPED = [
    ("color", SensorGroup, "get_color_sensor", lambda g: g.color(0)),
    # set 단계가 먼저 실패해도 전체가 감싸져 None 이어야 한다.
    ("color_set_fails", SensorGroup, "set_color_sensor", lambda g: g.color(0)),
    ("infrared", SensorGroup, "get_infrared_sensor", lambda g: g.infrared(1)),
    ("seeed_distance", SensorGroup, "get_seeed_distance_sensor", lambda g: g.seeed_distance(2)),
    ("seeed_color", SensorGroup, "get_seeed_color_sensor", lambda g: g.seeed_color(1)),
    ("seeed_temp", SensorGroup, "get_seeed_temp_sensor", lambda g: g.seeed_temp(3)),
    ("seeed_light", SensorGroup, "get_seeed_light_sensor", lambda g: g.seeed_light(0)),
    ("seeed_rgb", SensorGroup, "set_seeed_rgb", lambda g: g.seeed_rgb(1, 255.0)),
    ("set_servo", EffectorGroup, "set_servo_angle", lambda g: g.set_servo(1, 45.0)),
    ("get_servo", EffectorGroup, "get_servo_angle", lambda g: g.get_servo(1)),
    ("set_motor", IOGroup, "set_e_motor", lambda g: g.set_motor(0, True, 1000)),
    ("set_motor_steps", IOGroup, "set_e_motors", lambda g: g.set_motor_steps(1, False, 500, 2000)),
]

# 팔 컨트롤러 직결 → 매직박스와 무관하므로 예외를 그대로 전파해야 하는 대상.
EXCLUDED = [
    ("suck", EffectorGroup, "set_end_effector_suction_cup", lambda g: g.suck(True)),
    ("laser", EffectorGroup, "set_end_effector_laser", lambda g: g.laser(True)),
    ("set_do", IOGroup, "set_io_do", lambda g: g.set_do(5, 1)),
    ("get_di", IOGroup, "get_io_di", lambda g: g.get_di(7)),
    ("set_pwm", IOGroup, "set_io_pwm", lambda g: g.set_pwm(4, 1000.0, 50.0)),
]


def _group_with_failing(group_cls, ll_attr, exc):
    ll = MagicMock()
    getattr(ll, ll_attr).side_effect = exc
    return group_cls(ll)


@pytest.mark.parametrize(
    "group_cls,ll_attr,invoke",
    [(c[1], c[2], c[3]) for c in WRAPPED],
    ids=[c[0] for c in WRAPPED],
)
def test_peripheral_timeout_returns_none_and_warns(group_cls, ll_attr, invoke):
    group = _group_with_failing(group_cls, ll_attr, DobotTimeoutError("no response"))
    with pytest.warns(RuntimeWarning):
        assert invoke(group) is None


def test_peripheral_protocol_error_returns_none_and_warns():
    group = _group_with_failing(
        SensorGroup, "get_seeed_distance_sensor", DobotProtocolError("bad checksum")
    )
    with pytest.warns(RuntimeWarning):
        assert group.seeed_distance(2) is None


def test_short_payload_struct_error_returns_none_and_warns():
    # 실기 관찰(2026-07-16, COM7 매직박스 없음): 펌웨어가 타임아웃 없이 빈/짧은
    # 페이로드로 응답 → unpack 단계에서 struct.error. 프레임 자체는 정상이라
    # DobotProtocolError가 아니다. 이것도 '주변장치 미연결' 신호로 처리해야 한다.
    ll = MagicMock()
    ll.get_color_sensor.side_effect = struct.error(
        "unpack requires a buffer of 3 bytes"
    )
    with pytest.warns(RuntimeWarning):
        assert SensorGroup(ll).color(0) is None


def test_connection_error_is_not_swallowed():
    # 포트 미개방 등 설정 오류는 감지 대상이 아니라 그대로 터져야 한다.
    group = _group_with_failing(
        SensorGroup, "get_seeed_distance_sensor", DobotConnectionError("port closed")
    )
    with pytest.raises(DobotConnectionError):
        group.seeed_distance(2)


@pytest.mark.parametrize(
    "group_cls,ll_attr,invoke",
    [(c[1], c[2], c[3]) for c in EXCLUDED],
    ids=[c[0] for c in EXCLUDED],
)
def test_arm_native_methods_propagate_timeout(group_cls, ll_attr, invoke):
    group = _group_with_failing(group_cls, ll_attr, DobotTimeoutError("no response"))
    with pytest.raises(DobotTimeoutError):
        invoke(group)
