"""SDK coverage cross-check (PLAN Task 2.10) — the proof of "all features".

This test enumerates *every* function exported by the golden ``DobotDllType.py``
oracle, subtracts the pure DLL-plumbing helpers, normalises each remaining name
to the ``LowLevelArm`` snake_case method the category agents implemented, and
asserts that method exists. If any SDK function is uncovered the test fails with
the offending names, so the cross-check is a living guarantee that the
low-level arm API spans the entire SDK surface.

Normalisation rules (``_expected_method``):

* keep the ``Set``/``Get`` prefix as ``set_``/``get_`` (the agents expose
  separate getters and setters rather than merging them on one name);
* fold the trailing call-variant suffix: ``Ex`` -> base (no suffix),
  ``Ext`` -> ``_ext``, ``ExtEx`` -> ``_ext_ex``;
* split the CamelCase/acronym core into snake_case using the SDK's semantic
  token boundaries (``IODO`` -> ``io_do``, ``EMotorS`` -> ``e_motors``,
  ``WIFISSID`` -> ``wifi_ssid``, ``PTPLParams`` -> ``ptp_l_params`` ...).

``_SPECIAL`` records the handful of names where the agents deviated from the
algorithmic rule (verified against ``dir(LowLevelArm)``): the queue-control
verbs drop the redundant ``set_`` and the three ``*Cmd`` commands whose method
omits the trailing ``cmd``.
"""
import inspect
import re


from dobotkit.arm.lowlevel import LowLevelArm

# Pure DLL-plumbing helpers — not part of the public command surface.
EXCLUDED = {
    "enum", "load", "dSleep", "gettime", "SetDebugEnable", "PeriodicTask",
    "DobotExec", "PrintInfo", "SetProgbar", "GetMarlinVersion",
}

# Multi-letter acronyms / glued tokens the agents split semantically.
# Longest-first so e.g. ``EMotorS`` wins over ``EMotor`` and ``IOMultiplexing``
# is matched whole before its ``IO`` prefix.
_ACRONYMS = [
    ("EMotorS", "e_motors"), ("EMotor", "e_motor"),
    ("IOMultiplexing", "io_multiplexing"), ("IOPWM", "io_pwm"),
    ("IOADC", "io_adc"), ("IODO", "io_do"), ("IODI", "io_di"),
    ("UART4", "uart4"), ("WIFI", "wifi"), ("SSID", "ssid"), ("DNS", "dns"),
    ("HHT", "hht"), ("PTP", "ptp"), ("JOG", "jog"), ("ARC", "arc"),
    ("CPR", "cpr"), ("CP", "cp"), ("IP", "ip"), ("TRIG", "trig"),
    ("WAIT", "wait"), ("HOME", "home"), ("RGB", "rgb"), ("ADC", "adc"),
    ("PWM", "pwm"), ("FW", "fw"), ("SN", "sn"), ("ID", "id"),
    ("DO", "do"), ("DI", "di"),
]

# Agent-chosen names that deviate from the algorithmic rule. Keyed by the bare
# SDK function name *after* the Ex/Ext/ExtEx suffix has been folded away.
_SPECIAL = {
    # Connection lifecycle: terse verbs, no "Dobot" noun.
    "SearchDobot": "search_dobot",
    "ConnectDobot": "connect",
    "DisconnectDobot": "disconnect",
    # Queue control: the redundant Set-prefix is dropped.
    "SetQueuedCmdStartExec": "queued_cmd_start_exec",
    "SetQueuedCmdStopExec": "queued_cmd_stop_exec",
    "SetQueuedCmdForceStopExec": "queued_cmd_force_stop_exec",
    "SetQueuedCmdStartDownload": "queued_cmd_start_download",
    "SetQueuedCmdStopDownload": "queued_cmd_stop_download",
    "SetQueuedCmdClear": "queued_cmd_clear",
    # Continuous-path commands whose numeral / acronym gluing differs.
    "SetCP2Cmd": "set_cp2_cmd",
    "SetCPLECmd": "set_cp_le_cmd",
    # Commands whose method drops the trailing "Cmd".
    "SetAutoLevelingCmd": "set_auto_leveling",
    "SetUpgradeFWReadyCmd": "set_upgrade_fw_ready",
    "GetUpgradeFWReadyCmd": "get_upgrade_fw_ready",
    "SetLostStepEnableAndParamsCmd": "set_lost_step_enable_and_params",
    "GetLostStepEnableAndParamsCmd": "get_lost_step_enable_and_params",
}


def _snake_core(core: str) -> str:
    """snake_case the prefix/suffix-stripped core, honouring SDK acronyms."""
    tokens = []
    i = 0
    while i < len(core):
        for token, repl in _ACRONYMS:
            if core.startswith(token, i):
                tokens.append(repl)
                i += len(token)
                break
        else:
            # One CamelCase word (``Upper`` + lowers/digits) or a lowercase run.
            m = re.match(r"[A-Z][a-z0-9]*|[a-z0-9]+", core[i:])
            if m:
                tokens.append(m.group(0).lower())
                i += m.end()
            else:  # stray uppercase not covered above: emit one char
                tokens.append(core[i].lower())
                i += 1
    return "_".join(t for t in tokens if t)


def _expected_method(name: str) -> str:
    """Map an SDK function name to the expected ``LowLevelArm`` method name."""
    # Fold the call-variant suffix first.
    suffix = ""
    if name.endswith("ExtEx"):
        suffix, base = "_ext_ex", name[:-len("ExtEx")]
    elif name.endswith("Ext"):
        suffix, base = "_ext", name[:-len("Ext")]
    elif name.endswith("Ex"):
        suffix, base = "", name[:-len("Ex")]  # Ex folds onto the base name
    else:
        base = name

    if base in _SPECIAL:
        return _SPECIAL[base] + suffix

    prefix = ""
    if base.startswith("Set"):
        prefix, core = "set_", base[3:]
    elif base.startswith("Get"):
        prefix, core = "get_", base[3:]
    else:
        core = base
    return prefix + _snake_core(core) + suffix


def _sdk_functions(oracle):
    """Yield the non-plumbing, public function names defined on the oracle.

    ``DobotDllType.py`` does ``from ctypes import *``, so ``vars(oracle)`` also
    holds imported ctypes helpers (``create_string_buffer``, ``cast`` ...). They
    are excluded by requiring the function to be *defined in the oracle module*
    (``obj.__module__`` equal to the oracle's own ``__name__``).
    """
    for fname, obj in vars(oracle).items():
        if not inspect.isfunction(obj) or fname in EXCLUDED or fname.startswith("_"):
            continue
        if getattr(obj, "__module__", None) != oracle.__name__:
            continue
        yield fname


def test_every_sdk_function_has_lowlevel_method(oracle):
    methods = {n for n in dir(LowLevelArm) if not n.startswith("_")}
    missing = []
    for fname in _sdk_functions(oracle):
        if _expected_method(fname) not in methods:
            missing.append((fname, _expected_method(fname)))
    assert not missing, f"uncovered SDK functions: {sorted(missing)}"


def test_coverage_count_matches_sdk_surface(oracle):
    """The mapped function count should equal the non-plumbing SDK surface.

    213 total functions - 10 plumbing helpers = 203 functions that must each
    resolve to a ``LowLevelArm`` method.
    """
    mapped = list(_sdk_functions(oracle))
    assert len(mapped) == 203, f"expected 203 mapped SDK functions, got {len(mapped)}"
    for fname in mapped:
        assert _expected_method(fname) in {
            n for n in dir(LowLevelArm) if not n.startswith("_")
        }, fname
