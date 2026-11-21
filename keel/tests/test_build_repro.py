"""A4.2/A4.5 — reproducible builds and agent routing."""

from __future__ import annotations

from keel.build_repro import build_manifest, route_task


def test_manifest_is_deterministic():
    a = build_manifest("0.1.1", "windows", {"src": "abc", "deps": ["x", "y"]})
    b = build_manifest("0.1.1", "windows", {"deps": ["x", "y"], "src": "abc"})
    assert a.digest == b.digest
    c = build_manifest("0.1.2", "windows", {"src": "abc", "deps": ["x", "y"]})
    assert c.digest != a.digest


def test_task_routing():
    agent, model = route_task("refactor")
    assert agent == "code-agent" and model == "local-large"
    assert route_task("unknown")[0] == "general-agent"
