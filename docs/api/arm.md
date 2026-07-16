# Dobot Magician Lite — `dobotkit` 암(Arm) API 레퍼런스

> 4축 데스크톱 로봇팔(Magician Lite)을 **DobotLink**를 통해 제어하기 위한 실전 API 레퍼런스.
> 사람과 AI 에이전트가 코드 예제를 그대로 복사해 쓸 수 있도록 정리했습니다.

- **대상 하드웨어**: Dobot Magician Lite (4축 로봇팔). 보통 **Magic Box 컨트롤러**에 연결되어 USB로 PC와 통신합니다.
- **라이브러리**: `dobotkit` — 런타임 의존성은 `websockets`뿐입니다. DLL/시리얼 불필요, 크로스플랫폼.
- **연결 경로**: 팔은 시리얼로 직접 열리지 않습니다. Python은 **DobotLink** 데스크톱 서비스에 WebSocket(JSON-RPC 2.0)으로 접속하고, DobotLink가 팔의 COM 포트로 명령을 중계합니다.

  ```
  Python  --(WebSocket JSON-RPC)-->  DobotLink.exe  --(COM 포트)-->  Magician Lite
  ```

  **DobotLink.exe가 실행 중이어야 합니다.**
- **임포트**: `import dobotkit` 또는 `from dobotkit import MagicianLite`.

이 문서는 두 계층을 다룹니다:

1. **고수준 `MagicianLite`** — 일상 작업(연결/홈/이동/픽앤플레이스/IO/센서)을 위한 인체공학적 API. **권장.**
2. **`ArmCommands`** — DobotLink의 `Magician.*` JSON-RPC 메서드를 얇게 감싼 래퍼. `MagicianLite.cmds`로 접근하며, `effector`/`sensors`/`io` 그룹이 내부적으로 사용합니다.

---

## 0. 빠른 시작

```python
import dobotkit

# 컨텍스트 매니저로 열면 종료 시 큐 정지 + DobotLink 연결 해제가 항상 보장됩니다(예외 시에도).
with dobotkit.MagicianLite(port="auto") as arm:   # port="auto"면 DobotLink가 찾은 첫 포트 사용
    arm.home()                                     # 원점복귀 (전원 후 최초 1회 필수)
    arm.set_speed(velocity=100, acceleration=100)   # 속도%/가속%

    # 한 점으로 직선 이동 (기본 MOVL_XYZ). wait=True면 큐 실행 완료까지 블로킹.
    arm.move_to(220, 0, 40, wait=True)

    pose = arm.get_pose()                      # 현재 포즈 (dict)
    print(f"x={pose['x']:.1f} y={pose['y']:.1f} z={pose['z']:.1f} r={pose['r']:.1f}")
```

> ⚠️ **전원을 켠 직후에는 반드시 `arm.home()`을 먼저 실행**해야 좌표가 정확합니다.
> 작업 공간을 비우고 실행하세요(로봇팔이 원점으로 크게 움직입니다).

`port="auto"`는 DobotLink의 `SearchDobot` RPC가 찾은 첫 포트로 해석됩니다(`connect()` 시점에 조회). 포트가 없으면 `DobotConnectionError`가 발생합니다. DobotLink 자체가 응답하지 않으면(예: DobotLink.exe 미실행) 소켓 연결 단계에서 `DobotConnectionError`가 발생합니다.

---

## 1. 핵심 개념

### 명령 큐 (Command Queue)

Dobot은 모션 명령을 **큐(queue)** 에 쌓아 순차 실행합니다. `connect()`가 큐를 비우고(clear) 시작(start)하므로, 그 이후에 보내는 명령은 실제로 실행됩니다.

`MagicianLite`의 모션 메서드(`move_to`, `move_relative`, `home`, `pick_and_place`)는 **항상 큐에 적재**됩니다. 고수준 API의 `wait` 인자는 큐 실행 완료까지 폴링할지만 결정합니다:

| `wait` | 동작 |
|---|---|
| `True` | 명령을 큐에 적재하고, `current_index() >= 반환된 인덱스`가 될 때까지 폴링(기본 0.05초 간격, 기본 30초 타임아웃). 타임아웃 시 `DobotTimeoutError`를 발생시킵니다 — **절대 조용히 성공한 것처럼 반환하지 않습니다.** |
| `False` | 큐에 적재만 하고 바로 반환합니다(비동기). 반환값은 큐 인덱스(`int`, 이후 직접 `arm.cmds.current_index()`로 진행 상태를 확인할 수 있음). |

```python
# wait=True: 큐에 적재 → 해당 인덱스가 실행 완료될 때까지 블로킹 (또는 DobotTimeoutError)
idx = arm.move_to(220, 0, 40, wait=True)
```

`ArmCommands`(`arm.cmds`)의 큐 관련 메서드: `queue_clear()`, `queue_start()`, `queue_stop()`, `current_index() -> int`.

### 좌표계

- **데카르트(Cartesian)**: `x, y, z` (mm), `r`(엔드이펙터 회전, deg)
- `arm.get_pose()` → DobotLink의 `GetPose` 응답을 그대로 담은 `dict` (예: `{"x":.., "y":.., "z":.., "r":.., "jointAngle":[...]}`)

### Magic Box 연결 시 주의 (중요)

Magician Lite를 **Magic Box 컨트롤러에 꽂아** 쓰면 센서/서보 관련 호출이 Magic Box를 경유합니다. `arm.sensors.*`(과 `arm.io.get_di`/`get_adc`)는 Magic Box나 그 장치가 연결되어 있지 않으면 예외를 던지는 대신 **`None`을 반환하고 `RuntimeWarning`을 발생**시킵니다 — 아래 2.4절 참고.

---

## 2. 고수준 `MagicianLite` API

`from dobotkit import MagicianLite` 로 임포트합니다. 임포트 자체는 가볍습니다 — `websockets`는 실제로 DobotLink에 연결하는 시점에 로드됩니다(지연 임포트).

### 2.1 생성 / 수명주기

```python
MagicianLite(
    port="auto", *, host="localhost", ws_port=9090, timeout=10.0, auto_connect=True,
)
```

| 메서드/속성 | 설명 |
|---|---|
| `MagicianLite(port="auto", *, host="localhost", ws_port=9090, timeout=10.0, auto_connect=True)` | 생성. `port="auto"`면 `connect()` 시점에 DobotLink가 찾은 첫 포트 사용. `host`/`ws_port`는 DobotLink WebSocket 주소(`ws://{host}:{ws_port}`). `auto_connect=True`면 생성 시 `connect()` 호출. |
| `connect()` / `disconnect()` | DobotLink에 연결하고 팔 연결 + 큐 clear/start / 팔 연결 해제 |
| `with MagicianLite(...) as arm:` | 컨텍스트 매니저. `__exit__`는 항상 큐 정지를 시도한 뒤 `disconnect()`를 시도하며, 둘 중 무엇이 실패해도 `with` 본문의 예외를 가리지 않습니다 |
| `cmds` (속성) | 내부 `ArmCommands` 인스턴스 (DobotLink `Magician.*` RPC 래퍼) |
| `effector` / `sensors` / `io` (속성) | 인체공학적 디바이스 그룹 (아래 2.5) |

```python
arm = dobotkit.MagicianLite(port="auto")   # 생성과 동시에 연결
# ... 작업 ...
arm.disconnect()
```

### 2.2 홈 / 속도 / 포즈

| 메서드 | 설명 |
|---|---|
| `home(x=200, y=0, z=0, r=0, *, wait=True)` | 홈 파라미터 설정 후 홈 실행. 항상 큐에 적재되며, `wait=True`면 완료까지 블로킹(또는 `DobotTimeoutError`) |
| `set_speed(velocity, acceleration)` | PTP 공통 + 좌표 속도/가속(%) 동시 설정 |
| `get_pose() -> dict` | 현재 데카르트+관절 포즈 |

```python
arm.home()                                    # 원점복귀 (wait=True가 기본)
arm.set_speed(velocity=50, acceleration=50)    # 50% 속도로 안전하게 시작
p = arm.get_pose()
print(p["x"], p["y"], p["z"], p["r"])
```

### 2.3 이동(모션)

| 메서드 | 설명 |
|---|---|
| `move_to(x, y, z, r=0, *, mode=PTPMode.MOVL_XYZ, wait=False)` | 절대 데카르트 이동(기본 직선 MOVL). 항상 큐 적재. `wait=True`면 완료까지 블로킹 |
| `move_relative(dx=0, dy=0, dz=0, dr=0, *, wait=False)` | 상대 직선 증분 이동 (`MOVL_XYZ_INC`) |

```python
from dobotkit import PTPMode

# 절대 직선 이동, 완료까지 대기
arm.move_to(220, 0, 40, 0, wait=True)

# 관절 보간 이동으로 모드 변경
arm.move_to(180, 60, 20, 0, mode=PTPMode.MOVJ_XYZ, wait=True)

# 현재 위치에서 Z를 20mm 올리기(상대)
arm.move_relative(dz=20, wait=True)
```

> `wait=True`인데 큐 인덱스가 타임아웃(기본 30초) 내에 실행 완료되지 않으면 `DobotTimeoutError`가 발생합니다. 조용히 성공한 것처럼 반환되지 않습니다.

### 2.4 픽 앤 플레이스

```python
pick_and_place(src, dst, z_safe, settle_ms=200)
```

`src`/`dst`는 `(x, y, z)` 웨이포인트(그랩/릴리스 높이), `z_safe`는 이동 시 클리어런스 높이. 고전적인 8단계 사이클(위로→내려→흡착ON→들기→이동→내려→흡착OFF→들기)을 **모두 큐에 적재**해 하나의 모션 프로그램으로 실행하고 마지막 이동 완료까지 블로킹합니다(완료되지 않으면 `DobotTimeoutError`).

```python
source      = (200.0,   0.0, -30.0)    # 집을 위치 (x, y, z mm)
destination = (100.0, 150.0, -30.0)    # 놓을 위치
arm.pick_and_place(source, destination, z_safe=50.0, settle_ms=300)
```

전체 예제: `examples/arm_magicianlite.py`.

### 2.5 효과기/그리퍼 별칭

| 메서드 | 설명 |
|---|---|
| `suck(on)` | 흡착 ON(잡기)/OFF(놓기). (`effector.suck`에 위임, 컨트롤 전원은 항상 유지) |
| `grip(on)` | 그리퍼 닫기/열기. (`effector.grip`에 위임) |

```python
arm.suck(True)                        # 흡착 ON
arm.move_to(100, 150, 50, 0, wait=True)
arm.suck(False)                       # 흡착 OFF
```

### 2.6 디바이스 그룹 (`effector` / `sensors` / `io`)

저수준 RPC 메서드명을 노출하지 않고 읽기 쉬운 접근자를 제공하는 얇은 facade입니다(`src/dobotkit/arm/groups.py`).

**`arm.effector` (`EffectorGroup`)** — 항상 예외를 raise하는 arm-native 호출:

| 메서드 | 설명 |
|---|---|
| `suck(on, *, enable=True, queued=True)` | 흡착 ON(잡기)/OFF(놓기) |
| `grip(on, *, enable=True, queued=True)` | 그리퍼 닫기/열기 |
| `servo(index, angle, *, queued=True)` | 서보 각도 설정 (Magic Box 경로) |

**`arm.sensors` (`SensorGroup`)** — **모두 Magic Box 경유, 모두 가드됨** (아래 참고):

| 메서드 | 설명 |
|---|---|
| `adc(port) -> Optional[int]` | 해당 포트를 ADC 모드로 설정 후 아날로그 값 읽기 |
| `di(port) -> Optional[int]` | 디지털 입력 레벨 읽기 |
| `color(port) -> Optional[Any]` | 컬러 센서 활성화 후 읽기 |
| `infrared(port) -> Optional[Any]` | 적외선 센서 활성화 후 읽기 |
| `distance(port) -> Optional[Any]` | Seeed 거리 센서 읽기 (mm) |
| `temp(port) -> Optional[Any]` | Seeed 온도/습도 센서 읽기 |
| `light(port) -> Optional[Any]` | Seeed 조도 센서 읽기 (lux) |
| `rgb(port, value) -> Optional[int]` | Seeed RGB LED 출력 |

**`arm.io` (`IOGroup`)** — 읽기(`get_di`/`get_adc`)는 Magic Box 경유·가드됨, 쓰기는 arm-native·raise함:

| 메서드 | 설명 | 가드 여부 |
|---|---|---|
| `set_do(address, level)` | 디지털 출력 설정 | 아니오 (raise) |
| `get_di(address) -> Optional[int]` | 디지털 입력 읽기 | 예 (`None` + 경고) |
| `get_adc(address) -> Optional[int]` | 아날로그 입력 읽기(0~4095) | 예 (`None` + 경고) |
| `set_pwm(address, frequency, duty)` | PWM 출력 설정 | 아니오 (raise) |
| `set_multiplexing(address, multiplex)` | 핀 기능 설정 (`GPIOType`) | 아니오 (raise) |

**Magic Box 가드 동작**: `sensors.*`와 `io.get_di`/`io.get_adc`는 Magic Box(또는 연결된 센서)가 없으면 `DobotTimeoutError`/`DobotProtocolError`를 내부에서 잡아 `RuntimeWarning`을 발생시키고 `None`을 반환합니다 — 그래서 교육용 코드가 죽지 않고 계속 실행됩니다. 진짜 연결 오류(`DobotConnectionError`, 예: DobotLink 미실행)는 가드되지 않고 그대로 전파됩니다.

```python
# Magic Box 경유 센서: 없으면 경고 + None
rgb = arm.sensors.color(port=0)
if rgb is None:
    print("색 센서를 읽지 못했습니다 — 매직박스/센서 연결 확인")
else:
    print(rgb)

v = arm.sensors.adc(24)
if v is None:
    print("매직박스/센서 미연결")
else:
    print(f"ADC[24] = {v}")

# 디지털/아날로그 IO
arm.io.set_do(address=5, level=1)      # arm-native, 실패 시 raise
level = arm.io.get_di(address=2)       # Magic Box 경유, 실패 시 None + 경고
```

---

## 3. 예외 처리

`from dobotkit import ...`로 전체 예외 계층을 임포트할 수 있습니다(모두 `DobotError` 하위).

| 예외 | 발생 상황 |
|---|---|
| `DobotError` | 모든 dobotkit 오류의 기반 |
| `DobotConnectionError` | DobotLink 미실행, 포트 미발견, 연결 끊김 |
| `DobotTimeoutError` | DobotLink 응답 타임아웃, 또는 `wait=True` 모션이 제한 시간 내 완료되지 않음 |
| `DobotProtocolError` | DobotLink가 비정상 응답(디코드 실패)을 준 경우 — `sensors.*`/`io.get_di`/`io.get_adc`에서는 가드되어 `None`으로 변환됨 |
| `DobotValueError` | 인자 범위 오류 |
| `DobotLinkError` | DobotLink JSON-RPC가 에러 응답을 반환한 경우 |
| `DobotAlarmError` | 활성 알람 (`.codes` 보유) — 예외 계층에는 존재하나 현재 `MagicianLite`는 알람 비트맵을 읽는 API를 노출하지 않음 |

```python
from dobotkit import DobotConnectionError, DobotTimeoutError

try:
    with dobotkit.MagicianLite(port="auto") as arm:
        arm.home()
        arm.move_to(220, 0, 40, wait=True)
except DobotConnectionError:
    print("연결 실패 — DobotLink 실행 여부 / 포트 / 전원 확인")
except DobotTimeoutError:
    print("응답/모션 완료 타임아웃")
```

---

## 4. 안전 수칙 (사람·AI 공통)

1. **DobotLink.exe 실행 필수** — 팔은 시리얼로 직접 열리지 않고 DobotLink 경유로만 제어됩니다.
2. **전원 직후 홈 필수** — `arm.home()`으로 좌표 신뢰성 확보.
3. **작업 공간 확보** — 홈/큰 이동 전 주변 장애물 제거.
4. **속도는 낮게 시작** — `arm.set_speed(50, 50)`처럼 50% 이하에서 검증 후 올리기.
5. **상대 이동(`move_relative`)으로 소량 테스트** 후 절대 좌표 사용.
6. **항상 컨텍스트 매니저로 종료** — `with dobotkit.MagicianLite(...) as arm:`가 큐 정지 + DobotLink 연결 해제를 보장합니다.
7. **AI 에이전트라면**: 좌표를 추정하기 전에 `arm.get_pose()`로 현재값을 먼저 읽고, `move_relative`로 작은 증분으로 검증하세요. `wait=True`는 완료를 보장하거나 `DobotTimeoutError`로 실패를 알립니다 — 반환값을 성공으로 오인하지 마세요.
