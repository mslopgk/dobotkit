# dobotkit GO — 검증 필요 항목 총정리

> 최종 갱신: 2026-07-04. 이 문서는 dobotkit GO 스택에서 **실기 검증이 끝나지 않은 모든 항목**의
> 단일 목록입니다. 사실의 원천: 채굴된 와이어 스펙(DobotEDU 파이썬 래퍼 + 공식 CHM + DobotLink
> 플러그인 문자열 테이블 3중 교차검증) + 기존 실기 세션 기록.
> 관련 문서: [cheatsheet_go.md](cheatsheet_go.md) · [api/go.md](api/go.md)

---

## A. HANG 격리 5종 (`unsafe_` 접두 기존 명령)

대상: `unsafe_rotate` · `unsafe_move_dist` · `unsafe_arc_rad` · `unsafe_arc_cent` · `unsafe_increment_closed_loop`

| 항목 | 내용 |
|---|---|
| **격리 이유** | 실기에서 **완료 콜백 미도달 실측**. 이 명령들은 `isQueued=True, isWaitForFinish=True`(코드의 `_WAIT`)로 큐에 넣고 완료 신호를 기다리는데, 이 기체에서 완료 신호가 오지 않아 타임아웃(~7일)까지 멈춤(HANG). |
| **재검증 조건** | GO **펌웨어 업데이트 시에만** 재시도 가치 있음(펌웨어 버전은 `device_fw_software_version()`으로 기록). 같은 펌웨어에서 반복 프로브는 무의미. |
| **재시도 절차** | ① `clearance_ok` 인터록 통과 확인 → ② 저수준 `client.call`을 **짧은 타임아웃**(예: `DobotLinkClient(timeout=5.0)`)으로 잡고 최소 각도/거리(회전 10°, 이동 30mm 이하)로 **1회만 프로브** → ③ `DobotTimeoutError`가 나면 즉시 `emergency_stop()` 후 종료, HANG 판정 유지 → ④ 완료 응답이 오면 펌웨어 버전과 함께 기록하고 재분류 논의. |
| **안전 대체재** | `PreciseMover.goto_distance` / `turn_degrees`, `WaypointNav.go_to`(연속 `move()` + 오도미터/IMU 피드백, 타임아웃·클리어런스·비상정지 내장). |

신규 49종 중 `unsafe_move_pos`(SetMovePos)도 **동일한 큐드+대기 계열로 확정**(채굴: DobotLink 액션리스트에 포함, isQueued/isWaitForFinish 기본 true, DobotEDU는 timeout 604800000ms 전송)되어 같은 격리 정책을 적용합니다(→ C절).

## B. 기존 구현 중 미검증 항목

| 항목 | 미검증 내용 | 비고 |
|---|---|---|
| `coord_closed_loop` | 실효 동작 자체 미확인 | `_WAIT` 플래그 미전송이라 HANG 계열은 아님(코드 확인). 실제로 무엇을 하는지는 실측 필요 |
| `set_running_mode(mode)` | `mode` 값의 의미(0/1 = NORMAL/SAFE 추정) 미확정 | CHM keyword 표기 모순 있음(runningState vs runningMode). 와이어 파라미터는 `runningMode`로 확정(DobotEDU) |
| `car_camera_obj()` | DL(딥러닝) 검출 실동작 미확인 | 반환 구조는 방어적 읽기 전제 |
| `arm_camera_obj()` / `arm_camera_tag()` | 참조 기체 ARM 캠 405 비활성 — 정상 기체에서의 동작 미확인 | ARM 캠 활성 기체 확보 시 검증 |
| `move_direct(direction, speed)` | 실행 로그 없음 + `dir` 값 매핑(0=전진 추정) 미확정 | 검증 전엔 `forward()`/`move()` 사용 |
| `line_error(center)` 조향 부호 | P제어 `move(x=v, r=-kp*err)`의 `-` 부호가 기체별로 맞는지 미확인 | H3 차시 인수인계에도 미완 항목으로 기재됨 |
| `WaypointNav` 전체 | e2e 신뢰도는 **오도미터 mm 스케일 캘리브레이션이 전제** | 오도미터 3~4배 과소집계 실측 — 자로 실측 캘리브레이션 전엔 절대좌표 이동 오차 큼 |
| `trace_angle()` vs `firmware_trace_angle()` | **의미 대조 미실시** | `trace_angle`=GetCarCameraAngle(카메라 라인각). `firmware_trace_angle`=GetTraceAngle — 와이어 존재 자체가 미확인(→ C절). 둘이 같은 값인지/별개 소스인지 실기 대조 필요 |

## C. 신규 구현 49종 (2026-07-04 추가 — 전부 실기 미검증)

와이어 시그니처는 3중 소스로 채굴·교차검증되었으나 **하드웨어에서 단 한 번도 실행되지 않았습니다**
(모든 docstring에 "hardware-unverified (2026-07-04)" 명시). 파라미터 "확정"은 채굴 근거 2개 이상
일치를 뜻하며, "미확정"은 `**params` 패스스루로 구현되어 호출자가 와이어 이름을 직접 넘겨야 합니다.

### C.1 진단·조회 (읽기 전용 — 검증 위험도 최저)

| 메서드 | RPC | 파라미터 | 권장 검증 절차 |
|---|---|---|---|
| `get_alarm_info()` | GetAlarmInfo | 확정(portName만) | 호출 → `{warning: [...]}` 형태 확인 |
| `clean_alarm_info()` | CleanAlarmInfo | 확정 | 알람 존재 시 호출 → `get_alarm_info` 재조회로 소거 확인 |
| `running_state()` | GetRunningState | 확정(반환 필드 `runningState` 추정) | 호출 → 반환 dict 전체 로깅(필드명 확인). CHM 페이지 내용 뒤엉킴(SetCommuTimeout) — 플러그인 테이블만이 근거 |
| `stall_protection()` | GetStallProtection | 확정 | 호출 → `{isHappened:int}` 확인 |
| `off_ground()` | GetOffGround | 확정 | 평지 호출(0 기대) → 들어올려 재호출(1 기대) |
| `get_move_speed()` | GetMoveSpeed | 확정 | 정지 상태 호출(0,0,0 기대) → `drive_for` 중 호출로 x/y/r cm/s 대조 |
| `get_running_mode()` | GetRunningMode | 확정(반환 필드 `runningMode` vs `runningState` 모순 — 방어적 읽기) | 호출 → 반환 dict 전체 로깅 → `set_running_mode` 후 변화 확인 |

### C.2 트레이스 확장

| 메서드 | RPC | 파라미터 | 권장 검증 절차 |
|---|---|---|---|
| `firmware_trace_angle(**params)` | GetTraceAngle | **미확정** (`**params` 패스스루) | ⚠️ **와이어에 존재하지 않을 가능성 높음** — DobotLink 플러그인 메서드 테이블·JS SDK에 부재, CHM은 파일명만 있고 내용은 GetImuAngle. 라인 위에서 호출 → 405/에러면 "와이어 미구현" 확정 기록. 응답이 오면 같은 시점의 `trace_angle()`(GetCarCameraAngle)과 값 대조(B절 의미대조 항목) |
| `set_trace_line_info(lineInfo)` | SetTraceLineInfo | 확정(`lineInfo:int`) | 라인 트레이싱 중 값 변경 → 거동 차이 관찰. `lineInfo` 값 의미는 미확정 |

### C.3 절대주행 (⚠️ 모션 — 마지막에 검증)

| 메서드 | RPC | 파라미터 | 권장 검증 절차 |
|---|---|---|---|
| `unsafe_move_pos(x, y, s)` | SetMovePos | 확정(x,y: 목표 cm, s: 속도 0-100 cm/s + 큐 플래그) | **큐드+대기 확정 → HANG 추정.** A절 재시도 절차 준용: 사방 클리어 + 짧은 타임아웃 클라이언트 + 소거리(예: x=5cm) 1회 프로브 + finally `emergency_stop()`. DobotEDU는 사전에 `GetSpeedometer`+`SetRotate(-yaw)`로 방향 정렬함을 참고 |
| `move_speed_time(time, x, y, r, isAck=False)` | SetMoveSpeedTime | 확정(time:s, x/y:cm/s, r:deg/s, isAck 선택). 라이브러리가 x/y/r ±30·time 0~5초 클램프 | 비큐드 확정(JS 조그 구현이 사용) — HANG 계열 아님. 사방 클리어 후 `move_speed_time(time=0.5, x=10)` 식 짧은 프로브 → time 경과 후 자동 정지 여부 확인(데드맨 대체 후보) |
| `set_origin_point(enable)` | SetOriginPoint | 확정(enable:int 1/0) | 비큐드 확정. 호출 후 `odometer()` 변화 관찰(원점 기능의 실효 의미 미확정) |

### C.4 카메라 확장 (Car 7종 + Arm 6종 — 읽기 getter 먼저)

| 메서드 | RPC | 파라미터 | 권장 검증 절차 |
|---|---|---|---|
| `car_camera_color()` | GetCarCameraColor | 확정 | 색 블록 앞에 두고 호출 → `{count, color_obj:[{x,y,w,h,id}]}` 방어적 읽기(count=0이면 배열 키 부재 가능) |
| `car_camera_tag()` | GetCarCameraTag | 확정 | AprilTag 앞에서 호출 → `{count, aptag_obj:[{x,y,w,h,id,rot}]}` 확인 |
| `get_car_camera_model()` | GetCarCameraRunModel | 확정 | 호출 → `{runModelIndex:int}` 기록 |
| `set_car_camera_model(runModelIndex)` | SetCarCameraRunModel | 확정 | 기존 인덱스 기록 → 변경 → getter 재조회 → **원복** |
| `get_car_camera_calibration_mode()` | GetCarCameraCalibrationMode | 확정(반환 `isEnableCali` 추정 — 방어적 읽기) | 호출 → 반환 dict 로깅 |
| `set_car_camera_calibration_mode(isEnableCali)` | SetCarCameraCalibrationMode | 확정(1 진입/0 종료) | 진입 → getter 확인 → **반드시 0으로 종료** |
| `camera_calibration_data(april_list, device_list)` | GetCameraCalibrationData | 확정(9점 JSON 문자열 2개 필수 — Get이지만 입력 필요) | 캘리브레이션 9점 수집 후 호출 → `{data:"max_x_err:..."}` 문자열 파싱 확인. DobotLink이 fit_homography.exe 실행 |
| `arm_camera_color()` | GetArmCameraColor | 확정 | 참조 기체는 ARM 캠 405 예상 — 405면 기체 한계로 기록 |
| `arm_camera_angle()` | GetArmCameraAngle | 확정 | 동상(`{angle:int}`) |
| `get_arm_camera_model()` / `set_arm_camera_model(runModelIndex)` | Get/SetArmCameraRunModel | 확정 | Car 캠과 동일 절차(405 가능) |
| `get_arm_camera_calibration_mode()` / `set_arm_camera_calibration_mode(isEnableCali)` | Get/SetArmCameraCalibrationMode | 확정(반환 추정) | Car 캠과 동일 절차(405 가능) |

### C.5 큐 제어

| 메서드 | RPC | 파라미터 | 권장 검증 절차 |
|---|---|---|---|
| `queued_cmd_current_index()` | GetQueuedCmdCurrentIndex | 확정(반환 `queueCmdCurrentIndex` — 'Queued' 아닌 'queue' 철자 주의) | 유휴 상태 호출 → int 확인. CHM 구명칭 GetCmdQueueCurrentIndex와 별개 — 와이어명은 이쪽 |
| `cmd_queue_available_space()` | GetCmdQueueAvailableSpace | 확정 | 호출 → `{space:int}` 확인 |
| `clean_cmd_queue()` | CleanCmdQueue | 확정 | 호출 → result true. 큐 명령 검증(unsafe_move_pos 프로브) 실패 정리용으로 먼저 확보 |
| `cmd_queue_start()` / `cmd_queue_stop()` | SetCmdQueueStart/Stop | 확정 | 유휴 상태에서 start→stop 무해 확인 |
| `cmd_queue_force_stop()` | SetCmdQueueForcelyStop | 확정 | 공식 비상정지 시퀀스의 일부(JS) — unsafe_move_pos 프로브의 탈출 수단으로 함께 검증 |

### C.6 MagicBox / 상태 제어

| 메서드 | RPC(네임스페이스) | 파라미터 | 권장 검증 절차 |
|---|---|---|---|
| `magic_box_mode()` | GetMagicBoxMode (MagicianGO) | 확정 | 호출 → `{mode:int}` 확인 |
| `magic_box_num()` | GetMagicBoxNum (MagicianGO) | 확정(반환 num vs device hex 모순 — 방어적 읽기) | 호출 → 반환 dict 전체 로깅 |
| `stop_point_state()` | GetStopPointState (**MagicBox**) | 확정 | 호출 → `{result:bool}` 확인 |
| `set_stop_point_param(scopeErr, stopErr)` | SetStopPointParam (**MagicBox**) | 확정(기본 40/2) | 기본값 세팅 → result true |
| `set_stop_point_server(PointX, PointY)` | SetStopPointServer (**MagicBox**) | 확정(파이썬 인자명도 와이어 그대로 `PointX`/`PointY` 대문자 P) | ⚠️ **단위(cm/mm) 문서 미확정** — 작은 값(5 이하)으로만. 이 유닛에서 미정지/HANG 가능성 기존 경고 승계 |
| `set_running_state(**params)` | SetRunningState (MagicianGO) | **미확정** (`**params` 패스스루, `runningState:int` 추정) | JS 호출부·CHM 페이지 부재(문자열 테이블 인접성만). 다른 검증 전부 끝난 뒤 `runningState=현재값`으로 무해 프로브 |

### C.7 출력 / 디바이스

| 메서드 | RPC | 파라미터 | 권장 검증 절차 |
|---|---|---|---|
| `set_light_prompt(index)` | SetLightPrompt | 확정(0없음/1 USB/2 저전량/3 핸들/4 스크립트) | 각 index 순회하며 LED 표시 변화 관찰 → 0 원복. 저위험 set |
| `product_name()` | GetProductName | 확정 | 호출 → "MagicianGo" 기대(JS의 유효 디바이스 판정 기준) |
| `device_fw_software_version()` | GetDeviceFwSoftwareVersion | 확정(반환 majorVersionNum/secondVersionNum/revisionVersionNum/previousVersionNum — JS 확정, CHM 예시는 구식) | 호출 → 4필드 조립 `V{maj}.{sec}.{rev}.{prev}` 기록(A절 재검증 기준값) |
| `device_fw_hardware_version()` | GetDeviceFwHardwareVersion | 확정(반환 필드군 추정 — 방어적 읽기) | 동상 |
| `device_id()` | GetDeviceID | 확정 | 호출 → `{deviceID:[int,...]}` 확인 |
| `get_device_name()` / `set_device_name(deviceName)` | Get/SetDeviceName | 확정 | get → set(새 이름) → get 확인 → **원복** |
| `get_device_sn()` / `set_device_sn(deviceSN)` | Get/SetDeviceSN | 확정 | get만 권장. **SN 덮어쓰기는 원복 불가 위험 — set은 검증 생략 권장** |
| `device_time()` | GetDeviceTime | 확정 | 호출 → `{gSystick:int, passtime:"hh:mm:ss.z"}` 확인 |
| `device_reboot()` | DeviceReboot | 확정 | ⚠️ **호출 즉시 재부팅 → 연결 끊김.** 세션 마지막에만. 재부팅 후 재연결(`connect()`)까지가 검증 |
| `heartbeat()` | HeartBeat | 확정 | 호출 → result true(공식 JS는 2000ms 타임아웃, 3회 실패 시 연결끊김 처리 — keepalive 루프 구현 시 참고) |

### 안전한 검증 순서 (권장)

1. **읽기 전용**: C.1 진단 6종 → C.7 디바이스 getter(product_name, fw 버전 2종, device_id, get_device_name, get_device_sn, device_time, heartbeat) → C.4 카메라 getter 전종 → C.5 큐 getter 2종 → C.6 magic_box/stop_point getter.
2. **저위험 set**: set_car/arm_camera_model(원복 포함) → set_light_prompt(0 원복) → set_device_name(원복) → 카메라 캘리브레이션 모드(0 종료 필수).
3. **미확정 패스스루 프로브**: firmware_trace_angle(라인 위, 에러 기대치 포함) → set_running_state(현재값 재전송).
4. **모션 (마지막, 사방 클리어 필수)**: move_speed_time 짧은 프로브(0.5s) → set_origin_point → stop_point 3종(작은 좌표) → **unsafe_move_pos는 맨 끝**: A절 절차(짧은 타임아웃 + 소거리 1회 + `cmd_queue_force_stop`/`clean_cmd_queue` 탈출로 확보 + finally `emergency_stop`).
5. **파괴적**: device_reboot(세션 종료 직전). set_device_sn은 하지 않음.

## D. 다음 실기 세션 체크리스트 (우선순위순)

- [ ] **1. 오도미터 mm 스케일 캘리브레이션** — 자로 실측 거리 vs `odometer()` 변위 비율 산출(3~4배 과소집계 의심 해소). WaypointNav 신뢰의 전제 조건.
- [ ] **2. firmware_trace_angle 대조** — 라인 위에서 `firmware_trace_angle()` 호출(미구현 에러 여부 확정) + `trace_angle()`과 동시 로깅으로 의미 대조. `line_error` 조향 부호도 같은 셋업에서 확인.
- [ ] **3. 진단·조회 6종+α** — C.1 전체 + heartbeat + fw 버전 기록(읽기 전용, 10분 내 완료 가능).
- [ ] **4. 카메라 확장** — Car 캠 color/tag/model getter → set_model 원복 → (여유 시) 캘리브레이션 모드. ARM 캠은 405 재확인만.
- [ ] **5. WaypointNav e2e** — 1번 캘리브레이션 결과 반영 후 매트 왕복(`set_start` → `go_to` 2점 → `residual_cm` 기록).
- [ ] (여유 시) C절 4단계 모션 프로브, (세션 종료 직전) device_reboot 재연결 검증.
