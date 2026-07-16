# dobotkit GO API 치트시트 (LLM 접지용 1장)

> Dobot Magician GO 제어의 전체 공개 표면. **여기 없는 메서드는 존재하지 않습니다.**
> 2026-07-16 정리: 내장 폐루프/라인트레이싱/카메라/큐 제어/`WaypointNav`는 전부 제거, MagicBox 주변장치(`go.sensors`/`go.io`) 신규 추가(하드웨어 검증 2026-07-16).
> 자세한 예제: [api/go.md](api/go.md)

## 진입점

```python
from dobotkit import MagicianGO
# 또는: from dobotkit.go import MagicianGO, PreciseMover, NavigationAborted, DobotLinkClient

with MagicianGO.open(port_name="COM5") as go:   # DobotLink 연결+링크검증, 종료 시 자동 안전정지
    ...
```

전제: DobotLink.exe 실행 중(ws://localhost:9090) + GO 전원 ON. 직접 시리얼 경로 없음.
종료 teardown: `emergency_stop()`(notify, 무대기) → 확인용 `stop()` → (open()이 소유한 경우) 소켓 close.

## MagicianGO — 주행 (연속 속도뿐; 정지 명령 전까지 계속 달림)

| 메서드 | 설명 |
|---|---|
| `move(x=0, y=0, r=0)` | `x+`전진 `y+`좌횡 `r+`반시계(CCW, 실기 확정 2026-07-03). 각 성분 ±30 클램프(NaN/inf→0). 단위 미확정(8~30 실용) |
| `forward(v)` / `backward(v)` / `strafe(v)` / `spin(v)` | `move` 단축형 |
| `drive_for(x=0, y=0, r=0, seconds=0.5)` | **권장**: 데드맨 주행 — seconds(0~5s 클램프) 후 반드시 정지(finally) |
| `stop()` | 정지(응답 대기) |
| `emergency_stop()` | 무대기 정지(notify) — finally/인터럽트에서 안전 |

정밀 이동(정확한 거리/각도)이 필요하면 **이 위에 없다** — 아래 `PreciseMover` 참고.

## MagicianGO — 안전/연결

| 메서드 | 설명 |
|---|---|
| `clearance_ok(x=0, y=0, r=0, threshold=20)` | 의도 방향 초음파 체크 → `(bool, 사유/거리)`. `None` 초음파는 막힘 취급 |
| `connect(verify=True)` | `connect_robot()` + `battery()` 검증(권장 진입점) |
| `connect_robot()` / `disconnect_robot()` | 저수준 연결/해제. 핸드셰이크 거짓 성공 가능 — `connect()` 권장 |
| `search()` | 연결 가능 GO 탐색 — 응답 verbatim(구조 펌웨어 정의, 미확인) |

## MagicianGO — 네이티브 센서 (읽기 전용)

| 메서드 | 반환 |
|---|---|
| `battery()` | `{powerVoltage, powerPercentage}` — 링크 검증용 |
| `ultrasonic()` | `{front, back, left, right}` cm, **40 상한 클램프**; 이상 응답 → `None`(=모르면 멈춘다) |
| `ultrasonic_raw()` | 원시 응답(진단용) |
| `odometer()` / `set_odometer(x, y, yaw)` | 월드프레임 mm/deg; set으로 영점화. ⚠️ mm 스케일 실측 의심(3~4배 과소집계 관측) |
| `imu_angle()` | 전원 기준 절대각 `{yaw,...}` — 오도미터 yaw와 **혼용 금지** |

## MagicianGO — 진단/알람/MagicBox 상태

`get_alarm_info()` → `{warning:[...]}` · `clean_alarm_info()` ·
`running_state()` → `{runningState:int}` · `stall_protection()` → `{isHappened:int}` ·
`off_ground()` → `{isHappened:int}` ·
`magic_box_mode()` / `magic_box_num()` — ⚠️ 이름과 달리 `MagicianGO.*` 네임스페이스(MagicBox 자체 RPC 아님).

## MagicBox 주변장치 — `go.sensors` / `go.io` (🆕 신규, 하드웨어 검증 2026-07-16)

`MagicianGO`로 연결 한 번이면 충분 — `go.sensors`/`go.io`는 같은 연결 위에서 `MagicBox.*` RPC를 호출 (별도 MagicBox 연결 단계 없음; `MagicBox.ConnectDobot`을 직접 호출하면 GO가 오프라인됨 — 실기 확인).

**두 가지 주소 체계 (혼동 주의)**: `adc`/`di`/`set_do`/`get_di`/`get_adc`/`set_pwm`/`set_multiplexing`은 **EIO 핀(1..26)**, `color`/`infrared`/`distance`/`temp`/`light`/`rgb`는 **Grove 커넥터(1..6)**.

| 그룹 | 메서드 | 비고 |
|---|---|---|
| `go.sensors` | `adc(eio)` `di(eio)` | EIO 핀. 전부 guarded → `None`+`RuntimeWarning` |
| `go.sensors` | `color(port)` `infrared(port)` `distance(port)` `temp(port)` `light(port)` `rgb(port, value)` | Grove 커넥터. 전부 guarded |
| `go.io` | `set_do(eio, level)` `set_pwm(eio, frequency, duty)` `set_multiplexing(eio, multiplex)` | EIO 핀. **guard 없음** — 실패 시 그대로 예외 |
| `go.io` | `get_di(eio)` `get_adc(eio)` | EIO 핀. guarded → `None`+`RuntimeWarning` |

- **guarded** = MagicBox/센서 미부착 시 예외 대신 `None` + `RuntimeWarning`("주변장치 응답이 없습니다..."); 진짜 연결 오류는 그대로 예외.
- ✅ **실기 검증(2026-07-16)**: 교구 세트 가변저항은 Grove 커넥터 **4**번에 꽂혀 있지만 읽을 땐 EIO 핀 **22**번 — `go.sensors.adc(22)` → ~426 (0..4095), 노브 돌리면 변화. 멀티플렉스 값 `4` = ADC 모드.

```python
value = go.sensors.adc(22)        # Grove 4번 = EIO 22번 핀 (실기 검증)
color = go.sensors.color(port=1)  # Grove 1번 컬러 센서, 없으면 None+경고
go.io.set_do(5, 1)                # EIO 5번 핀 출력 High (guard 없음)
```

## MagicianGO — 출력

`rgb(number, effect, r, g, b, cycle, counts)` — **cycle=1, counts>=1 필수**(0이면 희미/무점등, 실측), effect 0=소등/1~3=점등, number는 int 1~5 / `LEDChannel` / `"LED_1".."LED_4","LED_ALL"` ·
`buzzer(index=5, tone=0, beat=0)` — 이 기본값이 깔끔한 '삑'(DobotLab 동일, 실측).

## 제거됨 (더 이상 존재하지 않음 — 지어내지 말 것)

내장 폐루프(`rotate`/`move_dist`/`arc_rad`/`arc_cent`/`increment_closed_loop`, `unsafe_` 변형 포함), `move_direct`, `move_speed_time`, `set_running_mode`, `set_origin_point` · 라인트레이싱(`auto_trace`/`trace_speed`/`trace_pid`/`trace_angle`/`line_error` 등) · 카메라(`car_camera_*`/`arm_camera_*`) · 큐 제어(`clean_cmd_queue` 등) · Stop-Point(`stop_point_state` 등) · 디바이스 관리(`product_name`/`device_*`/`heartbeat` 등) · `imu_speed`/`get_move_speed`/`get_running_mode` · **`WaypointNav`** 클래스 전체.
(내장 폐루프는 이 기체에서 완료 콜백이 안 와 HANG하기 때문에 제거 — 정밀 이동은 아래 `PreciseMover`로 직접 구성.)

## `PreciseMover` — 정밀 이동(유일한 폐루프 경로, 연속 move + 센서 피드백)

```python
from dobotkit.go.navigation import PreciseMover, NavigationAborted

mover = PreciseMover(go, max_speed=30, min_speed=8)
res = mover.goto_distance(300, speed=20, axis="x", threshold=20, timeout_s=8.0)
# {target, achieved, error, axis, timed_out, aborted[, reason]}  -- mm 단위!
res = mover.turn_degrees(90, speed=20, threshold=20, timeout_s=8.0)
# {target, achieved, error, timed_out, aborted[, reason]}  -- r+ = CCW, 실기 확정, 오차 ~1.5도

mover.goto_distance(300, raise_on_abort=True)   # 실패 시 NavigationAborted(.result 보유)
```

- 클리어런스 사전체크·0.25초마다 재체크·1초 무진행 스톨가드·절대 타임아웃·try/finally 비상정지 **전부 내장**.
- `aborted`(막힘/스톨)·`timed_out`은 정상 흐름 — 예외 아님(`raise_on_abort=True`가 아닌 한).
- 단위: **mm**(오도미터/명령 거리). 회전량은 IMU yaw, 병진 진행은 오도미터로 측정 — 두 yaw 소스 혼용 금지.

## 안전 3원칙

1. 항상 `with MagicianGO.open(...) as go:` — 크래시에도 자동 정지.
2. 정밀 이동은 `PreciseMover`만 — 내장 폐루프는 없음(HANG 위험으로 제거됨).
3. 센서를 모르면 멈춘다 — `ultrasonic() is None`, `go.sensors.*`의 `None`도 정지/분기 사유.
