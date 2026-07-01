"""Entry point for ``python -m dobotkit.gui`` (and ``--demo``).

Delegates straight to :func:`dobotkit.gui.app.main`, so both

    python -m dobotkit.gui
    python -m dobotkit.gui --demo

launch the control panel. The import stays module-local-cheap: importing
``dobotkit.gui.app`` only defines classes and pulls in ``tkinter`` (which does
not open a display), so no ``Tk()`` root is created until ``main()`` runs.
"""
from __future__ import annotations

from .app import main

if __name__ == "__main__":
    raise SystemExit(main())
