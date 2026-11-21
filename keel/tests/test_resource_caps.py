"""C9.3/C9.4 — per-feature resource caps and low-power mode."""

from __future__ import annotations

from keel.resource_caps import ResourceMeter


def test_meter_enforces_cap():
    meter = ResourceMeter()
    for _ in range(4):
        assert meter.acquire("browser") is True
    assert meter.acquire("browser") is False  # default cap is 4
    assert len(meter.meters()) == 3


def test_low_power_tightens_caps():
    meter = ResourceMeter(low_power=True)
    assert meter.acquire("browser") is True
    assert meter.acquire("browser") is False
    assert meter.acquire("container") is False
    meter.set_low_power(False)
    assert meter.acquire("browser") is True


def test_release():
    meter = ResourceMeter()
    assert meter.release("browser") is False
    meter.acquire("lsp")
    assert meter.release("lsp") is True
