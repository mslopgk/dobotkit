"""Back-compat: DobotLinkClient moved to dobotkit.link."""
import time  # noqa: F401 - kept so `client_mod.time` still resolves for tests
# that monkeypatch this module's `time` attribute (same singleton as
# ``dobotkit.link``'s, so the patch takes effect there too).

from dobotkit.link import DobotLinkClient

__all__ = ["DobotLinkClient"]
