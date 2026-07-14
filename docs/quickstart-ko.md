# dobotkit 빠른 시작 (Magician GO 주행 카)

> 이 문서는 사람과 **LLM 모두를 위한** 접지(grounding) 문서입니다. AI에게 GO 제어
> 코드를 부탁할 때 이 문서(또는 [cheatsheet_go.md](cheatsheet_go.md))를 프롬프트에
> 그대로 붙여 넣으면, 존재하지 않는 API를 지어내는 일을 막을 수 있습니다.
> 여기 적힌 규칙·상수는 2026-07-02 실제 하드웨어로 검증된 값입니다.

## 설치

아직 PyPI에 게시되지 않았습니다. 로컬 체크아웃에서 설치하세요:

```bash
pip install -e path/to/dobotkit     # 예: pip install -e C:/Users/user/dobot-main/dobotkit
```

## 연결 3단계

1. **DobotLink.exe 실행** — GO는 직접 시리얼이 아니라 DobotLink(ws://localhost:9090)
   JSON-RPC 를 통해서만 제어됩니다. (DobotLab을 켜도 내부적으로 DobotLink가 뜹니다.
   단, DobotLink는 시작 시 모든 COM 포트를 선점하므로 팔(Magician Lite)을 직접
   시리얼로 쓰는 프로그램과는 동시에 사용할 수 없습니다.)
2. **GO 전원 ON + 무선 동글 연결** — 전원이 켜져야 포트(관례상 COM5)가 나타납니다.
3. **`MagicianGO.open()`** — 연결 + 링크 검증(배터리 읽기)까지 한 줄:

```python
from dobotkit.go import MagicianGO

with MagicianGO.open(port_name="COM5") as go:   # 연결 + battery() 검증
    print(go.battery())                          # {'powerVoltage': 11.7, ...}
    go.drive_for(x=15, seconds=1.0)              # 1초 전진 후 확실히 정지
# with 블록이 어떻게 끝나든(예외/Ctrl-C 포함) 비상정지 + 트레이싱 OFF + 큐 강제정지 + 비상정지 + 소켓 종료
```

## 좌표·단위 규약

| 항목 | 규약 |
|---|---|
| `move(x, y, r)` | `x+` 전진, `y+` 좌횡이동(메카넘), `r+` 반시계 회전. **정지 명령 전까지 계속 달림** |
| 속도 단위 | 펌웨어 정의·미확정. **8~30이 실용 범위**, 라이브러리가 ±30으로 강제 클램프 |
| 오도미터 | mm / deg (월드 프레임, `set_odometer`로 영점화) |
| `WaypointNav` | **cm** 단위 (매트 좌표) — `PreciseMover`는 **mm**. 혼동 주의 |
| 초음파 | cm, **40 이상은 전부 40으로 클램프**(하드웨어 상한). 응답 이상 시 `None` |
| 라인 카메라 | `trace_angle()` → `{"angle", "count"}`. `count==0` = 라인 없음. 중앙값은 기체별 실측(참조 기체 ≈ 245) |

## 3대 금지사항 (안전 규칙)

1. **`unsafe_` 접두 계열 직접 호출 금지 (현재 6종 전부)** — `unsafe_rotate`/`unsafe_move_dist`/
   `unsafe_arc_rad`/`unsafe_arc_cent`/`unsafe_increment_closed_loop`는 이 기체에서
   **행(HANG)이 실측**된 펌웨어 큐 명령이고, `unsafe_move_pos`(신규 2026-07-04)도 동일한
   큐드+대기 계열로 확정되어 같은 위험이 추정됩니다.
   회전은 `PreciseMover.turn_degrees`, 직진은 `PreciseMover.goto_distance`를 쓰세요.
   (구명칭 `rotate` 등은 경고를 내며 동작하는 폐기 예정 별칭입니다.)
2. **무한 루프 금지** — 주행 루프는 반드시 `for i in range(n):` 같은 유한 루프로.
3. **`with` 없이 `move()` 금지** — 항상 `with MagicianGO.open(...) as go:` 안에서.
   크래시해도 로봇이 서 있는 것은 컨텍스트 매니저 덕분입니다. 한 번의 짧은 주행은
   `go.drive_for(x=..., seconds=...)`(데드맨 헬퍼, 최대 5초)를 우선 사용하세요.

## 검증된 라인 순찰 (펌웨어 내장)

DobotLab의 '라인 순찰' 버튼과 동일한 시퀀스입니다. 공식 파라미터: 속도 20, PID (0.5, 0, 0.5).
(PID를 50처럼 크게 주면 요동치다 라인을 이탈합니다 — 실측.)

```python
import time
from dobotkit.go import MagicianGO

with MagicianGO.open(port_name="COM5") as go:
    go.trace_speed(20)
    go.trace_pid(0.5, 0, 0.5)
    go.auto_trace(True)          # 내부적으로 isTrace=1(int)+type=0 — 검증된 포맷
    for _ in range(200):         # 유한 루프: 최대 20초
        u = go.ultrasonic()
        if u is None or min(u.values()) < 15:   # 모르면 멈춘다
            break
        time.sleep(0.1)
    go.auto_trace(False)
```

## 자체 P제어 라인트레이서 (교육용 최소 예제)

펌웨어를 끄고 같은 센서로 직접 조향합니다. `line_error()`가 인지-판단의 경계입니다.

```python
import time
from dobotkit.go import MagicianGO

KP, SPEED, CENTER = 0.3, 12, 245   # CENTER는 로봇을 라인에 올려두고 실측할 것

with MagicianGO.open(port_name="COM5") as go:
    for _ in range(200):                    # 유한 루프
        err = go.line_error(center=CENTER)  # None = 라인 없음
        if err is None:
            go.stop()                       # 안 보이면 서 있는 게 안전
            continue
        go.move(x=SPEED, r=-KP * err)       # 조향 부호는 기체별 확인:
        time.sleep(0.1)                     # 라인 오른쪽으로 틀었을 때
                                            # angle > CENTER 인지 먼저 관찰
```

## 좌표 주행 (웨이포인트)

```python
from dobotkit.go import MagicianGO, WaypointNav

with MagicianGO.open(port_name="COM5") as go:
    nav = WaypointNav(go)
    nav.set_start(20, 20, heading_deg=0)    # 필수! 없으면 go_to가 예외
    for wx, wy in [(100, 20), (100, 80)]:
        nav.go_to(wx, wy, raise_on_abort=True)   # 실패를 조용히 넘기지 않음
```

## 자주 겪는 문제

| 증상 | 원인/해결 |
|---|---|
| 연결 실패 | DobotLink.exe 미실행 → 실행 후 재시도 |
| `code 6: already opened device` | DobotLink 내부에서 포트가 선점/꼬임 — **무선 동글을 뺐다 다시 끼우면 풀림**(실측). 그래도 안 되면 GO 끈 상태에서 DobotLink 재시작 |
| `battery()` 타임아웃 | GO 전원 꺼짐/동글 미연결 (핸드셰이크는 거짓 성공 가능 — 그래서 검증이 기본) |
| 명령은 OK인데 안 움직임 | 과거 `auto_trace`의 bool 버그가 원인이었음 — 이 라이브러리는 수정 완료. 다른 스택 사용 시 isTrace가 int인지 확인 |
| P제어가 반대로 꺾음 | 조향 부호가 기체별 상이 — 위 확인 절차로 부호 결정 |
| `rotate`가 안 끝남 | 펌웨어 큐 명령 행(HANG) — `PreciseMover.turn_degrees` 사용 |
