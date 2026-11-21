"""B1.7 — hardware detection and quantization advisor."""

from __future__ import annotations

from keel.hardware import advise_quantization, detect


def test_detect_returns_local_facts():
    info = detect()
    assert info["os"] and info["arch"]
    assert info["ram_gb"] is None or info["ram_gb"] > 0


def test_advice_scales_with_ram():
    big = advise_quantization(7, {"ram_gb": 64})
    small = advise_quantization(7, {"ram_gb": 4})
    assert big["quant"] == "F16"
    assert small["quant"] in ("Q4_K_M", "Q3_K_S")


def test_unknown_ram_is_conservative():
    advice = advise_quantization(7, {"ram_gb": None})
    assert advice["quant"] == "Q4_K_M"
