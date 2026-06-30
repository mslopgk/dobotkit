# dobotkit — 설계 스펙 (Design Spec)

> **목표**: Dobot Magician Lite(4축 로봇팔)와 Magician GO(자율주행 카)를 하나의 패키지로 제어하는,
> **모든 SDK 기능을 지원하는** 순수 Python 오픈소스 라이브러리. pydobot이 일부 기능만 지원하는 한계를 넘어선다.

- **작성일**: 2026-06-30
- **상태**: 설계 확정 대기 (사용자 검토 중)
- **연구 기반**: `docs/두봇_라이트_API.md`, `docs/두봇_고_API.md`, `Dobot_Demo_V2.3/.../DobotDllType.py`, `pydobot-master/`, `magiciango_go/`

---

## 1. 개요 및 목표

### 1.1 무엇을 만드는가
`dobotkit` — 두 종류의 Dobot 기기를 제어하는 통합 Python 라이브러리.

| 기기 | 클래스 | 전송 방식 | 의존성 |
|---|---|---|---|
| Magician Lite (로봇팔) | `dobotkit.Magician` | USB 시리얼 (순수 Python 프로토콜 재구현) | `pyserial` |
| Magician GO (주행 카) | `dobotkit.MagicianGO` | DobotLink WebSocket (JSON-RPC) | `websockets` |

### 1.2 핵심 목표 (확정)
1. **모든 기능(All Features)** — Lite의 경우 공식 DLL(`DobotDllType.py`)이 노출하는 ~150개 함수 **전부**를 순수 Python 시리얼로 재구현. GO는 DobotLink RPC 전체를 래핑.
2. **순수 Python·독립 실행** — pydobot처럼 DLL/외부 바이너리 없이 `pip install` 후 바로 사용. 크로스플랫폼(Windows/Linux/macOS).
3. **범용 오픈소스 품질** — 타입힌트(`py.typed`), 문서, 예제, 가짜 트랜스포트 기반 단위테스트, 시맨틱 버저닝.
4. **안전 우선** — 연구 문서의 안전 원칙(동작 전 상태 읽기, 타임아웃, 항상 정지/해제)을 API에 내장.
5. **쉬움 + 완전함 동시** — 2계층 구조로 pydobot 수준의 쉬운 고수준 API와 빠짐없는 저수준 API를 모두 제공.

### 1.3 비목표 (YAGNI — 명시적 제외)
- 공식 DLL 백엔드 (사용자가 순수 Python 단독 실행 선택)
- GUI / 시각화 도구
- ROS / ROS2 연동
- 펌웨어 업그레이드(`UpgradeFW`) — 위험하고 하드웨어 brick 가능성. 저수준에 노출하되 고수준 편의는 제공 안 함.
- Dobot Magician(풀사이즈)·M1·MG400 등 타 모델 — Lite/GO에 집중. (단, 프로토콜이 호환되면 부수적으로 동작할 수 있음)

---

## 2. 패키지 레이아웃

```
dobotkit/
  pyproject.toml              # 빌드/메타/의존성 (src 레이아웃, hatchling 또는 setuptools)
  README.md                   # 개요·설치·퀵스타트(arm/go 둘 다)
  LICENSE                     # MIT
  CHANGELOG.md
  py.typed                    # (패키지 내부) 타입 배포 마커
  src/dobotkit/
    __init__.py               # 공개 API: Magician, MagicianGO, 전 enum, 전 예외, __version__
    _version.py
    exceptions.py             # 예외 계층 (전 기기 공통)
    enums.py                  # 전 enum (PTPMode, JOGMode, GPIOType, EndEffectorType, AlarmCode, CPMode, ...)
    _logging.py               # 라이브러리 로거 설정 헬퍼

    arm/                      # ===== Magician Lite (순수 Python 시리얼) =====
      __init__.py
      protocol.py             # Message 프레이밍·체크섬·바이트 (역)직렬화
      structures.py           # ~150개 명령 페이로드 (un)pack 스펙 (DobotDllType Structure 미러)
      ids.py                  # ProtocolId 완전 테이블 (전 명령 ID + rw/queued 메타)
      transport.py            # SerialTransport — pyserial 연결/탐색/송수신/타임아웃/락
      queue.py                # CommandQueue — start/stop/clear/index/motion-finish + wait 헬퍼
      lowlevel.py             # ★ LowLevelArm — 모든 SDK 함수 1:1 (완전성 보장 계층)
      magician.py             # ★ Magician — 고수준 Pythonic API + 안전 헬퍼 + 그룹 프로퍼티
      groups.py               # IOGroup / SensorGroup / EffectorGroup (arm.io / arm.sensors / arm.effector)
      alarms.py               # 알람 비트맵 ↔ 사람이 읽는 AlarmCode 디코딩 테이블

    go/                       # ===== Magician GO (DobotLink WebSocket) =====
      __init__.py
      client.py               # DobotLinkClient — WebSocket JSON-RPC (call/notify/connect/close)
      magiciango.py           # MagicianGO — 주행/센서/카메라/LED/부저/라인트레이스 고수준 API
      navigation.py           # PreciseMover + WaypointNav (연속 move + 센서 폐루프)
      geometry.py             # 순수함수: yaw_delta, bearing, clamp 등 (HW 불필요, 단위테스트 대상)

  tests/
    arm/                      # 가짜 시리얼(FakeSerial) 기반 프로토콜 왕복 테스트
    go/                       # 가짜 WebSocket 기반 RPC 테스트 + geometry 순수함수 테스트
    conftest.py
  examples/
    arm_pick_and_place.py
    arm_sensors.py
    arm_full_api_tour.py
    go_teleop.py
    go_waypoint_nav.py
    go_line_trace.py
  docs/
    superpowers/specs/        # 이 스펙
    api/                      # 사용자 API 레퍼런스 (기존 두봇 연구 문서를 흡수·갱신)
```

**설계 원칙**: 각 파일은 하나의 명확한 책임을 가지며 독립적으로 이해·테스트 가능해야 한다. `lowlevel.py`가 비대해지면 카테고리별로 분할(`lowlevel/motion.py`, `lowlevel/io.py` 등 믹스인)한다.

---

## 3. Arm(Lite) 아키텍처 — 계층 구조

```
┌─────────────────────────────────────────────┐
│ Magician (magician.py)  — 고수준, 안전, Pythonic │  ← 일반 사용자
│   move_to / home / pick_and_place / 컨텍스트매니저 │
│   .io .sensors .effector 그룹, 알람 자동 디코딩      │
├─────────────────────────────────────────────┤
│ LowLevelArm (lowlevel.py) — 모든 SDK 함수 1:1     │  ← 고급 사용자 / 완전성 보장
│   set_ptp_cmd / get_pose / set_io_pwm / ...      │
├─────────────────────────────────────────────┤
│ CommandQueue (queue.py) — 큐 실행/완료 대기        │
├─────────────────────────────────────────────┤
│ structures.py — 페이로드 (un)pack │ ids.py — 명령 ID │
├─────────────────────────────────────────────┤
│ protocol.py — Message 프레이밍·체크섬             │
├─────────────────────────────────────────────┤
│ SerialTransport (transport.py) — pyserial         │
└─────────────────────────────────────────────┘
```

### 3.1 프로토콜 레이어 (`protocol.py`)
Dobot 시리얼 프레임 (pydobot `message.py`에서 검증된 포맷):

```
[0xAA, 0xAA] [len] [id] [ctrl] [params...] [checksum]
  헤더(2)     길이   ID   제어    파라미터     체크섬(1)
```

- `len = 2 + len(params)` (id + ctrl + params 바이트 수)
- `ctrl` 바이트: bit0 = `rw`(0=읽기/get, 1=쓰기/set), bit1 = `isQueued`(0=즉시, 1=큐 적재)
- `checksum = (256 - (id + ctrl + Σparams) % 256) % 256`
- `Message` 클래스: `id, ctrl, params(bytes)` ↔ `to_bytes()` / `from_bytes()`. 응답 파싱 시 헤더·체크섬 검증, 불일치 시 `ProtocolError`.

### 3.2 구조체 레이어 (`structures.py`)
모든 명령의 페이로드는 `struct` 포맷으로 (역)직렬화. `DobotDllType.py`의 ctypes `Structure` 정의(필드 순서·타입)를 1:1로 미러링한다. 예:

```python
# Pose: GET_POSE 응답 (float32 x8)  →  "<8f"
# PTPCmd: SET_PTP_CMD 요청 (uint8 ptpMode + float32 x,y,z,r)  →  "<Bffff"
# JOGCmd: (uint8 isJoint, uint8 cmd)  →  "<BB"
# HOMEParams: (float32 x,y,z,r)  →  "<4f"
```
각 구조체는 `pack(**fields) -> bytes` / `unpack(bytes) -> dict|namedtuple` 제공. **단위테스트로 왕복(pack→unpack) 검증.**

### 3.3 명령 ID 테이블 (`ids.py`)
완전한 `ProtocolId` enum + 각 ID의 메타데이터(요청/응답 구조체, 큐 지원 여부). 재구성 출처:
1. `pydobot/enums/CommunicationProtocolIDs.py` — 부분(~30개, 검증된 값)
2. `DobotDllType.py`의 함수·Structure 정의 순서 — 전 명령의 페이로드 레이아웃
3. 공식 Dobot Communication Protocol의 **카테고리별 순차 번호** 규약:
   - 0–9 디바이스(SN/Name/Version/...), 10–19 포즈, 20–29 알람, 30–39 홈,
   - 60–69 엔드이펙터, 70–79 JOG, 80–89 PTP, 90–99 CP, 100–109 ARC,
   - 110–119 WAIT/TRIG, 120–129 EIO 확장, 130–139 IO, 140–149 EMotor,
   - 150–169 센서(컬러/적외선/Seeed), 240–249 큐 제어 (정확한 값은 구현 시 교차검증·확정)
4. 구현 중 하드웨어로 확인 가능한 명령은 실측 검증, 불가한 것은 명세 기반으로 표기.

> **리스크 & 완화**: 일부 ID는 공개 자료 간 불일치 가능. 완화책 — pydobot의 검증된 값을 1차 기준으로, 카테고리 순차 규약으로 보간, 각 ID에 출처(`verified`/`from_spec`) 태그. 하드웨어 테스트로 점진 검증.

### 3.4 트랜스포트 (`transport.py`)
- `SerialTransport(port, baudrate=115200, timeout=...)` — `pyserial` 래핑.
- `search() -> list[str]` — 연결 가능 포트 탐색(`serial.tools.list_ports`, 가능하면 핸드셰이크로 Dobot 확인).
- `send(message) -> Message` — 송신 후 응답 1프레임 수신(타임아웃 적용). **스레드 락**으로 동시 접근 방지.
- 연결 실패/점유/무응답 → `DobotConnectionError` / `DobotTimeoutError`.

### 3.5 큐 모델 (`queue.py`)
연구 문서의 큐 패턴을 캡슐화:
- `clear() / start() / stop() / force_stop()`
- `current_index() -> int`, `motion_finished() -> bool`
- `wait_for(cmd_index, poll=0.05, timeout=...)` — 인덱스 비교 폴링(타임아웃 필수, 무한대기 금지).
- 고수준 `wait=True`가 이 헬퍼를 사용.

### 3.6 저수준 완전 계층 (`lowlevel.py`) — ★ "모든 기능" 보장
공식 DLL의 **모든** 함수를 Python 메서드로 1:1 노출. snake_case + 타입힌트 + enum. `isQueued` 인자는 `queued: bool = False` 키워드. 반환은 디코딩된 값(구조체→namedtuple/dict). 카테고리:

- **연결/디바이스**: `search`, `connect`, `disconnect`, `set_cmd_timeout`, `get_device_sn`, `set/get_device_name`, `get_device_version`, `get_device_id`, `get_device_time`, `get_device_info`, `restart` (MagicBox)
- **큐**: `queued_cmd_clear/start_exec/stop_exec/force_stop_exec`, `get_queued_cmd_current_index`, `get_queued_cmd_motion_finish`
- **포즈/원점**: `get_pose`, `get_pose_l`, `get_kinematics`, `reset_pose`, `set/get_home_params`, `set_home_cmd`, `set_auto_leveling`, `get_auto_leveling_result`
- **PTP**: `set_ptp_cmd`, `set_ptp_with_l_cmd`, `set/get_ptp_common_params`, `..._coordinate_params`, `..._joint_params`, `..._jump_params`, `..._l_params`, `set/get_ptp_jump2_params`(있으면)
- **JOG**: `set_jog_cmd`, `set/get_jog_common_params`, `..._joint_params`, `..._coordinate_params`, `..._l_params`
- **CP**: `set_cp_cmd`, `set_cp2_cmd`, `set/get_cp_params`
- **ARC**: `set_arc_cmd`, `set_circle_cmd`, `set/get_arc_params`
- **WAIT/TRIG**: `set_wait_cmd`, `set_trig_cmd`
- **엔드이펙터**: `set/get_end_effector_params`, `..._suction_cup`, `..._gripper`, `..._laser`, `set/get_end_effector_type`, `set/get_servo_angle`
- **IO**: `set_io_do`, `get_io_di`, `get_io_adc`, `set_io_pwm`, `set/get_io_multiplexing` (+ 각 `_ext` / `_ext_ex` 변형: MagicBox slave=-1 라우팅)
- **EMotor**: `set_e_motor`, `set_e_motors`
- **센서**: `set/get_color_sensor`, `set/get_infrared_sensor`, `get_seeed_distance_sensor`, `set/get_seeed_light_sensor`, `..._temp_sensor`, `..._color_sensor`, `set_seeed_rgb`
- **속도비율**: `set/get_arm_speed_ratio`, `set/get_l_speed_ratio`
- **스텝손실(Lite)**: `set/get_lost_step_params`, `set_lost_step_cmd`
- **알람**: `get_alarms_state`, `clear_all_alarms_state`
- **WiFi**: `set/get_wifi_config_mode`, `set/get_wifi_ssid`, `..._password`, `..._ip_address`, `..._netmask`, `..._gateway`, `..._dns`, `get_wifi_connect_status`
- **펌웨어(저수준만, 위험)**: `set_fw_*` 류는 노출하되 docstring에 경고.

> 위 목록은 `docs/두봇_라이트_API.md` §10 인덱스 + `DobotDllType.py` 전수 함수와 대조해 **빠짐없이** 구현한다. 구현 산출물에 "구현된 함수 ↔ DobotDllType 함수" 대조표를 포함해 커버리지 100%를 증명한다.

### 3.7 고수준 계층 (`magician.py`) — ★ pydobot 수준의 쉬움
```python
with Magician(port="auto") as arm:          # 자동 탐지/연결, 종료 시 자동 정지·해제
    arm.home()                                # 홈 파라미터 설정 + 홈 실행 + 완료 대기
    arm.set_speed(velocity=50, acceleration=50)
    x, y, z, r = arm.pose.cartesian           # 또는 arm.get_pose()
    arm.move_to(200, 0, 50, 0, wait=True)     # MOVL 절대 (기본), mode= 로 변경 가능
    arm.move_relative(dz=20, wait=True)       # INC 모드
    arm.effector.suck(True)                   # 그룹 프로퍼티
    arm.io.set_do(addr=1, level=1)
    dist = arm.sensors.seeed_distance(port=1)
```
- **컨텍스트매니저**: `__enter__`/`__exit__`에서 연결/정리. 예외 시에도 `stop`+`disconnect` 보장.
- **wait 의미**: `wait=True`면 큐 적재 후 실행+완료 대기(블로킹). `wait=False`면 인덱스 반환.
- **알람 자동 처리**: 동작 메서드는 옵션으로 사전 알람 확인. 알람 발생 시 `DobotAlarmError(codes=[...])` (디코딩된 이름 포함).
- **그룹 프로퍼티**: `arm.io`(IOGroup), `arm.sensors`(SensorGroup), `arm.effector`(EffectorGroup) — 발견성↑. 평면 편의 메서드(`move_to`, `suck`)도 병행.
- **편의 시퀀스**: `arm.pick_and_place(src, dst, z_safe=...)`, `arm.jog(axis, direction, duration)` 등.
- **pydobot 호환 별칭**(선택): `move_to`, `suck`, `grip`, `speed`, `wait`, `pose`, `get_eio`, `set_eio` 시그니처를 pydobot과 호환되게 제공해 마이그레이션 용이.
- 저수준 접근: `arm.lowlevel` 으로 항상 노출(니치 함수용).

---

## 4. GO(카) 아키텍처

기존 `magiciango_go/magiciango/`(client.py, go.py)와 예제(precise_move.py, waypoint_nav.py)를 **흡수·정리·완성**한다. 전송은 DobotLink WebSocket으로 고정(선택지 없음).

### 4.1 `client.py` — DobotLinkClient
- `connect()`, `call(method, **params)`(응답 대기), `notify(method, **params)`(비상정지용 전송만), `close()`, 컨텍스트매니저.
- `dobotlink.` 접두어만 자동 보정. `MagicianGO.`/`MagicBox.` 네임스페이스는 호출자 책임(문서화).
- 미실행/무응답 → `DobotLinkError`(DobotLink 실행 안내 포함) / 타임아웃.

### 4.2 `magiciango.py` — MagicianGO
go.py의 전 메서드 + 타입힌트·docstring·반환구조 정리. 연구 문서의 위험 표시 반영:
- **연속 주행(✅ 신뢰)**: `move`, `move_direct`, `forward`, `backward`, `strafe`, `spin`, `stop`, `emergency_stop`
- **큐/폐루프(⚠️ HANG 위험)**: `rotate`, `move_dist`, `arc_rad`, `arc_cent`, `coord_closed_loop`, `increment_closed_loop` — docstring에 HANG 경고 + 권장 대안(PreciseMover) 명시. 기본 타임아웃 짧게.
- **센서(읽기, 안전)**: `ultrasonic`, `odometer`, `set_odometer`, `battery`, `imu_angle`, `imu_speed`
- **안전 헬퍼**: `clearance_ok(x,y,r,threshold)`
- **출력**: `rgb`, `buzzer`
- **라인트레이스**: `auto_trace`, `trace_speed`, `trace_pid`, `trace_angle`
- **카메라**: `car_camera_obj`, `arm_camera_obj`(405 가능), `arm_camera_tag` — 방어적 파싱
- **실험적 MagicBox.* RPC**(Stop-Point): 저수준 `client.call`로 접근하는 헬퍼 제공하되 "미보장" 경고.
- **링크 검증**: `connect_robot()` 후 `battery()` 응답 확인 패턴을 `connect(verify=True)`로 내장.

### 4.3 `navigation.py` — PreciseMover / WaypointNav
연구 문서 §6·§7 그대로 구현(검증된 안전 설계):
- `PreciseMover.goto_distance(...)`, `turn_degrees(...)` — 연속 move + 오도미터/IMU 폐루프, 절대 타임아웃, 클리어런스 인터록, MAX/MIN 속도 캡.
- `WaypointNav.set_start(...)`, `go_to(...)`, `pose_cm()`, `face(...)` — 매트 절대좌표. 헤딩 소스 규약(현재 헤딩=오도미터 yaw, 회전량=IMU yaw) 준수.
- 반환 dict 구조(aborted/timed_out/reason/legs/...)는 연구 문서 명세 유지.

### 4.4 `geometry.py` — 순수함수
`yaw_delta`, `bearing`, `clamp_speed`, cm↔mm 변환 등 하드웨어 불필요 순수함수. 기존 `tests/`의 pytest 자산 흡수.

---

## 5. 예외 계층 (`exceptions.py`)

```
DobotError                       # 베이스
 ├─ DobotConnectionError         # 연결 실패/포트 점유/장치 없음
 ├─ DobotTimeoutError            # 응답/완료 대기 타임아웃
 ├─ DobotProtocolError           # 프레임/체크섬 불일치, 디코딩 실패
 ├─ DobotAlarmError              # 알람 발생 (codes: list[AlarmCode], 디코딩된 이름)
 ├─ DobotLinkError               # GO: DobotLink 미실행/RPC error 응답
 └─ DobotValueError              # 잘못된 인자(범위 밖 좌표/포트 등)
```
모든 공개 메서드는 반환코드 점검 대신 **예외**로 실패를 알린다(파이썬다움). `aborted`/`timed_out` 같은 GO 폐루프 결과는 안전 설계상 정상 흐름이므로 예외가 아닌 결과 dict로 구분(연구 문서 규약 유지).

---

## 6. 안전 모델 (연구 문서 기반, API 내장)

| 원칙 | 구현 |
|---|---|
| 동작 전 상태 읽기 | 고수준 메서드 옵션 `check_alarms=True`(arm), `clearance_ok`(go) |
| 모든 루프 타임아웃 | `wait_for`, `goto_distance` 등 전부 절대 타임아웃. 무한대기 금지 |
| 항상 정지/해제로 종료 | 컨텍스트매니저 `__exit__`에서 stop+disconnect/close 보장 |
| 저속부터 검증 | 기본 속도 보수적, GO `MAX_SPEED=30` 캡 |
| 전원 직후 홈 | `Magician.home()` 강조, 미홈 상태 경고 옵션 |
| HANG 위험 명시 | GO 폐루프 메서드 docstring 경고 + 권장 대안 |

---

## 7. 테스트 전략

- **프로토콜 단위테스트(HW 불필요)**: `FakeSerial`(미리 정의된 응답 바이트) 으로 모든 명령의 요청 인코딩·응답 디코딩 왕복 검증. 체크섬·프레이밍 엣지케이스.
- **구조체 왕복**: 모든 `structures` pack→unpack 항등성.
- **ID 커버리지 테스트**: `DobotDllType` 함수 목록 ↔ `lowlevel` 메서드 대조표로 100% 커버 자동 검증.
- **GO RPC 테스트**: `FakeWebSocket` 으로 call/notify 페이로드·네임스페이스 접두어 검증.
- **geometry 순수함수**: 기존 pytest 자산 흡수.
- **하드웨어 게이트 통합테스트**: `@pytest.mark.hardware` — 환경변수/포트 있을 때만. CI에선 스킵.
- **목표 커버리지**: 비-하드웨어 코드 ≥90%.

---

## 8. 패키징·배포

- `pyproject.toml` (src 레이아웃). `name = "dobotkit"`, Python ≥3.9.
- 의존성 (**확정**): `pyserial`·`websockets` 둘 다 **기본 의존**으로 단순화(둘 다 순수 Python, 가벼움). 사용자는 `pip install dobotkit` 한 번으로 두 기기 모두 사용. 무거운 분리가 불필요하므로 extras는 두지 않음.
  - `dobotkit.arm`/`dobotkit.go` 서브패키지는 **지연 import**로 구성해, 한 기기만 쓰는 사용자가 다른 기기 모듈을 import하지 않아도 되게 한다(import 부수효과 최소화).
- `py.typed` 포함, 전 공개 API 타입힌트.
- 문서: README 퀵스타트 + `docs/api/`(기존 두봇 연구 문서 흡수·갱신, 한국어+코드).
- 라이선스: MIT. (pydobot 코드 직접 복사 시 해당 라이선스 준수 — 단 본 라이브러리는 명세 기반 독자 재구현 지향)
- CI(선택): GitHub Actions — lint(ruff)/type(mypy)/test(pytest), HW 테스트 제외.

---

## 9. 멀티에이전트 구현 전략 (개요 — 상세는 implementation plan에서)

병렬화 가능한 독립 단위로 분해(공유 상태 최소). 대략:
- **공통 기반**(먼저): `protocol.py`, `ids.py`, `structures.py`, `enums.py`, `exceptions.py` — 이후 모든 작업의 토대.
- **병렬 가능**: arm 카테고리별 lowlevel(motion/io/sensors/effector/device/wifi), go(client/magiciango/navigation/geometry), 각 테스트, 예제, 문서.
- **검증**: 각 산출물에 대해 프로토콜 왕복 테스트 + DobotDllType 커버리지 대조 + 적대적 리뷰.
- 실제 작업은 `superpowers:writing-plans` 으로 단계별 계획 작성 후, 멀티에이전트(Workflow/subagent)로 실행.

---

## 10. 미해결/구현 시 확정 항목

1. **프로토콜 ID 정확값** — 일부는 공개자료 교차검증 필요(§3.3 완화책).
2. **pydobot 호환 별칭** 범위 — 최소(move/suck/grip/pose/speed/wait/eio)로 시작.
3. **GO `move_direct` direction enum, running_mode 의미, buzzer/rgb cycle 의미** — 펌웨어 미확정, 실측 표기 유지.
4. **패키지명 `dobotkit`** — PyPI 가용성 확인 권장(대체: `dobotpy`, `dobot-full`, `pandobot`).
