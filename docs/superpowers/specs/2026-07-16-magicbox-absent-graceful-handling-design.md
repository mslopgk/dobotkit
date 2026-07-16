# 설계: 매직박스 미장착 시 주변장치 명령의 우아한 처리

- 날짜: 2026-07-16
- 대상: `dobotkit` — Magician Lite(arm)
- 상태: 설계 확정 (구현 예정)

## 배경 / 문제

Dobot Magician Lite에서 센서·서보·확장모터 등 주변장치는 **매직박스(MagicBox)**
를 통해 연결된다. 매직박스가 없는 상태에서 이 주변장치 명령을 호출하면, 저수준
전송 계층(`SerialTransport.send` → `_read_frame`)은 응답 프레임 1개를 기다리다가
기본 1초 후 `DobotTimeoutError`(또는 깨진 프레임이면 `DobotProtocolError`)를
던진다. 교육/강의 맥락에서 이 예외는 학생 코드를 그대로 중단시킨다.

### 전송 계층에서 검증된 사실

모든 명령(`_send`)은 읽기/쓰기 구분 없이 `transport.send()`로 응답 프레임 1개를
기다린다(`arm/lowlevel/_base.py`). 결과는 셋 중 하나:

1. 무응답 → `DobotTimeoutError` (기본 1초, `set_cmd_timeout`으로 조정)
2. 체크섬/프레임 깨짐 → `DobotProtocolError`
3. 응답이 오되 값이 0/쓰레기 → **에러 없이 그 값 반환** (조용한 오류)

case 3은 펌웨어가 로컬 ACK하는 경우로, 코드로는 감지 불가. 본 설계는 **case 1·2를
반응형으로 포착**하는 것을 범위로 한다(case 3은 감지 불가하므로 문서화로 남긴다).

## 목표

매직박스 미장착으로 **에러가 날 수 있는** 주변장치 명령을 호출해도 라이브러리가
크래시하지 않고, `RuntimeWarning`으로 원인을 알린 뒤 `None`을 반환한다.

## 설계

### 동작

주변장치 그룹 메서드의 내부 저수준 호출이 `DobotTimeoutError`,
`DobotProtocolError`, 또는 `struct.error`를 던지면:

1. `warnings.warn(_PERIPHERAL_UNAVAILABLE_MSG, RuntimeWarning, stacklevel=3)`
2. `None` 반환

> **실기 검증(2026-07-16, Magician Lite, 매직박스 없음, COM7)**: 예상했던
> "무응답 → 타임아웃"이 아니라, 펌웨어가 **타임아웃 없이 빈/짧은 페이로드로
> 응답**했다. 프레임은 정상(체크섬 통과)이라 `DobotProtocolError`가 아니며,
> `unpack_*` 디코딩에서 **`struct.error`**가 발생한다(color/seeed_distance/
> servo). 따라서 `_guard`의 포착 목록에 `struct.error`를 추가했다. 예외적으로
> **적외선 센서는 값(`value=1`)을 무오류로 반환**(감지 불가 case) — 문서화로 남김.

`DobotConnectionError`(포트 미개방 등 설정 오류)는 **포착하지 않고 전파**한다.
모션/이펙터/조회 등 다른 예외 경로도 영향 없음.

### 적용 대상 (매직박스/주변장치 경유 — 읽기·출력 대칭)

- `SensorGroup`: `color`, `infrared`, `seeed_distance`, `seeed_color`,
  `seeed_temp`, `seeed_light`, `seeed_rgb`
- `EffectorGroup`: `set_servo`, `get_servo`
- `IOGroup`: `set_motor`, `set_motor_steps`

### 제외 (팔 컨트롤러 직결 — 기존대로 예외 전파)

- `EffectorGroup`: `suck`, `grip`, `laser`, `set_type`, `get_type`
- `IOGroup`: `set_do`, `get_do`, `get_di`, `get_adc`, `set_pwm`,
  `set_multiplexing`, `get_multiplexing`
- `Magician`의 모든 모션 메서드

> 판단: E-motor(`set_motor(_steps)`)는 base 라우팅이 코드상 모호하나 "에러날 수
> 있는 것 모두"라는 요구에 따라 방어적으로 포함한다. base EIO는 팔 직결이므로
> 제외한다(포함 시 진짜 IO 오류를 삼킬 위험).

### 구현 위치 / 방식

전부 `src/dobotkit/arm/groups.py` 안에서 처리한다. 저수준
(`LowLevelArm`/`*Mixin`)은 **수정하지 않는다** — SDK 203/203 1:1 충실도와 타입드
반환 계약, 검증 스토리를 유지한다.

모듈 상단에 공용 헬퍼를 둔다:

```python
_PERIPHERAL_UNAVAILABLE_MSG = (
    "주변장치 응답이 없습니다 — 매직박스와 연결된 센서/서보/모터를 확인하세요 "
    "(no peripheral response; check the MagicBox and its attached device)"
)

T = TypeVar("T")

def _guard(call: Callable[[], T]) -> Optional[T]:
    """주변장치 호출 실행. 미연결(무응답/깨진 프레임)이면 경고 후 None."""
    try:
        return call()
    except (DobotTimeoutError, DobotProtocolError):
        warnings.warn(_PERIPHERAL_UNAVAILABLE_MSG, RuntimeWarning, stacklevel=3)
        return None
```

- set→get 순서가 있는 메서드(color/infrared/seeed_color/temp/light)는 set+get
  전체를 `_guard`로 감싼다(어느 쪽이 타임아웃나든 `None`).
- 단일 호출 메서드는 `lambda`로 감싼다.

### 반환 타입 변화

- 읽기: `color/infrared/seeed_distance/color/temp/light` → `Optional[...Reading]`,
  `get_servo` → `Optional[float]`
- 출력(세터): `seeed_rgb`, `set_servo`, `set_motor`, `set_motor_steps` — 이미
  `Optional[int]`이므로 시그니처 불변

## 에러 처리 경계

| 예외 | 처리 |
|---|---|
| `DobotTimeoutError` | 포착 → 경고 + `None` |
| `DobotProtocolError` | 포착 → 경고 + `None` |
| `DobotConnectionError` | 전파(설정 오류) |
| 기타 | 전파 |

**트레이드오프**: 반응형이라 실제 통신 장애도 `None`이 될 수 있음. `RuntimeWarning`
1줄이 이를 무음이 아니게 보완하고, 모션 계열은 그대로 예외를 던진다.

**감지 못 하는 경우**: 펌웨어가 로컬 ACK하며 0/쓰레기값을 돌려주는 case 3은
반응형으로 감지 불가 → docstring/README에 "매직박스 미장착 시 값이 0이거나 출력이
조용히 무시될 수 있음"을 명시한다.

## 테스트

`tests/arm/test_groups.py`(기존 MagicMock 위임 패턴)에 추가:

- 대상 메서드별로 저수준 mock에 `side_effect = DobotTimeoutError(...)`를 주고 →
  반환 `None` + `pytest.warns(RuntimeWarning)` 확인 (파라메트라이즈)
- 최소 1건은 `DobotProtocolError`로도 검증
- 제외 대상(예: `suck`, `set_do`)은 `DobotTimeoutError`를 **그대로 전파**하는지 확인
- 정상 경로(값 반환)는 기존 테스트로 회귀 방지 유지

## 문서

- 대상 그룹 메서드 docstring에 "미연결 시 `None`+경고" 명시
- `README.md` 센서/주변장치 절에 짧은 노트, case 3 한계 명시
- `CHANGELOG.md` Unreleased에 기록

## 후속: Magician Lite 완성 확정 (Phase 2)

위 구현이 머지되고 arm 테스트 스위트가 전부 통과하면:

- `CHANGELOG.md` 갱신
- `docs/VERIFICATION_NEEDED_ko.md`의 arm 항목 정리
- Magician Lite(arm) = 완성 선언
