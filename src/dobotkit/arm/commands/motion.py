"""Motion command RPC wrappers (PTP, CP, ARC, jog, ...)."""
from __future__ import annotations
from typing import Any
from dobotkit.arm.commands._base import _Base


class MotionMixin(_Base):
    """RPC wrappers for Magician arm motion commands (PTP, CP, ARC, jog, params)."""

    # -- pose / motion --
    def get_pose(self) -> Any:
        """Get current arm pose (x, y, z, r, jointAngle)."""
        return self._call("GetPose")

    def set_ptp_cmd(self, mode: int, x: float, y: float, z: float, r: float,
                    queued: bool = True) -> int:
        """Send PTP (point-to-point) motion command; returns queued command index."""
        return self._queued_index(self._call(
            "SetPTPCmd", ptpMode=int(mode), x=float(x), y=float(y), z=float(z), r=float(r),
            isQueued=queued))

    def set_home_params(self, x: float, y: float, z: float, r: float,
                        queued: bool = True) -> Any:
        """Set home position parameters."""
        return self._call("SetHOMEParams", x=x, y=y, z=z, r=r, isQueued=queued)

    def set_home_cmd(self, queued: bool = True) -> int:
        """Send home command; returns queued command index."""
        return self._queued_index(self._call("SetHOMECmd", isQueued=queued))

    def set_ptp_common_params(self, velocity: float, acceleration: float) -> Any:
        """Set PTP common parameters (velocity and acceleration ratios)."""
        return self._call("SetPTPCommonParams",
                          velocityRatio=velocity, accelerationRatio=acceleration)

    def set_ptp_coordinate_params(self, velocity: float, acceleration: float) -> Any:
        """Set PTP coordinate parameters (velocity and acceleration in xyz and r)."""
        return self._call("SetPTPCoordinateParams",
                          xyzVelocity=velocity, rVelocity=velocity,
                          xyzAcceleration=acceleration, rAcceleration=acceleration)

    def set_wait_cmd(self, ms: int, queued: bool = True) -> int:
        """Send wait command with timeout in milliseconds; returns queued command index."""
        return self._queued_index(self._call("SetWAITCmd", timeout=int(ms), isQueued=queued))
