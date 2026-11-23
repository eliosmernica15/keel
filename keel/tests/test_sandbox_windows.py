"""Adversarial tests for the genuine Windows OS-enforcement backend.

These tests launch REAL restricted child processes.  Every filesystem
assertion is enforced by a restricted primary token plus workspace ACLs and is
expected to hold; failures are not converted to skips.

Network scoping (F6): Windows network denial is genuinely unavailable to this
backend (AppContainer token promotion needs privileges absent from a
non-elevated token; no firewall rule is applied).  Therefore:

* the default ``allow_network=False`` path is asserted to FAIL CLOSED, and
* tests that need a running process pass ``allow_network=True`` explicitly.
  Those tests claim only filesystem / Job Object / token enforcement, never
  network enforcement.  No assertion is silently skipped to hide a failure.

On non-Windows hosts the whole module skips cleanly.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from keel.os_sandbox import SandboxUnavailable

WINDOWS = os.name == "nt"
pytestmark = pytest.mark.skipif(
    not WINDOWS, reason="Windows OS enforcement requires os.name == 'nt'")

if WINDOWS:
    from keel import sandbox_windows as sw
    from keel.sandbox_windows import capabilities, run_confined


COMSPEC = os.environ.get("COMSPEC", r"C:\WINDOWS\system32\cmd.exe")


def confined(argv, *, workspace, **kwargs):
    """Run with FS/token/Job enforcement; network is knowingly left open.

    Network denial is BLOCKED on Windows (see module docstring), so execution
    requires the explicit ``allow_network=True`` opt-in.  These tests assert
    only the boundaries that are actually applied.
    """
    kwargs.setdefault("allow_network", True)
    kwargs.setdefault("timeout_s", 10)
    return run_confined(argv, workspace=workspace, **kwargs)


def outside_secret(tmp_path: Path, name: str = "outside-secret.txt") -> Path:
    secret = tmp_path / name
    secret.write_text("OUTSIDE-TOP-SECRET", encoding="utf-8")
    return secret


# ---------------------------------------------------------------- capabilities
def test_capabilities_honest_about_network_and_appcontainer():
    caps = capabilities()
    assert caps["os"] == sys.platform
    assert caps["network_enforcement"] is False
    assert caps["windows_appcontainer"] is False
    assert caps["filesystem_enforcement"] is True
    assert caps["windows_restricted_token"] is True
    assert caps["windows_job_object"] is True
    joined = " ".join(caps["limitations"]).lower()
    assert "blocked" in joined
    assert "network" in joined
    assert "firewall" in joined
    assert "job object" in joined
    assert "appcontainer" in joined


def test_default_call_fails_closed_without_network_enforcement(tmp_path):
    # F6: assert the BLOCKED behavior directly instead of skipping it.
    with pytest.raises(SandboxUnavailable) as excinfo:
        run_confined([COMSPEC, "/c", "echo SHOULD-NOT-RUN"], workspace=tmp_path)
    message = str(excinfo.value).lower()
    assert "blocked" in message
    assert "network" in message


def test_fail_closed_when_token_boundary_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sw, "_load_api", lambda: (None, None))
    with pytest.raises(SandboxUnavailable):
        sw.run_confined([COMSPEC, "/c", "echo hi"],
                        workspace=tmp_path, allow_network=True)


def test_fail_closed_when_filesystem_enforcement_reported_false(tmp_path,
                                                               monkeypatch):
    fake = capabilities()
    fake["filesystem_enforcement"] = False
    monkeypatch.setattr(sw, "capabilities", lambda: fake)
    with pytest.raises(SandboxUnavailable):
        sw.run_confined([COMSPEC, "/c", "echo hi"],
                        workspace=tmp_path, allow_network=True)


# ---------------------------------------------------------------- filesystem
def test_workspace_file_access_succeeds(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "allowed.txt").write_text("WORKSPACE-OK", encoding="utf-8")
    result = confined([COMSPEC, "/c", f'type "{ws / "allowed.txt"}"'],
                      workspace=ws)
    assert result.ok is True, result.stderr
    assert "WORKSPACE-OK" in result.stdout


def test_unrelated_host_file_read_denied(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    secret = outside_secret(tmp_path)
    result = confined([COMSPEC, "/c", f'type "{secret}"'], workspace=ws)
    assert result.ok is False
    assert "OUTSIDE-TOP-SECRET" not in result.stdout


def test_write_outside_workspace_denied(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    target = tmp_path / "outside-write.txt"
    result = confined(
        [COMSPEC, "/c", f'echo HACK > "{target}"'], workspace=ws)
    assert result.ok is False
    assert not target.exists()


def test_outside_read_not_bypassable_via_path_tricks(tmp_path):
    """F4/F6: argv trickery must not defeat the OS boundary."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    secret = outside_secret(tmp_path, "policy-forbidden.txt")
    attacks = [
        f'type "{secret}"',
        f'type "{ws / ".." / secret.name}"',
        f'cmd.exe /c type "{secret}"',
    ]
    for attack in attacks:
        result = confined([COMSPEC, "/c", attack], workspace=ws)
        assert result.ok is False, attack
        assert "OUTSIDE-TOP-SECRET" not in result.stdout, attack


def test_no_string_command_parameter_in_run_entry_point(tmp_path):
    """F4: the only command surface is ``argv``; there is no shell string."""
    with pytest.raises(TypeError):
        run_confined(command="echo hi", workspace=tmp_path, allow_network=True)
    with pytest.raises(TypeError):
        run_confined(["echo", "hi"], cmd="echo hi", workspace=tmp_path,
                     allow_network=True)


# ---------------------------------------------------------------- child / tree
def test_child_process_inherits_filesystem_restrictions(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    secret = outside_secret(tmp_path)
    inside = ws / "inside.txt"
    inside.write_text("INSIDE-OK", encoding="utf-8")
    denied_out = ws / "denied.txt"
    allowed_out = ws / "allowed.txt"

    denied = confined(
        [COMSPEC, "/c",
         f'cmd.exe /c type "{secret}" > "{denied_out}" 2>&1'],
        workspace=ws)
    assert denied.ok is False
    assert "OUTSIDE-TOP-SECRET" not in (
        denied_out.read_text(errors="replace") if denied_out.exists() else "")

    marker = ws / "child-marker.txt"
    allowed = confined(
        [COMSPEC, "/c",
         f'cmd.exe /c (echo CHILD-RAN > "{marker}" & '
         f'type "{inside}" > "{allowed_out}" 2>&1)'],
        workspace=ws)
    assert marker.exists(), "child process failed to start"
    assert "INSIDE-OK" in allowed_out.read_text(errors="replace")


def test_timeout_terminates_process_tree(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    heartbeat = ws / "heartbeat.txt"
    result = confined(
        [COMSPEC, "/c",
         f'for /l %i in (1,1,100000000) do @echo tick >> "{heartbeat}"'],
        workspace=ws, timeout_s=3)
    assert result.timed_out is True
    assert heartbeat.exists()
    first = heartbeat.stat().st_size
    time.sleep(1.5)
    second = heartbeat.stat().st_size
    assert second == first, "descendant kept writing after the run returned"


# ---------------------------------------------------------------- limits
def test_cpu_limit_terminates_job_before_timeout(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    result = confined(
        [COMSPEC, "/c", "for /l %i in (1,1,100000000) do @rem"],
        workspace=ws, cpu_s=1, timeout_s=15)
    assert result.timed_out is False
    assert result.exit_code is not None and result.exit_code != 0


def test_memory_limit_is_applied_without_breaking_normal_process(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    result = confined([COMSPEC, "/c", "echo MEM-OK"], workspace=ws,
                      memory_mb=64, cpu_s=5)
    assert result.ok is True
    assert "MEM-OK" in result.stdout
    # Honest scope: the limit is set via JOB_OBJECT_LIMIT_PROCESS_MEMORY /
    # JOB_OBJECT_LIMIT_JOB_MEMORY.  Exhaustion is not exercised here because
    # the restricted token on this host can load only cmd.exe built-ins.


def test_active_process_limit_and_no_breakaway_are_configured():
    flags, limit = sw._job_limit_flags_for_test()
    assert flags & sw.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    assert flags & sw.JOB_OBJECT_LIMIT_ACTIVE_PROCESS
    assert flags & sw.JOB_OBJECT_LIMIT_PROCESS_TIME
    assert flags & sw.JOB_OBJECT_LIMIT_JOB_TIME
    assert flags & sw.JOB_OBJECT_LIMIT_PROCESS_MEMORY
    assert flags & sw.JOB_OBJECT_LIMIT_JOB_MEMORY
    assert limit >= 4
    assert not (flags & 0x00010000)  # JOB_OBJECT_LIMIT_BREAKAWAY_OK
    assert not (flags & 0x00020000)  # JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK


# ---------------------------------------------------------------- environment
def test_secret_environment_is_scrubbed(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    poisoned = dict(os.environ)
    poisoned.update({
        "KEEL_SANDBOX_SECRET_PROBE": "SHOULD-NOT-LEAK",
        "API_TOKEN_LEAK": "ALSO-SHOULD-NOT-LEAK",
    })
    result = confined([COMSPEC, "/c", "set"], workspace=ws, env=poisoned)
    assert result.ok is True
    assert "SHOULD-NOT-LEAK" not in result.stdout
    assert "ALSO-SHOULD-NOT-LEAK" not in result.stdout


# ---------------------------------------------------------------- __main__ escape
def test_main_bootstrap_escape_is_contained(tmp_path):
    """Regression for the __main__ global-mutation escape.

    The OS boundary must hold even if a Python-level audit hook is bypassed.
    On hosts where the Python interpreter cannot be loaded by the restricted
    SID (a default python.org install under the user profile), this test skips
    with the actual launch evidence rather than pretending it passed.
    """
    ws = tmp_path / "workspace"
    ws.mkdir()
    secret = outside_secret(tmp_path, "main-secret.txt")
    code = (f"import __main__; __main__._ROOT={str(tmp_path)!r}; "
            f"print(open({str(secret)!r}).read())")
    probe = confined([sys.executable, "-c", "print('PROBE-OK')"], workspace=ws)
    if not probe.ok and "PROBE-OK" not in probe.stdout:
        pytest.skip(
            "Python interpreter cannot start under the restricted token on "
            f"this host (exit={probe.exit_code}, stderr={probe.stderr[:200]!r}); "
            "OS boundary itself is proven by the cmd.exe tests above")
    result = confined([sys.executable, "-c", code], workspace=ws)
    assert "OUTSIDE-TOP-SECRET" not in result.stdout
