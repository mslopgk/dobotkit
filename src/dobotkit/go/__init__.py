"""dobotkit.go — Magician GO control over the DobotLink WebSocket (JSON-RPC).

This subpackage wraps the DobotLink ``MagicianGO.*`` RPC surface and layers
sensor-feedback navigation on top of it. It talks to ``ws://localhost:9090``
via the ``websockets`` library; nothing here touches the arm's serial stack.

Submodules are intentionally **not** imported eagerly. Importing
``dobotkit.go`` must stay light (no ``websockets`` import, no socket) so that a
program controlling only the arm never pulls in GO dependencies. Public
exports are wired up in Phase 5; until then import the concrete classes from
their modules directly, e.g.::

    from dobotkit.go.client import DobotLinkClient
    from dobotkit.go.magiciango import MagicianGO
    from dobotkit.go.navigation import PreciseMover, WaypointNav
"""
