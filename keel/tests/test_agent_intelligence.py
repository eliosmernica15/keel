"""C3.x — agent intelligence helpers."""

from __future__ import annotations

import json

from keel.agent_intelligence import (estimate_run, learn_style,
                                     record_postmortem, think_harder_effort,
                                     uncertainty_policy)


def test_think_harder_levels():
    assert think_harder_effort(0) == "minimal"
    assert think_harder_effort(3) == "high"
    assert think_harder_effort(99) == "high"


def test_estimate_and_uncertainty():
    estimate = estimate_run("short task")
    assert estimate["tokens"] > 0
    assert 0 < estimate["confidence"] <= 1
    assert uncertainty_policy(0.9) == "proceed"
    assert uncertainty_policy(0.1) == "ask_user"


def test_postmortem_and_style(tmp_path):
    entry = record_postmortem(tmp_path, "task", "boom")
    assert entry["error"] == "boom"
    assert (tmp_path / "postmortems.jsonl").is_file()
    profile = learn_style(tmp_path, "Short. Another sentence.\n- bullet")
    assert profile["samples"] == 1 and profile["bullet_style"] is True
    assert json.loads((tmp_path / "style-profile.json").read_text())["samples"] == 1
