"""Adversarial, real-process tests for non-elevated Windows network denial.

Every assertion below is checked against a REAL child process.  The controls
run the same code outside the sandbox on the same host, so a failure cannot be
explained by a disconnected network or a missing listener.  No assertion is
silently skipped to hide a failed boundary.

On non-Windows hosts the whole module skips cleanly.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from keel.os_sandbox import SandboxUnavailable

WINDOWS = os.name == "nt"
pytestmark = pytest.mark.skipif(
    not WINDOWS, reason="AppContainer network isolation requires os.name == 'nt'")

if WINDOWS:
    from keel import sandbox_windows as sw
    from keel import win_network


COMSPEC = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
POWERSHELL = os.path.join(
    os.environ.get("SystemRoot", r"C:\Windows"), "System32",
    "WindowsPowerShell", "v1.0", "powershell.exe")


def _listener():
    """Real TCP listener; returns (socket, port, accepted-connections list)."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    accepted: list[int] = []

    def serve():
        while True:
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            accepted.append(1)
            conn.close()

    threading.Thread(target=serve, daemon=True).start()
    return listener, listener.getsockname()[1], accepted


def _probe_code(port: int, *, dns: bool = False) -> str:
    parts = ["Write-Output 'BEGIN'"]
    parts.append(
        "try { $c=New-Object Net.Sockets.TcpClient; "
        f"$a=$c.BeginConnect('127.0.0.1',{port},$null,$null); "
        "if($a.AsyncWaitHandle.WaitOne(2500) -and $c.Connected)"
        "{Write-Output 'LOCALHOST=OK'}else{Write-Output 'LOCALHOST=FAIL'}; "
        "$c.Close() } catch {Write-Output 'LOCALHOST=ERR'}")
    if dns:
        parts.append(
            "try { [Net.Dns]::GetHostAddresses('example.com') | Out-Null; "
            "Write-Output 'DNS=OK' } catch {Write-Output 'DNS=FAIL'}")
    parts.append("Write-Output 'END'")
    return ";".join(parts)


def _confined_powershell(code: str, tmp_path: Path, **kwargs):
    return sw.run_confined([POWERSHELL, "-NoProfile", "-NonInteractive",
                            "-Command", code],
                           workspace=tmp_path, timeout_s=25, **kwargs)


def _control_powershell(code: str):
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", code],
        capture_output=True, text=True, timeout=30)


# ------------------------------------------------------------- capability report
def test_capabilities_honestly_report_real_network_enforcement():
    caps = sw.capabilities()
    assert caps["os"] == sys.platform
    assert caps["network_enforcement"] is True
    assert caps["windows_appcontainer"] is True
    assert caps["filesystem_enforcement"] is True
    assert caps["windows_job_object"] is True
    assert caps["wfp_filter_add_error"] == 5
    assert "appcontainer" in caps["mechanism"]
    joined = " ".join(caps["limitations"]).lower()
    assert "appcontainer" in joined
    assert "wfp" in joined
    assert "blocked" in joined
    assert "socket()" in joined  # socket creation is still allowed; be honest


def test_wfp_filter_add_is_denied_without_elevation():
    """The alternative mechanism is genuinely unavailable, not assumed."""
    open_rc, add_rc = win_network.wfp_filter_add_status()
    assert open_rc == 0, f"FwpmEngineOpen0 failed with {open_rc}"
    assert add_rc == 5, (
        f"FwpmFilterAdd0 returned {add_rc} (expected ERROR_ACCESS_DENIED 5); "
        f"IsUserAnAdmin={ctypes_admin()}")


def ctypes_admin() -> int:
    import ctypes
    return int(ctypes.windll.shell32.IsUserAnAdmin())


def test_appcontainer_profile_yields_stable_derived_sid():
    first = win_network.appcontainer_sid()
    assert first.value
    first_text = win_network.sid_to_string(first)
    second = win_network.appcontainer_sid()  # exercises the "profile exists" path
    assert second.value
    second_text = win_network.sid_to_string(second)
    win_network.free_sid(first)
    win_network.free_sid(second)
    assert first_text.startswith("S-1-15-2-"), first_text
    assert first_text == second_text, (first_text, second_text)


# ------------------------------------------------------------- real default path
def test_default_run_confined_applies_appcontainer_boundary(tmp_path):
    result = sw.run_confined([COMSPEC, "/c", "echo AC-SMOKE-OK"],
                             workspace=tmp_path)
    assert result.ok is True, (result.exit_code, result.stderr)
    assert "AC-SMOKE-OK" in result.stdout
    assert "appcontainer" in result.mechanism
    assert any("socket()" in item for item in result.limitations)


def test_loopback_connect_denied_while_control_succeeds(tmp_path):
    listener, port, accepted = _listener()
    try:
        code = _probe_code(port)
        control = _control_powershell(code)
        assert "LOCALHOST=OK" in control.stdout, control
        assert len(accepted) == 1, "control did not reach the listener"

        result = _confined_powershell(code, tmp_path)
        assert result.ok is True, (result.exit_code, result.stderr)
        assert "LOCALHOST=FAIL" in result.stdout, result.stdout
        assert len(accepted) == 1, (
            "confined process reached the localhost listener")
    finally:
        listener.close()


def test_dns_resolution_denied_while_control_succeeds(tmp_path):
    listener, port, accepted = _listener()
    try:
        code = _probe_code(port, dns=True)
        control = _control_powershell(code)
        if "DNS=OK" not in control.stdout:
            pytest.skip(
                "host DNS is unavailable, so DNS denial cannot be "
                f"distinguished from a failed resolver (control stdout: "
                f"{control.stdout[:300]!r}, stderr: {control.stderr[:200]!r})")
        assert "LOCALHOST=OK" in control.stdout

        result = _confined_powershell(code, tmp_path)
        assert "DNS=FAIL" in result.stdout, result.stdout
        assert "LOCALHOST=FAIL" in result.stdout, result.stdout
        assert len(accepted) == 1
    finally:
        listener.close()


def test_socket_creation_allowed_but_traffic_blocked(tmp_path):
    listener, port, accepted = _listener()
    try:
        code = (
            "try { $s=New-Object Net.Sockets.Socket("
            "[Net.Sockets.AddressFamily]::InterNetwork,"
            "[Net.Sockets.SocketType]::Stream,"
            "[Net.Sockets.ProtocolType]::Tcp); "
            "Write-Output 'SOCKET_CREATE=OK'; $s.Close() } "
            "catch {Write-Output 'SOCKET_CREATE=FAIL'};"
            + _probe_code(port))
        result = _confined_powershell(code, tmp_path)
        assert "SOCKET_CREATE=OK" in result.stdout, result.stdout
        assert "LOCALHOST=FAIL" in result.stdout, result.stdout
        assert not accepted, "traffic escaped the AppContainer boundary"
    finally:
        listener.close()


def test_child_inherits_the_network_denied_token(tmp_path):
    """A cmd.exe child spawning PowerShell must also be denied."""
    listener, port, accepted = _listener()
    try:
        code = (
            "try { $c=New-Object Net.Sockets.TcpClient; "
            f"$a=$c.BeginConnect('127.0.0.1',{port},$null,$null); "
            "if($a.AsyncWaitHandle.WaitOne(2500) -and $c.Connected)"
            "{Write-Output 'CHILD-LOCALHOST=OK'}else{Write-Output 'CHILD-LOCALHOST=FAIL'}; "
            "$c.Close() } catch {Write-Output 'CHILD-LOCALHOST=ERR'}")
        # Control runs the same probe without a cmd.exe parent (no shell
        # quoting layer), proving the listener is reachable on this host.
        control = subprocess.run(
            [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", code],
            capture_output=True, text=True, timeout=30)
        assert "CHILD-LOCALHOST=OK" in control.stdout, control
        assert len(accepted) == 1, "control did not reach the listener"
        accepted.clear()

        # Confined: cmd.exe is the AppContainer parent, PowerShell its child.
        argv = [COMSPEC, "/c",
                f'"{POWERSHELL}" -NoProfile -NonInteractive -Command "{code}"']
        result = sw.run_confined(argv, workspace=tmp_path, timeout_s=25)
        assert result.ok is True, (result.exit_code, result.stderr)
        assert "CHILD-LOCALHOST=FAIL" in result.stdout, result.stdout
        assert not accepted, "inherited AppContainer token reached the listener"
    finally:
        listener.close()


# ------------------------------------------------------------- filesystem + fallback
def test_outside_file_read_denied_under_appcontainer(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "allowed.txt").write_text("WORKSPACE-OK", encoding="utf-8")
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("OUTSIDE-TOP-SECRET", encoding="utf-8")

    allowed = sw.run_confined(
        [COMSPEC, "/c", f'type "{ws / "allowed.txt"}"'], workspace=ws)
    assert allowed.ok is True, allowed.stderr
    assert "WORKSPACE-OK" in allowed.stdout

    denied = sw.run_confined(
        [COMSPEC, "/c", f'type "{outside}"'], workspace=ws)
    assert denied.ok is False
    assert "OUTSIDE-TOP-SECRET" not in denied.stdout


def test_fails_closed_when_appcontainer_is_unavailable(tmp_path, monkeypatch):
    fake = sw.capabilities()
    fake["network_enforcement"] = False
    monkeypatch.setattr(sw, "capabilities", lambda: fake)
    marker = tmp_path / "must-not-run.txt"

    with pytest.raises(SandboxUnavailable) as excinfo:
        sw.run_confined(
            [COMSPEC, "/c", f'echo RAN > "{marker}"'], workspace=tmp_path)
    message = str(excinfo.value).lower()
    assert "blocked" in message
    assert "network" in message
    assert not marker.exists(), "fell back to an unrestricted launch"


def test_allow_network_true_keeps_original_open_network_contract(tmp_path):
    result = sw.run_confined([COMSPEC, "/c", "echo OPEN-NETWORK-OK"],
                             workspace=tmp_path, allow_network=True)
    assert result.ok is True, result.stderr
    assert "OPEN-NETWORK-OK" in result.stdout
    assert result.mechanism == sw.MECHANISM
    assert any("no network boundary" in item.lower()
               for item in result.limitations)
