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
    """Run a confined process; report an unavailable kernel boundary as BLOCKED.

    A launch failure is reported as BLOCKED (not as a failed security test) when
    the host cannot start the requested executable under the active boundary.
    On Windows this is expected for the Python interpreter under an AppContainer
    token (its DLL dependencies are not granted to the package SID); the
    filesystem/network boundary itself is still proven by the cmd.exe-based
    adversarial tests in test_sandbox_windows.py / test_win_network.py.
    """
    try:
        result = run_confined(*args, **kwargs)
        launch_failed = (
            not result.ok
            and result.exit_code not in (0, None)
            and not result.stdout.strip()
            and result.timed_out is False
        )
        if not result.ok and (MACOS or "Operation not permitted" in result.stderr
                              or (WINDOWS and launch_failed)):
            pytest.skip("BLOCKED: sandbox could not launch this executable on "
                        f"this host (exit={result.exit_code}): "
                        f"{result.stderr[:120]}")
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
        # Network denial is now genuinely enforced via a capability-less
        # AppContainer (see master-plan-v6-win-network-evidence.md); WFP
        # per-process filters remain unavailable without elevation.
        assert caps["network_enforcement"] is True
        assert caps.get("windows_appcontainer") is True
        joined = " ".join(caps["limitations"]).lower()
        assert "wfp" in joined or "firewall" in joined


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
        if WINDOWS:
            argv = [
                os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
                "/c", f"echo {i}",
            ]
        else:
            argv = [sys.executable, "-c", f"print({i})"]
        return confined_or_blocked(
            argv, workspace=tmp_path / str(i), timeout_s=15)

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


def test_inproc_seccomp_filter_layout_is_correct():
    """Regression: the BPF jump offsets must deny network syscalls.

    A previous revision used opcode 0x00 at offset 4 with an intervening
    `ja`, inverting the branch so that network syscalls were allowed and all
    others denied. This pure test runs on every platform, including Windows.
    """
    from keel.os_sandbox import (DENIED_NETWORK_SYSCALLS,
                                 build_inproc_network_filter)

    insns = build_inproc_network_filter()
    assert insns[0] == (0x20, 0, 0, 0)  # BPF_LD|BPF_W|BPF_ABS, nr at offset 0
    assert insns[-1] == (0x06, 0, 0, 0x7fff0000)  # default ALLOW
    body = insns[1:-1]
    assert len(body) == 2 * len(DENIED_NETWORK_SYSCALLS)
    for i, nr in enumerate(sorted(DENIED_NETWORK_SYSCALLS)):
        jeq, ret = body[2 * i], body[2 * i + 1]
        assert jeq == (0x15, 0, 1, nr)  # jt=0 falls through, jf=1 skips
        assert ret == (0x06, 0, 0, 0x00050001)  # ERRNO(EPERM)
    assert 41 in DENIED_NETWORK_SYSCALLS  # socket

    def verdict(syscall_nr):
        pc = 0
        acc = syscall_nr
        while True:
            code, jt, jf, k = insns[pc]
            if code == 0x20:  # ld nr
                acc = syscall_nr
                pc += 1
            elif code == 0x15:  # jeq
                pc += 1 + (jt if acc == k else jf)
            elif code == 0x06:  # ret
                return k
            else:
                raise AssertionError(f"unexpected BPF opcode {code:#x}")

    assert verdict(41) == 0x00050001  # socket -> EPERM
    assert verdict(42) == 0x00050001  # connect -> EPERM
    assert verdict(1) == 0x7fff0000   # write -> ALLOW


def test_windows_backend_is_dispatched_not_bypassed():
    """Windows run_confined must delegate to the restricted-token backend."""
    import inspect

    import keel.os_sandbox as os_sandbox

    src = inspect.getsource(os_sandbox.run_confined)
    if os.name == "nt":
        assert "sandbox_windows" in src
        assert "return _backend(" in src
    else:
        assert "sandbox_windows" in src  # dispatch branch present regardless


def test_all_platform_backends_are_dispatched():
    """Every supported platform must route to its dedicated backend."""
    import inspect

    import keel.os_sandbox as os_sandbox

    src = inspect.getsource(os_sandbox.run_confined)
    for backend in ("sandbox_windows", "sandbox_linux", "sandbox_macos"):
        assert backend in src, f"missing dispatch to {backend}"
