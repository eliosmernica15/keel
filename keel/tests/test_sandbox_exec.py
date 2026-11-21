"""B3.1/B3.2 — real bounded sandbox execution."""

from __future__ import annotations

import pytest

from keel.sandbox_exec import run_python


def test_success_and_output_capture():
    result = run_python("print('hello'); import sys; print('err', file=sys.stderr)")
    assert result.ok is True
    assert "hello" in result.stdout and "err" in result.stderr
    assert result.exit_code == 0


def test_error_result():
    result = run_python("raise ValueError('boom')")
    assert result.ok is False and result.exit_code != 0
    assert "ValueError" in result.stderr


def test_timeout_is_bounded():
    result = run_python("import time; time.sleep(30)", timeout_s=0.5)
    assert result.timed_out is True and result.ok is False
    assert result.elapsed_s < 3


def test_invalid_timeout():
    with pytest.raises(ValueError):
        run_python("pass", timeout_s=0)
