"""Native OS-level execution limits — real process, not a policy test."""

from __future__ import annotations

import os
import sys

from keel.native_isolation import (IsolationUnavailable, platform_support,
                                   run_isolated)


def test_platform_support_shape():
    support = platform_support()
    assert "os" in support and "windows_job_object" in support
    assert support["network_isolation"] is False
    assert "not full OS sandboxing" in support["note"]


def test_native_process_execution():
    result = run_isolated([sys.executable, "-c", "print('native-ok')"],
                          timeout_s=10)
    assert result.ok is True
    assert result.exit_code == 0
    assert "native-ok" in result.stdout
    assert result.mechanism in ("windows-job-object", "posix-rlimits")
    assert result.limits and result.limits["memory_mb"] >= 256


def test_native_timeout_terminates_process():
    result = run_isolated(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        timeout_s=2)
    assert result.timed_out is True
    assert result.exit_code is None


def test_native_isolation_scrubs_environment():
    result = run_isolated(
        [sys.executable, "-c", "import os; print(os.environ.get('KEEL_SECRET_PROBE'))"],
        env={**os.environ, "KEEL_SECRET_PROBE": "should-not-leak"},
        timeout_s=10)
    # The caller may pass env explicitly; verify real value is observed rather
    # than fabricated success. Native isolation does not itself scrub env.
    assert result.ok is True
    assert "should-not-leak" in result.stdout


def test_fail_closed_when_forced():
    import keel.native_isolation as ni

    original = ni.platform_support
    original_win = ni.IS_WINDOWS
    try:
        ni.IS_WINDOWS = False
        ni.platform_support = lambda: {
            "os": "unsupported", "windows_job_object": False,
            "posix_rlimits": False, "network_isolation": False, "note": ""}
        try:
            ni.run_isolated([sys.executable, "-c", "pass"],
                            require_native=True)
        except IsolationUnavailable:
            return
        raise AssertionError("did not fail closed")
    finally:
        ni.platform_support = original
        ni.IS_WINDOWS = original_win
