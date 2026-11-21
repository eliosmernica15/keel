"""B4.13 — auto-rollback after repeated failed starts."""

from __future__ import annotations

from keel import start_health


def test_three_failures_trigger_rollback(tmp_path):
    for _ in range(2):
        result = start_health.record_start(str(tmp_path), "0.2.0", ok=False)
        assert result["rollback"] is False
    result = start_health.record_start(str(tmp_path), "0.2.0", ok=False)
    assert result["rollback"] is True
    assert result["failures"] == 3


def test_success_resets_counter(tmp_path):
    start_health.record_start(str(tmp_path), "0.2.0", ok=False)
    start_health.record_start(str(tmp_path), "0.2.0", ok=False)
    result = start_health.record_start(str(tmp_path), "0.2.0", ok=True)
    assert result["failures"] == 0 and result["rollback"] is False


def test_versions_are_independent_and_reset(tmp_path):
    start_health.record_start(str(tmp_path), "0.2.0", ok=False)
    start_health.record_start(str(tmp_path), "0.2.0", ok=False)
    other = start_health.record_start(str(tmp_path), "0.3.0", ok=False)
    assert other["failures"] == 1
    start_health.reset(str(tmp_path), "0.2.0")
    fresh = start_health.record_start(str(tmp_path), "0.2.0", ok=False)
    assert fresh["failures"] == 1
