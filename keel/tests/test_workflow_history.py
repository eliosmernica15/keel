"""C5.x/C8 — workflow history and anomaly scoring."""

from __future__ import annotations

from keel.workflow_history import WorkflowHistory, anomaly_score


def test_versioning_and_restore(tmp_path):
    history = WorkflowHistory(tmp_path)
    assert history.save("deploy", {"steps": [1]}) == 1
    assert history.save("deploy", {"steps": [1, 2]}) == 2
    assert history.get("deploy")["steps"] == [1, 2]
    assert history.get("deploy", 1)["steps"] == [1]
    assert len(history.versions("deploy")) == 2


def test_anomaly_score():
    calm = [{"kind": "ok"} for _ in range(5)]
    storm = [{"tool": "delete_file"}] * 5
    assert anomaly_score(calm) == 0.0
    assert anomaly_score(storm) == 1.0
