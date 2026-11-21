"""A1.11 — browser and workspace resource management."""

from __future__ import annotations

import pytest

from keel.resource_limits import ResourceLimitError, ResourceManager


def test_tab_limit_and_close():
    manager = ResourceManager(max_tabs=2)
    manager.open_tab("a", url="https://a.test")
    manager.open_tab("b")
    assert manager.status()["tabs"] == 2
    with pytest.raises(ResourceLimitError, match="tab limit"):
        manager.open_tab("c")
    with pytest.raises(ResourceLimitError, match="already open"):
        manager.open_tab("a")
    assert manager.close_tab("a") is True
    assert manager.close_tab("missing") is False
    assert manager.open_tab("c")["id"] == "c"


def test_workspace_byte_budget():
    manager = ResourceManager(max_workspace_bytes=100)
    assert manager.attach_workspace(40) == 40
    with pytest.raises(ResourceLimitError, match="workspace"):
        manager.attach_workspace(70)
    assert manager.detach_workspace(20) == 20


def test_resource_size_cap():
    manager = ResourceManager(max_resource_bytes=10)
    assert manager.check_resource("12345") == 5
    with pytest.raises(ResourceLimitError, match="exceeds"):
        manager.check_resource("x" * 20)


def test_status_reports_limits():
    status = ResourceManager(max_tabs=3).status()
    assert status["tab_limit"] == 3
    assert status["tabs"] == 0
