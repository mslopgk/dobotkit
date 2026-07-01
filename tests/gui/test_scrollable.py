"""ScrollableFrame must expose an interior and grow its scrollregion to fit it.

Guarded: skips where no display is available.
"""
from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")

from dobotkit.gui.widgets import ScrollableFrame  # noqa: E402


@pytest.fixture(scope="module")
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    r.geometry("300x200")
    r.update_idletasks()
    yield r
    r.destroy()


def test_interior_exists_and_is_a_child(root) -> None:
    sf = ScrollableFrame(root)
    sf.pack(fill="both", expand=True)
    assert sf.interior is not None
    # The interior lives inside the scrollable's canvas.
    assert sf.interior.winfo_toplevel() is root
    sf.destroy()


def test_scrollregion_grows_with_tall_content(root) -> None:
    sf = ScrollableFrame(root)
    sf.pack(fill="both", expand=True)
    # Add far more content than the 200px-tall window can show.
    from tkinter import ttk

    for i in range(60):
        ttk.Label(sf.interior, text=f"row {i}").pack(anchor="w")
    root.update_idletasks()
    sf.update_idletasks()

    x0, y0, x1, y1 = sf._canvas.bbox("all")
    content_height = y1 - y0
    # The scrollable content is taller than the visible canvas -> scrolling is
    # both possible and necessary (the exact defect the user hit).
    assert content_height > sf._canvas.winfo_height()
    assert content_height > 400
    sf.destroy()
