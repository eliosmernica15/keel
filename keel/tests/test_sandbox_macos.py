"""Native macOS Seatbelt tests: real restricted processes, not policy checks.

Every test is skipped off macOS via a pytest marker.  On macOS the tests run
actual ``sandbox-exec`` processes and assert real denials.  A process that
cannot launch is a hard failure labelled BLOCKED with the exact stderr -- it
is never converted into a pass or a skip.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from keel.os_sandbox import SandboxUnavailable
from keel.sandbox_macos import build_profile, capabilities, run_confined

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="native macOS Seatbelt sandbox tests (require sandbox-exec)",
)


def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def _run(argv: list[str], **kwargs):
    try:
        return run_confined(argv, **kwargs)
    except SandboxUnavailable as exc:
        pytest.fail(f"BLOCKED: OS enforcement unavailable: {exc}", pytrace=False)


def _assert_launched(result, what: str) -> None:
    assert result.ok, (
        f"BLOCKED: {what} did not run under sandbox-exec "
        f"(exit={result.exit_code}, timed_out={result.timed_out}, "
        f"stderr={result.stderr[:800]!r})"
    )


def test_capabilities_are_honest():
    caps = capabilities()
    assert caps["os"] == "darwin"
    assert caps["sandbox_exec"] is True
    assert caps["available"] is True
    assert caps["deprecated"] is True
    assert caps["filesystem_enforcement"] == "PARTIAL"
    assert caps["filesystem_write_enforcement"] == "FULL"
    assert caps["network_enforcement"] is True
    assert caps["process_inheritance"] is True
    assert caps["rlimits"]["cpu"] is True
    assert caps["rlimits"]["nproc"] is False
    assert any("deprecated" in item.lower() for item in caps["limitations"])
    assert any("PARTIAL" in item for item in caps["limitations"])


def test_build_profile_is_restrictive(tmp_path):
    profile = build_profile(tmp_path, read_roots=["/usr/lib"])
    assert "(version 1)" in profile
    assert "(deny default)" in profile
    assert "(deny network*)" in profile
    assert "(allow network*)" not in profile
    # No global content reads: only narrow subpaths / device literals.
    assert "(allow file-read*)" not in profile
    assert f'(allow file-write* (subpath "{tmp_path}"))' in profile
    assert '(subpath "/usr/lib")' in profile
    assert '(literal "/dev/null")' in profile
    assert '(subpath "/dev")' not in profile
    assert profile.count("(allow file-read*") == 3  # workspace + roots + devices

    # Duplicate SBPL filters make sandbox-exec abort with SIGABRT (no stderr).
    dedup = build_profile(tmp_path, read_roots=["/usr", "/usr/lib", "/usr"])
    assert dedup.count('(subpath "/usr")') == 1
    assert dedup.count('(subpath "/usr/lib")') == 1
    assert build_profile(tmp_path, allow_network=True).count("(allow network*)") == 1


def test_profile_rejects_injection_in_workspace_path(tmp_path):
    hostile = str(tmp_path / 'ws") (allow file-read*) (deny default')
    with pytest.raises(SandboxUnavailable, match="injection"):
        run_confined(_py("print(1)"), workspace=hostile)


def test_python_launches_inside_profile(tmp_path):
    # This is the regression that was BLOCKED on macos-latest: the old profile
    # omitted /Users/runner/hostedtoolcache/... and RLIMIT_AS=256 MB killed
    # dyld before main().
    r = _run(_py("import sys; print(sys.version.split()[0])"), workspace=tmp_path)
    _assert_launched(r, "the Python interpreter")
    assert r.stdout.strip()
    assert r.mechanism == "macos-seatbelt-sandbox-exec"
    assert r.exit_code == 0


def test_workspace_read_write_and_unrelated_host_file_denied(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "allowed.txt").write_text("ALLOWED", encoding="utf-8")
    secret = tmp_path / "outside-secret.txt"
    secret.write_text("OUTSIDE-SECRET", encoding="utf-8")

    r = _run(_py(
        "from pathlib import Path; p = Path(%r); p.write_text('NEW'); "
        "print(p.read_text())" % str(ws / "allowed.txt")
    ), workspace=ws)
    _assert_launched(r, "workspace read/write")
    assert "NEW" in r.stdout

    r2 = _run(_py(f"print(open({str(secret)!r}).read())"), workspace=ws)
    assert r2.exit_code != 0
    assert "OUTSIDE-SECRET" not in r2.stdout


def test_unauthorized_write_denied(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    outside = tmp_path / "outside.txt"
    r = _run(_py(f"open({str(outside)!r}, 'w').write('PWNED')"), workspace=ws)
    assert not r.ok
    assert not outside.exists()


def test_network_denied_by_default(tmp_path):
    r = _run(_py(
        "import socket; s = socket.socket(); s.settimeout(1); "
        "s.connect(('127.0.0.1', 9)); print('CONNECTED')"
    ), workspace=tmp_path)
    assert "CONNECTED" not in r.stdout
    assert not r.ok


def test_child_processes_inherit_restrictions(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    secret = tmp_path / "outside-secret.txt"
    secret.write_text("OUTSIDE-SECRET", encoding="utf-8")
    inner = f"print(open({str(secret)!r}).read())"
    code = (
        "import subprocess, sys; "
        f"r = subprocess.run([sys.executable, '-c', {inner!r}], "
        "capture_output=True, text=True); "
        "print('CHILD_RC', r.returncode); print(r.stdout, end='')"
    )
    r = _run(_py(code), workspace=ws)
    _assert_launched(r, "the parent script")
    assert "CHILD_RC 0" not in r.stdout
    assert "OUTSIDE-SECRET" not in r.stdout


def test_timeout_terminates_child_process_group(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    marker = ws / "grandchild.pid"
    code = (
        "import subprocess, sys, time; "
        "p = subprocess.Popen([sys.executable, '-c', 'import time; "
        "time.sleep(30)']); "
        f"open({str(marker)!r}, 'w').write(str(p.pid)); "
        "time.sleep(30)"
    )
    r = _run(_py(code), workspace=ws, timeout_s=3)
    assert r.timed_out is True
    assert r.exit_code is not None and r.exit_code < 0

    pid = int(marker.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 3
    while True:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        if time.monotonic() > deadline:
            pytest.fail(f"grandchild pid {pid} survived process-group termination")
        time.sleep(0.1)


def test_cpu_rlimit_terminates_runaway(tmp_path):
    r = _run(_py("while True: pass"), workspace=tmp_path, cpu_s=1, timeout_s=12)
    assert r.timed_out is False
    assert not r.ok
    assert r.exit_code in (-24, 24, -9, 9), (
        f"expected SIGXCPU/SIGKILL, got {r.exit_code}: {r.stderr[:400]!r}")


def test_memory_ceiling_is_reported_and_applied(tmp_path):
    assert any("RLIMIT_AS raised" in item for item in capabilities()["limitations"])
    r = _run(_py(
        "import resource; print(resource.getrlimit(resource.RLIMIT_AS)[0])"
    ), workspace=tmp_path, memory_mb=256)
    _assert_launched(r, "rlimit query")
    assert int(r.stdout.strip()) >= 4096 * 1024 * 1024


def test_scratch_files_land_inside_workspace(tmp_path):
    # PyInstaller one-file sidecars unpack into TMPDIR; confinement must not
    # silently hand them an unwritable host /private/tmp path.
    r = _run(_py(
        "import os, tempfile; "
        "f = tempfile.NamedTemporaryFile(delete=False); "
        "f.write(b'ok'); f.close(); print(f.name)"
    ), workspace=tmp_path)
    _assert_launched(r, "tempfile creation")
    name = Path(r.stdout.strip())
    assert name.is_relative_to(tmp_path)
    assert name.read_bytes() == b"ok"


def test_launch_failure_is_reported_not_passed(tmp_path):
    r = _run(["/definitely/not/a/real/executable"], workspace=tmp_path)
    assert not r.ok
    assert r.exit_code != 0
    assert (r.stderr + r.stdout).strip(), (
        "launch failure must report the exact tool error, never a pass")
