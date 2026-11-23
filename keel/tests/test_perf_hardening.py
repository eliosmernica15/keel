"""Agent 46 — performance & resource hardening regressions.

Every test here exercises real functions: it either forces a real interleaving,
calls a helper 1000+ times and inspects retained state, or verifies that a cap
is actually enforced rather than merely reported.
"""

from __future__ import annotations

import gc
import threading
import time
import tracemalloc

import pytest

from keel import hardware
from keel.hardware import advise_quantization, detect
from keel.performance_budgets import check
from keel.resource_caps import DEFAULT_CAPS, ResourceMeter


# --- hardware: bounded cache + sane RAM hint --------------------------------

def test_detect_platform_cache_is_bounded_over_1000_calls():
    hardware._platform_facts.cache_clear()
    for _ in range(1000):
        detect()
    info = hardware._platform_facts.cache_info()
    assert info.maxsize == 1
    assert info.currsize <= 1
    assert info.hits >= 999  # the cache is doing real work, not just present


def test_detect_cache_does_not_freeze_the_dynamic_ram_hint(monkeypatch):
    monkeypatch.setenv("KEEL_SYSTEM_RAM_GB", "16")
    assert detect()["ram_gb"] == 16.0
    monkeypatch.setenv("KEEL_SYSTEM_RAM_GB", "8")
    assert detect()["ram_gb"] == 8.0
    monkeypatch.delenv("KEEL_SYSTEM_RAM_GB", raising=False)
    assert detect()["ram_gb"] is None


@pytest.mark.parametrize("raw", ["nan", "inf", "-inf", "-8", "0", "garbage", "  "])
def test_unusable_ram_hint_is_treated_as_unknown(monkeypatch, raw):
    monkeypatch.setenv("KEEL_SYSTEM_RAM_GB", raw)
    assert detect()["ram_gb"] is None
    assert advise_quantization(7)["quant"] == "Q4_K_M"


@pytest.mark.parametrize("ram", [float("nan"), float("inf"), -1, 0, "64"])
def test_quantization_ignores_injected_nonsense_ram(ram):
    assert advise_quantization(7, {"ram_gb": ram})["quant"] == "Q4_K_M"


def test_repeated_detect_does_not_retain_memory():
    gc.collect()
    tracemalloc.start()
    try:
        before = tracemalloc.get_traced_memory()[0]
        for _ in range(1000):
            detect()
        gc.collect()
        after = tracemalloc.get_traced_memory()[0]
    finally:
        tracemalloc.stop()
    assert after - before < 100_000


# --- performance budgets: explicit empty budgets + bounded retained memory ---

def test_explicit_empty_budgets_mean_no_checks():
    assert check({"cold_start_ms": 5000}, budgets={}) == []
    # None must still select the defaults.
    assert check({"cold_start_ms": 5000})[0].limit == 3000
    # A caller-supplied budget map must be honoured verbatim.
    results = check({"cold_start_ms": 5000}, budgets={"cold_start_ms": 10})
    assert len(results) == 1 and results[0].limit == 10 and results[0].within is False


def test_repeated_checks_do_not_retain_memory():
    measurements = {"cold_start_ms": 1200, "idle_memory_mb": 110,
                    "installer_size_mb": 150, "time_to_first_token_ms": 900}
    gc.collect()
    tracemalloc.start()
    try:
        before = tracemalloc.get_traced_memory()[0]
        for _ in range(1000):
            check(measurements)
        gc.collect()
        after = tracemalloc.get_traced_memory()[0]
    finally:
        tracemalloc.stop()
    assert after - before < 100_000


# --- resource caps: real cap enforcement under forced interleaving ----------

class _YieldingDict(dict):
    """A dict that switches threads at the exact read point of acquire()."""

    def get(self, key, default=None):
        value = super().get(key, default)
        time.sleep(0)
        return value


def test_cap_is_enforced_under_concurrent_acquire():
    # The check-then-increment window is widened by the yielding dict; a
    # lock-free meter over-issues here (8 acquisitions against a cap of 4).
    for _ in range(8):
        meter = ResourceMeter()
        meter._used = _YieldingDict({key: 0 for key in DEFAULT_CAPS})
        successes: list[bool] = []
        barrier = threading.Barrier(8)

        def worker() -> None:
            barrier.wait()
            if meter.acquire("browser"):
                successes.append(True)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert len(successes) <= DEFAULT_CAPS["browser"]
        assert meter.meters()[0].used <= DEFAULT_CAPS["browser"]


def test_meter_state_stays_bounded_across_10000_cycles():
    meter = ResourceMeter()
    for _ in range(10_000):
        for feature in DEFAULT_CAPS:
            assert meter.acquire(feature) is True
            assert meter.release(feature) is True
        assert meter.acquire("unregistered_feature") is False
    assert set(meter._used) == set(DEFAULT_CAPS)
    assert all(count == 0 for count in meter._used.values())


def test_creating_and_discarding_1000_meters_retains_nothing():
    gc.collect()
    tracemalloc.start()
    try:
        before = tracemalloc.get_traced_memory()[0]
        for _ in range(1000):
            meter = ResourceMeter()
            meter.acquire("browser")
            del meter
        gc.collect()
        after = tracemalloc.get_traced_memory()[0]
    finally:
        tracemalloc.stop()
    assert after - before < 100_000
