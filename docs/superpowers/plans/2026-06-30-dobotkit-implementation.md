# dobotkit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `dobotkit`, a pure-Python library that controls the Dobot Magician Lite arm (serial) and Magician GO car (DobotLink WebSocket) with **complete** SDK feature coverage — surpassing pydobot's partial support.

**Architecture:** Two-layer arm stack — a complete low-level client (every SDK function 1:1) over a pure-Python serial protocol, with an ergonomic high-level `Magician` on top. The GO is a clean WebSocket JSON-RPC wrapper plus sensor-feedback navigation. Both share an exception hierarchy and enum module.

**Tech Stack:** Python ≥3.9, `pyserial`, `websockets`, `pytest`, `ruff`, `mypy`. No DLL, no native binaries.

## Global Constraints

- **Python ≥ 3.9**, pure Python only — no native/DLL/binary runtime dependency.
- **Runtime deps:** `pyserial`, `websockets` (both core; no extras). Subpackages `dobotkit.arm`/`dobotkit.go` use **lazy imports** so importing one device never imports the other's deps at runtime.
- **Wire structs:** little-endian, **packed (no alignment padding)** — `struct` format derived from each `DobotDllType` `Structure._fields_`. Confirmed: `PTPCmd` = `<Bffff` (17 bytes).
- **Serial framing:** `[0xAA,0xAA][len][id][ctrl][params...][checksum]`, `len = 2 + len(params)`, `checksum = (256 - (id+ctrl+Σparams) % 256) % 256`.
- **ctrl byte:** bit0 = `rw` (0=get/read, 1=set/write), bit1 = `isQueued` (0=immediate, 1=queued).
- **Golden oracle (test-only):** `DobotDllType.py` imports and packs ctypes structs WITHOUT the DLL. Tests byte-compare our packing against `bytes(DobotDllType.StructX(...))`. Oracle is **never** a runtime dependency; loaded in tests via `DOBOT_ORACLE_PATH` env var (default: the repo's `Dobot_Demo_V2.3/.../DobotDllType.py`), and oracle-based tests `pytest.skip()` if it is not importable.
- **Type hints:** every public symbol typed; ship `py.typed`.
- **Style:** snake_case methods; `isQueued` exposed as `queued: bool = False`; failures raise exceptions (not return codes).
- **TDD:** every task is test-first. **Commit after every passing task.**
- **License:** MIT. Implement from protocol spec (independent re-implementation); do not copy pydobot/DobotDllType source verbatim into shipped code.
- **Commit message footer (every commit):**
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  ```
- Run `git -c commit.gpgsign=false commit` (repo has no signing key configured).

**Authoritative API surface to cover** (from `DobotDllType.py`): 49 payload `Structure` classes; 213 functions. Pure DLL-plumbing functions are **excluded** from the coverage requirement: `enum`, `load`, `dSleep`, `gettime`, `SetDebugEnable`, `PeriodicTask`, `DobotExec`, `PrintInfo`, `SetProgbar`, `GetMarlinVersion`. Everything else maps to a `LowLevelArm` method (Task 2.10 enforces this with a test).

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | build metadata, deps, ruff/mypy/pytest config |
| `src/dobotkit/__init__.py` | public exports, `__version__`, lazy device imports |
| `src/dobotkit/_version.py` | `__version__ = "0.1.0"` |
| `src/dobotkit/exceptions.py` | `DobotError` hierarchy |
| `src/dobotkit/enums.py` | all enums |
| `src/dobotkit/arm/protocol.py` | `Message` framing/checksum |
| `src/dobotkit/arm/ids.py` | `ProtocolId` + per-id metadata |
| `src/dobotkit/arm/structures.py` | `pack_*`/`unpack_*` for all payloads + ctypes→struct deriver |
| `src/dobotkit/arm/transport.py` | `SerialTransport` (pyserial) |
| `src/dobotkit/arm/queue.py` | `CommandQueue` |
| `src/dobotkit/arm/lowlevel.py` | `LowLevelArm` — all SDK functions 1:1 (may split into `lowlevel/` package if large) |
| `src/dobotkit/arm/alarms.py` | alarm bitmap ↔ `AlarmCode` decode |
| `src/dobotkit/arm/groups.py` | `IOGroup`/`SensorGroup`/`EffectorGroup` |
| `src/dobotkit/arm/magician.py` | `Magician` high-level API |
| `src/dobotkit/go/geometry.py` | pure functions (yaw_delta, bearing, clamp) |
| `src/dobotkit/go/client.py` | `DobotLinkClient` |
| `src/dobotkit/go/magiciango.py` | `MagicianGO` high-level wrapper |
| `src/dobotkit/go/navigation.py` | `PreciseMover`, `WaypointNav` |
| `tests/...` | mirror of src; `conftest.py` provides `FakeSerial`, `FakeWebSocket`, oracle loader |
| `examples/...` | runnable demos |

---

# PHASE 0 — Foundation (shared)

### Task 0.1: Package scaffold

**Files:**
- Create: `pyproject.toml`, `src/dobotkit/__init__.py`, `src/dobotkit/_version.py`, `src/dobotkit/py.typed`
- Create: `tests/conftest.py`, `tests/test_smoke.py`

**Interfaces:**
- Produces: importable package `dobotkit` with `dobotkit.__version__`.

- [ ] **Step 1: Write failing smoke test**

`tests/test_smoke.py`:
```python
def test_package_imports_and_has_version():
    import dobotkit
    assert isinstance(dobotkit.__version__, str)
    assert dobotkit.__version__.count(".") >= 1
```

- [ ] **Step 2: Run, verify it fails**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: FAIL (`ModuleNotFoundError: dobotkit`).

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "dobotkit"
dynamic = ["version"]
description = "Complete pure-Python control library for Dobot Magician Lite (arm) and Magician GO (car)"
readme = "README.md"
requires-python = ">=3.9"
license = { text = "MIT" }
authors = [{ name = "dobotkit contributors" }]
dependencies = ["pyserial>=3.5", "websockets>=11.0"]

[project.optional-dependencies]
dev = ["pytest>=7", "pytest-cov", "ruff", "mypy"]

[tool.hatch.version]
path = "src/dobotkit/_version.py"

[tool.hatch.build.targets.wheel]
packages = ["src/dobotkit"]

[tool.pytest.ini_options]
addopts = "-q"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py39"

[tool.mypy]
python_version = "3.9"
packages = ["dobotkit"]
strict = true
```

- [ ] **Step 4: Create package files**

`src/dobotkit/_version.py`:
```python
__version__ = "0.1.0"
```
`src/dobotkit/py.typed`: (empty file)
`src/dobotkit/__init__.py`:
```python
"""dobotkit — complete pure-Python control for Dobot Magician Lite and Magician GO."""
from ._version import __version__

__all__ = ["__version__"]
```

- [ ] **Step 5: Editable install + run test**

Run: `python -m pip install -e ".[dev]" && python -m pytest tests/test_smoke.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A && git -c commit.gpgsign=false commit -m "feat: package scaffold (pyproject, src layout, version)"
```

---

### Task 0.2: Exception hierarchy

**Files:**
- Create: `src/dobotkit/exceptions.py`, `tests/test_exceptions.py`

**Interfaces:**
- Produces: `DobotError`, `DobotConnectionError`, `DobotTimeoutError`, `DobotProtocolError`, `DobotAlarmError(codes: list)`, `DobotLinkError`, `DobotValueError` — all subclasses of `DobotError`. `DobotAlarmError.__init__(self, codes, message="")` stores `self.codes`.

- [ ] **Step 1: Write failing test**

`tests/test_exceptions.py`:
```python
import pytest
from dobotkit.exceptions import (
    DobotError, DobotConnectionError, DobotTimeoutError, DobotProtocolError,
    DobotAlarmError, DobotLinkError, DobotValueError,
)

@pytest.mark.parametrize("cls", [
    DobotConnectionError, DobotTimeoutError, DobotProtocolError,
    DobotLinkError, DobotValueError,
])
def test_subclasses_of_base(cls):
    assert issubclass(cls, DobotError)
    with pytest.raises(DobotError):
        raise cls("boom")

def test_alarm_error_carries_codes():
    err = DobotAlarmError(codes=[1, 7], message="planning error")
    assert issubclass(DobotAlarmError, DobotError)
    assert err.codes == [1, 7]
    assert "planning error" in str(err)
```

- [ ] **Step 2: Run, verify it fails** — Run: `python -m pytest tests/test_exceptions.py -v` → FAIL (import error).

- [ ] **Step 3: Implement**

`src/dobotkit/exceptions.py`:
```python
"""Exception hierarchy shared across all dobotkit devices."""
from __future__ import annotations
from typing import Sequence


class DobotError(Exception):
    """Base class for all dobotkit errors."""


class DobotConnectionError(DobotError):
    """Connection failed: device not found, port occupied, or disconnected."""


class DobotTimeoutError(DobotError):
    """A response or motion-completion wait exceeded its timeout."""


class DobotProtocolError(DobotError):
    """Malformed frame, bad checksum, or undecodable payload."""


class DobotValueError(DobotError):
    """An argument was out of range or otherwise invalid."""


class DobotLinkError(DobotError):
    """GO only: DobotLink not running, or an RPC returned an error response."""


class DobotAlarmError(DobotError):
    """The arm reported one or more active alarms."""

    def __init__(self, codes: Sequence[int], message: str = "") -> None:
        self.codes = list(codes)
        text = message or f"active alarms: {self.codes}"
        super().__init__(text)
```

- [ ] **Step 4: Run, verify pass** — Run: `python -m pytest tests/test_exceptions.py -v` → PASS.

- [ ] **Step 5: Commit** — `git add -A && git -c commit.gpgsign=false commit -m "feat: exception hierarchy"`

---

### Task 0.3: Enums

**Files:**
- Create: `src/dobotkit/enums.py`, `tests/test_enums.py`

**Interfaces:**
- Produces: `IntEnum`s — `PTPMode`, `JOGMode` (cmd values), `ContinuousPathMode` (`CPRelative=0`, `CPAbsolute=1`), `GPIOType`, `EndEffectorType`, `ColorPort`, `LEDChannel` (GO), and `EffectChannel`. Values copied verbatim from research docs.

- [ ] **Step 1: Write failing test**

`tests/test_enums.py`:
```python
from dobotkit.enums import PTPMode, GPIOType, ContinuousPathMode

def test_ptpmode_values():
    assert PTPMode.JUMP_XYZ == 0
    assert PTPMode.MOVJ_XYZ == 1
    assert PTPMode.MOVL_XYZ == 2
    assert PTPMode.MOVJ_ANGLE == 4
    assert PTPMode.MOVL_XYZ_INC == 7
    assert PTPMode.JUMP_MOVL_XYZ == 9

def test_gpiotype_values():
    assert GPIOType.DUMMY == 0
    assert GPIOType.DO == 1
    assert GPIOType.PWM == 2
    assert GPIOType.DI == 3
    assert GPIOType.ADC == 4
    assert GPIOType.DIPU == 5
    assert GPIOType.DIPD == 6

def test_cp_mode():
    assert ContinuousPathMode.RELATIVE == 0
    assert ContinuousPathMode.ABSOLUTE == 1
```

- [ ] **Step 2: Run, verify it fails.**

- [ ] **Step 3: Implement** `src/dobotkit/enums.py`:
```python
"""All enumerations used across dobotkit."""
from __future__ import annotations
from enum import IntEnum


class PTPMode(IntEnum):
    JUMP_XYZ = 0
    MOVJ_XYZ = 1
    MOVL_XYZ = 2
    JUMP_ANGLE = 3
    MOVJ_ANGLE = 4
    MOVL_ANGLE = 5
    MOVJ_ANGLE_INC = 6
    MOVL_XYZ_INC = 7
    MOVJ_XYZ_INC = 8
    JUMP_MOVL_XYZ = 9


class JOGMode(IntEnum):
    """SetJOGCmd `cmd` values. 0 = idle/stop; 1..8 = axis ±; 9..10 = L-axis ±."""
    IDLE = 0
    AP_DOWN = 1
    AN_DOWN = 2
    BP_DOWN = 3
    BN_DOWN = 4
    CP_DOWN = 5
    CN_DOWN = 6
    DP_DOWN = 7
    DN_DOWN = 8
    LP_DOWN = 9
    LN_DOWN = 10


class ContinuousPathMode(IntEnum):
    RELATIVE = 0
    ABSOLUTE = 1


class GPIOType(IntEnum):
    DUMMY = 0
    DO = 1
    PWM = 2
    DI = 3
    ADC = 4
    DIPU = 5
    DIPD = 6


class EndEffectorType(IntEnum):
    NONE = 0
    SUCTION_CUP = 1
    GRIPPER = 2
    LASER = 3


class ColorPort(IntEnum):
    GP1 = 0
    GP2 = 1
    GP4 = 2
    GP5 = 3


class LEDChannel(IntEnum):
    """GO RGB LED channel; SetLightRGB `number`."""
    LED_1 = 1
    LED_2 = 2
    LED_3 = 3
    LED_4 = 4
    LED_ALL = 5
```

- [ ] **Step 4: Run, verify pass.**

- [ ] **Step 5: Commit** — `git add -A && git -c commit.gpgsign=false commit -m "feat: enums"`

---

# PHASE 1 — Arm protocol core

### Task 1.1: Message framing + checksum

**Files:**
- Create: `src/dobotkit/arm/__init__.py` (empty), `src/dobotkit/arm/protocol.py`, `tests/arm/__init__.py`, `tests/arm/test_protocol.py`

**Interfaces:**
- Produces:
  - `class Message` with attrs `id:int`, `ctrl:int`, `params:bytes`.
  - `Message(id, ctrl=0, params=b"")` constructor.
  - `Message.to_bytes() -> bytes` (full frame incl. header+checksum).
  - `classmethod Message.from_bytes(raw: bytes) -> Message` (validates header `0xAA 0xAA` and checksum, else raises `DobotProtocolError`).
  - `make_ctrl(rw: bool, queued: bool) -> int`.
  - `checksum(id: int, ctrl: int, params: bytes) -> int`.

- [ ] **Step 1: Write failing test**

`tests/arm/test_protocol.py`:
```python
import pytest
from dobotkit.arm.protocol import Message, make_ctrl, checksum
from dobotkit.exceptions import DobotProtocolError

def test_make_ctrl():
    assert make_ctrl(rw=False, queued=False) == 0b00
    assert make_ctrl(rw=True, queued=False) == 0b01
    assert make_ctrl(rw=True, queued=True) == 0b11

def test_checksum_known_vector():
    # GetPose: id=10, ctrl=0, no params -> checksum = (256 - 10) % 256 = 246
    assert checksum(10, 0, b"") == 246

def test_roundtrip_no_params():
    m = Message(id=10, ctrl=0, params=b"")
    raw = m.to_bytes()
    assert raw[:2] == b"\xAA\xAA"
    assert raw[2] == 2          # len = 2 + 0
    assert raw[3] == 10         # id
    assert raw[4] == 0          # ctrl
    assert raw[5] == 246        # checksum
    back = Message.from_bytes(raw)
    assert back.id == 10 and back.ctrl == 0 and back.params == b""

def test_roundtrip_with_params():
    m = Message(id=84, ctrl=0b11, params=b"\x02\x00\x01")
    raw = m.to_bytes()
    back = Message.from_bytes(raw)
    assert back.id == 84 and back.ctrl == 0b11 and back.params == b"\x02\x00\x01"

def test_bad_header_raises():
    with pytest.raises(DobotProtocolError):
        Message.from_bytes(b"\x00\x00\x02\x0a\x00\xf6")

def test_bad_checksum_raises():
    with pytest.raises(DobotProtocolError):
        Message.from_bytes(b"\xAA\xAA\x02\x0a\x00\x00")
```

- [ ] **Step 2: Run, verify it fails.**

- [ ] **Step 3: Implement** `src/dobotkit/arm/protocol.py`:
```python
"""Dobot serial frame: [0xAA 0xAA][len][id][ctrl][params...][checksum]."""
from __future__ import annotations
from dobotkit.exceptions import DobotProtocolError

HEADER = b"\xAA\xAA"


def make_ctrl(rw: bool, queued: bool) -> int:
    return (1 if rw else 0) | (2 if queued else 0)


def checksum(id: int, ctrl: int, params: bytes) -> int:
    total = (id + ctrl + sum(params)) % 256
    return (256 - total) % 256


class Message:
    __slots__ = ("id", "ctrl", "params")

    def __init__(self, id: int, ctrl: int = 0, params: bytes = b"") -> None:
        self.id = id
        self.ctrl = ctrl
        self.params = bytes(params)

    def to_bytes(self) -> bytes:
        length = 2 + len(self.params)
        body = bytes([self.id, self.ctrl]) + self.params
        return HEADER + bytes([length]) + body + bytes([checksum(self.id, self.ctrl, self.params)])

    @classmethod
    def from_bytes(cls, raw: bytes) -> "Message":
        if len(raw) < 6 or raw[:2] != HEADER:
            raise DobotProtocolError(f"bad header: {raw[:2]!r}")
        length = raw[2]
        id_, ctrl = raw[3], raw[4]
        params = raw[5:5 + (length - 2)]
        expect = checksum(id_, ctrl, params)
        got = raw[5 + (length - 2)]
        if got != expect:
            raise DobotProtocolError(f"bad checksum: got {got}, expected {expect}")
        return cls(id=id_, ctrl=ctrl, params=params)

    def __repr__(self) -> str:
        return f"Message(id={self.id}, ctrl={self.ctrl:#04b}, params={self.params.hex()})"
```

- [ ] **Step 4: Run, verify pass.**

- [ ] **Step 5: Commit** — `git add -A && git -c commit.gpgsign=false commit -m "feat(arm): serial message framing + checksum"`

---

### Task 1.2: Protocol ID table

**Files:**
- Create: `src/dobotkit/arm/ids.py`, `tests/arm/test_ids.py`

**Interfaces:**
- Produces: `class ProtocolId(IntEnum)` with every command ID, plus `ID_RW_QUEUED: dict[ProtocolId, tuple[bool,bool] | None]` is **not** required (rw/queued is decided per call). Only the ID enum is required here.

**Reconstruction method (mechanical):**
1. Seed from `pydobot/enums/CommunicationProtocolIDs.py` (verified values): `GET_SET_DEVICE_SN=0`, `GET_SET_DEVICE_NAME=1`, `GET_POSE=10`, `RESET_POSE=11`, `GET_ALARMS_STATE=20`, `CLEAR_ALL_ALARMS_STATE=21`, `SET_GET_HOME_PARAMS=30`, `SET_HOME_CMD=31`, `SET_GET_HHTTRIG_MODE=40`, `SET_GET_HHTTRIG_OUTPUT_ENABLED=41`, `GET_HHTTRIG_OUTPUT=42`, `SET_GET_ARM_ORIENTATION=50`, `SET_GET_END_EFFECTOR_PARAMS=60`, `SET_GET_END_EFFECTOR_LASER=61`, `SET_GET_END_EFFECTOR_SUCTION_CUP=62`, `SET_GET_END_EFFECTOR_GRIPPER=63`, `SET_GET_JOG_JOINT_PARAMS=70`, `SET_GET_JOG_COORDINATE_PARAMS=71`, `SET_GET_JOG_COMMON_PARAMS=72`, `SET_JOG_CMD=73`, `SET_GET_PTP_JOINT_PARAMS=80`, `SET_GET_PTP_COORDINATE_PARAMS=81`, `SET_GET_PTP_JUMP_PARAMS=82`, `SET_GET_PTP_COMMON_PARAMS=83`, `SET_PTP_CMD=84`, `SET_GET_PTP_L_PARAMS=85`, `SET_PTP_WITH_L_CMD=86`, `SET_GET_CP_PARAMS=90`, `SET_CP_CMD=91`, `SET_GET_ARC_PARAMS=100`, `SET_ARC_CMD=101`, `SET_WAIT_CMD=110`, `SET_TRIG_CMD=120`, `SET_GET_IO_MULTIPLEXING=130`, `SET_GET_IO_DO=131`, `SET_GET_IO_PWM=132`, `GET_IO_DI=133`, `GET_IO_ADC=134`, `SET_EMOTOR=135`, `SET_GET_COLOR_SENSOR=137`, `SET_GET_IR_SWITCH=138`, `SET_QUEUED_CMD_START_EXEC=240`, `SET_QUEUED_CMD_STOP_EXEC=241`, `SET_QUEUED_CMD_FORCE_STOP_EXEC=242`, `SET_QUEUED_CMD_CLEAR=245`, `GET_QUEUED_CMD_CURRENT_INDEX=246`, `GET_QUEUED_CMD_MOTION_FINISH=247`.
2. Add the remaining IDs by the documented categorical numbering (device 0–9, kinematics 11–12, user params 13, auto-leveling 32–33, end-effector type/servo within 60s, CP2 92, CP common 93, CP-LE 94, circle 102, ARC common 103, EMotorS 136, WiFi 150–159, lost-step 170–171, motor-mode 172, speed-ratio 173–176, angle-sensor 211–214). **Each value must be cross-checked against the official Dobot Communication Protocol; tag uncertain ones with a comment `# unverified`.**
3. The `_ext`/`_extEx` variants reuse the **same** ID as their base (they differ only by routing to MagicBox slave -1, encoded elsewhere) — no separate IDs.

- [ ] **Step 1: Write failing test**

`tests/arm/test_ids.py`:
```python
from dobotkit.arm.ids import ProtocolId

def test_known_ids_match_pydobot():
    assert ProtocolId.GET_POSE == 10
    assert ProtocolId.GET_ALARMS_STATE == 20
    assert ProtocolId.SET_HOME_CMD == 31
    assert ProtocolId.SET_PTP_CMD == 84
    assert ProtocolId.SET_CP_CMD == 91
    assert ProtocolId.SET_QUEUED_CMD_CLEAR == 245
    assert ProtocolId.GET_QUEUED_CMD_CURRENT_INDEX == 246

def test_ids_unique():
    values = [m.value for m in ProtocolId]
    assert len(values) == len(set(values)), "duplicate protocol IDs"
```

- [ ] **Step 2: Run, verify it fails.**

- [ ] **Step 3: Implement** `src/dobotkit/arm/ids.py` — full `IntEnum` per the reconstruction method above. (Engineer enumerates all IDs from the seed list + categorical rule; the uniqueness test guards against collisions.)

- [ ] **Step 4: Run, verify pass.**

- [ ] **Step 5: Commit** — `git add -A && git -c commit.gpgsign=false commit -m "feat(arm): protocol ID table"`

---

### Task 1.3: Structure (un)packing + golden-oracle harness

**Files:**
- Create: `src/dobotkit/arm/structures.py`, `tests/arm/test_structures.py`
- Modify: `tests/conftest.py` (add oracle loader fixture)

**Interfaces:**
- Produces: for each of the 49 structures, `pack_<Name>(...) -> bytes` and `unpack_<Name>(data: bytes) -> <NamedTuple>`. Names mirror `DobotDllType` (e.g. `pack_PTPCmd`, `unpack_Pose`). A helper `fmt_from_fields(fields) -> str` documents the ctypes→struct mapping but production code uses explicit literal formats (clarity > cleverness).

**ctypes → struct char map** (little-endian, packed): `c_byte→b`, `c_ubyte/c_uint8→B`, `c_bool→?`, `c_char→c`, `c_short→h`, `c_ushort→H`, `c_int/c_int32→i`, `c_uint/c_uint32→I`, `c_long→l`, `c_float→f`, `c_double→d`. Fixed arrays (e.g. `c_byte*66`) → `66s` (bytes). All formats prefixed `<` and assume `_pack_=1`.

- [ ] **Step 1: Add oracle fixture to `tests/conftest.py`**

```python
import os, sys, importlib.util, pytest

def _load_oracle():
    path = os.environ.get(
        "DOBOT_ORACLE_PATH",
        os.path.join(os.path.dirname(__file__), "..", "..",
                     "Dobot_Demo_V2.3", "python64",
                     "demo-magician-python-64-master", "DobotDllType.py"),
    )
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return None
    sys.path.insert(0, os.path.dirname(path))
    try:
        spec = importlib.util.spec_from_file_location("DobotDllType_oracle", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # safe: top-level does not load the DLL
        return mod
    except Exception:
        return None

@pytest.fixture(scope="session")
def oracle():
    mod = _load_oracle()
    if mod is None:
        pytest.skip("DobotDllType oracle not importable (set DOBOT_ORACLE_PATH)")
    return mod
```

- [ ] **Step 2: Write failing test** — `tests/arm/test_structures.py`:
```python
import struct
from dobotkit.arm import structures as S

def test_ptpcmd_format_and_size():
    raw = S.pack_PTPCmd(mode=2, x=200.0, y=0.0, z=50.0, r=0.0)
    assert raw == struct.pack("<Bffff", 2, 200.0, 0.0, 50.0, 0.0)
    assert len(raw) == 17

def test_pose_unpack():
    raw = struct.pack("<8f", 1, 2, 3, 4, 5, 6, 7, 8)
    p = S.unpack_Pose(raw)
    assert (p.x, p.y, p.z, p.r) == (1, 2, 3, 4)
    assert (p.j1, p.j2, p.j3, p.j4) == (5, 6, 7, 8)

def test_ptpcmd_matches_oracle(oracle):
    ours = S.pack_PTPCmd(mode=2, x=200.0, y=0.0, z=50.0, r=0.0)
    o = oracle.PTPCmd(); o.ptpMode = 2; o.x = 200.0; o.y = 0.0; o.z = 50.0; o.rHead = 0.0
    assert ours == bytes(o)
```

- [ ] **Step 3: Run, verify it fails.**

- [ ] **Step 4: Implement** `src/dobotkit/arm/structures.py` for the **core motion set first** (`PTPCmd`, `Pose`, `HOMEParams`, `HOMECmd`, `PTPCommonParams`, `PTPCoordinateParams`, `PTPJointParams`, `PTPJumpParams`, `JOGCmd`, `JOGCommonParams`). Each:
```python
import struct
from typing import NamedTuple

class Pose(NamedTuple):
    x: float; y: float; z: float; r: float
    j1: float; j2: float; j3: float; j4: float

def pack_PTPCmd(mode: int, x: float, y: float, z: float, r: float) -> bytes:
    return struct.pack("<Bffff", mode, x, y, z, r)

def unpack_Pose(data: bytes) -> Pose:
    return Pose(*struct.unpack("<8f", data))
# ... remaining core structs
```
The remaining 39 structures are filled in by their owning Phase-2 task (each lowlevel category task adds the structs it needs + an oracle byte-match test for each).

- [ ] **Step 5: Run, verify pass** (oracle test runs if oracle present, else skips).

- [ ] **Step 6: Commit** — `git add -A && git -c commit.gpgsign=false commit -m "feat(arm): structure packing + golden-oracle test harness"`

---

### Task 1.4: Serial transport + FakeSerial

**Files:**
- Create: `src/dobotkit/arm/transport.py`, `tests/arm/test_transport.py`
- Modify: `tests/conftest.py` (add `FakeSerial`)

**Interfaces:**
- Produces:
  - `class SerialTransport(port: str, baudrate: int = 115200, timeout: float = 1.0, _serial_factory=serial.Serial)`.
  - `.send(message: Message) -> Message` — writes frame, reads one response frame, returns parsed `Message`. Thread-safe (internal `Lock`). Raises `DobotTimeoutError` on no/short response, `DobotConnectionError` on serial errors.
  - `.close()`, context manager support.
  - `staticmethod search() -> list[str]` via `serial.tools.list_ports`.
  - Internal `_read_frame()` reads header(2)+len(1)+body(len)+checksum(1).

- [ ] **Step 1: Add `FakeSerial` to `tests/conftest.py`**
```python
class FakeSerial:
    """In-memory serial double: queue response frames, capture writes."""
    def __init__(self, responses=None):
        self.written = bytearray()
        self._rx = bytearray()
        for r in (responses or []):
            self._rx += r
        self.is_open = True
    def write(self, data): self.written += data; return len(data)
    def read(self, n=1):
        out = self._rx[:n]; del self._rx[:n]; return bytes(out)
    def reset_input_buffer(self): pass
    def reset_output_buffer(self): pass
    def close(self): self.is_open = False
    def queue_response(self, frame: bytes): self._rx += frame
```

- [ ] **Step 2: Write failing test** — `tests/arm/test_transport.py`:
```python
from dobotkit.arm.transport import SerialTransport
from dobotkit.arm.protocol import Message
from dobotkit.exceptions import DobotTimeoutError
import pytest

def make_tx(responses):
    from tests.conftest import FakeSerial
    fake = FakeSerial(responses)
    tx = SerialTransport(port="FAKE", _serial_factory=lambda *a, **k: fake)
    return tx, fake

def test_send_writes_frame_and_parses_response():
    resp = Message(id=10, ctrl=0, params=b"\x01\x02").to_bytes()
    tx, fake = make_tx([resp])
    reply = tx.send(Message(id=10, ctrl=0))
    assert fake.written == Message(id=10, ctrl=0).to_bytes()
    assert reply.id == 10 and reply.params == b"\x01\x02"

def test_timeout_on_empty():
    tx, _ = make_tx([])
    with pytest.raises(DobotTimeoutError):
        tx.send(Message(id=10, ctrl=0))
```

- [ ] **Step 3: Run, verify it fails.**

- [ ] **Step 4: Implement** `transport.py` (pyserial-backed; `_serial_factory` injectable for tests; read header byte-by-byte until `0xAA 0xAA`, then length+body+checksum; raise `DobotTimeoutError` if `read` returns fewer bytes than needed).

- [ ] **Step 5: Run, verify pass.**

- [ ] **Step 6: Commit** — `git add -A && git -c commit.gpgsign=false commit -m "feat(arm): serial transport + FakeSerial test double"`

---

### Task 1.5: Command queue

**Files:** Create `src/dobotkit/arm/queue.py`, `tests/arm/test_queue.py`

**Interfaces:**
- Consumes: `SerialTransport.send`, `Message`, `ProtocolId`, `structures`.
- Produces: `class CommandQueue(transport)` with `clear()`, `start()`, `stop()`, `force_stop()`, `current_index() -> int`, `motion_finished() -> bool`, `wait_for(index: int, poll: float = 0.05, timeout: float = 30.0) -> None` (raises `DobotTimeoutError`). Uses `time.monotonic()` for absolute timeout, `time.sleep(poll)` between polls.

- [ ] **Step 1: Write failing test** — drive with `FakeSerial` queuing `GET_QUEUED_CMD_CURRENT_INDEX` responses (uint64). Test: `wait_for(5)` returns once index ≥ 5; `wait_for(99, timeout=0.2)` raises `DobotTimeoutError`. Use `monkeypatch` on `time.sleep` to avoid real delays.
```python
def test_wait_for_returns_when_index_reached(monkeypatch):
    import struct
    from tests.conftest import FakeSerial
    from dobotkit.arm.transport import SerialTransport
    from dobotkit.arm.queue import CommandQueue
    from dobotkit.arm.protocol import Message
    from dobotkit.arm.ids import ProtocolId
    frames = [Message(id=ProtocolId.GET_QUEUED_CMD_CURRENT_INDEX, ctrl=0,
                      params=struct.pack("<Q", i)).to_bytes() for i in (1, 3, 5)]
    fake = FakeSerial(frames)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    q = CommandQueue(SerialTransport(port="F", _serial_factory=lambda *a, **k: fake))
    q.wait_for(5, poll=0)  # should not raise
```

- [ ] **Step 2–5:** Run fail → implement → run pass → commit (`feat(arm): command queue + wait helper`).

---

# PHASE 2 — Arm low-level (complete SDK coverage)

> Each task adds the structs it needs to `structures.py` (with an oracle byte-match test per struct) and the methods to `LowLevelArm`. Every method: build `Message` (id from `ProtocolId`, ctrl via `make_ctrl`, params via `pack_*`), call `transport.send`, decode response via `unpack_*`. Queued setters return the queued index (`unpack` of the uint64 response). The **representative pattern** is shown once in Task 2.1; subsequent tasks list their exact functions + struct fields and reuse the pattern.

### Task 2.1: `LowLevelArm` base + connection/device commands

**Files:** Create `src/dobotkit/arm/lowlevel.py`, `tests/arm/test_lowlevel_device.py`

**Interfaces:**
- Produces: `class LowLevelArm(transport: SerialTransport)`; `.queue: CommandQueue`. Private `_send(id, params=b"", rw=False, queued=False)`. Methods this task: `get_device_sn()`, `set_device_name(name)`, `get_device_name()`, `get_device_version()`, `get_device_id()`, `get_device_time()`, `get_device_info()`, `restart_magic_box()`. Also `connect()/disconnect()` delegating to transport. Structs: `DeviceVersion`, `DeviceID`, `DevInfo`.

- [ ] **Step 1: Write failing test** (FakeSerial-backed): `get_device_version()` decodes an 8-byte response into a `DeviceVersion` namedtuple; assert the `_send` wrote a frame with `id=GET_DEVICE_VERSION`, `rw=0`.
```python
def test_get_device_version_decodes(... ):
    # queue Message(id=ProtocolId.GET_DEVICE_VERSION, params=bytes([1,2,3,4,5,6,7,8]))
    # assert ll.get_device_version() == DeviceVersion(1,2,3,4,5,6,7,8)
```

- [ ] **Step 2: Run, verify it fails.**

- [ ] **Step 3: Implement** — the **canonical pattern** all later methods follow:
```python
from dobotkit.arm import structures as S
from dobotkit.arm.ids import ProtocolId
from dobotkit.arm.protocol import Message, make_ctrl
from dobotkit.arm.queue import CommandQueue

class LowLevelArm:
    def __init__(self, transport):
        self.transport = transport
        self.queue = CommandQueue(transport)

    def _send(self, id, params=b"", *, rw=False, queued=False) -> Message:
        return self.transport.send(Message(id=id, ctrl=make_ctrl(rw, queued), params=params))

    def get_device_version(self):
        resp = self._send(ProtocolId.GET_DEVICE_VERSION)
        return S.unpack_DeviceVersion(resp.params)

    def set_device_name(self, name: str, *, queued: bool = False):
        resp = self._send(ProtocolId.GET_SET_DEVICE_NAME,
                          S.pack_DeviceName(name), rw=True, queued=queued)
        return self._queued_index(resp) if queued else None
    # ...
```

- [ ] **Step 4–5:** Run pass → commit (`feat(arm): lowlevel base + device commands`).

### Task 2.2: Pose / home / kinematics / auto-leveling

**Functions:** `get_pose`, `get_pose_l`, `get_kinematics`, `reset_pose`, `set_home_params`, `get_home_params`, `set_home_cmd`, `set_auto_leveling`, `get_auto_leveling_result`, `set_arm_orientation`, `get_arm_orientation`.
**Structs:** `Pose`, `Kinematics`, `HOMEParams`, `HOMECmd`, `AutoLevelingCmd`.
**Tests:** oracle byte-match per struct + a FakeSerial decode test for `get_pose` and `set_home_cmd` (queued index).
- [ ] Steps 1–5 per the Task 2.1 pattern → commit `feat(arm): pose/home/kinematics commands`.

### Task 2.3: PTP (all params + commands)

**Functions:** `set_ptp_cmd`, `set_ptp_with_l_cmd`, and set/get pairs for `ptp_joint_params`, `ptp_coordinate_params`, `ptp_l_params`, `ptp_jump_params`, `ptp_common_params`.
**Structs:** `PTPCmd`, `PTPWithLCmd`, `PTPJointParams`, `PTPCoordinateParams`, `PTPLParams`, `PTPJumpParams`, `PTPCommonParams`.
**Tests:** oracle byte-match per struct; FakeSerial test that `set_ptp_cmd(PTPMode.MOVL_XYZ, 200,0,50,0, queued=True)` writes `id=84, ctrl=0b11` and returns the queued index.
- [ ] Steps 1–5 → commit `feat(arm): PTP motion commands`.

### Task 2.4: JOG

**Functions:** `set_jog_cmd`, set/get pairs for `jog_joint_params`, `jog_coordinate_params`, `jog_l_params`, `jog_common_params`.
**Structs:** `JOGCmd`, `JOGJointParams`, `JOGCoordinateParams`, `JOGLParams`, `JOGCommonParams`.
- [ ] Steps 1–5 → commit `feat(arm): JOG commands`.

### Task 2.5: CP / ARC / Circle

**Functions:** `set_cp_cmd`, `set_cp2_cmd`, `set_cp_le_cmd`, set/get `cp_params`, set/get `cp_common_params`, set/get `cpr_hold_enable`, `set_arc_cmd`, `set_circle_cmd`, set/get `arc_params`, set/get `arc_common_params`.
**Structs:** `CPCmd`, `CP2Cmd`, `CPParams`, `CPCommonParams`, `ARCParams`, `ARCCmd`, `CircleCmd`, `ARCPoint`, `ARCCommonParams`.
- [ ] Steps 1–5 → commit `feat(arm): CP/ARC/Circle commands`.

### Task 2.6: End effector

**Functions:** set/get `end_effector_params`, `end_effector_laser`, `end_effector_suction_cup`, `end_effector_gripper`, set/get `end_effector_type`, `set_servo_angle`, `get_servo_angle`.
**Structs:** `EndTypeParams`, plus inline byte params for on/off pairs (`<BB` enableCtrl,on).
**Tests:** include the MagicBox-routed servo path note in docstrings; oracle match for `EndTypeParams`.
- [ ] Steps 1–5 → commit `feat(arm): end-effector commands`.

### Task 2.7: IO + EMotor + WAIT/TRIG (incl. Ext/ExtEx routing)

**Functions:** `set_io_multiplexing`/`get_io_multiplexing`, `set_io_do`/`get_io_do`, `set_io_pwm`/`get_io_pwm`, `get_io_di`, `get_io_adc`, `set_e_motor`, `set_e_motors`, `set_wait_cmd`, `set_trig_cmd`. Plus `*_ext` and `*_ext_ex` variants for the IO/EMotor functions: these set a `routed_to_magicbox=True` flag that prepends the MagicBox slave id (-1) per the SDK's Ext convention.
**Structs:** `IOMultiplexing`, `IODO`, `IOPWM`, `IODI`, `IOADC`, `EMotor`, `EMotorS`, `WAITCmd`, `TRIGCmd`.
**Implementation note:** Implement the base function once; generate `_ext`/`_ext_ex` as thin wrappers that set the routing flag — DRY, not 3 copies. Document that base functions auto-route under MagicBox (per research doc §1).
- [ ] Steps 1–5 → commit `feat(arm): IO/EMotor/WAIT/TRIG commands + Ext routing`.

### Task 2.8: Sensors (color / infrared / Seeed)

**Functions:** set/get `color_sensor`, set/get `infrared_sensor`, `get_seeed_distance_sensor`, set/get `seeed_color_sensor`, set/get `seeed_temp_sensor`, set/get `seeed_light_sensor`, `set_seeed_rgb` (+ `_ext`/`_ext_ex` variants).
**Structs:** inline byte params (port/enable) + multi-value responses (RGB, temp+humidity, etc.).
**Tests:** FakeSerial decode for `get_seeed_distance_sensor` (returns float mm), `get_seeed_temp_sensor` (returns `(temp, humidity)`).
- [ ] Steps 1–5 → commit `feat(arm): color/infrared/Seeed sensor commands`.

### Task 2.9: Queue control, alarms, speed-ratio, lost-step, motor-mode, WiFi, misc

**Functions:** `queued_cmd_clear/start_exec/stop_exec/force_stop_exec/start_download/stop_download`, `get_queued_cmd_current_index`, `get_queued_cmd_motion_finish`, `get_alarms_state`, `clear_all_alarms_state`, `get_user_params`, set/get `arm_speed_ratio`, set/get `l_speed_ratio`, `set_motor_mode`/`get_motor_mode`, `set_lost_step_params`, `set_lost_step_cmd`, `set_lost_step_enable_and_params`, `get_lost_step_enable_and_params`, set/get all WiFi (`config_mode`, `ssid`, `password`, `ip_address`, `netmask`, `gateway`, `dns`, `get_wifi_connect_status`), set/get HHT trig, angle-sensor & base-decoder calibration, `set_device_with_l`/`get_device_with_l`, `get_uart4_peripherals_type`, `get_device_version_ex`.
**Structs:** `AlarmsState`, `UserParams`, `WIFIIPAddress`, `WIFINetmask`, `WIFIGateway`, `WIFIDNS`.
**Note:** Some queue methods already exist on `CommandQueue`; `LowLevelArm` exposes thin pass-throughs so the coverage check (2.10) finds them.
- [ ] Steps 1–5 → commit `feat(arm): queue/alarm/speed/lost-step/wifi/misc commands`.

### Task 2.10: Coverage cross-check test

**Files:** Create `tests/arm/test_coverage.py`

**Interfaces:** Consumes the oracle + `LowLevelArm`.

- [ ] **Step 1: Write the test** — enumerate every oracle function name, normalize (`Set/Get` prefixes, `Ex`/`Ext`/`ExtEx` suffixes → expected snake_case method), subtract the excluded plumbing set, assert each maps to an attribute on `LowLevelArm`.
```python
EXCLUDED = {"enum","load","dSleep","gettime","SetDebugEnable","PeriodicTask",
            "DobotExec","PrintInfo","SetProgbar","GetMarlinVersion"}

def test_every_sdk_function_has_lowlevel_method(oracle):
    import inspect
    from dobotkit.arm.lowlevel import LowLevelArm
    methods = {n for n in dir(LowLevelArm) if not n.startswith("_")}
    missing = []
    for name, obj in vars(oracle).items():
        if not inspect.isfunction(obj) or name in EXCLUDED or name.startswith("_"):
            continue
        if _expected_method(name) not in methods:
            missing.append(name)
    assert not missing, f"uncovered SDK functions: {sorted(missing)}"
```
Provide `_expected_method()` mapping helper in the test (strip `Set`/`Get`, snake_case, fold `Ex`→base, `Ext`→`_ext`, `ExtEx`→`_ext_ex`). **This test is the proof of "all features."**

- [ ] **Step 2: Run** — fix any genuinely missing methods in the relevant Phase-2 file, then commit (`test(arm): full SDK coverage cross-check`).

---

# PHASE 3 — Arm high-level API

### Task 3.1: Alarm decode table

**Files:** Create `src/dobotkit/arm/alarms.py`, `tests/arm/test_alarms.py`
**Interfaces:** Produces `AlarmCode(IntEnum)` (common codes from the Dobot alarm spec: e.g. `0x00` reset, `0x10` planning-related, `0x20..` kinematics, `0x30..` limits — values tagged `# unverified` where uncertain), and `decode_alarms(bitmap: bytes) -> list[AlarmCode]` (each set bit → its code).
- [ ] **Step 1:** Test `decode_alarms` on a known bitmap (bit n set → code n present). **Steps 2–5** → commit `feat(arm): alarm bitmap decoding`.

### Task 3.2: Device groups

**Files:** Create `src/dobotkit/arm/groups.py`, `tests/arm/test_groups.py`
**Interfaces:** Produces `IOGroup(ll)`, `SensorGroup(ll)`, `EffectorGroup(ll)` — thin ergonomic facades delegating to `LowLevelArm`. E.g. `EffectorGroup.suck(on: bool)` → `ll.set_end_effector_suction_cup(enable=True, on=on, queued=True)`; `SensorGroup.seeed_distance(port)` → `ll.get_seeed_distance_sensor(port)`; `IOGroup.set_do(addr, level)`.
- [ ] **Step 1:** Tests assert each group method calls the right `LowLevelArm` method (use a `Mock` LowLevelArm). **Steps 2–5** → commit `feat(arm): io/sensor/effector groups`.

### Task 3.3: `Magician` high-level API

**Files:** Create `src/dobotkit/arm/magician.py`, `tests/arm/test_magician.py`
**Interfaces:**
- Produces `class Magician`:
  - `__init__(port="auto", baudrate=115200, *, auto_connect=True, _transport=None)`; `port="auto"` → `SerialTransport.search()[0]`.
  - `connect()/disconnect()`; `__enter__/__exit__` (exit calls `stop` + `disconnect`, suppresses nothing).
  - `home(x=200,y=0,z=0,r=0, wait=True)`; `set_speed(velocity, acceleration)`; `get_pose() -> Pose`; property `pose`.
  - `move_to(x,y,z,r=0, mode=PTPMode.MOVL_XYZ, wait=False)`; `move_relative(dx=0,dy=0,dz=0,dr=0, wait=False)`.
  - `pick_and_place(src, dst, z_safe, settle_ms=200)`.
  - Group properties `.io`, `.sensors`, `.effector`, and `.lowlevel`.
  - pydobot-compat aliases: `suck(on)`, `grip(on)`, `speed(velocity, acceleration)`, `wait(ms)`, `pose()`-style accessor, `get_eio(addr)`, `set_eio(addr,val)`.
  - On queued move with `wait=True`, calls `queue.start()` then `queue.wait_for(index)`.
  - Optional `check_alarms` param on motion → raises `DobotAlarmError` if alarms set.
- [ ] **Step 1:** Tests with a fake `LowLevelArm`/`FakeSerial`: `move_to(..., wait=True)` issues PTP + starts queue + waits; context manager disconnects on exit even after exception; `suck(True)` delegates correctly.
- [ ] **Steps 2–5** → commit `feat(arm): high-level Magician API`.

### Task 3.4: Arm examples + wire into `__init__`

**Files:** Create `examples/arm_pick_and_place.py`, `examples/arm_sensors.py`, `examples/arm_full_api_tour.py`; Modify `src/dobotkit/__init__.py` (lazy export `Magician`).
- [ ] **Step 1:** Add `__getattr__`-based lazy import in `__init__.py`:
```python
def __getattr__(name):
    if name == "Magician":
        from .arm.magician import Magician
        return Magician
    if name == "MagicianGO":
        from .go.magiciango import MagicianGO
        return MagicianGO
    raise AttributeError(name)
```
- [ ] **Step 2:** Smoke test `from dobotkit import Magician` (no serial port touched at import). **Steps 3–4** → commit `feat: examples + lazy Magician export`.

---

# PHASE 4 — Magician GO

### Task 4.1: Geometry pure functions

**Files:** Create `src/dobotkit/go/__init__.py` (empty), `src/dobotkit/go/geometry.py`, `tests/go/__init__.py`, `tests/go/test_geometry.py`
**Interfaces:** Produces `yaw_delta(a, b) -> float` (signed shortest, ±180 wrap), `bearing(dx, dy) -> float` (deg, 0°=+X, CCW+), `clamp_speed(v, lo, hi) -> float` (preserves sign), `cm_to_mm(cm)`, `mm_to_cm(mm)`. Port any existing pure-function tests from `magiciango_go/tests/`.
- [ ] **Step 1:** Tests: `yaw_delta(170,-170)==-20`(approx), `bearing(0,1)==90`, `clamp_speed(-50,8,30)==-30`. **Steps 2–5** → commit `feat(go): geometry helpers`.

### Task 4.2: DobotLinkClient + FakeWebSocket

**Files:** Create `src/dobotkit/go/client.py`, `tests/go/test_client.py`; Modify `tests/conftest.py` (`FakeWebSocket`).
**Interfaces:**
- Produces `class DobotLinkClient(host="localhost", port=9090, timeout=10.0, _ws_factory=None)`:
  - `connect() -> self`; `call(method, **params) -> Any` (sends JSON-RPC request, awaits matching id, raises `DobotLinkError` on error response / `DobotTimeoutError` on no reply); `notify(method, **params)` (fire-and-forget); `close()`; context manager.
  - Auto-prefix only `dobotlink.` (leave `MagicianGO.`/`MagicBox.` untouched).
  - JSON-RPC framing: `{"jsonrpc":"2.0","id":N,"method":...,"params":{...}}`.
- Sync wrapper over the `websockets` async API via an internal event loop/thread (the existing `magiciango/client.py` shows the working pattern — reuse its approach).
- [ ] **Step 1:** `FakeWebSocket` returns canned JSON responses; test `call("MagicianGO.GetBatteryVoltage", portName="COM5")` sends correct JSON & parses result; error response raises `DobotLinkError`; `notify` sends no-id frame.
- [ ] **Steps 2–5** → commit `feat(go): DobotLink WebSocket client`.

### Task 4.3: `MagicianGO` wrapper

**Files:** Create `src/dobotkit/go/magiciango.py`, `tests/go/test_magiciango.py`
**Interfaces:** Produces `class MagicianGO(client, port_name="COM5")` with the full method set from research doc §3 (and existing `go.py`), typed + docstringed:
- Connection: `connect_robot()`, `disconnect_robot()`, `search()`, `set_running_mode(mode)`, `connect(verify=True)` (calls `connect_robot` then `battery()`).
- Continuous: `move(x=0,y=0,r=0)`, `move_direct(direction,speed)`, `forward/backward/strafe/spin(speed)`, `stop()`, `emergency_stop()`.
- Closed-loop (⚠ HANG — docstring warns, recommends `PreciseMover`): `rotate`, `move_dist`, `arc_rad`, `arc_cent`, `coord_closed_loop`, `increment_closed_loop`.
- Sensors: `ultrasonic()`, `odometer()`, `set_odometer(x,y,yaw)`, `battery()`, `imu_angle()`, `imu_speed()`.
- Safety: `clearance_ok(x=0,y=0,r=0,threshold=20) -> (bool, dict|str)`.
- Output: `rgb(number,effect,r,g,b,cycle,counts)` (accepts `LEDChannel` or int/str), `buzzer(index,tone,beat)`.
- Line-trace: `auto_trace(on)`, `trace_speed(speed)`, `trace_pid(p,i,d)`, `trace_angle()`.
- Camera: `car_camera_obj()`, `arm_camera_obj()`, `arm_camera_tag()` (defensive parsing).
- Internal `_call(func, **params)` → `client.call(f"MagicianGO.{func}", portName=self.port_name, **params)`; `emergency_stop` uses `client.notify`.
- [ ] **Step 1:** Tests with a fake client (records calls): `forward(20)` → `MagicianGO.SetMoveSpeed(portName, x=20,...)`; `emergency_stop()` uses notify; `clearance_ok` logic with stubbed `ultrasonic`. **Steps 2–5** → commit `feat(go): MagicianGO high-level wrapper`.

### Task 4.4: Navigation (PreciseMover + WaypointNav)

**Files:** Create `src/dobotkit/go/navigation.py`, `tests/go/test_navigation.py`
**Interfaces:** Port `precise_move.py`/`waypoint_nav.py` semantics exactly (research doc §6–7):
- `PreciseMover(go, max_speed=30, min_speed=8)`: `goto_distance(distance_mm, speed, axis, threshold, timeout_s) -> dict{target,achieved,error,axis,timed_out,aborted[,reason]}`; `turn_degrees(deg, speed, threshold, timeout_s) -> dict`.
- `WaypointNav(go)`: `set_start(x_cm,y_cm,heading_deg)`, `go_to(x_cm,y_cm,arrive_tol_cm,max_iters) -> dict{...,legs}`, `pose_cm()`, `face(heading_deg) -> dict{...,bearing,from_heading}`.
- Heading-source rule: current heading = odometer yaw; rotation amount = IMU yaw delta (documented).
- All loops use `time.monotonic()` absolute timeout; every path ends in `emergency_stop`.
- [ ] **Step 1:** Tests inject a **simulated GO** (fake that advances odometer/imu per `move` calls + `monkeypatch` `time`) to verify: reaching target stops within tol; clearance-blocked returns `aborted=True,reason=...`; timeout returns `timed_out=True`. **Steps 2–5** → commit `feat(go): PreciseMover + WaypointNav`.

### Task 4.5: GO examples

**Files:** Create `examples/go_teleop.py`, `examples/go_waypoint_nav.py`, `examples/go_line_trace.py` (adapt existing `monitor.py`/`waypoint_nav.py`/`line_trace.py`, importing from `dobotkit.go`).
- [ ] Smoke-import test (no socket opened) → commit `feat(go): examples`.

---

# PHASE 5 — Integration & release

### Task 5.1: Top-level integration + lint/type gate

**Files:** Modify `src/dobotkit/__init__.py` (export enums + exceptions); Create `tests/test_integration.py`.
- [ ] **Step 1:** Test: `from dobotkit import Magician, MagicianGO, PTPMode, DobotError` all succeed; importing `dobotkit` does NOT import `serial` or `websockets` eagerly (assert via `sys.modules` before first device construction — or document that both are core deps so this only checks subpackage laziness).
- [ ] **Step 2:** Run full gate: `python -m pytest -q && python -m ruff check src tests && python -m mypy`. Fix issues. Commit `chore: integration + lint/type gate green`.

### Task 5.2: Docs + README

**Files:** Create `README.md`, `docs/api/arm.md`, `docs/api/go.md` (absorb & update `docs/두봇_라이트_API.md` / `docs/두봇_고_API.md`, retargeted to `dobotkit` imports).
- [ ] README: install, two quickstarts (arm pick-and-place, GO teleop), feature-coverage statement, safety notes. Commit `docs: README + API reference`.

### Task 5.3: Release polish

**Files:** Create `CHANGELOG.md`, `LICENSE` (MIT); verify `python -m build` produces a wheel; `pip install dist/*.whl` in a temp venv imports cleanly.
- [ ] Commit `chore: license, changelog, build verification`.

---

## Self-Review

**1. Spec coverage:**
- Spec §1 goals (all features / pure-Python / unified / open-source / safe / easy+complete) → Phases 0–5; "all features" proven by Task 2.10 coverage test + per-struct oracle match.
- §2 layout → File Structure table + tasks create each file.
- §3.1 framing → 1.1; §3.2 structs → 1.3 + per-category; §3.3 IDs → 1.2; §3.4 transport → 1.4; §3.5 queue → 1.5; §3.6 lowlevel → Phase 2; §3.7 high-level → Phase 3.
- §4 GO (client/wrapper/navigation/geometry) → Phase 4.
- §5 exceptions → 0.2. §6 safety → context manager (3.3), timeouts (1.5, 4.4), clearance (4.3). §7 testing → FakeSerial/FakeWebSocket/oracle/coverage throughout. §8 packaging → 0.1, 5.1, 5.3. §9 multiagent → execution handoff. §10 open items: IDs (1.2 cross-check + `# unverified` tags), pydobot aliases (3.3), GO unknowns (docstring notes in 4.3), package name (locked `dobotkit`).
- **No gaps found.**

**2. Placeholder scan:** Per-category Phase-2 tasks specify exact functions + structs + the canonical pattern (Task 2.1) + oracle gate — mechanical, not vague. No "TBD/add error handling/similar to Task N". OK.

**3. Type consistency:** `Message(id,ctrl,params)`, `make_ctrl(rw,queued)`, `LowLevelArm._send(id,params,*,rw,queued)`, `CommandQueue.wait_for(index,poll,timeout)`, `Pose` namedtuple, `pack_*/unpack_*` naming — consistent across tasks. `Magician` group props (`.io/.sensors/.effector/.lowlevel`) match Task 3.2/3.3. OK.
