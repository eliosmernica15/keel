"""C9.2 — virtualized list windowing and streaming backpressure."""

from __future__ import annotations

from keel.virtual_list import Backpressure, visible_window


def test_window_renders_only_visible_slice():
    window = visible_window(total=10000, scroll_top=5000,
                            viewport=400, item_height=20, overscan=2)
    assert window.end - window.start < 100
    assert window.start < 250 < window.end
    assert window.offset == window.start * 20


def test_window_at_top_and_bottom():
    top = visible_window(100, 0, 100, 10, overscan=1)
    assert top.start == 0
    bottom = visible_window(100, 990, 100, 10, overscan=1)
    assert bottom.end == 100


def test_backpressure_rate_limit():
    bp = Backpressure(rate=10, burst=2)
    assert bp.allow(now=0) is True
    assert bp.allow(now=0.01) is True
    assert bp.allow(now=0.02) is False  # burst exhausted
    assert bp.allow(now=0.2) is True   # tokens refilled
