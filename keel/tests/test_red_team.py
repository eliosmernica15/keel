"""C8.8 — local red-team evaluation suite."""

from __future__ import annotations

from keel.red_team import run_suite


def test_builtin_suite_passes():
    result = run_suite()
    assert result["total"] >= 4
    assert result["all_passed"] is True
    assert result["passed"] == result["total"]


def test_custom_case_can_fail():
    result = run_suite([("always_fails", lambda: (False, "nope"))])
    assert result["all_passed"] is False
    assert result["results"][0]["detail"] == "nope"


def test_exception_is_treated_as_refusal():
    def boom():
        raise RuntimeError("blocked")

    result = run_suite([("refuses", boom)])
    assert result["all_passed"] is True
