# Dobot Magician GO — `dobotkit` 카(Car) API 레퍼런스

> 메카넘 휠 기반 전방향 주행 로봇 카(Magician GO)를 **순수 파이썬**으로 제어하기 위한 실전 API 레퍼런스.
> 사람과 AI 에이전트가 코드 예제를 그대로 복사해 쓸 수 있도록 정리했습니다.

- **대상 하드웨어**: Dobot Magician GO (전방향 주행 카 + 초음파/IMU/오도미터, 카메라, RGB LED, 부저, 라인트레이싱)
- **라이브러리**: `dobotkit` — **순수 파이썬**(`websockets`만), DLL 불필요, 크로스플랫폼, `pip install dobotkit`.
- **임포트**: `from dobotkit import MagicianGO` + `from dobotkit.go.client import DobotLinkClient`.
- **연결 구조**:

```
Python  --(WebSocket JSON-RPC)-->  DobotLink.exe  --(COM 포트 / 무선동글)-->  Magician GO
```

GO는 직접 구동하지 않습니다. 파이썬은 **DobotLink** 데스크톱 서비스에 WebSocket JSON-RPC 2.0으로 붙고, DobotLink이 COM 포트/무선 동글로 카에 명령을 중계합니다. `dobotkit`는 Dobot의 DobotEDU/DobotRPC 패키지에 의존하지 않고 `websockets`만 사용합니다.

---

## 정직성 고지 (반드시 읽으세요)

`dobotkit`는 다음을 **정직하게** 공개합니다.

- **완전한 GO API 커버리지.** `MagicianGO`는 DobotLink의 `MagicianGO.*` JSON-RPC 표면 전체(연결/연속주행/폐루프/센서/안전/출력/라인트레이스/카메라)를 타입드 메서드로 래핑합니다.
- **순수 파이썬.** `websockets`만 사용하며 DLL/네이티브 바이너리에 의존하지 않습니다. `pip`로 설치되고 크로스플랫폼입니다(단, DobotLink.exe는 Windows 전용 서비스).
- ⚠️ **GO 내장 폐루프 명령은 HANG할 수 있습니다.** `rotate`/`move_dist`/`arc_rad`/`arc_cent`/`increment_closed_loop`는 이 기체에서 완료 콜백이 오지 않아 타임아웃(~7일)까지 **멈춥니다(HANG)**. 정밀 제어가 필요하면 `PreciseMover`/`WaypointNav`(연속 `move()` + 센서 피드백)를 사용하세요.
- ⚠️ **GO 폐루프 회전 방향(yaw 부호)은 실제 하드웨어 확인이 필요합니다.** 문서의 방향 규약(`r+` = 좌회전/CCW)은 소프트웨어 측 가정이며, 펌웨어 enum 값(`move_direct`의 `direction`, `arc_*`의 `mode`, `set_running_mode`의 `mode`)도 소스로 확정되지 않아 **실측이 필요**합니다.

---

## 0. 사전 준비 (필수)

1. **GO 전원 ON**, 무선 동글을 PC에 연결.
2. **DobotLink.exe 실행** (보통 `C:\Users\<user>\AppData\Local\Programs\DobotLink\DobotLink.exe`).
   - 파이썬은 `ws://localhost:9090`으로 DobotLink에 붙고, DobotLink이 COM 포트로 GO에 연결합니다.
3. GO가 붙은 **COM 포트** 확인(기본 가정값 `COM5`).
4. 의존성: `pip install dobotkit` (런타임에 `websockets`만 사용).

---

## 1. 빠른 시작

```python
from dobotkit import MagicianGO, DobotLinkError
from dobotkit.go.client import DobotLinkClient

client = DobotLinkClient(host="localhost", port=9090, timeout=10.0).connect()
go = MagicianGO(client, port_name="COM5")

try:
    go.connect()                       # connect_robot() 후 battery()로 링크 검증
    print("battery:", go.battery())    # 예: {'powerVoltage': 11.2, 'powerPercentage': 80}
    print("ultrasonic:", go.ultrasonic())

    go.forward(20)                     # 전진 (연속 속도 제어)
    import time; time.sleep(0.5)
    go.emergency_stop()                # 즉시 정지
finally:
    # 확실 정지: 응답 대기 없는 즉시 정지 후, 확인용 stop() 재시도
    go.emergency_stop()                # notify 기반 즉시 정지(응답 대기 없음)
    try:
        go.stop()                      # 확인용(응답 대기 = move(0,0,0))
    except DobotLinkError:
        go.emergency_stop()            # 확인 실패 시 비상정지 재발사
    client.close()
```

> `go.connect()`는 내부에서 `connect_robot()`를 호출한 뒤 (기본 `verify=True`) `battery()`를 읽어 링크를 검증합니다.

> ⚠️ **`connect_robot()`의 핸드셰이크는 거짓 성공을 보고할 수 있습니다.** 연결 직후 반드시 `go.battery()` 같은 읽기 호출로 실제 응답을 확인하세요(`go.connect()`가 이를 대신해 줍니다). 타임아웃 나면 GO 전원/무선 링크가 끊긴 것이니 중단합니다.

`DobotLinkClient`/`MagicianGO`/`DobotLinkError`는 모두 `dobotkit`에서 직접 임포트할 수 있습니다(클라이언트는 `dobotkit.go.client`에 있습니다). `import dobotkit`만으로는 `websockets`가 로드되지 않으며, 첫 연결 시점에 지연 임포트됩니다.

---

## 2. 아키텍처 / 동작 모델

### 2.1 두 가지 호출 방식 (`DobotLinkClient`)

| 메서드 | 의미 |
|---|---|
| `client.call(method, **params)` | JSON-RPC 요청 후 **응답 대기**(블로킹, timeout 적용). error 응답 시 `DobotLinkError`, 무응답 시 `DobotTimeoutError` |
| `client.notify(method, **params)` | 응답 없이 **전송만**(블로킹/타임아웃 없음) — 비상정지 전용 |

`MagicianGO`의 메서드는 (`search()` 제외) 내부 `_call` 헬퍼로 `MagicianGO.<함수>`를 `portName`과 함께 호출합니다. `search()`는 포트 선택 전 단계이므로 `portName` 없이 `MagicianGO.SearchDobot`을 호출합니다. `emergency_stop()`만 `client.notify`를 사용해 응답을 기다리지 않습니다.

### 2.2 주행 명령의 두 종류 (중요)

| 종류 | 메서드 | 특성 |
|---|---|---|
| **연속 속도 제어** | `move`, `move_direct`, `forward`, `backward`, `strafe`, `spin`, `stop`, `emergency_stop` | ✅ **정상 동작(신뢰)**. 속도를 주고 `stop()` 전까지 계속 이동 |
| **큐/폐루프 명령** | `rotate`, `move_dist`, `arc_rad`, `arc_cent`, `increment_closed_loop` | ⚠️ **이 기체에서 완료 신호가 안 와 HANG**(~7일 타임아웃)될 수 있음 |

> 폐루프 명령들은 `isQueued=True, isWaitForFinish=True` 플래그(코드의 `_WAIT`)로 큐에 넣고 완료 콜백을 대기하므로, 콜백이 오지 않으면 HANG합니다. **정밀 이동이 필요하면 연속 `move()` + 센서 피드백으로 폐루프를 구성**하세요(→ 6절 `PreciseMover`, 7절 `WaypointNav`).
>
> `coord_closed_loop`(`SetCoordClosedLoop`)도 폐루프 계열이지만 `_WAIT` 플래그를 **사용하지 않아** 위 명령들과 거동이 다릅니다(완료 대기/HANG 동작이 아님).

### 2.3 좌표/단위 규약

- **속도**: 정수 값(단위 미정규화). `PreciseMover`는 명령 속도 크기를 `max_speed=30`으로 **상한**, 목표 근처 감속 시 `min_speed=8`로 **하한** 강제합니다(강제 캡이며 권장 절대값이 아님). 부호는 유지됩니다.
- **오도미터(`odometer()`)**: `{x, y, yaw}` — **월드 프레임** 누적 위치. mm 단위(매트 좌표 cm와 ×10 변환).
- **IMU 각도(`imu_angle()`)**: `{yaw, ...}` — **전원 기준 절대각**(`set_odometer`와 무관).
- **방향 규약**: `x+` = 전진, `y+` = 좌측 횡이동(strafe), `r+` = 좌회전(반시계, CCW). ⚠️ **회전 부호는 실측 확인 필요**(정직성 고지 참조).
- **초음파(`ultrasonic()`)**: `{front, back, left, right}` — cm 단위.
- **yaw 출처 선택**: 제자리 회전량 측정은 `imu_angle()['yaw']`(상대 변화량이 안정적 → `PreciseMover.turn_degrees`), 매트 절대 헤딩은 `set_odometer`로 영점이 잡히는 `odometer()['yaw']`(→ `WaypointNav.pose_cm`)를 사용합니다. 두 yaw는 기준이 다르므로(IMU = 전원 기준, 오도미터 = `set_odometer` 기준) 절대값이 24° 이상 어긋날 수 있습니다. **혼용하지 마세요.**

---

## 3. `MagicianGO` API 레퍼런스

`from dobotkit import MagicianGO` → `MagicianGO(client, port_name="COM5")`.

### 3.1 연결

| 메서드 | 설명 |
|---|---|
| `search()` | 연결 가능한 GO 탐색(`MagicianGO.SearchDobot`). 다른 메서드와 달리 `portName`을 보내지 않음. **DobotLink 응답을 그대로 반환하며 반환 구조는 펌웨어 정의 — 정규화하지 않음(실측 필요)** |
| `connect_robot()` | DobotLink이 `port_name`으로 GO에 연결. **명령 전 필수**. 핸드셰이크가 거짓 성공할 수 있어 읽기로 검증 권장 |
| `disconnect_robot()` | GO 연결 해제 (`MagicianGO.DisconnectDobot`) |
| `connect(verify=True)` | `connect_robot()` 후 (기본) `battery()`로 링크 검증. 권장 진입점 |
| `set_running_mode(mode)` | 주행 모드 설정 (`SetRunningMode(runningMode=mode)`). `mode`는 정수이며 **각 값의 의미는 펌웨어 미확정(실측 필요)** — 예제는 `0`/`1`을 프로브 |

```python
go.connect()                  # connect_robot() + battery() 검증 (권장)
ports = go.search()           # 구조 미확정 — 실측 확인
go.set_running_mode(0)        # 의미 미확정 — 펌웨어 사양 확인 필요
```

### 3.2 연속 주행 (✅ 권장)

| 메서드 | 설명 |
|---|---|
| `move(x=0, y=0, r=0)` | 속도 벡터 지정(전진/횡이동/회전 동시 가능). `SetMoveSpeed` |
| `move_direct(direction, speed)` | 방향 지정 주행. `SetMoveSpeedDirect(dir=direction, speed=speed)`. `direction`(파이썬) → `dir`(RPC). `direction=0`을 전진으로 **추정**하나 값 매핑 펌웨어 미확정(실측 필요) |
| `forward(speed)` | 전진 (= `move(x=speed)`) |
| `backward(speed)` | 후진 (= `move(x=-speed)`) |
| `strafe(speed)` | 좌(+)/우(-) 횡이동 (= `move(y=speed)`) |
| `spin(speed)` | 제자리 회전 (= `move(r=speed)`) |
| `stop()` | 정지 (= `move(0, 0, 0)`, 응답 대기) |
| `emergency_stop()` | **즉시 정지** — `notify`로 전송, 블로킹/타임아웃 없음. `finally`/인터럽트 경로에서 안전 |

```python
go.move(x=20, y=0, r=0)       # 전진 20
go.strafe(15)                 # 좌측 횡이동
go.spin(-10)                  # 우회전(시계방향)
go.move_direct(direction=0, speed=20)   # dir=0을 전진으로 가정(실측 필요)
go.emergency_stop()
```

> 직진이 목적이면 `forward()`/`backward()`를 우선 쓰세요. `move_direct`의 `direction` 구체 값은 소스에 enum 정의가 없어 펌웨어 문서 확인이 필요합니다.

> 📄 실행 가능한 전체 예제: [`examples/go_teleop.py`](../../examples/go_teleop.py) — 키보드 텔레옵(W/S 전후, A/D 횡, J/L 회전, SPACE 정지, Q 종료) + 초음파 클리어런스 인터록 + 텔레메트리 출력. `python examples/go_teleop.py [COM포트]` (키 입력은 Windows `msvcrt` 사용).

### 3.3 안전 클리어런스 체크

```python
ok, info = go.clearance_ok(x=0, y=0, r=0, threshold=20)
# 진행 방향(x/y/r)의 초음파 거리가 threshold(cm) 이상이면 (True, 거리dict)
# 막혀 있으면 (False, 사유문자열). 회전(r)은 사방 모두 확보 요구.
if ok:
    go.forward(20)
else:
    print("막힘:", info)
```

`clearance_ok`는 `ultrasonic()`을 읽어 의도한 방향의 클리어런스를 검증합니다: `x>0`→front, `x<0`→back, `y!=0`→좌우 최소, `r!=0`→사방 최소(제자리 회전은 원을 그림).

### 3.4 큐/폐루프 주행 (⚠️ HANG 위험 — 2.2 참고)

| 메서드 | 설명 |
|---|---|
| `rotate(r, Vr)` | 각도 `r`만큼 회전(속도 `Vr`) |
| `move_dist(x, y, Vx, Vy)` | 거리 지정 이동 |
| `arc_rad(velocity, radius, angle, mode)` | 반경 기반 원호. `mode`=정수 방향/모드 플래그(예제는 `mode=0`, 의미 미확정) |
| `arc_cent(velocity, x, y, angle, mode)` | 중심점 기반 원호. `mode`=정수 플래그(예제는 `mode=0`, 의미 미확정) |
| `coord_closed_loop(is_enable, angle)` | 좌표 폐루프 (`SetCoordClosedLoop`). ⚠️ 다른 큐 명령과 달리 `_WAIT` 플래그 미전송 — 완료 대기(HANG) 동작 아님 |
| `increment_closed_loop(x, y, angle)` | 증분 폐루프 |

> ⚠️ **HANG 가능 — 실측/디버깅 전용, 반드시 `clearance_ok` 인터록과 함께.** 아래는 인자 순서/이름을 보여주는 호출 예입니다(인터록 통과 시 소량만, 끝에 `emergency_stop`).

```python
ok, info = go.clearance_ok(r=1, threshold=25)
if ok:
    try:
        go.rotate(20, 30)                  # 회전 20deg, 속도 Vr=30
        # go.move_dist(30, 0, 30, 0)        # x=30mm 이동, Vx=30
        # go.increment_closed_loop(30, 0, 0)
        # go.arc_rad(30, 50, 30, 0)         # velocity, radius, angle, mode
        # go.arc_cent(30, 50, 0, 30, 0)     # velocity, x, y, angle, mode
    finally:
        go.emergency_stop()
```

> 이 폐루프 명령군 전체가 이 기체에서 **완료 신호 미수신으로 HANG될 수 있으므로** 실사용은 권장하지 않습니다. 정밀 제어는 6·7절(연속 `move()` + 센서 피드백)을 사용하세요.

### 3.5 센서 (읽기 — 안전, 모터 무동작)

| 메서드 | 반환 | 설명 |
|---|---|---|
| `ultrasonic()` | `{front, back, left, right}` (cm) | 4방향 초음파 거리 (`GetUltrasoundData`) |
| `odometer()` | `{x, y, yaw}` | 누적 위치(월드프레임, mm). RPC는 `GetSpeedometer`('Speedometer' 철자) |
| `set_odometer(x, y, yaw)` | — | 오도미터 값 강제 세팅(좌표 영점). RPC `SetSpeedometer` |
| `battery()` | `{powerVoltage, powerPercentage}` | 배터리 전압(V)+잔량(%). **링크 검증용으로 자주 사용** |
| `imu_angle()` | `{yaw, ...}` | IMU 각도(전원 기준 절대) |
| `imu_speed()` | `{...}` | IMU 각속도 |

```python
go.set_odometer(0, 0, 0)      # 현재 위치를 좌표 원점(0,0,yaw=0)으로 영점화
u = go.ultrasonic()           # {'front':.., 'back':.., 'left':.., 'right':..}
odo = go.odometer()           # {'x':.., 'y':.., 'yaw':..}  (mm, deg)
bat = go.battery()            # 링크 검증
```

> **헤딩(yaw) 소스 구분 (중요)**: 절대 매트 좌표 내비게이션(`WaypointNav.pose_cm`)은 `set_odometer`로 매트 프레임에 영점이 잡히는 **오도미터 yaw**를 사용합니다. 단발 제자리 회전 정확도(`PreciseMover.turn_degrees`)는 시작 대비 **상대 변화량**만 보므로 **IMU yaw**를 사용합니다. 두 소스는 혼용하지 마세요.

### 3.6 출력 (LED / 부저)

```python
go.rgb(number, effect, r, g, b, cycle, counts)   # 내부 RPC: SetLightRGB
#   number : 1~5 정수, LEDChannel enum, 또는 "LED_1".."LED_4","LED_ALL" (문자열은 내부 매핑)
#   effect : 1 = 점등(ON), 0 = 소등(OFF)
#   r,g,b  : 0~255
#   cycle, counts : 점멸 주기/횟수(정수). 상시 점등/소등은 0 사용 (정확한 의미 펌웨어 미확정)

go.buzzer(index, tone, beat)   # 내부 RPC: SetBuzzerSound
#   index/tone/beat : 정수(음 인덱스/음정/박자로 추정). 범위·의미 펌웨어 미확정(실측 필요)
```

**`LEDChannel`** (`from dobotkit import LEDChannel`): `LED_1=1, LED_2=2, LED_3=3, LED_4=4, LED_ALL=5`. `number` 인자는 `LEDChannel`/int/문자열을 모두 받습니다.

```python
from dobotkit import LEDChannel

go.rgb("LED_ALL", effect=1, r=255, g=0, b=0, cycle=0, counts=0)   # 전체 빨강 점등
go.rgb(LEDChannel.LED_1, 1, 0, 255, 0, 0, 0)                      # LED_1 초록 (enum)
go.rgb(1, 1, 0, 255, 0, 0, 1)                                     # LED_1 초록 (int)
go.rgb("LED_ALL", 0, 0, 0, 0, 0, 1)                              # 전체 소등
go.buzzer(index=1, tone=1, beat=1)                               # 부저 1회
```

### 3.7 라인 트레이싱

| 메서드 | 설명 |
|---|---|
| `auto_trace(on)` | 라인 트레이싱 ON/OFF (내부적으로 `SetTraceLoop` + `SetTraceAuto`) |
| `trace_speed(speed)` | 트레이싱 속도 (`SetTraceSpeed`) |
| `trace_pid(p, i, d)` | 라인 추종 PID 게인 (`SetTracePid`) |
| `trace_angle()` | **CAR 카메라**(`GetCarCameraAngle`)가 인식한 라인 각도 `{angle, count}`. ARM 카메라가 비활성(405)이어도 영향 없음 |

```python
go.trace_speed(30)            # SetTraceSpeed(speed=30)
go.trace_pid(50, 0, 10)       # P, I, D
go.auto_trace(True)           # SetTraceLoop(enable=True) → SetTraceAuto(isTrace=True)
print(go.trace_angle())       # {'angle': ..., 'count': ...}
go.auto_trace(False)          # 추종 종료
```

### 3.8 카메라 (객체/태그 인식)

| 메서드 | 설명 |
|---|---|
| `car_camera_obj()` | CAR(차체) 카메라 딥러닝 객체 인식 결과 (`GetCarCameraObj`) |
| `arm_camera_obj()` | ARM 카메라 객체 인식 (기체에 따라 비활성 가능 — 405/타임아웃) |
| `arm_camera_tag()` | ARM 카메라 AprilTag/마커 인식 |

> **반환 구조는 펌웨어/버전마다 다릅니다.** 예: `{count, dl_obj: [...]}`. 필드명이 변할 수 있으므로 **방어적으로** 읽으세요(`result.get("count", len(result.get("dl_obj", [])))`).

```python
res  = go.car_camera_obj()
n    = res.get("count", 0)        # count 키 없으면 len(objs)로 대체
objs = res.get("dl_obj", [])      # 검출 객체 리스트
```

> 참고: 일부 기체는 ARM 카메라가 비활성입니다. 이 경우 `arm_camera_obj()`/`arm_camera_tag()`가 firmware error `{'code': 405, ...}`(또는 타임아웃)를 반환합니다. CAR 카메라가 정상인데 ARM만 405면 DobotLink↔GO 경로는 정상이고 ARM 모듈만 미응답입니다. 평상시에는 CAR 카메라(`car_camera_obj()`)를 우선 사용하세요.

---

## 4. `DobotLinkClient` API

저수준 JSON-RPC 클라이언트. `from dobotkit.go.client import DobotLinkClient`.

```python
from dobotkit.go.client import DobotLinkClient

client = DobotLinkClient(host="localhost", port=9090, timeout=10.0)
client.connect()                       # 연결 (실패 시 DobotConnectionError)
result = client.call("MagicianGO.GetBatteryVoltage", portName="COM5")
client.notify("MagicianGO.SetMoveSpeed", portName="COM5", x=0, y=0, r=0)  # 비상정지
client.close()

# with 문도 지원
with DobotLinkClient() as client:
    print(client.call("MagicianGO.GetBatteryVoltage", portName="COM5"))
```

| 메서드 | 설명 |
|---|---|
| `DobotLinkClient(host="localhost", port=9090, timeout=10.0)` | 생성. `timeout`은 연결/응답 대기 공통 |
| `connect() -> self` | WebSocket 연결(멱등). 실패 시 `DobotConnectionError`(DobotLink 미실행 안내 포함) |
| `call(method, **params) -> Any` | 요청+응답 대기. error 응답 시 `DobotLinkError`, 무응답 시 `DobotTimeoutError`. 응답의 `result` 필드 반환 |
| `notify(method, **params) -> None` | 응답 없이 전송만(no id) |
| `close()` | 연결 종료(멱등) |

> ⚠️ `method`에는 **`dobotlink.` 접두어만 자동으로 붙습니다**(`dobotlink.`로 시작하면 그대로 둠). **`MagicianGO.`(또는 `MagicBox.`) 네임스페이스는 자동 보정되지 않으므로** 저수준 `call`/`notify`를 직접 쓸 때는 호출자가 직접 포함해야 합니다 — 예: `client.call("MagicianGO.GetBatteryVoltage", portName="COM5")`. (`MagicianGO` 래퍼의 고수준 메서드는 `MagicianGO.` 접두어를 내부에서 붙여 줍니다.)

### 4.1 실험적 RPC (`MagicBox.*`) — 좌표 정지점(Stop-Point)

아래 RPC는 `MagicianGO.*`가 아닌 `MagicBox.*` 네임스페이스라 `MagicianGO` 래퍼에 없으며, 저수준 `client.call`로 직접 호출합니다.

| 메서드 | 설명 |
|---|---|
| `MagicBox.SetStopPointServer(portName, PointX, PointY)` | 목표 정지 좌표 설정 |
| `MagicBox.SetStopPointParam(portName, scopeErr, stopErr)` | 허용오차 설정(예: scopeErr=40, stopErr=2) |
| `MagicBox.GetStopPointState(portName)` | `{'result': bool}` 반환. result=True면 도착·정지 |

```python
client.call("MagicBox.SetStopPointServer", portName="COM5", PointX=5, PointY=0)
```

> 주의: (1) `PointX`/`PointY` 단위(매트 cm vs 내부 mm)가 미확정이니 작은 값으로 검증하세요. (2) 이 유닛에서 동작 미보장 — 내장 폐루프처럼 HANG/미정지 가능하므로 오도메트리 웨이포인트(`WaypointNav`) 사용을 권장합니다.

---

## 5. 라인 트레이싱 예제 (안전 인터록 포함)

```python
import time
from dobotkit import MagicianGO
from dobotkit.go.client import DobotLinkClient

client = DobotLinkClient().connect()
go = MagicianGO(client, port_name="COM5")
try:
    go.connect()                     # connect_robot() + battery() 검증
    go.trace_speed(30)
    go.trace_pid(50, 0, 10)          # P, I, D
    go.auto_trace(True)              # 추종 시작

    start = time.monotonic()
    while time.monotonic() - start < 20:
        u = go.ultrasonic()
        nearest_dir = min(u, key=u.get)
        if u[nearest_dir] < 15:      # 15cm 미만 장애물 → 즉시 정지
            go.auto_trace(False)
            go.emergency_stop()
            break
        time.sleep(0.1)
finally:
    go.auto_trace(False)
    go.emergency_stop()
    client.close()
```

> 실제 바닥 라인이 있어야 추종합니다. 라인이 없으면 제자리 동작만 시도합니다.

> 📄 실행 가능한 전체 예제: [`examples/go_line_trace.py`](../../examples/go_line_trace.py) — `python examples/go_line_trace.py [COM포트] [지속시간초]`. 위 안전 인터록 + `try/finally` 정리가 그대로 들어 있습니다.

---

## 6. 정밀 이동 — 연속 move() + 센서 폐루프 (`PreciseMover`)

내장 폐루프가 HANG하므로(2.2), 연속 속도 제어에 오도미터/IMU 피드백을 얹어 직접 폐루프를 만듭니다. `from dobotkit.go.navigation import PreciseMover`.

```python
from dobotkit.go.navigation import PreciseMover

mover = PreciseMover(go, max_speed=30, min_speed=8)

# X축으로 50mm 전진 후 정지 (목표 근처 비례 감속, 클리어런스 사전 확인, 안전 타임아웃)
res = mover.goto_distance(50, speed=25, axis="x", threshold=20, timeout_s=8.0)
# res: {target, achieved, error, axis, timed_out, aborted}  (aborted=True 시 reason 키 추가)
if res["aborted"]:
    print("진행 방향 막힘:", res["reason"])   # 클리어런스 인터록(정상 안전 동작)
elif res["timed_out"]:
    print("타임아웃 — 목표 미도달, error(mm)=", res["error"])
else:
    print("도달, 오차(mm)=", res["error"])

# 제자리 +45도 회전 (r+ = 좌회전, IMU yaw 피드백, ±180 wraparound 처리)
res = mover.turn_degrees(45, speed=25, threshold=20, timeout_s=8.0)
# res: {target, achieved, error, timed_out, aborted}  (aborted=True 시 reason 키 추가)
```

| 메서드 | 설명 |
|---|---|
| `PreciseMover(go, max_speed=30, min_speed=8)` | 연속 `move` 위의 오도미터/IMU 피드백 폐루프 |
| `goto_distance(distance_mm, speed=25, axis="x", threshold=20, timeout_s=8.0) -> dict` | `axis="x"`(전후, `+`전진)/`"y"`(횡, `+`좌). 부호가 방향. 오도미터 변위 크기로 측정 |
| `turn_degrees(deg, speed=25, threshold=20, timeout_s=8.0) -> dict` | 제자리 회전(`+`=CCW). IMU yaw 변화량으로 측정 |

> `clearance_ok`로 진행 방향이 막혀 `aborted=True`가 되면 반환 dict에 `reason` 키(예: `"clearance blocked: front=12<20"`)가 추가됩니다. `aborted`(막힘)와 `timed_out`(타임아웃)은 안전 설계상 **정상 흐름**이며 예외가 아니라 반환 dict로 구분됩니다. 항상 결과를 점검하세요.

**핵심 안전 설계** (그대로 따를 것):
- 매 제어 루프에 **절대 타임아웃(`time.monotonic`)** — 목표 미도달이어도 영원히 돌지 않음.
- 이동 전 **`clearance_ok()`로 진행 방향 확인** — 막히면 그 동작 중단(`aborted`).
- 모든 동작은 **`try/finally` 안에서 `emergency_stop()`** 으로 끝남(내부 `_settle_stop`).
- 속도는 보수적으로 캡(`max_speed=30`, 목표 근처 `min_speed=8`로 감속).

---

## 7. 좌표 자율주행 — 절대 매트 좌표 웨이포인트 (`WaypointNav`)

`PreciseMover` 위에 절대 좌표 내비게이션을 얹습니다. `from dobotkit.go.navigation import WaypointNav`.

```python
from dobotkit.go.navigation import WaypointNav

nav = WaypointNav(go)

# 1) 시작 포즈 보정 — 매트 위 실제 좌표/방위를 정확히 선언 (cm, deg)
nav.set_start(x_cm=100, y_cm=48, heading_deg=0)

# 2) 절대 매트 좌표로 이동 (매 반복마다 재측정 → 베어링 회전 → 직진)
res = nav.go_to(112, 48, arrive_tol_cm=2.0, max_iters=3)
# res: {start, target, final, residual_cm, iters, legs, arrived}

# 보조
nav.pose_cm()                 # 현재 {x_cm, y_cm, heading_deg}
nav.face(heading_deg=90)      # 절대 방위로 회전
```

| 메서드 | 설명 |
|---|---|
| `WaypointNav(go, mover=None)` | `mover` 생략 시 내부에서 `PreciseMover(go)` 생성 |
| `set_start(x_cm, y_cm, heading_deg=0.0) -> dict` | 현재 매트 포즈를 선언(오도미터 영점, cm→mm). 사람의 보정 필요 |
| `pose_cm() -> dict` | 현재 `{x_cm, y_cm, heading_deg}`. 헤딩은 **오도미터 yaw** |
| `face(heading_deg, speed=25, threshold=20, timeout_s=8.0) -> dict` | 절대 방위로 회전. `turn_degrees` 결과 + `{bearing, from_heading}` |
| `go_to(x_cm, y_cm, speed=25, arrive_tol_cm=2.0, max_iters=3, ...) -> dict` | 절대 좌표로 이동. `legs`에 반복별 상세 |

**`face()` 반환값**: `turn_degrees` 결과 dict에 다음이 추가됨.

| 키 | 의미 |
|---|---|
| `bearing` | 목표 절대 방위(deg) — 입력 `heading_deg` |
| `from_heading` | 회전 시작 시점의 현재 헤딩(deg) |

**`go_to()`의 `legs`**: 각 반복(leg)당 dict 리스트 — `{iter, bearing, dist_cm, turn, move}`.

**좌표 규약**: 매트=cm(내부 이동은 mm, ×10 변환), `0deg`=+X 바라봄, 반시계(+). 헤딩 측정(현재 방위)은 오도미터 yaw, 회전량은 IMU yaw로 측정하므로 두 소스가 어긋나면 회전 후 베어링 오차가 생길 수 있고, `go_to`는 매 반복 재측정(`max_iters`)으로 보정합니다.

> **주의**: `set_start`로 선언한 값이 **실제 시작 위치/방위와 일치**해야 자율주행이 맞습니다(사람의 보정 필요).

> 📄 실행 가능한 전체 예제: [`examples/go_waypoint_nav.py`](../../examples/go_waypoint_nav.py) — `connect` → `set_start` → 절대 매트 좌표 2개로 `go_to` 후 결과 dict 출력. `python examples/go_waypoint_nav.py [COM포트]`. (시작 포즈는 가정값이니 실제 매트에 맞게 보정하세요.)

---

## 8. 예외 처리

`from dobotkit import ...`로 전체 예외 계층을 임포트할 수 있습니다(모두 `DobotError` 하위).

| 예외 | 발생 상황 |
|---|---|
| `DobotError` | 모든 dobotkit 오류의 기반 |
| `DobotConnectionError` | DobotLink WebSocket 연결 실패(주로 DobotLink.exe 미실행) |
| `DobotLinkError` | RPC error 응답, 또는 미연결 상태에서 호출 |
| `DobotTimeoutError` | 응답 무수신 타임아웃(GO 전원/무선 링크 단절 가능) |

```python
from dobotkit import DobotConnectionError, DobotLinkError, DobotTimeoutError

try:
    client = DobotLinkClient().connect()
except DobotConnectionError:
    print("DobotLink.exe 미실행 — 실행 후 재시도")
```

---

## 9. 안전 수칙 (사람·AI 공통, 매우 중요)

> 과거 개루프 테스트가 벽으로 돌진해 전원이 차단된 사례가 있습니다. 반드시 지키세요.

1. **링크 검증**: `go.connect()`(= `connect_robot()` + `battery()`)로 실제 응답 확인. 실패 시 즉시 중단.
2. **이동 전 클리어런스**: `clearance_ok()`로 진행 방향 거리 확인(≥15~20cm).
3. **연속 명령만 신뢰**: 내장 폐루프(`move_dist`/`rotate`/`arc_*`/`increment_closed_loop`)는 HANG 가능 → 연속 `move()` + 피드백(`PreciseMover`/`WaypointNav`) 사용.
4. **항상 정지로 종료**: 모든 제어를 `try/finally` 안에서 `go.emergency_stop()` + `client.close()`.
5. **속도 상한 고정**: `max_speed=30` 이하, 짧은 거리/각도부터 검증.
6. **모든 루프에 타임아웃**: 절대 무한 대기 금지(`PreciseMover`/`WaypointNav`는 `timeout_s` 내장).
7. **회전 방향(yaw 부호)은 실측 확인**: `r+`=CCW 규약은 가정이며, 실제 하드웨어로 부호를 검증한 뒤 자율주행에 사용하세요.
8. **AI 에이전트라면**: 동작 명령 전 `ultrasonic()`/`odometer()`로 상태를 먼저 읽고, 작은 펄스로 검증 후 확장하세요.

---

## 10. 빠른 트러블슈팅

| 증상 | 원인/해결 |
|---|---|
| `cannot connect to DobotLink at ws://localhost:9090` (`DobotConnectionError`) | DobotLink.exe 미실행 → 실행 후 재시도 |
| `connect()`/`connect_robot()`은 OK인데 `battery()` 타임아웃 | GO 전원 OFF 또는 무선 동글 분리 → 전원/링크 확인 |
| `move_dist`/`rotate`가 영원히 멈춤(HANG) | 내장 폐루프 미지원 → 연속 `move()` + 피드백(6·7절) 사용 |
| 자율주행이 목표에서 빗나감 | `set_start` 시작 좌표/헤딩 보정 우선. 오도미터 드리프트는 `go_to` 재측정으로 보정 |
| ARM 카메라 405 에러 | 해당 기체 ARM 카메라 비활성 → `car_camera_obj()` 사용 |
| 회전이 반대로 돎 | yaw 부호 규약 미검증 — 실제 하드웨어로 `r+` 방향 확인 후 보정 |
