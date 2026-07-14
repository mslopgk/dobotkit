# Dobot Magician (Lite) — `dobotkit` 암(Arm) API 레퍼런스

> 4축 데스크톱 로봇팔(Magician Lite)을 **순수 파이썬**으로 제어하기 위한 실전 API 레퍼런스.
> 사람과 AI 에이전트가 코드 예제를 그대로 복사해 쓸 수 있도록 정리했습니다.

- **대상 하드웨어**: Dobot Magician Lite (4축 로봇팔). 보통 **Magic Box 컨트롤러**에 연결되어 USB로 PC와 통신합니다.
- **라이브러리**: `dobotkit` — **순수 파이썬**(`pyserial`만), DLL 불필요, 크로스플랫폼, `pip install dobotkit`.
- **임포트**: `import dobotkit` 또는 `from dobotkit import Magician`.

이 문서는 두 가지 사용 경로를 다룹니다:

1. **고수준 `Magician`** — 일상 작업(연결/홈/이동/픽앤플레이스/IO/센서)을 위한 인체공학적 API. **권장.**
2. **저수준 `LowLevelArm`** — Dobot 시리얼 프로토콜의 **모든 SDK 함수**를 1:1로 노출하는 완전 커버리지 계층. `arm.lowlevel`로 접근.

---

## 정직성 고지 (반드시 읽으세요)

`dobotkit`는 다음을 **정직하게** 공개합니다.

- **완전한 SDK 커버리지.** 공식 Dobot 암 SDK(`DobotDllType`) 함수 **203/203개**가 `LowLevelArm` 메서드로 매핑되어 있습니다. 이 사실은 `tests/arm/test_coverage.py`(오라클 SDK 함수명을 열거 → 각각이 `LowLevelArm` 메서드에 대응하는지 검증)로 **증명**됩니다.
- **순수 파이썬.** `pyserial`만 사용하며 DLL/네이티브 바이너리에 의존하지 않습니다. 따라서 Windows/Linux/macOS 어디서나 동작하고 `pip`로 설치됩니다.
- **프로토콜 명령 ID는 공식 문서로 교차 검증되었습니다 (2026-07-01 갱신).** 초기에는 `pydobot` 시드 + `DobotDllType` 구조체 레이아웃 + 카테고리별 번호 규칙으로 재구성했으나, 이후 **공식 Dobot Communication Protocol V1.1.5 PDF와 SDK `ProtocolID.h`/`cmd_id.h`로 교차 검증해 98개 중 84개를 확정**했습니다(73개 일치 확인, 11개 수정). 나머지 **14개만 `# unverified` 주석으로 태깅**되어 있으며(주로 MagicBox/Seeed 확장·DLL 전용 호출), 실제 하드웨어로 확인이 필요합니다.
- **구조체 바이트 레이아웃은 검증됨.** 각 페이로드 구조체의 바이트 패킹은 `DobotDllType`에 대해 오프라인 골든-오라클 테스트(`bytes(DobotDllType.StructX(...))`와 바이트 단위 비교)로 **검증**되어 있습니다. 오라클은 절대 런타임 의존성이 아니며 테스트에서만 로드됩니다.

> 요약: **구조체 바이트 레이아웃 검증됨**, **명령 ID 84/98 공식 문서로 확정** — 남은 14개(`# unverified`)만 실제 하드웨어로 확인하세요.

---

## 0. 빠른 시작 (고수준 `Magician`)

```python
import dobotkit

# 컨텍스트 매니저로 열면 종료 시 큐 정지 + 연결 해제가 항상 보장됩니다(예외 시에도).
with dobotkit.Magician(port="COM3") as arm:   # port="auto"면 첫 시리얼 포트 자동탐지
    arm.home(wait=True)                        # 원점복귀 (전원 후 최초 1회 필수)
    arm.set_speed(velocity=100, acceleration=100)   # 속도%/가속%

    # 한 점으로 직선 이동 (기본 MOVL_XYZ). wait=True면 큐에 적재→실행→완료까지 블로킹.
    arm.move_to(220, 0, 40, 0, wait=True)

    pose = arm.get_pose()                      # 현재 포즈 (NamedTuple)
    print(f"x={pose.x:.1f} y={pose.y:.1f} z={pose.z:.1f} r={pose.r:.1f}")
```

> ⚠️ **전원을 켠 직후에는 반드시 `arm.home()`을 먼저 실행**해야 좌표가 정확합니다.
> 작업 공간을 비우고 실행하세요(로봇팔이 원점으로 크게 움직입니다).

`port="auto"`는 `SerialTransport.search()`(= `pyserial`의 `list_ports`)가 찾은 첫 포트로 해석됩니다. 포트가 없으면 `DobotConnectionError`가 발생합니다.

---

## 1. 핵심 개념

### 명령 큐 (Command Queue)

Dobot은 모션 명령을 **큐(queue)** 에 쌓아 순차 실행합니다. `dobotkit`에서는 큐 동작이 `queued` 불리언 인자로 결정됩니다.

| `queued` | 동작 |
|---|---|
| `True` | 큐에 명령을 적재(비동기). `arm.lowlevel.queue.start()`로 실행. 큐 세터는 **명령 인덱스(int)** 를 반환. |
| `False` | 즉시 실행(동기, 비큐). 설정/읽기 명령의 기본값. 반환값은 `None`. |

> 와이어 프로토콜의 `isQueued`는 `dobotkit`에서 `queued: bool` 키워드 인자로 노출됩니다. (전역 규약: `isQueued` → `queued`.)

고수준 API의 `wait=True`는 이 모든 과정을 묶어 줍니다.

```python
# wait=True: 명령을 큐에 적재 → 큐 시작 → 해당 인덱스가 실행 완료될 때까지 블로킹
idx = arm.move_to(220, 0, 40, 0, wait=True)
```

저수준에서 직접 완료 대기 패턴을 쓰려면:

```python
ll = arm.lowlevel
from dobotkit.enums import PTPMode
idx = ll.set_ptp_cmd(PTPMode.MOVL_XYZ, 220, 0, 40, 0, queued=True)
ll.queue.start()
ll.queue.wait_for(idx)            # current_index >= idx 까지 폴링(기본 timeout=30s)
ll.queue.stop()
```

`CommandQueue`의 메서드: `clear()`, `start()`, `stop()`, `force_stop()`, `current_index() -> int`, `motion_finished() -> bool`, `wait_for(index, poll=0.05, timeout=30.0)`(미도달 시 `DobotTimeoutError`).

### 좌표계

- **데카르트(Cartesian)**: `x, y, z` (mm), `r`(엔드이펙터 회전, deg)
- **관절(Joint)**: `j1, j2, j3, j4` (deg)
- `arm.get_pose()` → `Pose` NamedTuple `(x, y, z, r, j1, j2, j3, j4)`
- pydobot 호환 튜플이 필요하면 `arm.pose()` → `(x, y, z, r, j1, j2, j3, j4)`

### Magic Box 연결 시 주의 (중요)

Magician Lite를 **Magic Box 컨트롤러에 꽂아** 쓰면 Lite는 Magic Box의 슬레이브(slave=-1) 장치가 됩니다.

- **디지털/아날로그 IO 기본 함수**(`set_io_do`, `get_io_di`, `get_io_adc`, `set_io_pwm`, `set_io_multiplexing`)는 기본형으로도 동작하며, 명시적으로 Magic Box(slave=-1)를 대상으로 하려면 `_ext` 변형(`set_io_do_ext` 등)을 씁니다.
- 단, **Seeed 그로브 센서**(`get_seeed_distance_sensor` 등)와 **`set_servo_angle`/`get_servo_angle`**은 Magic Box(slave=-1) 경로로 라우팅되므로 Magic Box 연결 환경에서만 동작합니다.

`dobotkit`는 base 함수를 한 번 구현하고 `_ext`/`_ext_ex`는 라우팅 플래그만 세팅하는 얇은 래퍼로 제공합니다(DRY). 즉 `set_io_do`, `set_io_do_ext`, `set_io_do_ext_ex`가 모두 존재합니다.

---

## 2. 고수준 `Magician` API

`from dobotkit import Magician` 으로 임포트합니다(또는 `dobotkit.Magician`). 임포트 자체는 가볍습니다 — `pyserial`은 첫 장치 생성 시점에 로드됩니다(지연 임포트).

### 2.1 생성 / 수명주기

```python
Magician(port="auto", baudrate=115200, *, auto_connect=True)
```

| 메서드/프로퍼티 | 설명 |
|---|---|
| `Magician(port="auto", baudrate=115200, *, auto_connect=True)` | 생성. `port="auto"`면 첫 시리얼 포트 자동탐지. `auto_connect=True`면 생성 시 `connect()` 호출. |
| `connect()` / `disconnect()` | 연결 열기/닫기 |
| `with Magician(...) as arm:` | 컨텍스트 매니저. `__exit__`는 항상 큐 정지 + 연결 해제하며 본문 예외를 억제하지 않음 |
| `lowlevel` (property) | 내부 `LowLevelArm` 인스턴스 (전체 SDK 표면) |
| `effector` / `sensors` / `io` (property) | 인체공학적 디바이스 그룹 (아래 2.6) |

```python
arm = dobotkit.Magician(port="auto")   # 생성과 동시에 연결
# ... 작업 ...
arm.disconnect()
```

### 2.2 홈 / 속도 / 포즈

| 메서드 | 설명 |
|---|---|
| `home(x=200, y=0, z=0, r=0, *, wait=True)` | 홈 파라미터 설정 후 홈 실행. `wait=True`면 큐 적재→실행→완료 블로킹 |
| `set_speed(velocity, acceleration)` | PTP 공통 + 좌표 속도/가속(%) 동시 설정 (pydobot `speed`와 동일 효과) |
| `get_pose() -> Pose` | 현재 데카르트+관절 포즈 |
| `pose_obj` (property) | `get_pose()`와 동일(프로퍼티 형태) |

```python
arm.home(wait=True)                    # 원점복귀
arm.set_speed(velocity=50, acceleration=50)   # 50% 속도로 안전하게 시작
p = arm.get_pose()
print(p.x, p.y, p.z, p.r, p.j1, p.j2, p.j3, p.j4)
```

### 2.3 이동(모션)

| 메서드 | 설명 |
|---|---|
| `move_to(x, y, z, r=0, *, mode=PTPMode.MOVL_XYZ, wait=False, check_alarms=False)` | 절대 데카르트 이동(기본 직선 MOVL). `wait=True`면 큐+대기. `check_alarms=True`면 사전 알람 체크 |
| `move_relative(dx=0, dy=0, dz=0, dr=0, *, wait=False, check_alarms=False)` | 상대 직선 증분 이동 (`MOVL_XYZ_INC`) |

```python
from dobotkit.enums import PTPMode

# 절대 직선 이동, 완료까지 대기
arm.move_to(220, 0, 40, 0, wait=True)

# 관절 보간 이동으로 모드 변경
arm.move_to(180, 60, 20, 0, mode=PTPMode.MOVJ_XYZ, wait=True)

# 현재 위치에서 Z를 20mm 올리기(상대)
arm.move_relative(dz=20, wait=True)

# 이동 직전 알람을 먼저 확인하고 활성 시 DobotAlarmError 발생
arm.move_to(220, 0, 40, 0, wait=True, check_alarms=True)
```

> **절대 이동**은 `PTPMode.*_XYZ`(0~2), **상대 이동**은 `*_INC`(6~8)를 씁니다. 전체 `PTPMode` 값은 아래 4.3 표 참조.

### 2.4 픽 앤 플레이스

```python
pick_and_place(src, dst, z_safe, settle_ms=200)
```

`src`/`dst`는 `(x, y, z)` 웨이포인트(그랩/릴리스 높이), `z_safe`는 이동 시 클리어런스 높이. 고전적인 8단계 사이클(위로→내려→흡착ON→들기→이동→내려→흡착OFF→들기)을 **모두 큐에 적재**해 하나의 모션 프로그램으로 실행하고 마지막 이동 완료까지 블로킹합니다.

```python
source      = (200.0,   0.0, -30.0)    # 집을 위치 (x, y, z mm)
destination = (100.0, 150.0, -30.0)    # 놓을 위치
arm.pick_and_place(source, destination, z_safe=50.0, settle_ms=300)
```

전체 예제: `examples/arm_pick_and_place.py`.

### 2.5 pydobot 호환 별칭

기존 `pydobot.Dobot` 스크립트가 최소 변경으로 포팅되도록 다음 별칭을 제공합니다.

| 별칭 | 위임 대상 |
|---|---|
| `suck(on)` | 흡착 ON/OFF (`effector.suck`) |
| `grip(on)` | 그리퍼 닫기/열기 (`effector.grip`) |
| `speed(velocity=100, acceleration=100)` | `set_speed` |
| `wait(ms)` | 큐에 대기 명령 적재 |
| `pose()` | `(x, y, z, r, j1, j2, j3, j4)` 튜플 |
| `get_eio(addr)` / `set_eio(addr, val)` | 확장 IO 디지털 입력/출력 |

```python
arm.suck(True)                        # 흡착 ON
arm.grip(True)                        # 그리퍼 닫기
arm.speed(velocity=100, acceleration=100)
arm.wait(1000)                        # 1초 대기 (큐)
x, y, z, r, j1, j2, j3, j4 = arm.pose()
arm.set_eio(5, 1)                     # 확장 IO 핀 5 디지털 출력 HIGH
level = arm.get_eio(5)                # 디지털 입력 읽기
```

### 2.6 디바이스 그룹 (`effector` / `sensors` / `io`)

저수준 SDK 메서드명을 노출하지 않고 읽기 쉬운 접근자를 제공하는 얇은 facade입니다. 흡착/그리퍼/레이저 헬퍼는 `queued=True`가 기본이라 모션 프로그램 안에서 올바르게 시퀀스됩니다.

**`arm.effector` (`EffectorGroup`)**

| 메서드 | 설명 |
|---|---|
| `suck(on, *, queued=True)` | 흡착 ON(잡기)/OFF(놓기). 컨트롤 전원은 항상 유지 |
| `grip(on, *, queued=True)` | 그리퍼 닫기/열기 |
| `laser(on, *, queued=True)` | 레이저 ON/OFF |
| `set_type(end_type, *, queued=False)` / `get_type()` | 말단 타입 설정/읽기 (`EndEffectorType`) |
| `set_servo(servo_id, angle, *, queued=False)` / `get_servo(servo_id)` | 서보 각도 직접 제어/읽기 (Magic Box 경로) |

**`arm.sensors` (`SensorGroup`)**

| 메서드 | 설명 |
|---|---|
| `color(port) -> ColorSensorReading` | 컬러 센서 활성화 후 `(r, g, b)` 읽기 |
| `infrared(port) -> InfraredSensorReading` | 적외선 센서 활성화 후 읽기 |
| `seeed_distance(port) -> SeeedDistanceReading` | Seeed 거리(mm) |
| `seeed_color(port) -> SeeedColorReading` | Seeed 색상 `(r, g, b, cct)` |
| `seeed_temp(port) -> SeeedTempReading` | Seeed 온도/습도 |
| `seeed_light(port) -> SeeedLightReading` | Seeed 조도(lux) |
| `seeed_rgb(port, rgb)` | Seeed RGB LED 출력 |

**`arm.io` (`IOGroup`)**

| 메서드 | 설명 |
|---|---|
| `set_do(address, level, *, queued=False)` / `get_do(address) -> int` | 디지털 출력 설정/읽기 |
| `get_di(address) -> int` | 디지털 입력 읽기 |
| `get_adc(address) -> int` | 아날로그 입력(0~4095) |
| `set_pwm(address, frequency, duty_cycle, *, queued=False)` | PWM 출력 |
| `set_multiplexing(address, multiplex, *, queued=False)` / `get_multiplexing(address)` | 핀 기능 설정/읽기 |
| `set_motor(index, enabled, speed, *, queued=False)` | 외부 스텝모터 연속 구동 |
| `set_motor_steps(index, enabled, speed, distance, *, queued=False)` | 외부 스텝모터 거리 지정 구동 |

```python
# 흡착 → 이동 → 놓기
arm.effector.suck(True)
arm.move_to(100, 150, 50, 0, wait=True)
arm.effector.suck(False)

# Seeed 그로브 센서 (Magic Box 포트 1~6)
r, g, b, cct = arm.sensors.seeed_color(port=1)
temp, hum    = arm.sensors.seeed_temp(port=1)
dist         = arm.sensors.seeed_distance(port=1)

# 디지털/아날로그 IO
arm.io.set_do(address=5, level=1)
val = arm.io.get_adc(address=2)
```

전체 센서 예제: `examples/arm_sensors.py`. 전체 API 투어: `examples/arm_full_api_tour.py`.

---

## 3. 알람(에러) 확인

암은 `GetAlarmsState`로 활성 결함을 **비트맵**으로 보고합니다. `dobotkit`는 비트맵을 디코드하는 도우미를 제공합니다.

```python
from dobotkit.arm.alarms import decode_alarms

bitmap = arm.lowlevel.get_alarms_state()   # raw bytes
codes  = decode_alarms(bitmap)             # list[AlarmCode]
if codes:
    print("활성 알람:", [int(c) for c in codes])
    arm.lowlevel.clear_all_alarms_state()  # 모든 알람 해제
```

또는 모션 호출에서 `check_alarms=True`를 주면 이동 직전 비트맵을 읽어 활성 시 `DobotAlarmError(codes)`를 발생시킵니다.

```python
from dobotkit import DobotAlarmError
try:
    arm.move_to(220, 0, 40, 0, wait=True, check_alarms=True)
except DobotAlarmError as exc:
    print("알람으로 모션 중단:", exc.codes)
```

> `decode_alarms`는 각 set 비트 `n`을 `AlarmCode(n)`으로 매핑합니다. 비트 인덱스 → 코드 매핑은 검증됨이나, 개별 **`AlarmCode` 값**(예: `PLANNING_INVERSE_KINEMATIC=0x10`)은 공식 알람 사양에 anchor되지 않은 한 `# unverified`로 태깅됩니다.

**스텝 손실(리스텝) 감지** (Lite):

```python
ll = arm.lowlevel
ll.set_lost_step_enable_and_params(enable=True, threshold=2.0)   # 활성화 + 임계값
enabled, threshold = ll.get_lost_step_enable_and_params()
ll.set_lost_step_cmd(queued=True)                                # 1회 검사 실행
```

---

## 4. 저수준 `LowLevelArm` 카테고리 레퍼런스 (완전 SDK 커버리지)

`arm.lowlevel`로 접근합니다. 모든 SDK 함수가 1:1로 매핑되어 있으며, 각 메서드는 `Message`(id=`ProtocolId`, ctrl=`make_ctrl(rw, queued)`, params=`pack_*`)를 만들어 전송하고 응답을 `unpack_*`으로 디코드합니다. 큐 세터는 큐 인덱스(int)를 반환합니다.

> **`# unverified` 표기**: 아래 표의 **Protocol ID** 열에 `(uv)`가 붙은 것은 `pydobot` 시드로 확인되지 않아 코드에서 `# unverified`로 태깅된 ID입니다(`src/dobotkit/arm/ids.py`). 구조체 바이트 레이아웃은 골든-오라클로 검증되어 있지만, ID 값 자체는 실제 하드웨어/공식 프로토콜로 확인이 필요합니다.

### 4.1 디바이스 / 연결 (`device.py`)

| 메서드 | Protocol ID | 설명 |
|---|---|---|
| `get_device_sn()` / `set_device_sn(sn)` | `GET_SET_DEVICE_SN` (0) | 시리얼 번호 (UTF-8) |
| `get_device_name()` / `set_device_name(name)` | `GET_SET_DEVICE_NAME` (1) | 장치 이름 |
| `set_device_num_name(num)` | `GET_SET_DEVICE_NAME` (1) | 숫자 id로 이름 설정 (`c_int`) |
| `get_device_version()` / `get_device_version_ex()` | `GET_DEVICE_VERSION` (2 uv) | 펌웨어/하드웨어 버전 (8바이트) |
| `get_device_id()` | `GET_DEVICE_ID` (3 uv) | 3×32비트 장치 id |
| `get_device_time()` | `GET_DEVICE_TIME` (4 uv) | 가동 시간 카운터 (`c_uint32`) |
| `get_device_info()` | `GET_DEVICE_INFO` (5 uv) | 누적 가동/전원 카운터 |
| `set_device_with_l(is_with_l, version=0, *, queued=False)` / `get_device_with_l()` | `SET_GET_DEVICE_WITH_L` (6 uv) | 슬라이드레일("with L") 토글 |
| `restart_magic_box()` | `RESTART_MAGIC_BOX` (7 uv) | MagicBox 재시작 |
| `get_uart4_peripherals_type()` | `GET_UART4_PERIPHERALS_TYPE` (8 uv) | UART4 주변기기 타입 코드 |
| `set_cmd_timeout(timeout_ms)` | (local) | 전송 읽기 타임아웃(초)로 변환 — 와이어 명령 아님 |
| `search_dobot()` (staticmethod) | (local) | `pyserial`로 시리얼 포트 열거 — DLL `SearchDobot` 대체 |
| `connect()` / `disconnect()` | (transport) | 전송 열기/닫기 |

### 4.2 포즈 / 홈 / 키네매틱스 (`pose.py`)

| 메서드 | Protocol ID | 설명 |
|---|---|---|
| `get_pose() -> Pose` | `GET_POSE` (10) | `(x,y,z,r,j1,j2,j3,j4)` |
| `get_pose_l() -> float` / `get_pose_ex(index)` | `GET_POSE_L` (13 uv) | 슬라이드레일(L축) 위치 |
| `get_kinematics() -> Kinematics` | `GET_KINEMATICS` (12 uv) | `(velocity, acceleration)` |
| `reset_pose(...)` | `RESET_POSE` (11) | 포즈 리셋 |
| `set_home_params(x, y, z, r, *, queued=False)` / `get_home_params() -> HOMEParams` | `SET_GET_HOME_PARAMS` (30) | 홈 위치 정의 |
| `set_home_cmd(temp=0.0, *, queued=False)` | `SET_HOME_CMD` (31) | 홈(원점복귀) 실행 |
| `set_auto_leveling(...)` / `get_auto_leveling_result() -> float` | `SET_AUTO_LEVELING` (32 uv), `GET_AUTO_LEVELING` (33 uv) | 자동 수평 보정 |
| `set_arm_orientation(...)` / `get_arm_orientation() -> int` | `SET_GET_ARM_ORIENTATION` (50) | 좌수/우수 방향 |
| `get_user_params() -> UserParams` | `GET_USER_PARAMS` (14 uv) | 사용자 파라미터 |

### 4.3 PTP — 점대점 이동 (`ptp.py`)

| 메서드 | Protocol ID | 설명 |
|---|---|---|
| `set_ptp_cmd(mode, x, y, z, r, *, queued=False)` | `SET_PTP_CMD` (84) | PTP 이동 (가장 많이 씀) |
| `set_ptp_with_l_cmd(...)` | `SET_PTP_WITH_L_CMD` (86) | 슬라이드레일 동반 PTP |
| `set_ptp_joint_params(...)` / `get_ptp_joint_params()` | `SET_GET_PTP_JOINT_PARAMS` (80) | 관절별 속도/가속 |
| `set_ptp_coordinate_params(...)` / `get_ptp_coordinate_params()` | `SET_GET_PTP_COORDINATE_PARAMS` (81) | 데카르트 축별 속도/가속 |
| `set_ptp_l_params(...)` / `get_ptp_l_params()` | `SET_GET_PTP_L_PARAMS` (85) | 슬라이드레일 속도/가속 |
| `set_ptp_jump_params(...)` / `get_ptp_jump_params()` | `SET_GET_PTP_JUMP_PARAMS` (82) | JUMP 모드 들어올림 높이/한계 |
| `set_ptp_common_params(velocity, acceleration, *, queued=False)` / `get_ptp_common_params()` | `SET_GET_PTP_COMMON_PARAMS` (83) | 전체 속도%/가속% |

**`PTPMode` 값** (`from dobotkit.enums import PTPMode`):

| 모드 | 값 | 의미 |
|---|---|---|
| `JUMP_XYZ` | 0 | 점프(들었다 놨다) — 좌표 |
| `MOVJ_XYZ` | 1 | 관절 보간 이동 — 좌표 입력 |
| `MOVL_XYZ` | 2 | **직선 이동** — 좌표 입력 (가장 직관적) |
| `JUMP_ANGLE` | 3 | 점프 — 관절각 입력 |
| `MOVJ_ANGLE` | 4 | 관절 이동 — 관절각 입력 |
| `MOVL_ANGLE` | 5 | 직선 이동 — 관절각 입력 |
| `MOVJ_ANGLE_INC` | 6 | 관절각 **증분(상대)** 이동 |
| `MOVL_XYZ_INC` | 7 | 좌표 **증분(상대)** 직선 이동 |
| `MOVJ_XYZ_INC` | 8 | 좌표 증분 관절 이동 |
| `JUMP_MOVL_XYZ` | 9 | 점프 후 직선 |

```python
from dobotkit.enums import PTPMode
ll = arm.lowlevel

# 속도/가속 먼저 설정(% 0~100)
ll.set_ptp_common_params(velocity=100, acceleration=100, queued=True)
ll.set_ptp_joint_params(200,200, 200,200, 200,200, 200,200, queued=True)

# 직선 이동, 큐 적재
idx = ll.set_ptp_cmd(PTPMode.MOVL_XYZ, 220, 0, 40, 0, queued=True)
ll.queue.start(); ll.queue.wait_for(idx)
```

### 4.4 JOG — 연속 수동 이동 (`jog.py`)

| 메서드 | Protocol ID | 설명 |
|---|---|---|
| `set_jog_cmd(is_joint, cmd, *, queued=False)` | `SET_JOG_CMD` (73) | 버튼식 연속 이동 |
| `set_jog_joint_params(...)` / `get_jog_joint_params()` | `SET_GET_JOG_JOINT_PARAMS` (70) | 관절 JOG 속도/가속 |
| `set_jog_coordinate_params(...)` / `get_jog_coordinate_params()` | `SET_GET_JOG_COORDINATE_PARAMS` (71) | 좌표 JOG 속도/가속 |
| `set_jog_l_params(...)` / `get_jog_l_params()` | `SET_GET_JOG_L_PARAMS` (74 uv) | 슬라이드레일 JOG |
| `set_jog_common_params(...)` / `get_jog_common_params()` | `SET_GET_JOG_COMMON_PARAMS` (72) | 전체 JOG 속도%/가속% |

**`JOGMode`/`cmd` 값**: `0`=정지, `1~8`=각 축(1~4) ±, `9~10`=L축 ±. `is_joint`(0=좌표계, 1=관절계)로 축 그룹을 구분합니다.

```python
ll.set_jog_common_params(velocity_ratio=50, acceleration_ratio=50)
ll.set_jog_cmd(is_joint=0, cmd=1, queued=True)   # X+ 방향 연속 이동
# ... 잠시 후 ...
ll.set_jog_cmd(is_joint=0, cmd=0, queued=True)   # 정지
```

### 4.5 CP / ARC / Circle — 연속 경로 / 원호 (`cp_arc.py`)

| 메서드 | Protocol ID | 설명 |
|---|---|---|
| `set_cp_cmd(cp_mode, x, y, z, velocity, *, queued=False)` | `SET_CP_CMD` (91) | 연속 경로(CP) 점 추가 |
| `set_cp2_cmd(...)` | `SET_CP2_CMD` (92 uv) | CP 점 추가(velocity 인자 없음) |
| `set_cp_le_cmd(...)` | `SET_CP_LE_CMD` (94 uv) | 레이저 인그레이빙용 CP |
| `set_cp_params(...)` / `get_cp_params()` | `SET_GET_CP_PARAMS` (90) | CP 계획가속/접합속도/실제가속 |
| `set_cp_common_params(...)` / `get_cp_common_params()` | `SET_GET_CP_COMMON_PARAMS` (93 uv) | CP 공통 속도%/가속% |
| `set_cpr_hold_enable(is_enable, *, queued=False)` / `get_cpr_hold_enable()` | `SET_GET_CPR_HOLD_ENABLE` (95 uv) | CPR 홀드 토글 |
| `set_arc_cmd(...)` | `SET_ARC_CMD` (101) | 원호 이동(경유점+도착점) |
| `set_circle_cmd(...)` | `SET_CIRCLE_CMD` (102 uv) | 완전한 원 이동 |
| `set_arc_params(...)` / `get_arc_params()` | `SET_GET_ARC_PARAMS` (100) | ARC xyz/r 속도·가속 |
| `set_arc_common_params(...)` / `get_arc_common_params()` | `SET_GET_ARC_COMMON_PARAMS` (103 uv) | ARC 공통 속도%/가속% |

> **인자 순서 주의**: `set_arc_params`는 `(xyz_velocity, r_velocity, xyz_acceleration, r_acceleration)` 순서입니다(속도2+가속2가 아님). `cir_point`/`to_point`는 각각 `(x, y, z, r)` 형태의 `ARCPoint`이며, 시작점은 현재 로봇 위치입니다.

```python
from dobotkit.enums import ContinuousPathMode

# 절대좌표 연속 경로(CP)
ll.set_cp_params(plan_acc=100, junction_vel=100, acc=100, queued=True)
for (x, y, z) in [(220, 0, 0), (220, 40, 0), (180, 40, 0)]:
    ll.set_cp_cmd(ContinuousPathMode.ABSOLUTE, x, y, z, 50, queued=True)
```

### 4.6 엔드이펙터 (`effector.py`)

| 메서드 | Protocol ID | 설명 |
|---|---|---|
| `set_end_effector_suction_cup(enable_ctrl, on, *, queued=False)` / `get_end_effector_suction_cup() -> (bool, bool)` | `SET_GET_END_EFFECTOR_SUCTION_CUP` (62) | 흡착컵 |
| `set_end_effector_gripper(enable_ctrl, on, *, queued=False)` / `get_end_effector_gripper()` | `SET_GET_END_EFFECTOR_GRIPPER` (63) | 그리퍼 |
| `set_end_effector_laser(enable_ctrl, on, *, queued=False)` / `get_end_effector_laser()` | `SET_GET_END_EFFECTOR_LASER` (61) | 레이저 |
| `set_end_effector_params(...)` / `get_end_effector_params() -> EndTypeParams` | `SET_GET_END_EFFECTOR_PARAMS` (60) | 말단 바이어스 |
| `set_end_effector_type(end_type, *, queued=False)` / `get_end_effector_type() -> int` | `SET_GET_END_EFFECTOR_TYPE` (64 uv) | 말단 타입 |
| `set_servo_angle(servo_id, angle, *, queued=False)` / `get_servo_angle(servo_id) -> float` | `SET_GET_SERVO_ANGLE` (65 uv) | 서보 각도(Magic Box 경로) |

**`EndEffectorType`** (`from dobotkit.enums import EndEffectorType`): `NONE=0`, `SUCTION_CUP=1`, `GRIPPER=2`, `LASER=3`.

```python
ll.set_end_effector_suction_cup(enable_ctrl=True, on=True, queued=True)   # 흡착 ON
ll.set_end_effector_gripper(enable_ctrl=True, on=False, queued=True)      # 그리퍼 열기
```

### 4.7 IO / EMotor / WAIT / TRIG (`io.py`)

각 IO/EMotor 함수는 base + `_ext` + `_ext_ex` 3종(Magic Box 라우팅)을 제공합니다.

| 메서드 | Protocol ID | 설명 |
|---|---|---|
| `set_io_multiplexing(address, multiplex, *, queued=False)` / `get_io_multiplexing(address)` (+`_ext`, `_ext_ex`) | `SET_GET_IO_MULTIPLEXING` (130) | 핀 기능 설정 |
| `set_io_do(address, level, *, queued=False)` / `get_io_do(address)` (+`_ext`, `_ext_ex`) | `SET_GET_IO_DO` (131) | 디지털 출력 |
| `set_io_pwm(address, frequency, duty_cycle, *, queued=False)` / `get_io_pwm(address)` (+`_ext`, `_ext_ex`) | `SET_GET_IO_PWM` (132) | PWM 출력 |
| `get_io_di(address)` (+`_ext`, `_ext_ex`) | `GET_IO_DI` (133) | 디지털 입력 |
| `get_io_adc(address)` (+`_ext`, `_ext_ex`) | `GET_IO_ADC` (134) | 아날로그 입력(0~4095) |
| `set_e_motor(index, is_enabled, speed, *, queued=False)` (+`_ext`, `_ext_ex`) | `SET_EMOTOR` (135) | 외부 스텝모터 연속 |
| `set_e_motors(index, is_enabled, speed, distance, *, queued=False)` (+`_ext`, `_ext_ex`) | `SET_EMOTOR_S` (136 uv) | 외부 스텝모터 거리 지정 |
| `set_wait_cmd(wait_time_ms, *, queued=False)` | `SET_WAIT_CMD` (110) | 큐 대기(ms) |
| `set_trig_cmd(...)` | `SET_TRIG_CMD` (120) | 트리거 명령 |

**`GPIOType`** (`from dobotkit.enums import GPIOType`): `DUMMY=0`(미사용), `DO=1`(디지털출력), `PWM=2`, `DI=3`(디지털입력), `ADC=4`(아날로그), `DIPU=5`(입력 풀업), `DIPD=6`(입력 풀다운).

```python
ll.set_io_do(address=5, level=1, queued=True)        # 디지털 출력 HIGH
level = ll.get_io_di(2).level                        # 디지털 입력
adc   = ll.get_io_adc(3).value                       # 아날로그
ll.set_e_motor(index=0, is_enabled=1, speed=10000, queued=True)   # 컨베이어
ll.set_wait_cmd(1000, queued=True)                   # 1초 대기(큐)
```

### 4.8 센서 — 컬러 / 적외선 / Seeed (`sensor.py`)

Seeed 함수도 base + `_ext` + `_ext_ex`를 제공합니다(Seeed는 Magic Box 경로 권장).

| 메서드 | Protocol ID | 설명 |
|---|---|---|
| `set_color_sensor(enable, port, version=0)` / `get_color_sensor() -> ColorSensorReading` (+`_ext`) | `SET_GET_COLOR_SENSOR` (137) | 컬러 센서 `(r, g, b)` |
| `set_infrared_sensor(enable, port, version=0)` / `get_infrared_sensor(port)` (+`_ext`) | `SET_GET_IR_SWITCH` (138) | 적외선 센서 |
| `get_seeed_distance_sensor(port) -> SeeedDistanceReading` (+`_ext`) | `SET_GET_SEEED_DISTANCE` (215 uv) | Seeed 거리(mm) |
| `set_seeed_color_sensor(port)` / `get_seeed_color_sensor() -> SeeedColorReading` (+`_ext`, `_ext_ex`) | `SET_GET_SEEED_COLOR` (216 uv) | Seeed RGB+CCT |
| `set_seeed_temp_sensor(port)` / `get_seeed_temp_sensor() -> SeeedTempReading` (+`_ext`, `_ext_ex`) | `SET_GET_SEEED_TEMP` (217 uv) | Seeed 온도/습도 |
| `set_seeed_light_sensor(port)` / `get_seeed_light_sensor() -> SeeedLightReading` (+`_ext`, `_ext_ex`) | `SET_GET_SEEED_LIGHT` (218 uv) | Seeed 조도(lux) |
| `set_seeed_rgb(port, rgb)` (+`_ext`, `_ext_ex`) | `SET_SEEED_RGB` (219 uv) | Seeed RGB LED 출력 |

> **컬러/IR 센서 포트** `ColorPort` (`from dobotkit.enums import ColorPort`): `GP1=0`, `GP2=1`, `GP4=2`, `GP5=3`.
> Seeed 센서 ID(215~219)는 골든 SDK에 전용 id 시드가 없어 카테고리 규칙으로 채운 **미검증 블록**입니다(`# unverified`).

```python
# Set로 활성화/포트 지정 → Get로 읽기
r, g, b, cct = arm.sensors.seeed_color(port=1)        # 그룹 헬퍼(권장)
temp, hum    = arm.lowlevel.get_seeed_temp_sensor()   # 저수준 직접 호출
dist         = arm.lowlevel.get_seeed_distance_sensor(port=1)
```

### 4.9 시스템 — 큐 / 알람 / 속도비율 / 리스텝 / 모터모드 / WiFi / 기타 (`system.py`)

| 메서드 | Protocol ID | 설명 |
|---|---|---|
| `queued_cmd_clear()` / `queued_cmd_start_exec()` / `queued_cmd_stop_exec()` / `queued_cmd_force_stop_exec()` | `SET_QUEUED_CMD_*` (240~245) | 큐 제어 (얇은 pass-through; `arm.lowlevel.queue`에도 동일 기능) |
| `queued_cmd_start_download(total_loop, line_per_loop)` / `queued_cmd_stop_download()` | (243 uv / 244 uv) | 오프라인 다운로드 모드 |
| `get_queued_cmd_current_index() -> int` / `get_queued_cmd_motion_finish() -> bool` | (246 / 247) | 큐 진행 상태 |
| `get_alarms_state() -> bytes` / `clear_all_alarms_state()` | `GET_ALARMS_STATE` (20), `CLEAR_ALL_ALARMS_STATE` (21) | 알람 비트맵 / 해제 |
| `set_arm_speed_ratio(...)` / `get_arm_speed_ratio(params_mode=0)` | `SET_GET_ARM_SPEED_RATIO` (173 uv) | 전체 속도비율(%) |
| `set_l_speed_ratio(...)` / `get_l_speed_ratio(params_mode=0)` | `SET_GET_L_SPEED_RATIO` (174 uv) | 슬라이드레일 속도비율 |
| `set_motor_mode(mode)` / `get_motor_mode() -> int` | `SET_GET_MOTOR_MODE` (172 uv) | 모터 모드 |
| `set_lost_step_params(...)` / `set_lost_step_cmd(*, queued=False)` | (170 uv / 171 uv) | 스텝 손실 파라미터/검사 |
| `set_lost_step_enable_and_params(enable, threshold, *, ...)` / `get_lost_step_enable_and_params() -> (bool, float)` | `SET_GET_LOST_STEP_ENABLE_AND_PARAMS` (177 uv) | 스텝 손실 감지 활성화+임계 |
| `set_hht_trig_mode(mode)` / `get_hht_trig_mode()` / `set_hht_trig_output_enabled(...)` / `get_hht_trig_output_enabled()` / `get_hht_trig_output()` | `SET_GET_HHTTRIG_*` (40~42) | 핸드홀드 티칭 트리거 |
| `set_angle_sensor_static_error(...)` / `get_angle_sensor_static_error()` / `set_angle_sensor_coef(...)` / `get_angle_sensor_coef()` | (211 uv / 212 uv) | 각도 센서 보정 |
| `set_base_decoder_static_error(...)` / `get_base_decoder_static_error()` | `SET_GET_BASE_DECODER_STATIC_ERROR` (213 uv) | 베이스 디코더 보정 |
| `set_wifi_config_mode(enable)` / `get_wifi_config_mode()` | `SET_GET_WIFI_CONFIG_MODE` (150 uv) | WiFi 설정 모드 |
| `set_wifi_ssid(ssid)` / `get_wifi_ssid()` | `SET_GET_WIFI_SSID` (151 uv) | WiFi SSID |
| `set_wifi_password(password)` / `get_wifi_password()` | `SET_GET_WIFI_PASSWORD` (152 uv) | WiFi 비밀번호 |
| `set_wifi_ip_address(...)` / `get_wifi_ip_address() -> WIFIIPAddress` | `SET_GET_WIFI_IP_ADDRESS` (153 uv) | WiFi IP |
| `set_wifi_netmask(...)` / `get_wifi_netmask()` / `set_wifi_gateway(...)` / `get_wifi_gateway()` / `set_wifi_dns(...)` / `get_wifi_dns()` | (154~156 uv) | WiFi 넷마스크/게이트웨이/DNS |
| `get_wifi_connect_status() -> bool` | `GET_WIFI_CONNECT_STATUS` (157 uv) | WiFi 연결 상태 |
| `set_upgrade_fw_ready(fw_size, md5)` / `get_upgrade_fw_ready(fw_size, md5)` | `SET_GET_UPGRADE_FW_READY` (250 uv) | 펌웨어 업그레이드 핸드셰이크 |

```python
ll = arm.lowlevel
ratio = ll.get_arm_speed_ratio(params_mode=1)   # 재현(PTP/CP) 속도비율
ll.set_arm_speed_ratio(params_mode=0, speed_ratio=50)   # JOG 속도비율 50%
finished = ll.get_queued_cmd_motion_finish()
```

---

## 5. 예외 처리

`from dobotkit import ...`로 전체 예외 계층을 임포트할 수 있습니다(모두 `DobotError` 하위).

| 예외 | 발생 상황 |
|---|---|
| `DobotError` | 모든 dobotkit 오류의 기반 |
| `DobotConnectionError` | 장치 미발견, 포트 점유, 연결 끊김 |
| `DobotTimeoutError` | 응답/모션 완료 대기 타임아웃 |
| `DobotProtocolError` | 잘못된 프레임/체크섬/디코드 실패 |
| `DobotValueError` | 인자 범위 오류 |
| `DobotAlarmError` | 활성 알람 (`.codes` 보유) |
| `DobotLinkError` | (GO 전용) DobotLink 미실행/RPC 오류 |

```python
from dobotkit import DobotConnectionError, DobotAlarmError, DobotTimeoutError

try:
    with dobotkit.Magician(port="auto") as arm:
        arm.home(wait=True)
        arm.move_to(220, 0, 40, 0, wait=True, check_alarms=True)
except DobotConnectionError:
    print("연결 실패 — 포트/전원/케이블 확인")
except DobotAlarmError as exc:
    print("알람:", exc.codes)
except DobotTimeoutError:
    print("응답/모션 타임아웃")
```

---

## 6. 안전 수칙 (사람·AI 공통)

1. **전원 직후 홈 필수** — `arm.home(wait=True)`로 좌표 신뢰성 확보.
2. **작업 공간 확보** — 홈/큰 이동 전 주변 장애물 제거.
3. **속도는 낮게 시작** — `arm.set_speed(50, 50)`처럼 50% 이하에서 검증 후 올리기.
4. **상대 이동(`move_relative`)으로 소량 테스트** 후 절대 좌표 사용.
5. **항상 컨텍스트 매니저로 종료** — `with dobotkit.Magician(...) as arm:`가 큐 정지 + 연결 해제를 보장합니다.
6. **AI 에이전트라면**: 좌표를 추정하기 전에 `arm.get_pose()`로 현재값을 먼저 읽고, `move_relative`로 작은 증분으로 검증하세요. 모션 호출에 `check_alarms=True`를 붙이면 결함 상태에서 구동을 막을 수 있습니다.

---

## 7. SDK 커버리지 증명

`dobotkit`가 "모든 기능"을 커버한다는 주장은 코드가 아니라 **테스트로 증명**됩니다.

- `tests/arm/test_coverage.py` — 오라클(`DobotDllType`)의 모든 함수명을 열거하고, 순수 DLL 플러밍 함수(`enum`, `load`, `dSleep`, `gettime`, `SetDebugEnable`, `PeriodicTask`, `DobotExec`, `PrintInfo`, `SetProgbar`, `GetMarlinVersion`)를 제외한 **203개 전부**가 `LowLevelArm`의 메서드에 대응함을 검증합니다.
- 각 페이로드 구조체는 골든-오라클 바이트 매치 테스트(`tests/arm/test_structures*.py`)로 `bytes(DobotDllType.StructX(...))`와 바이트 단위 비교됩니다.
- 전체 스위트(arm+go)는 그린입니다.

> 다시 강조: **구조체 바이트 레이아웃은 검증됨**. **명령 ID 중 `# unverified` 태깅된 값은 미검증** — 실제 하드웨어/공식 프로토콜 문서로 확인하세요(`src/dobotkit/arm/ids.py`, `src/dobotkit/arm/alarms.py`).
