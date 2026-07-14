# dobotkit GO API 치트시트 (LLM 접지용 1장)

> Dobot Magician GO 제어의 전체 공개 표면. **여기 없는 메서드는 존재하지 않습니다.**
> 하드웨어 검증 2026-07-02 · 확장 API 49종 추가 2026-07-04(전부 실기 미검증 — [검증 목록](VERIFICATION_NEEDED_ko.md)).
> 자세한 예제: [quickstart-ko.md](quickstart-ko.md)

## 진입점

```python
from dobotkit.go import MagicianGO, PreciseMover, WaypointNav, NavigationAborted

with MagicianGO.open(port_name="COM5") as go:   # DobotLink 연결+링크검증, 종료 시 자동 안전정지
    ...
```

전제: DobotLink.exe 실행 중(ws://localhost:9090) + GO 전원 ON. 직접 시리얼 경로 없음.

## MagicianGO — 주행 (연속 속도; 정지 명령 전까지 계속 달림)

| 메서드 | 설명 |
|---|---|
| `move(x=0, y=0, r=0)` | `x+`전진 `y+`좌횡 `r+`반시계. 각 성분 ±30 클램프. 단위 미확정(8~30 실용) |
| `forward(v)` / `backward(v)` / `strafe(v)` / `spin(v)` | `move` 단축형 |
| `move_direct(direction, speed)` | 방향 지정 주행(SetMoveSpeedDirect). `direction`(파이썬)→`dir`(RPC) 정수 enum — 0=전진 **추정**, 값 매핑 미확정. `speed` ±30 클램프. 일반 주행은 `forward`/`move` 우선 |
| `drive_for(x=0, y=0, r=0, seconds=0.5)` | **권장**: 데드맨 주행 — seconds(≤5) 후 반드시 정지 |
| `stop()` | 정지(응답 대기) |
| `emergency_stop()` | 무대기 정지(notify) — finally/인터럽트에서 안전 |

## MagicianGO — 센서 (읽기 전용)

| 메서드 | 반환 |
|---|---|
| `battery()` | `{powerVoltage, powerPercentage}` — 링크 검증용 |
| `ultrasonic()` | `{front, back, left, right}` cm, **40 상한 클램프**; 이상 응답 → `None`(=모르면 멈춘다) |
| `ultrasonic_raw()` | 원시 응답(진단용) |
| `odometer()` / `set_odometer(x, y, yaw)` | 월드프레임 'mm'/deg; set으로 영점화. ⚠️ mm 스케일 실측 의심(3~4배 과소집계 관측) — 캘리브레이션 전엔 상대 진행량으로만 |
| `imu_angle()` | 전원 기준 절대각 `{yaw,...}` — 오도미터 yaw와 **혼용 금지**(24°+ 어긋남 실측) |
| `imu_speed()` | 원시 IMU `{ax,ay,az,gx,gy,gz}` (가속도 g + 자이로 — 이름과 달리 각속도 yaw 아님, 실측) |
| `clearance_ok(x=0, y=0, r=0, threshold=20)` | 의도 방향 초음파 체크 → `(bool, 사유/거리)` |

## MagicianGO — 라인 트레이싱

| 메서드 | 설명 |
|---|---|
| `trace_speed(v)` | 순찰 속도 (공식값 20) |
| `trace_pid(p, i, d)` | 순찰 PID (공식값 0.5, 0, 0.5 — 50처럼 크면 요동·이탈 실측) |
| `auto_trace(on)` | 펌웨어 순찰 ON/OFF — 내부적으로 `isTrace=int`+`type=0` (검증된 포맷) |
| `trace_angle()` | `{"angle": int, "count": int}` — `count==0`=라인 없음. 중앙값 기체별 실측(참조 ≈245) |
| `line_error(center)` | `angle - center` 또는 라인 없으면 `None`. P제어: `move(x=v, r=-kp*err)` (부호 기체별 확인) |

## MagicianGO — 카메라/출력/기타

`car_camera_obj()` `arm_camera_obj()` `arm_camera_tag()` (탐지 결과만 — **원시 영상 접근 불가**,
ARM 캠은 기체에 따라 405 비활성) ·
`rgb(number, effect, r, g, b, cycle, counts)` — **cycle=1, counts>=1 필수**(0이면 희미/무점등, 실측), effect 0=소등/1~3=점등 ·
`buzzer(index=5, tone=0, beat=0)` — 이 기본값이 깔끔한 '삑'(DobotLab 동일, 실측) ·
`search()` → 응답 verbatim 반환(구조 추정 `[{description, portName, status}]` — **실측 미확인**, 펌웨어 정의·비정규화) ·
`connect()` `connect_robot()`(핸드셰이크 거짓 성공 가능 — 읽기 검증 필요, `connect()` 권장) `disconnect_robot()` `set_running_mode(mode)`

## ⚠️ 사용 금지 (행 HANG 실측 — 큐 명령)

`unsafe_rotate` `unsafe_move_dist` `unsafe_arc_rad` `unsafe_arc_cent`
`unsafe_increment_closed_loop` — 완료 콜백이 오지 않아 **멈춤(HANG)**.
구명칭(`rotate` 등)은 UserWarning을 내는 폐기 예정 별칭.
`unsafe_move_pos`(신규 2026-07-04)도 동일 큐드+대기 계열로 확정 — HANG 추정, 미검증.
예외: `coord_closed_loop(is_enable, angle)`(SetCoordClosedLoop)은 `_WAIT` 미전송이라
완료 대기(HANG) 계열이 **아님** — 단 실효 동작 자체는 미검증.
→ 정밀 이동은 대신 아래 내비게이션 계층 사용.

## 확장 API 49종 (전부 미검증 2026-07-04 — 와이어 스펙만 채굴 교차검증)

> 시그니처는 공식 소스 3중 교차검증(DobotEDU 래퍼+CHM+DobotLink 플러그인)이나 **실기 실행 0회**.
> 검증 절차·순서: [VERIFICATION_NEEDED_ko.md](VERIFICATION_NEEDED_ko.md) C절.

### 진단·조회 (읽기 전용, 미검증 2026-07-04)

| 메서드 | RPC | 반환 |
|---|---|---|
| `get_alarm_info()` | GetAlarmInfo | `{warning: [...]}` |
| `clean_alarm_info()` | CleanAlarmInfo | result true |
| `running_state()` | GetRunningState | `{runningState:int}` 추정 — 방어적 읽기 |
| `stall_protection()` | GetStallProtection | `{isHappened:int}` (모터 스톨) |
| `off_ground()` | GetOffGround | `{isHappened:int}` (들림 감지) |
| `get_move_speed()` | GetMoveSpeed | `{x,y,r}` (cm/s, deg/s) |
| `get_running_mode()` | GetRunningMode | `{runningMode:int}` 추정(0 NORMAL/1 SAFE) — 방어적 읽기 |

### 트레이스 확장 (미검증 2026-07-04)

| 메서드 | 설명 |
|---|---|
| `firmware_trace_angle(**params)` | GetTraceAngle — ⚠️ **와이어 존재 미확인**(패스스루, unconfirmed). 기존 `trace_angle()`(=GetCarCameraAngle)과 별개 — 의미 대조 필요 |
| `set_trace_line_info(lineInfo)` | SetTraceLineInfo — `lineInfo:int` (값 의미 미확정) |

### 절대주행 (⚠️ 모션, 미검증 2026-07-04)

| 메서드 | 설명 |
|---|---|
| `unsafe_move_pos(x, y, s)` | SetMovePos — 목표 (x,y) cm로 이동, 속도 s(0-100 cm/s). **큐드+대기 확정 → HANG 추정(사용 금지 목록)** |
| `move_speed_time(time, x, y, r, isAck=False)` | SetMoveSpeedTime — time초 동안 속도 (x,y cm/s, r deg/s). x/y/r **±30 클램프**, time **0~5초 클램프**(펌웨어 주행이 스크립트 크래시를 살아남으므로). 비큐드 확정(HANG 계열 아님), 데드맨 대체 후보 |
| `set_origin_point(enable)` | SetOriginPoint — 원점 사용 1/미사용 0. 비큐드. 실효 의미 미확정 |

### 카메라 확장 (미검증 2026-07-04; count=0 시 배열 키 부재 가능 — 방어적 읽기)

| 메서드 | RPC | 반환/인자 |
|---|---|---|
| `car_camera_color()` | GetCarCameraColor | `{count(≤5), color_obj:[{x,y,w,h,id}]}` |
| `car_camera_tag()` | GetCarCameraTag | `{count(≤5), aptag_obj:[{x,y,w,h,id,rot}]}` |
| `get_car_camera_model()` / `set_car_camera_model(i)` | Get/SetCarCameraRunModel | `{runModelIndex:int}` / runModelIndex |
| `get_car_camera_calibration_mode()` / `set_car_camera_calibration_mode(i)` | Get/SetCarCameraCalibrationMode | `{isEnableCali:int}` 추정 / 1 진입·0 종료 |
| `camera_calibration_data(april_list, device_list)` | GetCameraCalibrationData | 9점 JSON 문자열 2개 필수 → `{data:"max_x_err:..."}` |
| `arm_camera_color()` / `arm_camera_angle()` | GetArmCameraColor/Angle | color_obj / `{angle:int}` (ARM 캠 405 기체 존재) |
| `get_arm_camera_model()` / `set_arm_camera_model(i)` | Get/SetArmCameraRunModel | Car와 동일 |
| `get_arm_camera_calibration_mode()` / `set_arm_camera_calibration_mode(i)` | Get/SetArmCameraCalibrationMode | Car와 동일 |

### 큐 제어 (미검증 2026-07-04)

`clean_cmd_queue()` `cmd_queue_start()` `cmd_queue_stop()` `cmd_queue_force_stop()`(공식 비상정지 시퀀스 일부) ·
`queued_cmd_current_index()` → `{queueCmdCurrentIndex:int}`('queue' 철자 주의) ·
`cmd_queue_available_space()` → `{space:int}`

### MagicBox / 상태 (미검증 2026-07-04)

| 메서드 | RPC(네임스페이스) | 설명 |
|---|---|---|
| `magic_box_mode()` / `magic_box_num()` | GetMagicBoxMode/Num (MagicianGO) | `{mode:int}` / `{num:int}` 추정 — 방어적 읽기 |
| `stop_point_state()` | GetStopPointState (**MagicBox**) | `{result:bool}` 도착·정지 시 true |
| `set_stop_point_param(scopeErr, stopErr)` | SetStopPointParam (**MagicBox**) | 진입범위(기본 40)/정지정밀도(기본 2) |
| `set_stop_point_server(PointX, PointY)` | SetStopPointServer (**MagicBox**) | 정지점 좌표(인자명 대문자 P 그대로) — ⚠️ 단위(cm/mm) 미확정, 작은 값으로만 |
| `set_running_state(**params)` | SetRunningState (MagicianGO) | **미확정 패스스루**(`runningState:int` 추정) |

### 출력·디바이스 (미검증 2026-07-04)

`set_light_prompt(index)` (0없음/1 USB/2 저전량/3 핸들/4 스크립트) ·
`product_name()` → `{productName}`("MagicianGo"면 유효 디바이스) ·
`device_fw_software_version()` / `device_fw_hardware_version()` → `{majorVersionNum, secondVersionNum, revisionVersionNum, previousVersionNum}`(방어적 읽기) ·
`device_id()` → `{deviceID:[int]}` · `get_device_name()` / `set_device_name(deviceName)` ·
`get_device_sn()` / `set_device_sn(deviceSN)`(⚠️ SN 덮어쓰기 원복 불가 위험) ·
`device_time()` → `{gSystick, passtime:"hh:mm:ss.z"}` ·
`device_reboot()` — ⚠️ **즉시 재부팅·연결 끊김** · `heartbeat()` — keepalive(공식 JS: 2000ms 타임아웃×3회 실패 시 끊김 처리)

## PreciseMover / WaypointNav — 안전 내비게이션 (권장)

```python
mover = PreciseMover(go)                       # max_speed=30, min_speed=8
mover.goto_distance(300, speed=20)             # +300 mm 전진 (mm 단위!)
mover.turn_degrees(90, speed=20)               # 제자리 90° 반시계 — CCW 부호 실기 확정, 오차 ~1.5° 실측

nav = WaypointNav(go)
nav.set_start(20, 20, heading_deg=0)           # 필수 — 안 하면 go_to가 RuntimeError
nav.pose_cm()                                  # {"x_cm", "y_cm", "heading_deg"}
nav.go_to(100, 80, raise_on_abort=True)        # cm 단위! 실패 시 NavigationAborted
```

- 클리어런스 사전체크·벽시계 타임아웃·try/finally 비상정지 **전부 내장**.
- 결과 dict: `{target, achieved, error, timed_out, aborted[, reason]}` /
  go_to: `{start, target, final, residual_cm, iters, legs, arrived}`.
- `raise_on_abort=True`를 주면 실패가 예외(`NavigationAborted`, `.result` 보유)로 승격 — 교육 코드 권장.
- **단위 경계**: PreciseMover=mm, WaypointNav=cm.

## 안전 3원칙

1. 항상 `with MagicianGO.open(...) as go:` — 크래시에도 자동 정지.
2. 주행 루프는 유한 루프(`for`)만. 한 번의 이동은 `drive_for`.
3. 센서를 모르면 멈춘다 — `ultrasonic() is None`도 정지 사유.
