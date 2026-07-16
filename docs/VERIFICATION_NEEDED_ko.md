# dobotkit GO — 검증 필요 항목 총정리

> 최종 갱신: 2026-07-16 (GO 스택 정리 반영).
> 이 문서는 dobotkit **GO 스택**에서 실기 검증이 끝나지 않은 항목의 단일 목록입니다.
> 관련 문서: [cheatsheet_go.md](cheatsheet_go.md) · [api/go.md](api/go.md)

---

## 정리(2026-07-16)로 해소된 항목

이전 판(2026-07-04)이 "검증 필요"로 나열했던 확장 API 대부분은 **검증 대신 제거**되어
더 이상 라이브러리에 존재하지 않습니다:

- 펌웨어 내장 폐루프/큐드 주행(`unsafe_rotate`/`unsafe_move_dist`/`unsafe_arc_*`/
  `unsafe_increment_closed_loop`/`unsafe_move_pos`, `move_direct`, `move_speed_time`,
  `set_origin_point`, `set_running_mode`) — 이 기체에서 HANG이 실측돼 제거. 정밀 이동은
  `PreciseMover`(연속 `move()` + 센서 피드백)로 대체.
- 라인트레이싱 전체 · 카메라 전체 · 펌웨어 큐 제어 · MagicBox Stop-Point · 디바이스 관리
  RPC · `imu_speed`/`get_move_speed`/`get_running_mode`/`set_light_prompt`/
  `set_running_state` · `WaypointNav` 클래스 — 전부 제거.

## 실기 검증 완료 항목

- **주행(연속)·본체센서(초음파/오도미터/IMU/배터리)·RGB/부저** — 검증 완료(2026-07-03).
  회전 방향 `r+`=반시계(CCW) 확정.
- **MagicBox 주변장치 읽기(`go.sensors`/`go.io`)** — 검증 완료(2026-07-16). `MagicBox.*`
  네임스페이스로 `MagicianGO` 단일 연결에서 공존. 가변저항 Grove 4번 = **EIO 핀 22**,
  `go.sensors.adc(22)` 실값(≈426, 0~4095) 확인. ADC/DI/DO/PWM=EIO 핀 1~26,
  컬러/적외/Seeed=Grove 커넥터 1~6. 미연결 시 `None`+경고.
- **`magic_box_mode()`/`magic_box_num()`** — 실기 응답 확인(mode 2, num/device id).

## 남은 미검증 항목 (소수)

아래 진단/상태 getter는 유지되었으나 반환 형태가 소스에서 방어적으로만 파싱됩니다
(정상 동작하나 반환 필드 스키마가 실기로 완전 확정되진 않음). 실기 세션 시 값 형태 확인 권장:

| 메서드 | RPC | 기대 형태(방어적) |
|---|---|---|
| `get_alarm_info()` | `GetAlarmInfo` | `{"warning": [...]}` |
| `clean_alarm_info()` | `CleanAlarmInfo` | (알람 해제) |
| `running_state()` | `GetRunningState` | `{"runningState": int}` |
| `stall_protection()` | `GetStallProtection` | `{"isHappened": int}` |
| `off_ground()` | `GetOffGround` | `{"isHappened": int}` |

## 다음 실기 세션 체크리스트

1. 위 5개 진단 getter의 실제 반환 형태 확인(있으면 docstring/타입 확정).
2. `PreciseMover.goto_distance`의 오도미터 mm 스케일 실측 보정(자에 대고 측정 — 3~4배
   과소계수 의심, `odometer()` docstring 참고).
