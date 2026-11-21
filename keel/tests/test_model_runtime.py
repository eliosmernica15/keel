"""C9.1 — real local model runtime manager."""

from __future__ import annotations

from keel.model_runtime import ModelRuntime


def test_budget_and_lru_eviction():
    runtime = ModelRuntime(budget_bytes=100)
    assert runtime.load("a", 60, "cmd-a") is True
    assert runtime.load("b", 50, "cmd-b") is True  # evicts a (LRU)
    assert "a" in runtime.evicted
    assert "a" not in runtime.models and "b" in runtime.models
    assert runtime.used == 50


def test_touch_and_unload():
    runtime = ModelRuntime(budget_bytes=100)
    runtime.load("x", 40)
    assert runtime.touch("x") is True
    assert runtime.touch("missing") is False
    assert runtime.unload("x") is True
    assert runtime.unload("x") is False


def test_status_and_no_command_launch():
    runtime = ModelRuntime(budget_bytes=100)
    runtime.load("x", 40)
    status = runtime.status()
    assert status["used_bytes"] == 40 and status["budget_bytes"] == 100
    assert runtime.start("x") is None  # no command supplied
