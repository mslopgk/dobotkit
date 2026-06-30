"""Pack/unpack for Dobot arm payload structures (split into category modules).

This package aggregates every wire-payload (un)packer. The **core motion set**
lives in :mod:`._core`; remaining categories live in sibling modules owned by
their respective Phase-2 tasks. All names are re-exported here so callers can
use ``from dobotkit.arm import structures as S`` and reach any ``pack_*`` /
``unpack_*`` / struct ``NamedTuple`` regardless of which module defines it.

See :mod:`._core` for the little-endian / packed wire-format conventions and the
:func:`fmt_from_fields` ctypes-to-``struct`` mapping helper.
"""
from __future__ import annotations

from ._core import *  # noqa: F401,F403
from .device import *  # noqa: F401,F403
from .pose import *  # noqa: F401,F403
from .ptp import *  # noqa: F401,F403
from .jog import *  # noqa: F401,F403
from .cp_arc import *  # noqa: F401,F403
from .effector import *  # noqa: F401,F403
from .io import *  # noqa: F401,F403
from .sensor import *  # noqa: F401,F403
from .system import *  # noqa: F401,F403
