"""C9.1 — local model manager with budgets and idle unload."""

from __future__ import annotations

from keel.model_manager import ModelManager


def test_load_and_budget():
    manager = ModelManager(budget_mb=100)
    assert manager.load("small", 40, now=0) is True
    assert manager.load("medium", 50, now=0) is True
    assert manager.load("too-big", 80, now=0) is False
    assert manager.total_mb == 90
    assert manager.status(now=0)["budget_mb"] == 100


def test_idle_unload():
    manager = ModelManager(budget_mb=100, idle_timeout_s=10)
    assert manager.load("a", 30, now=0) is True
    manager.touch("a", now=5)
    assert manager.unload_idle(now=14) == []  # only 9s idle
    assert manager.unload_idle(now=16) == ["a"]
    assert manager.total_mb == 0
    assert manager.status()["unloaded"] == ["a"]


def test_explicit_unload_and_touch():
    manager = ModelManager(budget_mb=100)
    manager.load("x", 20, now=0)
    assert manager.touch("x", now=1) is True
    assert manager.touch("missing", now=1) is False
    assert manager.unload("x") is True
    assert manager.unload("x") is False
