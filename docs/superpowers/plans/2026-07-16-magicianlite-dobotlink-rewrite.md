# MagicianLite DobotLink Rewrite — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Dobot arm stack as `MagicianLite`, driven entirely through DobotLink JSON-RPC (`dobotlink.Magician.*`), removing the serial engine.

**Architecture:** `MagicianLite` (high-level) → `arm/commands.py` (thin `Magician.*` RPC wrappers) → shared `DobotLinkClient` (WebSocket to `ws://localhost:9090`). DobotLink performs the controller↔MagicBox slave routing that raw serial cannot. Groups (`effector`/`sensors`/`io`) are ergonomic facades. Unit tests use a `FakeClient` that records `(method, params)` and returns canned dicts — no socket, no hardware. A final task smoke-tests against real DobotLink + arm.

**Tech Stack:** Python ≥3.9, `websockets` (runtime), `pytest`/`mypy`/`ruff` (dev). No DLL, no `pyserial` for the arm.

## Global Constraints

- Python ≥3.9; fully type-hinted; package ships `py.typed`; `mypy --strict` clean.
- Runtime deps: `websockets` only (drop `pyserial` from arm path).
- Every RPC call goes through `DobotLinkClient.call("Magician.<Name>", portName=<port>, **params)`.
- DobotLink method names/params in this plan mirror the Dobot SDK (`DobotDllType.py`). Unit tests assert these names; **Task 9 verifies them live and fixes any mismatch**.
- Confirmed-on-hardware RPC shapes (PoC 2026-07-16): `SearchDobot`→`[{portName,status,description}]`; `ConnectDobot{portName}`→`{firmwareName,firmwareVersion,productName}`; `DisconnectDobot{portName}`→`True`; `GetPose{portName}`→`{x,y,z,r,jointAngle:[j1,j2,j3,j4]}`; `SetIOMultiplexing{portName,address,multiplex}`→`True`; `GetIOADC{portName,address}`→`{port,value}`.
- ruff line-length 100. Commit after each task.
- Only modify the `dobotkit` library. Do not touch other repo folders. Preserve git history (removed files stay recoverable).

---

### Task 1: Promote `DobotLinkClient` + test doubles to shared location

**Files:**
- Create: `src/dobotkit/link.py`
- Modify: `src/dobotkit/go/client.py` (becomes a re-export shim), `src/dobotkit/go/magiciango.py:148` (import path), `src/dobotkit/go/__init__.py` (lazy map)
- Create: `tests/conftest.py` (move `FakeWebSocket`/`FakeClient` here from `tests/go/conftest.py`)
- Modify: `tests/go/conftest.py` (import shared fakes, keep `SimulatedGo` + fixtures)

**Interfaces:**
- Produces: `dobotkit.link.DobotLinkClient` with `.connect()`, `.close()`, `.call(method, **params)`, `.notify(method, **params)`, context-manager. Behaviour identical to today's `go/client.py`.
- Produces (tests): `FakeWebSocket`, `FakeClient` importable from `tests/conftest.py`.

- [ ] **Step 1: Move client module.** `git mv src/dobotkit/go/client.py src/dobotkit/link.py`. In `link.py` fix the module docstring to say "shared DobotLink client (arm + GO)".

- [ ] **Step 2: Add compat shim.** Create `src/dobotkit/go/client.py`:

```python
"""Back-compat: DobotLinkClient moved to dobotkit.link."""
from dobotkit.link import DobotLinkClient

__all__ = ["DobotLinkClient"]
```

- [ ] **Step 3: Move shared fakes.** Create `tests/conftest.py` containing the `FakeWebSocket` and `FakeClient` classes (copy verbatim from `tests/go/conftest.py`) plus `fake_ws` and `fake_client` fixtures. In `tests/go/conftest.py`, delete those two classes and add `from tests.conftest import FakeWebSocket, FakeClient` (keep `SimulatedGo` and `sim_go`).

- [ ] **Step 4: Run the whole suite to prove the move is behaviour-preserving.**

Run: `PYTHONPATH=src python -m pytest -q`
Expected: same as baseline — `514 passed, 50 skipped`.

- [ ] **Step 5: Typecheck + lint.**

Run: `MYPYPATH=src python -m mypy && python -m ruff check src tests`
Expected: `Success` + `All checks passed!`

- [ ] **Step 6: Commit.**

```bash
git add -A && git commit -m "refactor: promote DobotLinkClient to dobotkit.link (shared by arm + GO)"
```

---

### Task 2: `arm/commands.py` — connection + queue RPC wrappers

**Files:**
- Create: `src/dobotkit/arm/commands.py`
- Test: `tests/arm/test_commands_connection.py`

**Interfaces:**
- Produces: `class ArmCommands` constructed with `ArmCommands(client, port_name)`. Methods:
  - `search() -> list` → `call("Magician.SearchDobot")` (no portName)
  - `connect() -> dict` → `call("Magician.ConnectDobot", portName=...)`
  - `disconnect() -> Any` → `call("Magician.DisconnectDobot", portName=...)`
  - `queue_clear()/queue_start()/queue_stop() -> Any` → `Magician.QueuedCmdClear/Start/Stop`
  - `current_index() -> int` → `Magician.GetQueuedCmdCurrentIndex` → reads `queuedCmdIndex` (defensive: `.get("queuedCmdIndex", 0)`)
  - internal `_call(func, **p)` → `client.call(f"Magician.{func}", portName=self.port_name, **p)`

- [ ] **Step 1: Write failing tests.**

```python
# tests/arm/test_commands_connection.py
from tests.conftest import FakeClient
from dobotkit.arm.commands import ArmCommands


def test_connect_sends_portname():
    c = FakeClient(results={"Magician.ConnectDobot": {"firmwareName": "Dobot"}})
    cmd = ArmCommands(c, "COM8")
    assert cmd.connect() == {"firmwareName": "Dobot"}
    assert c.find_call("Magician.ConnectDobot") == ("Magician.ConnectDobot", {"portName": "COM8"})


def test_search_sends_no_portname():
    c = FakeClient(results={"Magician.SearchDobot": [{"portName": "COM8"}]})
    assert ArmCommands(c, "COM8").search() == [{"portName": "COM8"}]
    assert c.find_call("Magician.SearchDobot") == ("Magician.SearchDobot", {})


def test_current_index_reads_field():
    c = FakeClient(results={"Magician.GetQueuedCmdCurrentIndex": {"queuedCmdIndex": 7}})
    assert ArmCommands(c, "COM8").current_index() == 7
```

- [ ] **Step 2: Run to verify failure.** Run: `PYTHONPATH=src python -m pytest tests/arm/test_commands_connection.py -q` → FAIL (`No module named dobotkit.arm.commands`).

- [ ] **Step 3: Implement.**

```python
# src/dobotkit/arm/commands.py
"""Thin dobotlink.Magician.* RPC wrappers for the Magician Lite arm."""
from __future__ import annotations
from typing import Any, List
from dobotkit.link import DobotLinkClient


class ArmCommands:
    """1:1 wrappers over the arm's DobotLink RPC surface."""

    def __init__(self, client: DobotLinkClient, port_name: str) -> None:
        self._client = client
        self.port_name = port_name

    def _call(self, func: str, **params: Any) -> Any:
        params["portName"] = self.port_name
        return self._client.call(f"Magician.{func}", **params)

    # -- connection --
    def search(self) -> List[Any]:
        return self._client.call("Magician.SearchDobot")

    def connect(self) -> Any:
        return self._call("ConnectDobot")

    def disconnect(self) -> Any:
        return self._call("DisconnectDobot")

    # -- queue --
    def queue_clear(self) -> Any:
        return self._call("QueuedCmdClear")

    def queue_start(self) -> Any:
        return self._call("QueuedCmdStart")

    def queue_stop(self) -> Any:
        return self._call("QueuedCmdStop")

    def current_index(self) -> int:
        resp = self._call("GetQueuedCmdCurrentIndex")
        return int(resp.get("queuedCmdIndex", 0)) if isinstance(resp, dict) else int(resp or 0)
```

Also create empty `src/dobotkit/arm/__init__.py` if the old one referenced removed modules — replace its body with `from dobotkit.arm.magicianlite import MagicianLite` **only in Task 8** (leave a minimal `__all__ = []` for now to keep imports clean).

- [ ] **Step 4: Run tests.** Run: `PYTHONPATH=src python -m pytest tests/arm/test_commands_connection.py -q` → PASS.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat(arm): ArmCommands connection + queue RPC wrappers"`

---

### Task 3: `arm/commands.py` — pose + motion + params

**Files:**
- Modify: `src/dobotkit/arm/commands.py`
- Test: `tests/arm/test_commands_motion.py`

**Interfaces:**
- Consumes: `ArmCommands._call` (Task 2).
- Produces:
  - `get_pose() -> dict` → `Magician.GetPose` (returns `{x,y,z,r,jointAngle}`)
  - `set_ptp_cmd(mode, x, y, z, r, queued=True) -> int` → `Magician.SetPTPCmd{ptpMode,x,y,z,r,isQueued}`, returns `queuedCmdIndex`
  - `set_home_params(x,y,z,r,queued=True) -> Any`, `set_home_cmd(queued=True) -> int`
  - `set_ptp_common_params(velocity, acceleration) -> Any`, `set_ptp_coordinate_params(v,a) -> Any`
  - `set_wait_cmd(ms, queued=True) -> int`

- [ ] **Step 1: Write failing tests.**

```python
# tests/arm/test_commands_motion.py
from tests.conftest import FakeClient
from dobotkit.arm.commands import ArmCommands


def test_set_ptp_cmd_maps_params_and_returns_index():
    c = FakeClient(results={"Magician.SetPTPCmd": {"queuedCmdIndex": 12}})
    idx = ArmCommands(c, "COM8").set_ptp_cmd(2, 220.0, 0.0, 40.0, 0.0, queued=True)
    assert idx == 12
    m, p = c.find_call("Magician.SetPTPCmd")
    assert p == {"portName": "COM8", "ptpMode": 2, "x": 220.0, "y": 0.0,
                 "z": 40.0, "r": 0.0, "isQueued": True}


def test_get_pose_passthrough():
    pose = {"x": 214.0, "y": 0.0, "z": 0.0, "r": 0.0, "jointAngle": [0, 25, 67, 0]}
    c = FakeClient(results={"Magician.GetPose": pose})
    assert ArmCommands(c, "COM8").get_pose() == pose


def test_set_wait_cmd_maps_timeout():
    c = FakeClient(results={"Magician.SetWAITCmd": {"queuedCmdIndex": 3}})
    assert ArmCommands(c, "COM8").set_wait_cmd(200, queued=True) == 3
    _, p = c.find_call("Magician.SetWAITCmd")
    assert p == {"portName": "COM8", "timeout": 200, "isQueued": True}
```

- [ ] **Step 2: Run to verify failure.** Run: `PYTHONPATH=src python -m pytest tests/arm/test_commands_motion.py -q` → FAIL (`AttributeError: set_ptp_cmd`).

- [ ] **Step 3: Implement — append to `ArmCommands`.**

```python
    def _queued_index(self, resp: Any) -> int:
        if isinstance(resp, dict):
            return int(resp.get("queuedCmdIndex", 0))
        return int(resp or 0)

    # -- pose / motion --
    def get_pose(self) -> Any:
        return self._call("GetPose")

    def set_ptp_cmd(self, mode: int, x: float, y: float, z: float, r: float,
                    queued: bool = True) -> int:
        return self._queued_index(self._call(
            "SetPTPCmd", ptpMode=int(mode), x=x, y=y, z=z, r=r, isQueued=queued))

    def set_home_params(self, x: float, y: float, z: float, r: float,
                        queued: bool = True) -> Any:
        return self._call("SetHOMEParams", x=x, y=y, z=z, r=r, isQueued=queued)

    def set_home_cmd(self, queued: bool = True) -> int:
        return self._queued_index(self._call("SetHOMECmd", isQueued=queued))

    def set_ptp_common_params(self, velocity: float, acceleration: float) -> Any:
        return self._call("SetPTPCommonParams",
                          velocityRatio=velocity, accelerationRatio=acceleration)

    def set_ptp_coordinate_params(self, velocity: float, acceleration: float) -> Any:
        return self._call("SetPTPCoordinateParams",
                          xyzVelocity=velocity, rVelocity=velocity,
                          xyzAcceleration=acceleration, rAcceleration=acceleration)

    def set_wait_cmd(self, ms: int, queued: bool = True) -> int:
        return self._queued_index(self._call("SetWAITCmd", timeout=int(ms), isQueued=queued))
```

- [ ] **Step 4: Run tests.** Run: `PYTHONPATH=src python -m pytest tests/arm/test_commands_motion.py -q` → PASS.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat(arm): pose/motion/params RPC wrappers"`

---

### Task 4: `arm/commands.py` — effector + servo + IO

**Files:**
- Modify: `src/dobotkit/arm/commands.py`
- Test: `tests/arm/test_commands_effector_io.py`

**Interfaces:**
- Produces:
  - `set_suction_cup(enable_ctrl, on, queued=True) -> int` → `Magician.SetEndEffectorSuctionCup{enableCtrl,on,isQueued}`
  - `set_gripper(enable_ctrl, on, queued=True) -> int` → `Magician.SetEndEffectorGripper{...}`
  - `set_servo_angle(index, angle, queued=True) -> int` → `Magician.SetServoAngle{index,value,isQueued}`
  - `set_io_multiplexing(address, multiplex, queued=False) -> Any` → `Magician.SetIOMultiplexing{address,multiplex}` (bool)
  - `get_io_adc(address) -> dict` → `Magician.GetIOADC{address}` → `{port,value}`
  - `get_io_di(address) -> dict` → `Magician.GetIODI{address}`
  - `set_io_do(address, level, queued=False) -> Any` → `Magician.SetIODO{address,level,isQueued}`
  - `set_io_pwm(address, freq, duty, queued=False) -> Any` → `Magician.SetIOPWM{address,frequency,dutyCycle,isQueued}`

- [ ] **Step 1: Write failing tests.**

```python
# tests/arm/test_commands_effector_io.py
from tests.conftest import FakeClient
from dobotkit.arm.commands import ArmCommands


def test_suction_cup_maps():
    c = FakeClient(results={"Magician.SetEndEffectorSuctionCup": {"queuedCmdIndex": 1}})
    ArmCommands(c, "COM8").set_suction_cup(True, True, queued=True)
    _, p = c.find_call("Magician.SetEndEffectorSuctionCup")
    assert p == {"portName": "COM8", "enableCtrl": True, "on": True, "isQueued": True}


def test_set_io_multiplexing_maps():
    c = FakeClient(results={"Magician.SetIOMultiplexing": True})
    ArmCommands(c, "COM8").set_io_multiplexing(24, 4)
    _, p = c.find_call("Magician.SetIOMultiplexing")
    assert p == {"portName": "COM8", "address": 24, "multiplex": 4}


def test_get_io_adc_passthrough():
    c = FakeClient(results={"Magician.GetIOADC": {"port": 0, "value": 3565}})
    assert ArmCommands(c, "COM8").get_io_adc(24) == {"port": 0, "value": 3565}
```

- [ ] **Step 2: Run to verify failure.** Run: `PYTHONPATH=src python -m pytest tests/arm/test_commands_effector_io.py -q` → FAIL.

- [ ] **Step 3: Implement — append to `ArmCommands`.**

```python
    # -- end effectors --
    def set_suction_cup(self, enable_ctrl: bool, on: bool, queued: bool = True) -> int:
        return self._queued_index(self._call(
            "SetEndEffectorSuctionCup", enableCtrl=bool(enable_ctrl), on=bool(on), isQueued=queued))

    def set_gripper(self, enable_ctrl: bool, on: bool, queued: bool = True) -> int:
        return self._queued_index(self._call(
            "SetEndEffectorGripper", enableCtrl=bool(enable_ctrl), on=bool(on), isQueued=queued))

    def set_servo_angle(self, index: int, angle: float, queued: bool = True) -> int:
        return self._queued_index(self._call(
            "SetServoAngle", index=int(index), value=float(angle), isQueued=queued))

    # -- IO --
    def set_io_multiplexing(self, address: int, multiplex: int, queued: bool = False) -> Any:
        return self._call("SetIOMultiplexing", address=int(address), multiplex=int(multiplex))

    def get_io_adc(self, address: int) -> Any:
        return self._call("GetIOADC", address=int(address))

    def get_io_di(self, address: int) -> Any:
        return self._call("GetIODI", address=int(address))

    def set_io_do(self, address: int, level: int, queued: bool = False) -> Any:
        return self._call("SetIODO", address=int(address), level=int(level), isQueued=queued)

    def set_io_pwm(self, address: int, frequency: float, duty: float, queued: bool = False) -> Any:
        return self._call("SetIOPWM", address=int(address),
                          frequency=float(frequency), dutyCycle=float(duty), isQueued=queued)
```

- [ ] **Step 4: Run tests.** → PASS.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat(arm): effector/servo/IO RPC wrappers"`

---

### Task 5: `arm/commands.py` — sensors + alarms

**Files:**
- Modify: `src/dobotkit/arm/commands.py`
- Test: `tests/arm/test_commands_sensors.py`

**Interfaces:**
- Produces (param names mirror SDK; **Task 9 verifies live**):
  - `set_color_sensor(enable, port, version=1) -> Any` → `Magician.SetColorSensor{enable,colorPort,version}`
  - `get_color_sensor() -> dict` → `Magician.GetColorSensor` → `{r,g,b}`
  - `set_infrared_sensor(enable, port, version=1) -> Any` → `Magician.SetInfraredSensor{enable,infraredPort,version}`
  - `get_infrared_sensor(port) -> dict` → `Magician.GetInfraredSensor{infraredPort}` → `{value}`
  - `get_seeed_distance(port) -> dict` / `get_seeed_temp(port)` / `get_seeed_light(port)` / `set_seeed_rgb(port, rgb)` → `Magician.GetSeeed*/SetSeeedRgb`
  - `get_alarms_state() -> Any` → `Magician.GetAlarmsState`

- [ ] **Step 1: Write failing tests.**

```python
# tests/arm/test_commands_sensors.py
from tests.conftest import FakeClient
from dobotkit.arm.commands import ArmCommands


def test_color_sensor_set_and_get():
    c = FakeClient(results={"Magician.GetColorSensor": {"r": 10, "g": 20, "b": 30}})
    cmd = ArmCommands(c, "COM8")
    cmd.set_color_sensor(1, 0)
    _, p = c.find_call("Magician.SetColorSensor")
    assert p == {"portName": "COM8", "enable": 1, "colorPort": 0, "version": 1}
    assert cmd.get_color_sensor() == {"r": 10, "g": 20, "b": 30}


def test_infrared_get_maps_port():
    c = FakeClient(results={"Magician.GetInfraredSensor": {"value": 1}})
    assert ArmCommands(c, "COM8").get_infrared_sensor(1) == {"value": 1}
    _, p = c.find_call("Magician.GetInfraredSensor")
    assert p == {"portName": "COM8", "infraredPort": 1}
```

- [ ] **Step 2: Run to verify failure.** → FAIL.

- [ ] **Step 3: Implement — append to `ArmCommands`.**

```python
    # -- sensors --
    def set_color_sensor(self, enable: int, port: int, version: int = 1) -> Any:
        return self._call("SetColorSensor", enable=int(enable),
                          colorPort=int(port), version=int(version))

    def get_color_sensor(self) -> Any:
        return self._call("GetColorSensor")

    def set_infrared_sensor(self, enable: int, port: int, version: int = 1) -> Any:
        return self._call("SetInfraredSensor", enable=int(enable),
                          infraredPort=int(port), version=int(version))

    def get_infrared_sensor(self, port: int) -> Any:
        return self._call("GetInfraredSensor", infraredPort=int(port))

    def get_seeed_distance(self, port: int) -> Any:
        return self._call("GetSeeedDistanceSensor", port=int(port))

    def get_seeed_temp(self, port: int) -> Any:
        return self._call("GetSeeedTempSensor", port=int(port))

    def get_seeed_light(self, port: int) -> Any:
        return self._call("GetSeeedLightSensor", port=int(port))

    def set_seeed_rgb(self, port: int, rgb: float) -> Any:
        return self._call("SetSeeedRGBLED", port=int(port), rgb=float(rgb))

    def get_alarms_state(self) -> Any:
        return self._call("GetAlarmsState")
```

- [ ] **Step 4: Run tests.** → PASS.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat(arm): sensor + alarm RPC wrappers"`

---

### Task 6: `arm/groups.py` — ergonomic facades

**Files:**
- Create: `src/dobotkit/arm/groups.py`
- Test: `tests/arm/test_arm_groups.py`

**Interfaces:**
- Consumes: `ArmCommands` (Tasks 2–5).
- Produces:
  - `EffectorGroup(cmds)`: `suck(on, *, enable=True, queued=True)`, `grip(on, *, enable=True, queued=True)`, `servo(index, angle, *, queued=True)`
  - `SensorGroup(cmds)`: `adc(port) -> Optional[int]`, `di(port) -> Optional[int]`, `color(port) -> Optional[dict]`, `infrared(port) -> Optional[dict]`, `distance/temp/light(port)`, `rgb(port, value)`. Each read guarded so a missing peripheral returns `None` + `RuntimeWarning` (reuse the `_guard` pattern from the retired serial groups: catch `DobotTimeoutError`, `DobotProtocolError`).
  - `IOGroup(cmds)`: `set_do(addr, level)`, `get_di(addr) -> Optional[int]`, `get_adc(addr) -> Optional[int]`, `set_pwm(addr, f, d)`, `set_multiplexing(addr, mux)`
- Note: `adc(port)` does `cmds.set_io_multiplexing(port, 4)` then `cmds.get_io_adc(port)` and returns the `value` field.

- [ ] **Step 1: Write failing tests.**

```python
# tests/arm/test_arm_groups.py
import pytest
from tests.conftest import FakeClient
from dobotkit.arm.commands import ArmCommands
from dobotkit.arm.groups import EffectorGroup, SensorGroup
from dobotkit.exceptions import DobotTimeoutError


def _cmds(**results):
    return ArmCommands(FakeClient(results=results), "COM8")


def test_suck_delegates():
    c = FakeClient(results={"Magician.SetEndEffectorSuctionCup": {"queuedCmdIndex": 1}})
    EffectorGroup(ArmCommands(c, "COM8")).suck(True)
    _, p = c.find_call("Magician.SetEndEffectorSuctionCup")
    assert p == {"portName": "COM8", "enableCtrl": True, "on": True, "isQueued": True}


def test_adc_sets_mux_then_reads_value():
    c = FakeClient(results={"Magician.GetIOADC": {"port": 0, "value": 3565},
                            "Magician.SetIOMultiplexing": True})
    assert SensorGroup(ArmCommands(c, "COM8")).adc(24) == 3565
    assert c.find_call("Magician.SetIOMultiplexing")[1]["multiplex"] == 4


def test_sensor_timeout_returns_none_and_warns():
    class Boom(FakeClient):
        def call(self, method, **p):
            raise DobotTimeoutError("no response")
    with pytest.warns(RuntimeWarning):
        assert SensorGroup(ArmCommands(Boom(), "COM8")).color(0) is None
```

- [ ] **Step 2: Run to verify failure.** → FAIL.

- [ ] **Step 3: Implement `groups.py`** (guarded sensor reads + facades):

```python
# src/dobotkit/arm/groups.py
"""Ergonomic facades over ArmCommands (effector / sensors / io)."""
from __future__ import annotations
import warnings
from typing import Any, Callable, Optional, TypeVar
from dobotkit.exceptions import DobotProtocolError, DobotTimeoutError

_T = TypeVar("_T")
_UNAVAILABLE = ("주변장치 응답이 없습니다 — 매직박스/센서 연결을 확인하세요 "
                "(no peripheral response; check the MagicBox and its device)")


def _guard(call: Callable[[], _T]) -> Optional[_T]:
    try:
        return call()
    except (DobotTimeoutError, DobotProtocolError):
        warnings.warn(_UNAVAILABLE, RuntimeWarning, stacklevel=3)
        return None


class _Group:
    def __init__(self, cmds: Any) -> None:
        self.cmds = cmds


class EffectorGroup(_Group):
    def suck(self, on: bool, *, enable: bool = True, queued: bool = True) -> Optional[int]:
        return self.cmds.set_suction_cup(enable, on, queued=queued)

    def grip(self, on: bool, *, enable: bool = True, queued: bool = True) -> Optional[int]:
        return self.cmds.set_gripper(enable, on, queued=queued)

    def servo(self, index: int, angle: float, *, queued: bool = True) -> Optional[int]:
        return self.cmds.set_servo_angle(index, angle, queued=queued)


class SensorGroup(_Group):
    def adc(self, port: int) -> Optional[int]:
        def _read() -> int:
            self.cmds.set_io_multiplexing(port, 4)  # 4 = ADC (GPIOTypeADC)
            return int(self.cmds.get_io_adc(port)["value"])
        return _guard(_read)

    def di(self, port: int) -> Optional[int]:
        return _guard(lambda: int(self.cmds.get_io_di(port).get("value", self.cmds.get_io_di(port).get("level", 0))))

    def color(self, port: int) -> Optional[Any]:
        def _read() -> Any:
            self.cmds.set_color_sensor(1, port)
            return self.cmds.get_color_sensor()
        return _guard(_read)

    def infrared(self, port: int) -> Optional[Any]:
        def _read() -> Any:
            self.cmds.set_infrared_sensor(1, port)
            return self.cmds.get_infrared_sensor(port)
        return _guard(_read)

    def distance(self, port: int) -> Optional[Any]:
        return _guard(lambda: self.cmds.get_seeed_distance(port))

    def temp(self, port: int) -> Optional[Any]:
        return _guard(lambda: self.cmds.get_seeed_temp(port))

    def light(self, port: int) -> Optional[Any]:
        return _guard(lambda: self.cmds.get_seeed_light(port))

    def rgb(self, port: int, value: float) -> Optional[int]:
        return _guard(lambda: self.cmds.set_seeed_rgb(port, value))


class IOGroup(_Group):
    def set_do(self, address: int, level: int) -> Any:
        return self.cmds.set_io_do(address, level)

    def get_di(self, address: int) -> Optional[int]:
        return _guard(lambda: int(self.cmds.get_io_di(address).get("value", 0)))

    def get_adc(self, address: int) -> Optional[int]:
        return _guard(lambda: int(self.cmds.get_io_adc(address)["value"]))

    def set_pwm(self, address: int, frequency: float, duty: float) -> Any:
        return self.cmds.set_io_pwm(address, frequency, duty)

    def set_multiplexing(self, address: int, multiplex: int) -> Any:
        return self.cmds.set_io_multiplexing(address, multiplex)
```

(Simplify the `di` double-call above during implementation to read once into a local.)

- [ ] **Step 4: Run tests.** → PASS.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat(arm): ergonomic effector/sensor/io groups with None-on-missing sensors"`

---

### Task 7: `arm/magicianlite.py` — high-level `MagicianLite`

**Files:**
- Create: `src/dobotkit/arm/magicianlite.py`
- Test: `tests/arm/test_magicianlite.py`

**Interfaces:**
- Consumes: `DobotLinkClient`, `ArmCommands`, groups.
- Produces: `class MagicianLite`:
  - `MagicianLite(port="auto", *, host="localhost", ws_port=9090, timeout=10.0, auto_connect=True, _client=None)`
  - `connect()` (opens client + `ConnectDobot` + `queue_clear`/`queue_start`), `disconnect()` (`DisconnectDobot` + close owned client), context-manager (`__exit__` stops queue + disconnects, never suppresses)
  - `home(*, wait=True)`, `move_to(x,y,z,r=0,*,mode=2,wait=False)`, `move_relative(dx,dy,dz,dr=0,*,wait=False)`, `pick_and_place(src,dst,z_safe,settle_ms=200)`, `set_speed(velocity,acceleration)`, `get_pose()->dict`
  - properties `.effector`, `.sensors`, `.io`
  - `_wait_for(index)` polls `cmds.current_index()` until `>= index` (or a monotonic-time deadline), sleeping 0.05s.
- `port="auto"` → `cmds.search()`, pick first `portName`.

- [ ] **Step 1: Write failing tests.**

```python
# tests/arm/test_magicianlite.py
from tests.conftest import FakeClient
from dobotkit.arm.magicianlite import MagicianLite


def _arm(**results):
    return MagicianLite(port="COM8", auto_connect=False, _client=FakeClient(results=results))


def test_move_to_sends_ptp_no_wait():
    c = FakeClient(results={"Magician.SetPTPCmd": {"queuedCmdIndex": 5}})
    arm = MagicianLite(port="COM8", auto_connect=False, _client=c)
    arm.move_to(220, 0, 40, 0, wait=False)
    _, p = c.find_call("Magician.SetPTPCmd")
    assert p["x"] == 220 and p["ptpMode"] == 2 and p["portName"] == "COM8"


def test_move_to_wait_polls_current_index():
    c = FakeClient(results={"Magician.SetPTPCmd": {"queuedCmdIndex": 2},
                            "Magician.GetQueuedCmdCurrentIndex": {"queuedCmdIndex": 2}})
    arm = MagicianLite(port="COM8", auto_connect=False, _client=c)
    arm.move_to(1, 2, 3, wait=True)
    assert "Magician.GetQueuedCmdCurrentIndex" in c.methods_called()


def test_context_manager_disconnects():
    c = FakeClient()
    with MagicianLite(port="COM8", auto_connect=False, _client=c) as arm:
        arm.connect()
    assert c.find_call("Magician.DisconnectDobot") is not None
```

- [ ] **Step 2: Run to verify failure.** → FAIL.

- [ ] **Step 3: Implement `magicianlite.py`.**

```python
# src/dobotkit/arm/magicianlite.py
"""High-level Magician Lite arm over DobotLink."""
from __future__ import annotations
import time
from typing import Any, Optional, Tuple
from dobotkit.arm.commands import ArmCommands
from dobotkit.arm.groups import EffectorGroup, IOGroup, SensorGroup
from dobotkit.exceptions import DobotConnectionError

Point = Tuple[float, float, float]
_MOVL_XYZ = 2


class MagicianLite:
    def __init__(self, port: str = "auto", *, host: str = "localhost",
                 ws_port: int = 9090, timeout: float = 10.0,
                 auto_connect: bool = True, _client: Optional[Any] = None) -> None:
        self._owns_client = _client is None
        if _client is None:
            from dobotkit.link import DobotLinkClient
            _client = DobotLinkClient(host=host, port=ws_port, timeout=timeout).connect()
        self._client = _client
        self._port = port
        self.cmds = ArmCommands(_client, port if port != "auto" else "")
        self.effector = EffectorGroup(self.cmds)
        self.sensors = SensorGroup(self.cmds)
        self.io = IOGroup(self.cmds)
        if auto_connect:
            self.connect()

    def connect(self) -> None:
        if self._port == "auto":
            ports = self.cmds.search() or []
            if not ports:
                raise DobotConnectionError("no Dobot ports found via DobotLink")
            self.cmds.port_name = ports[0]["portName"]
        self.cmds.connect()
        self.cmds.queue_clear()
        self.cmds.queue_start()

    def disconnect(self) -> None:
        try:
            self.cmds.disconnect()
        finally:
            if self._owns_client:
                self._client.close()

    def __enter__(self) -> "MagicianLite":
        return self

    def __exit__(self, *exc: object) -> None:
        try:
            self.cmds.queue_stop()
        except Exception:  # pragma: no cover - teardown must not mask body errors
            pass
        finally:
            self.disconnect()

    def _wait_for(self, index: Optional[int], wait: bool, timeout_s: float = 30.0) -> Optional[int]:
        if wait and index is not None:
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                if self.cmds.current_index() >= index:
                    break
                time.sleep(0.05)
        return index

    def get_pose(self) -> Any:
        return self.cmds.get_pose()

    def set_speed(self, velocity: float, acceleration: float) -> None:
        self.cmds.set_ptp_common_params(velocity, acceleration)
        self.cmds.set_ptp_coordinate_params(velocity, acceleration)

    def home(self, x: float = 200, y: float = 0, z: float = 0, r: float = 0,
             *, wait: bool = True) -> Optional[int]:
        self.cmds.set_home_params(x, y, z, r, queued=wait)
        return self._wait_for(self.cmds.set_home_cmd(queued=wait), wait)

    def move_to(self, x: float, y: float, z: float, r: float = 0, *,
                mode: int = _MOVL_XYZ, wait: bool = False) -> Optional[int]:
        return self._wait_for(self.cmds.set_ptp_cmd(mode, x, y, z, r, queued=True), wait)

    def move_relative(self, dx: float = 0, dy: float = 0, dz: float = 0, dr: float = 0,
                      *, wait: bool = False) -> Optional[int]:
        return self._wait_for(self.cmds.set_ptp_cmd(7, dx, dy, dz, dr, queued=True), wait)  # 7=MOVL_XYZ_INC

    def suck(self, on: bool) -> Optional[int]:
        return self.effector.suck(bool(on))

    def grip(self, on: bool) -> Optional[int]:
        return self.effector.grip(bool(on))

    def pick_and_place(self, src: Point, dst: Point, z_safe: float, settle_ms: int = 200) -> None:
        sx, sy, sz = src
        dx, dy, dz = dst
        m = _MOVL_XYZ
        self.cmds.set_ptp_cmd(m, sx, sy, z_safe, 0); self.cmds.set_ptp_cmd(m, sx, sy, sz, 0)
        self.cmds.set_suction_cup(True, True); self.cmds.set_wait_cmd(settle_ms)
        self.cmds.set_ptp_cmd(m, sx, sy, z_safe, 0)
        self.cmds.set_ptp_cmd(m, dx, dy, z_safe, 0); self.cmds.set_ptp_cmd(m, dx, dy, dz, 0)
        self.cmds.set_suction_cup(True, False); self.cmds.set_wait_cmd(settle_ms)
        last = self.cmds.set_ptp_cmd(m, dx, dy, z_safe, 0)
        self._wait_for(last, True)
```

- [ ] **Step 4: Run tests.** → PASS.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat(arm): high-level MagicianLite over DobotLink"`

---

### Task 8: Wire exports + remove serial stack

**Files:**
- Modify: `src/dobotkit/__init__.py` (lazy map: `Magician`→remove, add `MagicianLite`)
- Modify: `src/dobotkit/arm/__init__.py` (export `MagicianLite`)
- Delete: `src/dobotkit/arm/transport.py`, `protocol.py`, `queue.py`, `ids.py`, `magician.py`, `structures/`, `lowlevel/`, old `arm/groups.py`(replaced), old `arm/alarms.py`(if unused)
- Delete: `tests/arm/test_ll_*.py`, `test_transport.py`, `test_protocol.py`, `test_structures.py`, `test_queue.py`, `test_magician.py`, `test_coverage.py`, `test_ids.py`, `test_alarms.py`, `test_groups.py` (serial-era)
- Modify: `pyproject.toml` (drop `pyserial` from `dependencies`)

**Interfaces:**
- Produces: `dobotkit.MagicianLite`, `dobotkit.MagicianGO` as the two device classes.

- [ ] **Step 1: Update `dobotkit/__init__.py`** `_LAZY` and `__all__`: replace `"Magician": ("dobotkit.arm.magician","Magician")` with `"MagicianLite": ("dobotkit.arm.magicianlite","MagicianLite")`; keep `MagicianGO`. Update the `TYPE_CHECKING` import and `__all__` list accordingly.

- [ ] **Step 2: Update `arm/__init__.py`** to lazily expose `MagicianLite` from `dobotkit.arm.magicianlite` (mirror the existing PEP 562 `__getattr__` pattern; drop `LowLevelArm`/`SerialTransport`).

- [ ] **Step 3: Delete the serial modules and their tests.**

```bash
git rm src/dobotkit/arm/transport.py src/dobotkit/arm/protocol.py \
  src/dobotkit/arm/queue.py src/dobotkit/arm/ids.py src/dobotkit/arm/magician.py \
  -r src/dobotkit/arm/structures src/dobotkit/arm/lowlevel
git rm tests/arm/test_ll_*.py tests/arm/test_transport.py tests/arm/test_protocol.py \
  tests/arm/test_structures.py tests/arm/test_queue.py tests/arm/test_magician.py \
  tests/arm/test_coverage.py tests/arm/test_ids.py tests/arm/test_alarms.py tests/arm/test_groups.py
```

(Keep `arm/alarms.py` only if `get_alarms_state` decode reuses it; otherwise `git rm` it too.)

- [ ] **Step 4: Drop `pyserial`** from `[project].dependencies` in `pyproject.toml` (leave `websockets`). Remove the `pyserial`/`serial` mypy override block if present.

- [ ] **Step 5: Run full suite + typecheck + lint.**

Run: `PYTHONPATH=src python -m pytest -q && MYPYPATH=src python -m mypy && python -m ruff check src tests`
Expected: all green; only arm-DobotLink + GO tests remain. Fix any dangling imports (e.g. `test_integration.py`/`test_subpackage_api.py` referencing `Magician`).

- [ ] **Step 6: Commit.** `git add -A && git commit -m "refactor(arm): remove serial stack; export MagicianLite; drop pyserial"`

---

### Task 9: Docs + live hardware smoke test (verify RPC surface)

**Files:**
- Modify: `README.md`, `docs/quickstart-ko.md`, `CHANGELOG.md`
- Create: `examples/arm_magicianlite.py`

- [ ] **Step 1: Live smoke test — verify the real RPC names/params.** With DobotLink running and the arm connected, run a scratch script that drives `MagicianLite` against the real client: `search`→`connect`→`get_pose`→`sensors.adc(3)` (turn the pot, confirm it changes)→a small `move_to` in a cleared workspace (only if safe)→`disconnect`. For any RPC that errors (wrong method/param name), record DobotLink's error and fix the name/param in `arm/commands.py`, re-running the affected unit test. Confirmed-good names from the PoC (SearchDobot/ConnectDobot/GetPose/SetIOMultiplexing/GetIOADC) need no change.

- [ ] **Step 2: Update unit tests** for any RPC name/param corrected in Step 1; re-run `PYTHONPATH=src python -m pytest -q`.

- [ ] **Step 3: Write `examples/arm_magicianlite.py`** showing connect → home → move_to → suck → `sensors.adc(3)` with a `None` guard.

- [ ] **Step 4: Rewrite README arm section + quickstart-ko** for `MagicianLite`, stating DobotLink must be running; drop serial/`pyserial` wording. Add a `CHANGELOG` entry: "Arm rewritten on DobotLink; `Magician`→`MagicianLite`; serial stack removed; `pyserial` dropped."

- [ ] **Step 5: Commit.** `git add -A && git commit -m "docs+example: MagicianLite (DobotLink) usage; verify live RPC surface"`

---

## Self-Review

- **Spec coverage:** connection (T2,T7) · motion/home/pick (T3,T7) · effector+servo (T4,T6,T7) · all sensors incl. adc/di/color/infrared/Grove (T5,T6) · io (T4,T6) · queue/wait polling (T3,T7) · auto-discovery (T7) · DobotLink-down error (reused client, T7) · serial removal + naming + pyserial drop (T8) · live RPC verification (T9) · docs (T9). All spec sections covered.
- **Placeholders:** none — every code step has real code; the only "verify later" is Task 9's explicit live-verification task (by design, since DobotLink RPC param casing is only knowable against the running service).
- **Type consistency:** `ArmCommands` method names/returns used in Tasks 6–7 match Tasks 2–5 (`set_suction_cup`, `set_ptp_cmd`, `get_io_adc`, `current_index`, etc.). `_queued_index`/`_wait_for` consistent.
