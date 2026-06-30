"""Shared test fixtures for dobotkit.

Provides:
- ``oracle`` session fixture: loads the golden ``DobotDllType.py`` (test-only,
  never a runtime dependency) for byte-comparing our struct packing. Tests that
  use it ``pytest.skip()`` when the oracle is not importable.
- ``FakeSerial``: an in-memory serial double for arm transport/queue tests.
"""
import os
import sys
import importlib.util
import pytest

# Absolute default path to the golden oracle. Override with DOBOT_ORACLE_PATH.
_DEFAULT_ORACLE_PATH = (
    r"C:/Users/user/dobot-main/Dobot_Demo_V2.3/python64/"
    r"demo-magician-python-64-master/DobotDllType.py"
)


def _load_oracle():
    path = os.environ.get("DOBOT_ORACLE_PATH", _DEFAULT_ORACLE_PATH)
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


class FakeSerial:
    """In-memory serial double: queue response frames, capture writes."""

    def __init__(self, responses=None):
        self.written = bytearray()
        self._rx = bytearray()
        for r in (responses or []):
            self._rx += r
        self.is_open = True

    def write(self, data):
        self.written += data
        return len(data)

    def read(self, n=1):
        out = self._rx[:n]
        del self._rx[:n]
        return bytes(out)

    def reset_input_buffer(self):
        pass

    def reset_output_buffer(self):
        pass

    def close(self):
        self.is_open = False

    def queue_response(self, frame: bytes):
        self._rx += frame
