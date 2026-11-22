"""C13.2 — deterministic trajectory judge, comparison and auditability."""

from __future__ import annotations

from keel.judge import compare, evaluate, rubric_report
from keel.external_adapters import judge_score


def _trajectory():
    return [
        {"tool": "read_file", "input": "a.py", "ok": True},
        {"tool": "read_file", "input": "a.py", "ok": True},   # duplicate/wasted
        {"tool": "write_file", "input": "b.py", "ok": True,
         "policy_violation": True},
    ]


def test_evaluate_criteria_and_evidence():
    report = evaluate(_trajectory())
    assert report["steps"] == 3
    assert report["violations"] == 1
    assert report["wasted"] == 1
    assert set(report["criteria"]) == {
        "completion", "policy", "efficiency", "latency"}
    assert report["criteria"]["completion"]["score"] == 1.0
    assert report["criteria"]["policy"]["score"] < 1.0
    assert report["deterministic"] is True
    assert report["model_called"] is False
    assert 0 <= report["score"] <= 1
    assert report["grade"] in ("A", "B", "C", "D", "F")


def test_empty_trajectory():
    report = evaluate([])
    assert report["score"] == 0.0 and report["steps"] == 0


def test_weights_change_score():
    base = evaluate(_trajectory())
    weighted = evaluate(_trajectory(), weights={"completion": 1.0,
                                                 "policy": 0.0,
                                                 "efficiency": 0.0,
                                                 "latency": 0.0})
    assert weighted["score"] != base["score"]


def test_expected_steps_latency():
    efficient = evaluate([{"ok": True}], expected_steps=1)
    bloated = evaluate([{"ok": True}] * 10, expected_steps=1)
    assert efficient["criteria"]["latency"]["score"] > \
        bloated["criteria"]["latency"]["score"]


def test_compare_ranks():
    good = [{"ok": True}, {"ok": True}]
    bad = [{"ok": False}, {"ok": False}, {"ok": False}]
    result = compare([bad, good], names=["bad", "good"])
    assert result["winner"] == "good"
    assert [c["rank"] for c in result["candidates"]] == [1, 2]
    assert result["model_called"] is False


def test_rubric_report():
    text = rubric_report(evaluate(_trajectory()))
    assert "Score:" in text and "| Criterion |" in text
    assert "no model was called" in text


def test_backward_compatible_judge_score():
    result = judge_score([{"ok": True}, {"ok": False}, {"ok": True}])
    assert result["score"] > 0.5 and result["steps"] == 3
    assert "violations" in result


def test_capability_integration():
    from keel import capability_registry  # noqa: F401
    from keel.capabilities import invoke

    report = invoke("code.judge.evaluate",
                    {"trajectory": [{"ok": True}]}, context={})["result"]
    assert report["steps"] == 1
    ranked = invoke("code.judge.compare",
                    {"trajectories": [[{"ok": True}], [{"ok": False}]]},
                    context={})["result"]
    assert ranked["winner"] is not None
