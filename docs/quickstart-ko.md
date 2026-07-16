# dobotkit 빠른 시작 (Magician GO 주행 카)

> 이 문서는 사람과 **LLM 모두를 위한** 접지(grounding) 문서입니다. AI에게 GO 제어
> 코드를 부탁할 때 이 문서(또는 [cheatsheet_go.md](cheatsheet_go.md))를 프롬프트에
> 그대로 붙여 넣으면, 존재하지 않는 API를 지어내는 일을 막을 수 있습니다.
> 여기 적힌 규칙·상수는 2026-07-02 실제 하드웨어로 검증된 값입니다.

## 설치

```bash
pip install dobotkit
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
# with 블록이 어떻게 끝나든(예외/Ctrl-C 포함) 비상정지 + 확인용 정지 + 소켓 종료
```

## 좌표·단위 규약

| 항목 | 규약 |
|---|---|
| `move(x, y, r)` | `x+` 전진, `y+` 좌횡이동(메카넘), `r+` 반시계 회전. **정지 명령 전까지 계속 달림** |
| 속도 단위 | 펌웨어 정의·미확정. **8~30이 실용 범위**, 라이브러리가 ±30으로 강제 클램프 |
| 오도미터 | mm / deg (월드 프레임, `set_odometer`로 영점화) |
| `PreciseMover` | 거리 **mm** / 회전 **deg** (연속 `move` + 오도미터·IMU 피드백) |
| 초음파 | cm, **40 이상은 전부 40으로 클램프**(하드웨어 상한). 응답 이상 시 `None` |
| MagicBox 센서 | `go.sensors.adc/di`·`go.io.*` = **EIO 핀 1~26**; `color`/`infrared`/`distance`/`temp`/`light`/`rgb` = **Grove 커넥터 1~6**. 미연결 시 `None`+경고 |

## 3대 금지사항 (안전 규칙)

1. **정밀 이동은 `PreciseMover`로** — 회전은 `PreciseMover.turn_degrees`, 직진은
   `PreciseMover.goto_distance`(연속 `move()` + 센서 피드백)를 쓰세요. 펌웨어 내장
   폐루프 명령(`rotate`/`move_dist`/`arc_*`/`*_closed_loop`)은 이 기체에서 완료
   콜백이 오지 않아 **행(HANG)이 실측**돼 라이브러리에서 제거되었습니다.
2. **무한 루프 금지** — 주행 루프는 반드시 `for i in range(n):` 같은 유한 루프로.
3. **`with` 없이 `move()` 금지** — 항상 `with MagicianGO.open(...) as go:` 안에서.
   크래시해도 로봇이 서 있는 것은 컨텍스트 매니저 덕분입니다. 한 번의 짧은 주행은
   `go.drive_for(x=..., seconds=...)`(데드맨 헬퍼, 최대 5초)를 우선 사용하세요.

## 정밀 이동 (PreciseMover)

정확한 거리·각도가 필요하면 연속 `move()` + 오도미터/IMU 피드백으로 도는
`PreciseMover`를 씁니다. 절대 시간 타임아웃·정지 가드가 내장돼 무한 대기가 없습니다.

```python
from dobotkit.go import MagicianGO
from dobotkit.go.navigation import PreciseMover

with MagicianGO.open(port_name="COM5") as go:
    mover = PreciseMover(go)
    mover.goto_distance(300, speed=20)   # 약 300mm 전진 후 정지
    mover.turn_degrees(90, speed=20)     # +90도(반시계) IMU 폐루프
```

## MagicBox 센서 읽기

GO에 MagicBox를 달면 `go.sensors` / `go.io`로 센서를 읽습니다. `MagicianGO`로 한 번
연결하면 같은 연결에서 그대로 동작합니다(별도 MagicBox 연결 불필요). **주소 체계가
둘로 나뉩니다**:

- **아날로그/디지털/PWM**(`adc`·`di`·`set_do`·`set_pwm`·`set_multiplexing`) → **EIO 핀 1~26**
- **컬러·광전(적외)·Seeed**(`color`·`infrared`·`distance`·`temp`·`light`·`rgb`) → **Grove 커넥터 1~6**

미연결 시 `None`+`RuntimeWarning`으로 degrade하므로 수업 코드가 멈추지 않습니다.

```python
from dobotkit.go import MagicianGO

with MagicianGO.open(port_name="COM5") as go:
    v = go.sensors.adc(22)          # Grove 4번 가변저항 = EIO 핀 22 (0~4095, 실측)
    if v is not None:
        print("가변저항:", v)
    print("컬러:", go.sensors.color(1))     # Grove 1번
    print("적외:", go.sensors.infrared(2))  # Grove 2번
```

## 자주 겪는 문제

| 증상 | 원인/해결 |
|---|---|
| 연결 실패 | DobotLink.exe 미실행 → 실행 후 재시도 |
| `code 6: already opened device` | DobotLink 내부에서 포트가 선점/꼬임 — **무선 동글을 뺐다 다시 끼우면 풀림**(실측). 그래도 안 되면 GO 끈 상태에서 DobotLink 재시작 |
| `battery()` 타임아웃 | GO 전원 꺼짐/동글 미연결 (핸드셰이크는 거짓 성공 가능 — 그래서 검증이 기본) |
| 명령은 OK인데 안 움직임 | GO **본체 전원** 확인(MagicBox만 USB로 켜져 섀시가 응답 안 할 수 있음). 컨트롤러 알람은 `get_alarm_info()`/`clean_alarm_info()` |
| MagicBox 센서가 0/`None` | `adc`/`di`엔 Grove 번호가 아니라 **EIO 핀(1~26)** 을 넘겨야 함(가변저항 Grove4=EIO22). 센서 미연결이면 `None`+경고가 정상 |
| 정밀 회전/직진이 안 끝남 | 내장 폐루프는 제거됨 — `PreciseMover.turn_degrees`/`goto_distance` 사용 |
