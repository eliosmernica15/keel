"""A1.17/A1.18/A1.20 — CLI extras."""

from __future__ import annotations

import json

from keel.cli_extras import create_agent_spec, env_overrides, usage_stats


def test_usage_stats(tmp_path):
    path = tmp_path / "cost-usage.jsonl"
    path.write_text(json.dumps({"model": "m1", "ts": "2026-01-01T00:00:00Z",
                                "cost_usd": 0.5}) + "\n", encoding="utf-8")
    stats = usage_stats(tmp_path)
    assert stats["by_model"]["m1"] == 1
    assert stats["by_day"]["2026-01-01"] == 0.5


def test_env_overrides_masked(monkeypatch):
    monkeypatch.setenv("KEEL_TEST_FLAG", "secret-value")
    overrides = env_overrides()
    assert overrides["KEEL_TEST_FLAG"] == "set"
    assert "secret-value" not in str(overrides)


def test_agent_spec():
    spec = create_agent_spec("writer", model="local", surface="cowork")
    assert spec["name"] == "writer" and spec["surface"] == "cowork"
