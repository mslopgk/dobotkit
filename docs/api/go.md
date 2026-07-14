# Dobot Magician GO — `dobotkit` 카(Car) API 레퍼런스

> 메카넘 휠 기반 전방향 주행 로봇 카(Magician GO)를 **순수 파이썬**으로 제어하기 위한 실전 API 레퍼런스.
> 사람과 AI 에이전트가 코드 예제를 그대로 복사해 쓸 수 있도록 정리했습니다.

- **대상 하드웨어**: Dobot Magician GO (전방향 주행 카 + 초음파/IMU/오도미터, 카메라, RGB LED, 부저, 라인트레이싱)
- **라이브러리**: `dobotkit` — **순수 파이썬**(`websockets`만), DLL 불필요, 크로스플랫폼. (PyPI 미게시 — `pip install -e <로컬 경로>`)
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
- ⚠️ **GO 내장 폐루프 명령은 HANG할 수 있습니다.** `unsafe_rotate`/`unsafe_move_dist`/`unsafe_arc_rad`/`unsafe_arc_cent`/`unsafe_increment_closed_loop`(구명칭 `rotate` 등은 경고를 내는 폐기 별칭)는 이 기체에서 완료 콜백이 오지 않아 타임아웃(~7일)까지 **멈춥니다(HANG)**. 정밀 제어가 필요하면 `PreciseMover`/`WaypointNav`(연속 `move()` + 센서 피드백)를 사용하세요.
- ✅ **회전 방향 규약은 실기 확정되었습니다 (2026-07-03).** `r+` = 좌회전(반시계/CCW) — `PreciseMover.turn_degrees(+90)` 실기에서 반시계 회전, 오차 1.5°. 단 펌웨어 enum 값(`move_direct`의 `direction`, `arc_*`의 `mode`, `set_running_mode`의 `mode`)은 여전히 **실측 필요**합니다.
- 🆕 **확장 API 49종은 hardware-unverified입니다 (2026-07-04).** 진단/카메라 확장/큐 제어/MagicBox/디바이스 메서드(→ 3.9절)의 와이어 시그니처는 공식 소스 3중 교차검증(DobotEDU 파이썬 래퍼 + 공식 CHM + DobotLink 플러그인 프로토콜 테이블)으로 채굴했으나 **실기 실행은 0회**입니다. 검증 절차·순서는 [VERIFICATION_NEEDED_ko.md](../VERIFICATION_NEEDED_ko.md)를 따르세요.

---

## 0. 사전 준비 (필수)

1. **GO 전원 ON**, 무선 동글을 PC에 연결.
2. **DobotLink.exe 실행** (보통 `C:\Users\<user>\AppData\Local\Programs\DobotLink\DobotLink.exe`).
   - 파이썬은 `ws://localhost:9090`으로 DobotLink에 붙고, DobotLink이 COM 포트로 GO에 연결합니다.
3. GO가 붙은 **COM 포트** 확인(기본 가정값 `COM5`).
4. 의존성: `pip install -e <dobotkit 로컬 경로>` (PyPI 미게시; 런타임에 `websockets`만 사용).

---

## 1. 빠른 시작

```python
from dobotkit import MagicianGO, DobotLinkError
from dobotkit.go.client import DobotLinkClient

client = DobotLinkClient(host="localhost", port=9090, timeout=10.0).connect()
go = MagicianGO(client, port_name="COM5")

try:
    go.connect()                       # connect_robot() 후 battery()로 링크 검증
    print("battery:", go.battery())    # 예: {'powerVoltage': 11.7, 'powerPercentage': 0.99}
                                       # (잔량 스케일은 펌웨어별 상이 — 참조 기체는 0~1 분율)
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
| **큐/폐루프 명령** | `unsafe_rotate`, `unsafe_move_dist`, `unsafe_arc_rad`, `unsafe_arc_cent`, `unsafe_increment_closed_loop` (구명칭은 경고 별칭), `unsafe_move_pos` (신규 2026-07-04, 미검증 — 큐드 계열 확정으로 동일 위험 추정) | ⚠️ **이 기체에서 완료 신호가 안 와 HANG**(~7일 타임아웃)될 수 있음 |

> 폐루프 명령들은 `isQueued=True, isWaitForFinish=True` 플래그(코드의 `_WAIT`)로 큐에 넣고 완료 콜백을 대기하므로, 콜백이 오지 않으면 HANG합니다. **정밀 이동이 필요하면 연속 `move()` + 센서 피드백으로 폐루프를 구성**하세요(→ 6절 `PreciseMover`, 7절 `WaypointNav`).
>
> `coord_closed_loop`(`SetCoordClosedLoop`)도 폐루프 계열이지만 `_WAIT` 플래그를 **사용하지 않아** 위 명령들과 거동이 다릅니다(완료 대기/HANG 동작이 아님).

### 2.3 좌표/단위 규약

- **속도**: 정수 값(단위 미정규화). `PreciseMover`는 명령 속도 크기를 `max_speed=30`으로 **상한**, 목표 근처 감속 시 `min_speed=8`로 **하한** 강제합니다(강제 캡이며 권장 절대값이 아님). 부호는 유지됩니다.
- **오도미터(`odometer()`)**: `{x, y, yaw}` — **월드 프레임** 누적 위치. 명목 mm 단위(매트 좌표 cm와 ×10 변환). ⚠️ mm 스케일은 실측 의심(3~4배 과소집계 관측) — 자로 캘리브레이션 전엔 상대 진행량으로 취급.
- **IMU 각도(`imu_angle()`)**: `{yaw, ...}` — **전원 기준 절대각**(`set_odometer`와 무관).
- **방향 규약**: `x+` = 전진, `y+` = 좌측 횡이동(strafe), `r+` = 좌회전(반시계, CCW). ✅ **회전 부호 실기 확정(2026-07-03)**.
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
| `move(x=0, y=0, r=0)` | 속도 벡터 지정(전진/횡이동/회전 동시 가능). `SetMoveSpeed`. **각 성분 크기 ±30 클램프**(NaN/inf → 0: 미정의 속도는 주행 거부), 단위 미확정(8~30 실용) |
| `drive_for(x=0, y=0, r=0, seconds=0.5)` | **데드맨 주행(권장)**: `move` 후 `seconds`(≤5s) 지나면 반드시 정지 — 크래시/Ctrl-C에도 finally가 정지 보장 |
| `move_direct(direction, speed)` | 방향 지정 주행. `SetMoveSpeedDirect(dir=direction, speed=speed)`. `speed` 크기 ±30 클램프. `direction`(파이썬) → `dir`(RPC). `direction=0`을 전진으로 **추정**하나 값 매핑 펌웨어 미확정(실측 필요) |
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

### 3.4 큐/폐루프 주행 (⚠️ HANG 위험 — 2.2 참고, 정식 명칭은 `unsafe_` 접두사)

행(HANG)이 실측된 큐 명령들의 **정식 명칭에는 `unsafe_` 접두사**가 붙습니다(자동완성/LLM이
실수로 집지 못하도록). 구명칭(`rotate` 등)은 `UserWarning`을 내며 위임하는 폐기 예정 별칭입니다.

| 메서드 (정식) | 설명 |
|---|---|
| `unsafe_rotate(r, Vr)` | 각도 `r`만큼 회전(속도 `Vr`) |
| `unsafe_move_dist(x, y, Vx, Vy)` | 거리 지정 이동 |
| `unsafe_arc_rad(velocity, radius, angle, mode)` | 반경 기반 원호. `mode`=정수 방향/모드 플래그(예제는 `mode=0`, 의미 미확정) |
| `unsafe_arc_cent(velocity, x, y, angle, mode)` | 중심점 기반 원호. `mode`=정수 플래그(예제는 `mode=0`, 의미 미확정) |
| `coord_closed_loop(is_enable, angle)` | 좌표 폐루프 (`SetCoordClosedLoop`). ⚠️ 다른 큐 명령과 달리 `_WAIT` 플래그 미전송 — 완료 대기(HANG) 동작이 아니라 `unsafe_` 아님 |
| `unsafe_increment_closed_loop(x, y, angle)` | 증분 폐루프 |

> ⚠️ **HANG 가능 — 실측/디버깅 전용, 반드시 `clearance_ok` 인터록과 함께.** 아래는 인자 순서/이름을 보여주는 호출 예입니다(인터록 통과 시 소량만, 끝에 `emergency_stop`).

```python
ok, info = go.clearance_ok(r=1, threshold=25)
if ok:
    try:
        go.unsafe_rotate(20, 30)             # 회전 20deg, 속도 Vr=30
        # go.unsafe_move_dist(30, 0, 30, 0)   # x=30mm 이동, Vx=30
        # go.unsafe_increment_closed_loop(30, 0, 0)
        # go.unsafe_arc_rad(30, 50, 30, 0)    # velocity, radius, angle, mode
        # go.unsafe_arc_cent(30, 50, 0, 30, 0)  # velocity, x, y, angle, mode
    finally:
        go.emergency_stop()
```

> 이 폐루프 명령군 전체가 이 기체에서 **완료 신호 미수신으로 HANG될 수 있으므로** 실사용은 권장하지 않습니다. 정밀 제어는 6·7절(연속 `move()` + 센서 피드백)을 사용하세요.

### 3.5 센서 (읽기 — 안전, 모터 무동작)

| 메서드 | 반환 | 설명 |
|---|---|---|
| `ultrasonic()` | `{front, back, left, right}` (cm) **또는 `None`** | 4방향 초음파 거리 — **검증·정규화됨**: 40 이상은 40으로 클램프(하드웨어 상한, "40 = 40cm 이상"), 키 누락·비수치·0 이하·NaN 응답은 `None`(**모르면 멈춘다** — 주행 코드는 `None`을 정지 사유로 처리할 것) |
| `ultrasonic_raw()` | 원시 응답 | 무검증 `GetUltrasoundData` (진단용) |
| `odometer()` | `{x, y, yaw}` | 누적 위치(월드프레임, mm). RPC는 `GetSpeedometer`('Speedometer' 철자) |
| `set_odometer(x, y, yaw)` | — | 오도미터 값 강제 세팅(좌표 영점). RPC `SetSpeedometer` |
| `battery()` | `{powerVoltage, powerPercentage}` | 배터리 전압(V)+잔량. **잔량 스케일은 펌웨어별 상이**(참조 기체 실측: 0~1 분율) — 표시할 땐 `pct*100 if pct<=1 else pct` 식으로 방어. **링크 검증용으로 자주 사용** |
| `imu_angle()` | `{yaw, ...}` | IMU 각도(전원 기준 절대) |
| `imu_speed()` | `{ax, ay, az, gx, gy, gz}` | **원시 가속도(g)+자이로** (실측 확정 — RPC 이름과 달리 각속도 yaw dict가 아님) |

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
#   effect : 0 = 소등(OFF), 1~3 = 점등(모드 enum — DobotLab 자체 퀵테스트는 3 전송)
#   r,g,b  : 0~255
#   cycle  : 점멸 주기 — **1 사용** (0이면 희미/무점등, 2026-07-03 실측)
#   counts : 점멸 횟수 — **>=1 사용** (0이면 희미/무점등, 2026-07-03 실측)

go.buzzer(index=5, tone=0, beat=0)   # 내부 RPC: SetBuzzerSound
#   기본값 (5, 0, 0) = DobotLab 자체 비프와 동일 조합 — 깔끔한 '삑' 실측 확정(2026-07-03).
#   다른 조합(예: index=1, tone=5, beat=1)은 덜그럭거리는 버즈 또는 무음 — 전체 범위 의미는 펌웨어 정의.
```

> ✅ **하드웨어 검증(2026-07-03)**: `cycle=0, counts=0`은 effect와 무관하게 LED가 희미하거나 켜지지 않습니다.
> **점등에는 반드시 `cycle=1, counts>=1`** 을 보내세요.

**`LEDChannel`** (`from dobotkit import LEDChannel`): `LED_1=1, LED_2=2, LED_3=3, LED_4=4, LED_ALL=5`. `number` 인자는 `LEDChannel`/int/문자열을 모두 받습니다.

```python
from dobotkit import LEDChannel

go.rgb("LED_ALL", effect=1, r=255, g=0, b=0, cycle=1, counts=1)   # 전체 빨강 점등
go.rgb(LEDChannel.LED_1, 3, 0, 255, 0, 1, 1)                      # LED_1 초록 (enum, DobotLab 스타일 effect=3)
go.rgb(1, 1, 0, 255, 0, 1, 1)                                     # LED_1 초록 (int)
go.rgb("LED_ALL", 0, 0, 0, 0, 0, 0)                              # 전체 소등 (effect=0)
go.buzzer()                                                       # 검증된 기본값 (5, 0, 0) — 깔끔한 삑
```

### 3.7 라인 트레이싱

| 메서드 | 설명 |
|---|---|
| `auto_trace(on)` | 라인 트레이싱 ON/OFF. 내부적으로 `SetTraceLoop` + `SetTraceAuto{isTrace: int, type: 0}` — **isTrace는 int 필수**(2026-07-02 실기 확정: bool을 보내면 펌웨어가 조용히 무시해 켜지지도 꺼지지도 않음). 래퍼가 처리하므로 호출자는 bool을 넘겨도 됨 |
| `trace_speed(speed)` | 트레이싱 속도 (`SetTraceSpeed`). **공식 순찰값 20** |
| `trace_pid(p, i, d)` | 라인 추종 PID 게인 (`SetTracePid`). **공식값 (0.5, 0, 0.5)** — 50 같은 값은 실측상 요동으로 라인 이탈 |
| `trace_angle()` | **CAR 카메라**(`GetCarCameraAngle`)의 라인 각도, `{"angle": int, "count": int}`로 정규화(이상 응답 → `{"angle": 0, "count": 0}`). `count==0`=라인 없음. ARM 카메라가 비활성(405)이어도 영향 없음 |
| `line_error(center)` | `angle - center` 또는 라인 없으면 `None` — 자체 P제어용 교육 프리미티브. `center`는 기체별 실측(참조 기체 ≈245) |

```python
go.trace_speed(20)            # 공식 순찰 속도
go.trace_pid(0.5, 0, 0.5)     # 공식 PID (하드웨어 검증값)
go.auto_trace(True)           # SetTraceLoop(enable=True) → SetTraceAuto(isTrace=1, type=0)
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

### 3.9 확장 API 49종 (2026-07-04 추가 — **hardware-unverified**)

기존에 "미구현/미노출"로 표기됐던 DobotLink RPC 표면이 타입드 메서드로 추가되었습니다.
와이어 시그니처는 공식 소스 3중 교차검증(DobotEDU 래퍼 + CHM + 플러그인 프로토콜 테이블)으로
확정했으나, **아래 메서드 전부 실기 실행 이력이 없습니다(hardware-unverified, 2026-07-04)**.
그룹별 권장 검증 절차와 안전한 검증 순서는 [VERIFICATION_NEEDED_ko.md](../VERIFICATION_NEEDED_ko.md) C절 참조.

> **키워드 인자명 규약**: 확장 메서드의 파이썬 인자명은 **와이어 파라미터명 그대로**입니다
> (camelCase — 예: `lineInfo`, `runModelIndex`, `isEnableCali`, `scopeErr`, `deviceName`;
> Stop-Point는 대문자 `PointX`/`PointY`). snake_case로 키워드 호출하면 `TypeError`가 납니다.

#### 3.9.1 진단·조회 (읽기 전용)

| 메서드 | RPC | 반환 |
|---|---|---|
| `get_alarm_info()` | `GetAlarmInfo` | `{warning: [...]}` |
| `clean_alarm_info()` | `CleanAlarmInfo` | result true (알람 소거) |
| `running_state()` | `GetRunningState` | `{runningState:int}` **추정** — 공식 문서 페이지 뒤엉킴, 방어적 읽기 |
| `stall_protection()` | `GetStallProtection` | `{isHappened:int}` — 모터 스톨 발생 여부 |
| `off_ground()` | `GetOffGround` | `{isHappened:int}` — 들림 감지 |
| `get_move_speed()` | `GetMoveSpeed` | `{x:float, y:float, r:float}` (x/y cm/s 0-100, r deg/s) |
| `get_running_mode()` | `GetRunningMode` | `{runningMode:int}` 추정(0 NORMAL / 1 SAFE) — CHM 필드명 모순 있음, 방어적 읽기 |

#### 3.9.2 트레이스 확장

| 메서드 | RPC | 설명 |
|---|---|---|
| `firmware_trace_angle(**params)` | `GetTraceAngle` | ⚠️ **와이어 존재 미확인** — DobotLink 플러그인 메서드 테이블·공식 JS SDK 어디에도 없음(CHM엔 파일명만 존재). `**params` 패스스루로만 구현. 기존 `trace_angle()`(= `GetCarCameraAngle`, 카메라 라인각)과 **별개 RPC**이며 의미 대조가 필요합니다 |
| `set_trace_line_info(lineInfo)` | `SetTraceLineInfo` | `lineInfo:int` 설정 — 값 의미 미확정 |

#### 3.9.3 절대주행 (⚠️ 모션)

| 메서드 | RPC | 설명 |
|---|---|---|
| `unsafe_move_pos(x, y, s)` | `SetMovePos` | 월드 좌표 (x, y) cm로 이동, 속도 `s`(0-100 cm/s). **큐드 액션 명령 확정**(isQueued/isWaitForFinish 기본 true) → 기존 `unsafe_` 5종과 동일한 **HANG 위험**(2.2절). 공식 DobotEDU는 사전에 오도미터 yaw 기준 `-yaw` 회전으로 방향 정렬 후 호출 |
| `move_speed_time(time, x, y, r, isAck=False)` | `SetMoveSpeedTime` | `time`초 동안 속도 (x, y cm/s, r deg/s)로 주행 — **비큐드 확정**(공식 JS 조그가 사용, 큐 플래그 미전송·`isAck=false`)이라 `unsafe_` 아님. x/y/r 크기 **±30 클램프**, `time`은 **0~5초 클램프**(펌웨어 측 주행이라 스크립트가 죽어도 계속 달림 — `drive_for`와 동일 상한). 데드맨 주행 대체 후보이나 자동 정지 여부는 실측 필요 |
| `set_origin_point(enable)` | `SetOriginPoint` | 원점 사용(1)/미사용(0) — 비큐드. 실효 의미(오도미터 원점?)는 미확정 |

#### 3.9.4 카메라 확장 (Car/Arm)

> 반환은 CHM 예시 기준이며 `count == 0`일 때 배열 키가 없을 수 있습니다 — 3.8절 `car_camera_obj`처럼 **방어적으로** 읽으세요. ARM 캠 계열은 기체에 따라 405 비활성(3.8절과 동일).

| 메서드 | RPC | 반환/인자 |
|---|---|---|
| `car_camera_color()` | `GetCarCameraColor` | `{count:int(≤5), color_obj:[{x,y,w,h,id}]}` |
| `car_camera_tag()` | `GetCarCameraTag` | `{count:int(≤5), aptag_obj:[{x,y,w,h,id,rot:float}]}` |
| `get_car_camera_model()` / `set_car_camera_model(runModelIndex)` | `Get/SetCarCameraRunModel` | `{runModelIndex:int}` / `runModelIndex:int` |
| `get_car_camera_calibration_mode()` / `set_car_camera_calibration_mode(isEnableCali)` | `Get/SetCarCameraCalibrationMode` | `{isEnableCali:int}` 추정 / `isEnableCali:int`(1 진입, 0 종료) |
| `camera_calibration_data(april_list, device_list)` | `GetCameraCalibrationData` | Get이지만 **입력 필수**: 9점 `[[x,y],...]` JSON 문자열 2개(AprilTag 좌표/기계 좌표) → `{data:"max_x_err:0.44,..."}` 문자열. DobotLink이 내부적으로 fit_homography.exe 실행 |
| `arm_camera_color()` | `GetArmCameraColor` | `{count, color_obj:[...]}` |
| `arm_camera_angle()` | `GetArmCameraAngle` | `{angle:int}` |
| `get_arm_camera_model()` / `set_arm_camera_model(runModelIndex)` | `Get/SetArmCameraRunModel` | Car와 동일 |
| `get_arm_camera_calibration_mode()` / `set_arm_camera_calibration_mode(isEnableCali)` | `Get/SetArmCameraCalibrationMode` | Car와 동일 |

#### 3.9.5 큐 제어

| 메서드 | RPC | 설명 |
|---|---|---|
| `clean_cmd_queue()` | `CleanCmdQueue` | 명령 큐 비우기 |
| `cmd_queue_start()` / `cmd_queue_stop()` | `SetCmdQueueStart/Stop` | 큐 실행 시작/정지 |
| `cmd_queue_force_stop()` | `SetCmdQueueForcelyStop` | 강제 정지 — 공식 비상정지 시퀀스의 일부(JS) |
| `queued_cmd_current_index()` | `GetQueuedCmdCurrentIndex` | `{queueCmdCurrentIndex:int}` — 반환 필드는 'Queued'가 아닌 'queue' 철자 주의. CHM 구명칭 `GetCmdQueueCurrentIndex`와 별개로 와이어명은 이쪽이 정식 |
| `cmd_queue_available_space()` | `GetCmdQueueAvailableSpace` | `{space:int}` |

#### 3.9.6 MagicBox / 상태 제어

4.1절의 저수준 `client.call` 예시로만 가능했던 Stop-Point RPC가 타입드 메서드로 승격되었습니다.
`MagicBox.*` 네임스페이스는 Stop-Point 계열뿐이고, 이름과 달리 `GetMagicBoxMode`/`GetMagicBoxNum`/`SetRunningState`는 `MagicianGO.*` 네임스페이스입니다(공식 JS 호출부로 확정).

| 메서드 | RPC (네임스페이스) | 설명 |
|---|---|---|
| `magic_box_mode()` | `GetMagicBoxMode` (MagicianGO) | `{mode:int}` |
| `magic_box_num()` | `GetMagicBoxNum` (MagicianGO) | `{num:int}` 추정 — CHM은 hex device 코드로 표기(모순), 방어적 읽기 |
| `stop_point_state()` | `GetStopPointState` (**MagicBox**) | `{result:bool}` — 도착·정지 시 true |
| `set_stop_point_param(scopeErr, stopErr)` | `SetStopPointParam` (**MagicBox**) | 진입범위(기본 40)/정지정밀도(기본 2) |
| `set_stop_point_server(PointX, PointY)` | `SetStopPointServer` (**MagicBox**) | 정지점 좌표 — 파이썬 인자명도 와이어 그대로 대문자 `PointX`/`PointY`. ⚠️ **단위(cm/mm) 문서 미확정** — 작은 값으로 검증 |
| `set_running_state(**params)` | `SetRunningState` (MagicianGO) | **미확정 패스스루** — `runningState:int` 추정이나 공식 호출부·문서 부재. 와이어 이름을 직접 넘길 것 |

#### 3.9.7 출력 / 디바이스

| 메서드 | RPC | 설명 |
|---|---|---|
| `set_light_prompt(index)` | `SetLightPrompt` | 상태 표시등: 0 없음 / 1 USB / 2 저전량 / 3 핸들 / 4 스크립트 |
| `product_name()` | `GetProductName` | `{productName:string}` — 공식 JS는 `"MagicianGo"`일 때 유효 디바이스로 판정 |
| `device_fw_software_version()` | `GetDeviceFwSoftwareVersion` | `{majorVersionNum, secondVersionNum, revisionVersionNum, previousVersionNum}` — 공식 JS가 `V{maj}.{sec}.{rev}.{prev}`로 조립(확정). CHM 예시 필드명은 구식 — 방어적 읽기 |
| `device_fw_hardware_version()` | `GetDeviceFwHardwareVersion` | 동일 필드군 추정 — 방어적 읽기 |
| `device_id()` | `GetDeviceID` | `{deviceID: [int, ...]}` |
| `get_device_name()` / `set_device_name(deviceName)` | `Get/SetDeviceName` | `{deviceName:string}` / 이름 설정(예: `"MgoNO.1"`) |
| `get_device_sn()` / `set_device_sn(deviceSN)` | `Get/SetDeviceSN` | `{deviceSN:string}` / ⚠️ SN 덮어쓰기는 원복 불가 위험 — 실사용 비권장 |
| `device_time()` | `GetDeviceTime` | `{gSystick:int, passtime:"hh:mm:ss.z"}` |
| `device_reboot()` | `DeviceReboot` | ⚠️ **호출 즉시 재부팅 — 이후 연결 끊김.** 재연결 필요. 반환값 정규화 없음(Any) |
| `heartbeat()` | `HeartBeat` | keepalive — 공식 JS는 2000ms 타임아웃으로 호출, 3회 연속 실패 시 연결끊김 처리 |

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

아래 RPC는 `MagicianGO.*`가 아닌 `MagicBox.*` 네임스페이스입니다. 2026-07-04부터 `MagicianGO` 래퍼에도 타입드 메서드(`stop_point_state`/`set_stop_point_param`/`set_stop_point_server`, hardware-unverified — 3.9.6절)가 있으며, 아래는 저수준 `client.call`로 직접 호출하는 경우의 와이어 형태입니다.

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

with MagicianGO.open(port_name="COM5") as go:   # 연결 + battery() 검증, 종료 시 자동 안전정지
    go.trace_speed(20)               # 공식 순찰 속도
    go.trace_pid(0.5, 0, 0.5)        # 공식 PID (50 같은 값은 요동으로 이탈 — 실측)
    go.auto_trace(True)              # 추종 시작

    start = time.monotonic()
    while time.monotonic() - start < 20:
        u = go.ultrasonic()
        # None = 판독 이상(모르면 멈춘다), 15cm 미만 = 장애물 → 즉시 정지
        if u is None or min(u.values()) < 15:
            go.auto_trace(False)
            go.emergency_stop()
            break
        time.sleep(0.1)
    go.auto_trace(False)
# with 종료가 비상정지→트레이스OFF→큐 강제정지(best-effort)→비상정지→소켓 종료까지 보장
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
3. **연속 명령만 신뢰**: 내장 폐루프(`unsafe_move_dist`/`unsafe_rotate`/`unsafe_arc_*`/`unsafe_increment_closed_loop`)는 HANG 가능 → 연속 `move()` + 피드백(`PreciseMover`/`WaypointNav`) 사용.
4. **항상 정지로 종료**: 모든 제어를 `try/finally` 안에서 `go.emergency_stop()` + `client.close()`.
5. **속도 상한 고정**: `max_speed=30` 이하, 짧은 거리/각도부터 검증.
6. **모든 루프에 타임아웃**: 절대 무한 대기 금지(`PreciseMover`/`WaypointNav`는 `timeout_s` 내장).
7. **회전 부호는 확정, 조향 부호는 실측 확인**: `r+`=CCW(좌회전)는 **실기 확정(2026-07-03)** 입니다. 아직 미확정인 것은 `line_error` 기반 P제어의 **조향 부호**(`move(x=v, r=-kp*err)`의 `-`가 기체별로 맞는지) — 라인 위에서 부호를 관찰·확인한 뒤 사용하세요.
8. **AI 에이전트라면**: 동작 명령 전 `ultrasonic()`/`odometer()`로 상태를 먼저 읽고, 작은 펄스로 검증 후 확장하세요.

---

## 10. 빠른 트러블슈팅

| 증상 | 원인/해결 |
|---|---|
| `cannot connect to DobotLink at ws://localhost:9090` (`DobotConnectionError`) | DobotLink.exe 미실행 → 실행 후 재시도 |
| `connect()`/`connect_robot()`은 OK인데 `battery()` 타임아웃 | GO 전원 OFF 또는 무선 동글 분리 → 전원/링크 확인 |
| `unsafe_move_dist`/`unsafe_rotate`가 영원히 멈춤(HANG) | 내장 폐루프 미지원 → 연속 `move()` + 피드백(6·7절) 사용 |
| 자율주행이 목표에서 빗나감 | `set_start` 시작 좌표/헤딩 보정 우선. 오도미터 드리프트는 `go_to` 재측정으로 보정 |
| ARM 카메라 405 에러 | 해당 기체 ARM 카메라 비활성 → `car_camera_obj()` 사용 |
| 라인 P제어가 반대로 꺾음 | `line_error` 조향 부호가 기체별 상이(미검증) — `r+`=CCW 자체는 실기 확정(2026-07-03)이므로, 라인 오른쪽으로 틀었을 때 `angle > center`인지 관찰해 `-kp` 부호를 결정 |
