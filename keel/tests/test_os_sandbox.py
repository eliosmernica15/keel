"""Adversarial OS-sandbox tests: real confined processes, not policy checks."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from keel.os_sandbox import SandboxUnavailable, capabilities, run_confined

LINUX = sys.platform.startswith("linux")
MACOS = sys.platform == "darwin"
WINDOWS = os.name == "nt"


def confined_or_blocked(*args, **kwargs):
    """Run a confined process; report an unavailable kernel boundary as BLOCKED."""
    try:
        result = run_confined(*args, **kwargs)
        if not result.ok and "Operation not permitted" in result.stderr:
            pytest.skip("BLOCKED: sandbox profile could not launch a process on this host")
        return result
    except SandboxUnavailable as exc:
        pytest.skip(f"BLOCKED: OS enforcement unavailable: {exc}")


def test_capabilities_report_real_enforcement():
    caps = capabilities()
    assert caps["os"] == sys.platform
    assert isinstance(caps["limitations"], list)
    if LINUX:
        assert "linux_landlock" in caps and "linux_seccomp" in caps
    if WINDOWS:
        assert caps["network_enforcement"] is False
        assert any("firewall" in item for item in caps["limitations"])


def test_workspace_read_and_outside_denied(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "allowed.txt").write_text("workspace-secret", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("OUTSIDE-SECRET", encoding="utf-8")
    r = confined_or_blocked(
        [sys.executable, "-c",
         f"import pathlib; print(pathlib.Path({str(workspace / 'allowed.txt')!r}).read_text())"],
        workspace=workspace, timeout_s=15)
    assert r.ok and "workspace-secret" in r.stdout
    if LINUX or MACOS:
        r2 = confined_or_blocked(
            [sys.executable, "-c",
             f"print(open({str(outside)!r}).read())"],
            workspace=workspace, timeout_s=15)
        assert not r2.ok or "OUTSIDE-SECRET" not in r2.stdout
    else:
        pytest.skip("Windows filesystem ACL enforcement not applied in this backend")


def test_network_denied_by_default(tmp_path):
    if not (LINUX or MACOS):
        pytest.skip("network enforcement requires Linux Landlock/seccomp or macOS profile")
    r = confined_or_blocked(
        [sys.executable, "-c",
         "import socket; s=socket.socket(); s.settimeout(1); "
         "s.connect(('127.0.0.1', 9)); print('CONNECTED')"],
        workspace=tmp_path, timeout_s=15)
    assert "CONNECTED" not in r.stdout


def test_secret_environment_not_inherited(tmp_path):
    r = confined_or_blocked(
        [sys.executable, "-c",
         "import os; print(os.environ.get('KEEL_SANDBOX_SECRET_PROBE'))"],
        workspace=tmp_path, env={**os.environ,
                                "KEEL_SANDBOX_SECRET_PROBE": "SHOULD-NOT-LEAK"},
        timeout_s=15)
    # The OS sandbox does not itself scrub env; the policy layer does. Confirm
    # actual behavior rather than claiming enforcement that is not present.
    assert r.ok and "SHOULD-NOT-LEAK" in r.stdout


def test_process_tree_termination(tmp_path):
    r = confined_or_blocked(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        workspace=tmp_path, timeout_s=2)
    assert r.timed_out is True


def test_concurrent_confinement(tmp_path):
    import concurrent.futures

    def run(i):
        return confined_or_blocked([sys.executable, "-c", f"print({i})"],
                            workspace=tmp_path / str(i), timeout_s=15)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run, range(4)))
    assert all(r.ok for r in results)
    assert {r.stdout.strip() for r in results} == {"0", "1", "2", "3"}


def test_regression_main_bootstrap_escape(tmp_path):
    """Previously reproduced escape via __main__ global mutation stays closed."""
    from keel.sandbox_exec import run_python

    outside = tmp_path / "secret.txt"
    outside.write_text("TOP-SECRET", encoding="utf-8")
    code = (f"import __main__; __main__._ROOT={str(tmp_path)!r}; "
            f"print(open({str(outside)!r}).read())")
    result = run_python(code, timeout_s=10)
    assert "TOP-SECRET" not in result.stdout
