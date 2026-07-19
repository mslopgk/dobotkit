# Dobot Magician GO — `dobotkit` 카(Car) API 레퍼런스

> 메카넘 휠 기반 전방향 주행 로봇 카(Magician GO)를 **순수 파이썬**으로 제어하기 위한 실전 API 레퍼런스.
> 사람과 AI 에이전트가 코드 예제를 그대로 복사해 쓸 수 있도록 정리했습니다.

- **대상 하드웨어**: Dobot Magician GO (전방향 주행 카 + 초음파/IMU/오도미터, RGB LED, 부저, MagicBox 주변장치 허브)
- **라이브러리**: `dobotkit` — **순수 파이썬**(`websockets`만), DLL 불필요, 크로스플랫폼. (PyPI 미게시 — `pip install -e <로컬 경로>`)
- **임포트**: `from dobotkit import MagicianGO` + `from dobotkit.link import DobotLinkClient` (또는 `from dobotkit.go import MagicianGO, PreciseMover, NavigationAborted, DobotLinkClient`).
- **연결 구조**:

```
Python  --(WebSocket JSON-RPC)-->  DobotLink.exe  --(COM 포트 / 무선동글)-->  Magician GO
```

GO는 직접 구동하지 않습니다. 파이썬은 **DobotLink** 데스크톱 서비스에 WebSocket JSON-RPC 2.0으로 붙고, DobotLink이 COM 포트/무선 동글로 카에 명령을 중계합니다. `dobotkit`는 Dobot의 DobotEDU/DobotRPC 패키지에 의존하지 않고 `websockets`만 사용합니다.

---

## 정직성 고지 (반드시 읽으세요)

`dobotkit`는 다음을 **정직하게** 공개합니다.

- **트리밍된 공개 표면(2026-07-16 정리).** 이 문서에 나온 것이 `MagicianGO`가 노출하는 전부입니다 — 연결/연속주행/안전/출력/네이티브 센서/진단·알람 + MagicBox 주변장치(`go.sensors`/`go.io`) + `PreciseMover`. **여기 없는 메서드·클래스는 존재하지 않습니다.**
- **순수 파이썬.** `websockets`만 사용하며 DLL/네이티브 바이너리에 의존하지 않습니다. `pip`로 설치되고 크로스플랫폼입니다(단, DobotLink.exe는 Windows 전용 서비스).
- ⚠️ **펌웨어 내장 폐루프(큐드) 주행 명령과 라인트레이싱/카메라 API는 완전히 제거되었습니다.** 이 기체에서 큐드 폐루프 명령은 완료 콜백이 오지 않아 타임아웃(~7일)까지 **HANG**했기 때문입니다. 정밀 이동은 연속 `move()` + 센서 피드백을 직접 구성하는 **`PreciseMover`**(5절)만 사용하세요. 절대 매트좌표 웨이포인트 내비게이션(`WaypointNav`)도 함께 제거되었습니다.
- ✅ **회전 방향 규약은 실기 확정되었습니다 (2026-07-03).** `r+` = 좌회전(반시계/CCW) — `PreciseMover.turn_degrees(+90)` 실기에서 반시계 회전, 오차 1.5°.
- 🆕 **MagicBox 주변장치 지원이 신규 추가되었습니다 (하드웨어 검증 2026-07-16).** `go.sensors` / `go.io`로 ADC/DI/DO/PWM(EIO 핀) 및 color/infrared/거리/온습도/조도/RGB(Grove 커넥터) 센서를 읽고 씁니다. 3.7절 참고.

---

## 0. 사전 준비 (필수)

1. **GO 전원 ON**, 무선 동글을 PC에 연결.
2. **DobotLink.exe 실행** (보통 `C:\Users\<user>\AppData\Local\Programs\DobotLink\DobotLink.exe`).
   - 파이썬은 `ws://localhost:9090`으로 DobotLink에 붙고, DobotLink이 COM 포트로 GO에 연결합니다.
3. GO가 붙은 **COM 포트** 확인(기본 가정값 `COM5`).
4. 의존성: `pip install -e <dobotkit 로컬 경로>` (PyPI 미게시; 런타임에 `websockets`만 사용).

> 📄 첫 실행 진단 스크립트: [`examples/go_discover.py`](../../examples/go_discover.py) — **모터를 절대 움직이지 않고** 연결/배터리/초음파/MagicBox/오도미터·IMU를 순서대로 점검합니다. `python examples/go_discover.py [COM포트]`.

---

## 1. 빠른 시작

```python
from dobotkit import MagicianGO, DobotLinkError
from dobotkit.link import DobotLinkClient

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

> **권장 진입점**은 `MagicianGO.open()` 클래스메서드입니다 — DobotLink 연결 + `MagicianGO` 래핑 + `connect()` 검증을 한 번에 하고, `with`로 쓰면 종료 시 teardown(아래 3.1절)까지 자동입니다:
>
> ```python
> from dobotkit import MagicianGO
>
> with MagicianGO.open(port_name="COM5") as go:
>     go.forward(15)
>     ...
> # <- emergency_stop + 확인용 stop + 소켓 종료까지 보장 (에러가 나도)
> ```

`DobotLinkClient`/`MagicianGO`/`DobotLinkError`는 모두 `dobotkit`에서 직접 임포트할 수 있습니다(클라이언트는 `dobotkit.link`에 있습니다). `import dobotkit`만으로는 `websockets`가 로드되지 않으며, 첫 연결 시점에 지연 임포트됩니다.

---

## 2. 아키텍처 / 동작 모델

### 2.1 두 가지 호출 방식 (`DobotLinkClient`)

| 메서드 | 의미 |
|---|---|
| `client.call(method, **params)` | JSON-RPC 요청 후 **응답 대기**(블로킹, timeout 적용). error 응답 시 `DobotLinkError`, 무응답 시 `DobotTimeoutError` |
| `client.notify(method, **params)` | 응답 없이 **전송만**(블로킹/타임아웃 없음) — 비상정지 전용 |

`MagicianGO`의 메서드는 (`search()` 제외) 내부 `_call` 헬퍼로 `MagicianGO.<함수>`를 `portName`과 함께 호출합니다. `search()`는 포트 선택 전 단계이므로 `portName` 없이 `MagicianGO.SearchDobot`을 호출합니다. `emergency_stop()`만 `client.notify`를 사용해 응답을 기다리지 않습니다. `go.sensors`/`go.io`(MagicBox 주변장치, 3.7절)는 같은 연결 위에서 `MagicBox.<함수>`를 호출하는 별도의 얇은 래퍼입니다.

### 2.2 주행 명령 모델 (연속 속도 전용)

GO의 주행은 **연속 속도 제어 한 가지뿐**입니다: `move`(및 `forward`/`backward`/`strafe`/`spin`, 그리고 시간 제한이 있는 `drive_for`)로 속도 벡터를 주면 `stop()`/`emergency_stop()` 전까지 계속 달립니다. 이것이 이 기체에서 검증된 유일한 신뢰 가능 경로입니다.

> ⚠️ 펌웨어가 원래 갖고 있던 **큐드 폐루프 명령**(각도만큼 회전, 거리만큼 이동, 원호 이동 등)은 이 기체에서 완료 콜백이 오지 않아 **HANG**하는 것으로 실측되어 `dobotkit`에서 완전히 제거되었습니다. **정밀 이동(정확한 거리/각도)이 필요하면 연속 `move()` + 오도미터/IMU 피드백으로 직접 폐루프를 구성하는 5절 `PreciseMover`를 사용하세요.**

### 2.3 좌표/단위 규약

- **속도**: 정수 값(단위 미정규화, 8~30이 실용 범위). 모든 속도 성분은 `move`/`forward`/`backward`/`strafe`/`spin` 내부에서 크기 ±30(`SPEED_CAP`)으로 클램프됩니다. NaN/inf 같은 비유한값은 **0**으로 대체됩니다(정의되지 않은 속도는 주행을 거부 — naive `max(min(...))` 클램프는 NaN을 최고속도로 흘려보내기 때문).
- **오도미터(`odometer()`)**: `{x, y, yaw}` — **월드 프레임** 누적 위치. 명목 mm 단위. ⚠️ mm 스케일은 실측 의심(2026-07-03 측정: 오도미터 누적 ~110이 실제 370~470mm에 대응 — 3~4배 과소집계) — 자로 캘리브레이션 전엔 상대 진행량으로만 취급.
- **IMU 각도(`imu_angle()`)**: `{yaw, ...}` — **전원 기준 절대각**(`set_odometer`와 무관, 리셋 안 됨).
- **방향 규약**: `x+` = 전진, `y+` = 좌측 횡이동(strafe), `r+` = 좌회전(반시계, CCW). ✅ **회전 부호 실기 확정(2026-07-03)**.
- **초음파(`ultrasonic()`)**: `{front, back, left, right}` — cm 단위, 40cm에서 클램프.
- **yaw 출처**: 제자리 회전량 측정(`PreciseMover.turn_degrees`)은 상대 변화가 안정적인 `imu_angle()['yaw']`를 사용합니다. `odometer()['yaw']`는 `set_odometer`로 영점이 잡히는 별개 기준이므로 **두 yaw를 혼용하지 마세요**(기준이 달라 절대값이 어긋날 수 있음).

---

## 3. `MagicianGO` API 레퍼런스

`from dobotkit import MagicianGO` → `MagicianGO(client, port_name="COM5")`. 인스턴스는 `sensors`(`GoSensorGroup`)와 `io`(`GoIOGroup`) 속성을 생성자에서 바로 갖습니다(3.7절).

### 3.1 연결 (lifecycle)

| 메서드 | 설명 |
|---|---|
| `MagicianGO.open(port_name="COM5", host="localhost", port=9090, timeout=10.0)` (classmethod) | **권장 진입점**: `DobotLinkClient(host, port, timeout).connect()` + `MagicianGO(client, port_name)` + `connect()`(검증 포함)를 한 번에. 반환 인스턴스가 클라이언트를 **소유**하므로 `with`로 쓰면 종료 시 소켓까지 닫힘. 검증 실패 시 소켓을 닫고 예외 재발생 |
| `search()` | 연결 가능한 GO 탐색(`MagicianGO.SearchDobot`). 다른 메서드와 달리 `portName`을 보내지 않음. DobotLink 응답을 그대로 반환(구조는 펌웨어 정의, 정규화 없음) |
| `connect_robot()` | DobotLink이 `port_name`으로 GO에 연결(`ConnectDobot`). **명령 전 필수**. 성공 시 `connected=True`. ⚠️ 핸드셰이크가 **거짓 성공**을 보고할 수 있어 읽기로 검증 권장(`connect()`가 대신 해 줌) |
| `disconnect_robot()` | GO 연결 해제(`DisconnectDobot`). `connected=False` |
| `connect(verify=True)` | `connect_robot()` 후 (기본) `battery()`로 링크 검증(응답을 반환). 검증 실패 시 `connected=False`로 되돌리고 원래 예외를 다시 발생시킴. `verify=False`면 `connect_robot()` 결과만 반환 |

**컨텍스트 매니저 종료(`with ... as go:` 블록 끝, 또는 예외 발생 시)** — 새 teardown 순서(라인트레이스/큐 강제정지는 더 이상 없음):

1. `emergency_stop()` **먼저** — 무대기 notify라 링크가 죽어 있어도 즉시 발사됨.
2. `stop()` — 확인용 blocking `SetMoveSpeed(0)`. 실패하면 `emergency_stop()`을 재발사.
3. `connected = False`.
4. `MagicianGO.open()`으로 생성된 인스턴스라면(소켓을 소유) `client.close()`까지 수행.

모든 teardown 단계는 예외를 삼킵니다(원래 예외를 절대 가리지 않음).

```python
go.connect()                  # connect_robot() + battery() 검증 (권장)
ports = go.search()           # 구조 미확정 — 실측 확인
```

### 3.2 연속 주행 (✅ 유일한 주행 경로)

| 메서드 | 설명 |
|---|---|
| `move(x=0, y=0, r=0)` | 속도 벡터 지정(전진/횡이동/회전 동시 가능). `SetMoveSpeed`. **각 성분 크기 ±30 클램프**(NaN/inf → 0), 단위 미확정(8~30 실용). **정지 명령 전까지 계속 이동** — 시간 제한 펄스가 필요하면 `drive_for` 우선 |
| `forward(speed)` | 전진 (= `move(x=speed)`) |
| `backward(speed)` | 후진 (= `move(x=-speed)`) |
| `strafe(speed)` | 좌(+)/우(-) 횡이동 (= `move(y=speed)`) |
| `spin(speed)` | 제자리 회전 (= `move(r=speed)`, `+`=CCW) |
| `stop()` | 정지 (= `move(0, 0, 0)`, 응답 대기) |
| `drive_for(x=0, y=0, r=0, seconds=0.5)` | **데드맨 주행(권장)**: `move` 후 `seconds`(0~5s 클램프) 지나면 `finally`에서 반드시 정지 — 크래시/Ctrl-C에도 안전(`emergency_stop` 후 확인용 `stop`, 실패 시 `emergency_stop` 재발사) |
| `emergency_stop()` | **즉시 정지** — `notify`로 `SetMoveSpeed(x=0, y=0, r=0)` 전송, 블로킹/타임아웃 없음. `finally`/인터럽트 경로에서 안전 |

```python
go.move(x=20, y=0, r=0)       # 전진 20
go.strafe(15)                 # 좌측 횡이동
go.spin(-10)                  # 우회전(시계방향)
go.drive_for(x=20, seconds=1.0)   # 1초간 전진 후 확실히 정지
go.emergency_stop()
```

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

`clearance_ok(x=0, y=0, r=0, threshold=20)`는 `ultrasonic()`을 읽어 의도한 방향의 클리어런스를 검증합니다: `x>0`→front, `x<0`→back, `y!=0`→좌우 최소, `r!=0`→사방 최소(제자리 회전은 원을 그림). `ultrasonic()`이 `None`(판독 이상)이면 그 자체가 막힘 사유입니다(**모르면 멈춘다**).

### 3.4 출력 (LED / 부저)

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

### 3.5 네이티브 센서 (읽기 전용, 모터 무동작)

| 메서드 | 반환 | 설명 |
|---|---|---|
| `ultrasonic()` | `{front, back, left, right}` (cm) **또는 `None`** | 4방향 초음파 거리 — **검증·정규화됨**: 40 이상은 40으로 클램프(하드웨어 상한, "40 = 40cm 이상"), 키 누락·비수치·0 이하·NaN 응답은 `None`(**모르면 멈춘다** — 주행 코드는 `None`을 정지 사유로 처리할 것) |
| `ultrasonic_raw()` | 원시 응답 | 무검증 `GetUltrasoundData` (진단용) |
| `odometer()` | `{x, y, yaw}` | 누적 위치(월드프레임, mm). RPC는 `GetSpeedometer`('Speedometer' 철자). ⚠️ mm 스케일 실측 의심(2.3절) |
| `set_odometer(x, y, yaw)` | — | 오도미터 값 강제 세팅(좌표 영점). RPC `SetSpeedometer` |
| `battery()` | `{powerVoltage, powerPercentage}` | 배터리 전압(V)+잔량. **잔량 스케일은 펌웨어별 상이**(참조 기체 실측: 0~1 분율) — 표시할 땐 `pct*100 if pct<=1 else pct` 식으로 방어. **링크 검증용으로 자주 사용** |
| `imu_angle()` | `{yaw, ...}` | IMU 각도(전원 기준 절대, `set_odometer`와 무관) |

```python
go.set_odometer(0, 0, 0)      # 현재 위치를 좌표 원점(0,0,yaw=0)으로 영점화
u = go.ultrasonic()           # {'front':.., 'back':.., 'left':.., 'right':..}
odo = go.odometer()           # {'x':.., 'y':.., 'yaw':..}  (mm, deg)
bat = go.battery()            # 링크 검증
```

### 3.6 진단 · 알람 · MagicBox 상태

| 메서드 | RPC | 반환/설명 |
|---|---|---|
| `get_alarm_info()` | `GetAlarmInfo` | 활성 알람/경고 목록. 예상 형태 `{"warning": [...]}` — 방어적으로 읽으세요 |
| `clean_alarm_info()` | `CleanAlarmInfo` | 활성 알람 소거 |
| `stall_protection()` | `GetStallProtection` | `{"isHappened": int}` — 모터 스톨 발생 여부 |
| `off_ground()` | `GetOffGround` | `{"isHappened": int}` — 바퀴 들림 감지 |
| `magic_box_mode()` | `GetMagicBoxMode` | `{"mode": int}`. ⚠️ 이름과 달리 **`MagicianGO.*` 네임스페이스**(MagicBox 자체 RPC 아님) |
| `magic_box_num()` | `GetMagicBoxNum` | 부착된 MagicBox 개수/식별자 — 형태 미확정, 방어적으로 읽으세요. ⚠️ 이 메서드도 **`MagicianGO.*` 네임스페이스** |

> `magic_box_mode()`/`magic_box_num()`은 이름 때문에 헷갈리기 쉽지만 실제로는 `MagicianGO.*` RPC입니다. **실제 MagicBox 센서/IO 읽기는 아래 3.7절의 `go.sensors`/`go.io`가 별도로 `MagicBox.*` 네임스페이스를 호출**합니다.

### 3.7 MagicBox 주변장치 — `go.sensors` / `go.io` (🆕 신규, 하드웨어 검증 2026-07-16)

GO는 팔(Magician Lite)과 동일한 **MagicBox** 주변장치 허브를 장착할 수 있습니다. 그 센서/IO 읽기·쓰기는 `MagicianGO.*`가 아니라 DobotLink의 **`MagicBox.*`** JSON-RPC 네임스페이스로 나갑니다. 그러나 **연결은 하나뿐**입니다 — `MagicianGO`로 (`connect()`/`connect_robot()`/`open()`) 한 번 연결하면 `go.sensors`/`go.io`가 같은 연결 위에서 `MagicBox.*` 호출을 실어 나릅니다. **별도의 MagicBox 연결 단계는 없습니다** — 오히려 `MagicBox.ConnectDobot`을 직접 호출하면 GO 차체 연결이 끊어지는 것으로 실기 확인되었으므로(2026-07-16), `dobotkit`는 이를 절대 호출하지 않습니다.

```python
from dobotkit import MagicianGO

go = MagicianGO(client, port_name="COM5")
go.connect()                 # MagicianGO 연결 한 번이면 충분
value = go.sensors.adc(22)   # go.sensors / go.io가 같은 연결 위에서 MagicBox.* 호출
```

**두 가지 주소 체계 (중요, 혼동 주의)** — 공식 DobotLab apiBook 기준:

| 체계 | 메서드 | 인자 |
|---|---|---|
| **EIO 핀 (1..26)** | `go.sensors.adc(eio)`, `go.sensors.di(eio)`, `go.io.set_do(eio, level)`, `go.io.get_di(eio)`, `go.io.get_adc(eio)`, `go.io.set_pwm(eio, frequency, duty)`, `go.io.set_multiplexing(eio, multiplex)` | 원시 EIO 핀 번호 |
| **Grove 커넥터 (1..6)** | `go.sensors.color(port)`, `go.sensors.infrared(port)`, `go.sensors.distance(port)`, `go.sensors.temp(port)`, `go.sensors.light(port)`, `go.sensors.rgb(port, value)` | 라벨이 붙은 Grove 커넥터 번호 |

같은 물리 커넥터라도 두 번호가 다릅니다 — **✅ 하드웨어 검증(2026-07-16)**: 교구 세트의 가변저항이 **Grove 커넥터 4번**에 꽂혀 있지만, ADC로 읽을 때는 **EIO 핀 22번**을 지정해야 합니다:

```python
value = go.sensors.adc(22)   # Grove 4번 슬롯의 가변저항 -> EIO 22번 핀
print(value)                 # ~426 (범위 0..4095), 노브를 돌리면 값이 변함 (실기 검증)
```

내부적으로 `adc(eio)`는 `SetIOMultiplexing(port=eio, multiplex=4)`(멀티플렉스 `4` = ADC 모드, `GPIOType.ADC`)로 핀을 ADC로 세팅한 뒤 `GetIOADC(port=eio)`를 읽습니다.

**`GoSensorGroup` (`go.sensors`)** — 전부 *guarded*(아래 참조):

| 메서드 | 반환 | 설명 |
|---|---|---|
| `adc(eio)` | `int` 또는 `None` | EIO 핀을 ADC 모드로 설정 후 아날로그 값 읽기 |
| `di(eio)` | `int`(0/1) 또는 `None` | EIO 핀의 디지털 입력 레벨 |
| `color(port)` | `{"red", "green", "blue"}` 또는 `None` | Grove 컬러 센서 활성화 후 읽기 |
| `infrared(port)` | `{"status": 0 또는 1}` 또는 `None` | Grove 적외선(광전) 센서 — 1=물체 감지 |
| `distance(port)` | 원시 응답 또는 `None` | Grove Seeed 거리 센서 |
| `temp(port)` | 원시 응답 또는 `None` | Grove Seeed 온습도 센서 |
| `light(port)` | 원시 응답 또는 `None` | Grove Seeed 조도 센서 |
| `rgb(port, value)` | 원시 응답 또는 `None` | Grove Seeed RGB LED 설정 |

**`GoIOGroup` (`go.io`)** — 전부 EIO 핀(1..26) 주소:

| 메서드 | 설명 | guarded? |
|---|---|---|
| `set_do(eio, level)` | 디지털 출력 레벨(0/1) 설정 | 아니오 — 실패 시 그대로 예외 |
| `get_di(eio)` | 디지털 입력 레벨(0/1) 읽기 | 예 |
| `get_adc(eio)` | ADC 값 읽기 | 예 |
| `set_pwm(eio, frequency, duty)` | PWM 설정(주파수 Hz, 듀티 % 0..100) | 아니오 |
| `set_multiplexing(eio, multiplex)` | EIO 핀에 멀티플렉스 기능 할당(`dobotkit.enums.GPIOType` 참고) | 아니오 |

> **guarded란**: `go.sensors`의 모든 메서드와 `go.io.get_di`/`go.io.get_adc`는 MagicBox나 해당 센서가 없을 때 나는 `DobotTimeoutError`/`DobotProtocolError`를 내부에서 잡아 **`None` + `RuntimeWarning`**으로 낮춥니다(예외를 던지지 않음) — 교구/교육 코드가 센서 하나 빠졌다고 죽지 않게 하기 위함입니다. 경고 메시지(이중언어): `"주변장치 응답이 없습니다 — 매직박스/센서 연결을 확인하세요 (no peripheral response; check the MagicBox and its device)"`. **진짜 연결 오류**(DobotLink 다운, GO 미연결 등)는 여전히 그대로 예외를 던집니다. `go.io`의 **쓰기** 메서드(`set_do`/`set_pwm`/`set_multiplexing`)는 guard되지 **않으므로** 실패 시 바로 예외가 올라옵니다.

```python
import warnings

with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    color = go.sensors.color(port=1)   # 센서가 없으면 color is None
    if color is None:
        print("컬러 센서 응답 없음:", caught[-1].message)

go.io.set_do(5, 1)            # EIO 5번 핀 디지털 출력 High
di = go.io.get_di(6)          # EIO 6번 핀 입력 읽기 (guarded)
go.io.set_pwm(7, frequency=1000, duty=50)   # EIO 7번 핀 PWM
```

`GoSensorGroup`/`GoIOGroup`은 보통 `go.sensors`/`go.io`로 충분하지만, 타입 힌트 등을 위해 직접 임포트하려면 `from dobotkit.go.groups import GoSensorGroup, GoIOGroup`.

> 📄 실행 가능한 전체 예제: [`examples/go_magicbox_sensor.py`](../../examples/go_magicbox_sensor.py) — EIO 핀(기본 22, 교구 세트 가변저항)을 10초간 반복 읽어 막대그래프로 출력, 읽기 전용(모터 무동작). `python examples/go_magicbox_sensor.py [COM포트] [EIO핀]`.

---

## 4. `DobotLinkClient` API

저수준 JSON-RPC 클라이언트. `from dobotkit.link import DobotLinkClient`.

```python
from dobotkit.link import DobotLinkClient

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

> ⚠️ `method`에는 **`dobotlink.` 접두어만 자동으로 붙습니다**(`dobotlink.`로 시작하면 그대로 둠). **`MagicianGO.`/`MagicBox.` 네임스페이스는 자동 보정되지 않으므로** 저수준 `call`/`notify`를 직접 쓸 때는 호출자가 직접 포함해야 합니다 — 예: `client.call("MagicianGO.GetBatteryVoltage", portName="COM5")`, `client.call("MagicBox.GetIOADC", portName="COM5", port=22)`. (`MagicianGO` 래퍼의 고수준 메서드와 `go.sensors`/`go.io`는 각각 `MagicianGO.`/`MagicBox.` 접두어를 내부에서 붙여 줍니다.)

---

## 5. 정밀 이동 — 연속 move() + 센서 폐루프 (`PreciseMover`)

⚠️ **왜 필요한가**: 이 기체의 펌웨어 내장 폐루프 명령(각도만큼 회전/거리만큼 이동/원호 이동 등)은 완료 콜백이 오지 않아 **HANG**하는 것으로 실측되어 `dobotkit`에서 완전히 제거되었습니다. **정밀 이동(정확한 거리/각도)이 필요하면 이 절의 `PreciseMover`가 유일한 경로입니다** — 연속 속도 제어(`move`)에 오도미터/IMU 피드백을 얹어 직접 폐루프를 만들고, 목표에 도달하는 순간 정지합니다.

`from dobotkit.go.navigation import PreciseMover` (또는 `from dobotkit.go import PreciseMover, NavigationAborted`).

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

# 실패를 예외로 승격하고 싶으면 raise_on_abort=True
from dobotkit.go.navigation import NavigationAborted
try:
    mover.goto_distance(300, raise_on_abort=True)
except NavigationAborted as exc:
    print("이동 실패:", exc, exc.result)   # .result 에 전체 결과 dict 보존
```

| 메서드 | 설명 |
|---|---|
| `PreciseMover(go, max_speed=30, min_speed=8)` | 연속 `move` 위의 오도미터/IMU 피드백 폐루프. `go`는 `MagicianGO`(또는 동일한 인터페이스를 가진 객체) |
| `goto_distance(distance_mm, speed=25, axis="x", threshold=20, timeout_s=8.0, raise_on_abort=False) -> dict` | `axis="x"`(전후, `+`전진)/`"y"`(횡, `+`좌). 부호가 방향. 오도미터 변위 크기(`hypot(dx,dy)`)로 측정 |
| `turn_degrees(deg, speed=25, threshold=20, timeout_s=8.0, raise_on_abort=False) -> dict` | 제자리 회전(`+`=CCW). IMU yaw 변화량으로 측정 |

`NavigationAborted`(`from dobotkit.go.navigation import NavigationAborted`)는 `raise_on_abort=True`일 때만 발생하며, `DobotError`를 상속하고(`except DobotError`로도 잡힘) 실패한 결과 dict 전체를 `.result`에 보존합니다.

> `clearance_ok`로 진행 방향이 막혀 `aborted=True`가 되면 반환 dict에 `reason` 키(예: `"clearance blocked: front=12<20"`)가 추가됩니다. `aborted`(막힘)와 `timed_out`(타임아웃)은 안전 설계상 **정상 흐름**이며 예외가 아니라 반환 dict로 구분됩니다(`raise_on_abort=True`가 아닌 한). 항상 결과를 점검하세요.

**핵심 안전 설계** (그대로 따를 것):

- 매 제어 루프에 **절대 타임아웃(`time.monotonic`, `timeout_s`)** — 목표 미도달이어도 영원히 돌지 않음.
- 이동 전 **`clearance_ok()`로 진행 방향 확인** — 막히면 그 동작 즉시 중단(`aborted`), 이동 중에도 0.25초마다 재확인.
- **스톨 가드**: 속도를 명령했는데 오도미터/IMU 진행이 1초 이상 멈추면(벽에 눌림 등) 충돌로 간주하고 즉시 중단.
- 모든 동작은 **`try/finally` 안에서 `emergency_stop()`(무대기) → 확인용 `stop()`** 으로 끝남(내부 `_settle_stop`).
- 속도는 보수적으로 캡(`max_speed=30`, 목표 근처 `min_speed=8`로 비례 감속).

---

## 6. 예외 처리

`from dobotkit import ...`로 전체 예외 계층을 임포트할 수 있습니다(모두 `DobotError` 하위).

| 예외 | 발생 상황 |
|---|---|
| `DobotError` | 모든 dobotkit 오류의 기반 |
| `DobotConnectionError` | DobotLink WebSocket 연결 실패(주로 DobotLink.exe 미실행) |
| `DobotLinkError` | RPC error 응답, 또는 미연결 상태에서 호출 |
| `DobotTimeoutError` | 응답 무수신 타임아웃(GO 전원/무선 링크 단절 가능). `go.sensors`/`go.io`의 guarded 읽기는 이를 내부에서 잡아 `None`+`RuntimeWarning`으로 낮춤 |
| `DobotProtocolError` | 잘못된 프레임/응답. `go.sensors`/`go.io`의 guarded 읽기는 이것도 `None`+`RuntimeWarning`으로 낮춤 |

```python
from dobotkit import DobotConnectionError, DobotLinkError, DobotTimeoutError

try:
    client = DobotLinkClient().connect()
except DobotConnectionError:
    print("DobotLink.exe 미실행 — 실행 후 재시도")
```

---

## 7. 안전 수칙 (사람·AI 공통, 매우 중요)

> 과거 개루프 테스트가 벽으로 돌진해 전원이 차단된 사례가 있습니다. 반드시 지키세요.

1. **링크 검증**: `go.connect()`(= `connect_robot()` + `battery()`)로 실제 응답 확인. 실패 시 즉시 중단.
2. **이동 전 클리어런스**: `clearance_ok()`로 진행 방향 거리 확인(≥15~20cm).
3. **연속 명령만 존재합니다**: 정밀 이동은 펌웨어 내장 폐루프가 아니라 **`PreciseMover`**(연속 `move()` + 피드백)로 직접 구성하세요 — 내장 폐루프는 HANG 위험 때문에 라이브러리에서 완전히 제거되었습니다.
4. **항상 정지로 종료**: 모든 제어를 `try/finally` 안에서 `go.emergency_stop()` + `client.close()`(또는 `with MagicianGO.open(...)` 사용).
5. **속도 상한 고정**: `max_speed=30` 이하, 짧은 거리/각도부터 검증.
6. **모든 루프에 타임아웃**: 절대 무한 대기 금지(`PreciseMover`는 `timeout_s` 내장).
7. **회전 부호는 확정**: `r+`=CCW(좌회전)는 **실기 확정(2026-07-03)** 입니다.
8. **MagicBox 센서는 `None`을 반환할 수 있습니다**: `go.sensors.*` 및 `go.io.get_di`/`get_adc`는 미부착/오결선 시 예외 없이 `None`(+`RuntimeWarning`)을 반환합니다 — 판단 로직에서 반드시 `None` 분기를 처리하세요.
9. **AI 에이전트라면**: 동작 명령 전 `ultrasonic()`/`odometer()`로 상태를 먼저 읽고, 작은 펄스로 검증 후 확장하세요.

---

## 8. 빠른 트러블슈팅

| 증상 | 원인/해결 |
|---|---|
| `cannot connect to DobotLink at ws://localhost:9090` (`DobotConnectionError`) | DobotLink.exe 미실행 → 실행 후 재시도 |
| `connect()`/`connect_robot()`은 OK인데 `battery()` 타임아웃 | GO 전원 OFF 또는 무선 동글 분리 → 전원/링크 확인 |
| 예전에 쓰던 `rotate`/`move_dist`/`arc_*`/`WaypointNav`가 안 보임 | 완전히 제거되었습니다(HANG 위험) → 정밀 이동은 5절 `PreciseMover` 사용 |
| `PreciseMover` 결과에 `aborted=True` | `clearance_ok`가 막혔거나(진행 방향 장애물) 스톨 감지(벽에 눌림) — `reason` 키 확인 |
| `PreciseMover` 결과에 `timed_out=True` | 목표 미도달인 채 `timeout_s` 초과 → `timeout_s`를 늘리거나 `speed`/기구 확인 |
| `go.sensors.*` / `go.io.get_di`·`get_adc`가 `None` + `RuntimeWarning` | 해당 MagicBox/센서 미부착 또는 배선 오류 → `magic_box_num()`으로 부착 여부 확인, Grove 커넥터 번호와 EIO 핀 번호를 혼동하지 않았는지(3.7절) 재확인 |
| MagicBox 센서가 전부 안 읽힘 | `MagicBox.ConnectDobot`을 직접 호출하지 않았는지 확인 — 이 RPC는 GO 차체를 오프라인으로 만듭니다(2026-07-16 실기 확인). `MagicianGO`로만 연결하세요 |
