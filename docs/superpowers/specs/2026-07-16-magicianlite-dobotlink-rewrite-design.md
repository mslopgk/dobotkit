# 설계: Magician Lite 팔 스택 — DobotLink 기반 클린 재작성

- 날짜: 2026-07-16
- 대상: `dobotkit` — 팔 스택을 시리얼 → **DobotLink RPC** 로 전환, `MagicianLite`로 재명명
- 상태: 설계 확정(그릴 완료), 구현 예정
- 관련: [CONTEXT.md](../../../CONTEXT.md), 근본원인 조사(commit 68ae248 이후 세션)

## 배경 / 결정 근거

기존 dobotkit 팔은 순수 시리얼(`transport.py` + 프레임 프로토콜)로 팔 컨트롤러에
직접 붙는다. 그러나 Magician Lite는 **Controller(master) + MagicBox(slave -1)**
토폴로지라, 센서/서보/아날로그 등 MagicBox 경유 주변장치는 **slave 라우팅**이
있어야 읽히는데 그 와이어 포맷은 벤더 DLL 바이너리에만 존재한다(직접 시리얼로
재현 불가, 실기로 규명). 반면 **DobotLink**(데스크톱 서비스)는 이 라우팅을 내부
처리하며, PoC에서 `dobotlink.Magician.*` RPC로 팔 모션·IO·ADC(가변저항 addr24,
값 0↔1642 추종)를 실기 구동 확인했다. GO 스택은 이미 DobotLink를 쓴다.

→ 팔도 DobotLink로 전환한다. 트레이드오프는 **DobotLink 실행 필수** 하나이며,
커리큘럼 PC엔 이미 설치돼 있어 실질 부담이 없다. DLL은 쓰지 않는다(라이브러리
패키징 단순 유지).

## 목표

Magician Lite의 **일반 사용 기능만** 깨끗하게 제공: 움직임 / 흡착·그리퍼·서보 /
전체 센서. 시리얼 엔진과 미사용 기능은 제거. 고수준 API는 친숙하게 유지.

## 아키텍처

```
Python → DobotLinkClient(ws://localhost:9090) → DobotLink → 팔 + MagicBox
```

패키지(클린):

```
src/dobotkit/
├── __init__.py        # MagicianLite, MagicianGO, enums, exceptions 노출
├── enums.py           # (재사용)
├── exceptions.py      # (재사용)
├── link.py            # DobotLinkClient (go/client.py에서 공용으로 승격)
├── arm/
│   ├── __init__.py
│   ├── magicianlite.py  # 고수준 MagicianLite (컨텍스트매니저·모션·그룹)
│   ├── commands.py      # 얇은 dobotlink.Magician.* RPC 래퍼 (구 lowlevel 대체)
│   └── groups.py        # EffectorGroup / SensorGroup / IOGroup 파사드
└── go/                # (그대로) magiciango.py, navigation.py — link.py 공용 사용
```

**제거**(git 이력 보존): `arm/transport.py`, `arm/protocol.py`, `arm/structures/`,
`arm/lowlevel/`, `arm/queue.py`, `arm/ids.py`. (알람 디코드는 필요 시 유지)

**재사용**: `DobotLinkClient`(→ `link.py`), `enums`, `exceptions`, groups 패턴,
GO 테스트의 가짜-웹소켓 방식.

## 공개 API (친숙하게 유지)

```python
import dobotkit
with dobotkit.MagicianLite(port="COM8") as arm:   # port="auto"면 SearchDobot
    arm.home()
    arm.move_to(220, 0, 40, wait=True)
    arm.suck(True)
    v = arm.sensors.adc(port=3)        # 가변저항 등 아날로그
    btn = arm.sensors.di(port=1)       # 디지털 입력
```

- 내부: `MagicianLite(port)` → `DobotLinkClient` 접속 + `Magician.ConnectDobot(portName=port)`.
- `__exit__`: 큐 정지 + `Magician.DisconnectDobot` + 소켓 close (예외에도 항상).
- 저수준 `commands.py`는 `client.call("Magician.<SDK명>", portName=..., **params)` 래퍼.

## 기능 범위 (그릴 확정)

**포함**
- 움직임: `home`, `move_to`, `move_relative`, `pick_and_place`, `get_pose`, `set_speed`
- 이펙터: `suck`(흡착), `grip`(그리퍼), `servo`(외부 서보)
- 센서 **전부**: `adc`(아날로그) · `di`(디지털) · `color` · `infrared` ·
  Seeed Grove `distance`/`temp`/`light`/`rgb`
- IO: `io.set_do` / `get_di` / `get_adc` / `pwm` / `multiplexing`
- 안전: 알람 확인, 큐 제어(내부)

**제외**
- 시리얼 엔진 전체 · CP(연속경로) · ARC(원호) · JOG(수동조그)
- 리니어레일(with-L) · WiFi 설정 · 캘리브레이션류(auto-leveling/angle-sensor/kinematics/HHT)
- 컨베이어(EMotor)/TRIG · 레이저 · 버저(SDK에 없음) · 디바이스 관리 잡다 · pydobot 별칭

## 연결 / wait / 에러 모델

- **연결**: `port="auto"` → `Magician.SearchDobot`로 첫 포트 선택; 명시 포트도 허용.
- **wait 모션**: `wait=True`면 `QueuedCmdStart` + 큐 인덱스 폴링으로 완료 대기.
  구체 RPC(현재 인덱스 조회 메서드명·반환형)는 **구현 때 실기 검증**.
- **DobotLink 미실행**: `DobotConnectionError`로 명확히("DobotLink 실행 확인").
  기존 `DobotLinkClient` 동작 그대로.

## 테스트

- 가짜 `DobotLinkClient`(호출 기록 / 정해진 dict 반환)로 단위 테스트 — GO 방식.
- 고수준 각 메서드가 올바른 `Magician.*` RPC + 파라미터로 위임하는지 검증.
- 연결/해제 컨텍스트매니저, wait 폴링 로직, 에러 전파.
- 실기 스모크(선택): 실제 DobotLink+팔로 move/adc/sensor 확인.

## 구현 때 실기로 확인할 항목 (미확정)

1. **센서 RPC 가용성**: `Magician.GetColorSensor` / `GetInfraredSensor` /
   `GetSeeed*` 가 DobotLink에 실제 존재/동작하는지. 되는 것만 넣고, 안 되면 해당
   센서는 "DobotLink 미지원"으로 문서화(범위 축소).
2. **아날로그 읽기 절차**: `SetIOMultiplexing(ADC)` 선행 필요 확인(PoC상 필요).
   포트↔주소 매핑(가변저항=addr24=MagicBox 포트3) 일반화.
3. **wait 폴링**: 큐 인덱스 조회 RPC 명/반환형, 완료 판정.
4. **명령 표면 차이**: Lite가 클래식 Magician 대비 미지원 명령 있는지(각 기능 검증).

## 문서

- `README` / quickstart: "DobotLink 실행 필수", `MagicianLite` 예제로 개편.
- `CHANGELOG`: 팔 스택 DobotLink 전환 + `Magician`→`MagicianLite` 재명명 기록.
- 시리얼 관련 문서 제거/갱신.

## 마이그레이션 메모

- 클래스 `Magician` → `MagicianLite`. 기존 커리큘럼 호환 코드가 있으면 별칭 검토
  (현재 없음으로 확인되면 별칭 없이 깨끗이).
- `dobotkit` 이름·GO 스택·enums/exceptions는 유지.
