from __future__ import annotations

import signal
import subprocess
from types import SimpleNamespace

import pytest

from keel import sandbox_macos
from keel.os_sandbox import SandboxUnavailable


def _support():
    return {
        "available": True,
        "restrictive": False,
        "restrictive_abort": True,
        "broad": True,
        "narrow_subpath": False,
        "restrictive_error": "exit=-6, stderr=b''",
    }


def _setup(monkeypatch, probes):
    monkeypatch.setattr(
        sandbox_macos,
        "sys",
        SimpleNamespace(platform="darwin", prefix="/usr",
                         base_prefix="/usr", executable="/usr/bin/python"),
    )
    monkeypatch.setattr(sandbox_macos.shutil, "which",
                        lambda _name: "/usr/bin/sandbox-exec")
    monkeypatch.setattr(sandbox_macos, "_support", _support)
    monkeypatch.setattr(sandbox_macos, "_runtime_read_roots", lambda _argv: [])
    monkeypatch.setattr(sandbox_macos, "_sbpl_path", lambda _path: "/tmp/workspace")
    monkeypatch.setattr(
        sandbox_macos,
        "build_profile",
        lambda _workspace, **kwargs: (
            "broad" if kwargs.get("restrict_reads") is False else "restrictive"
        ),
    )
    calls = []

    def probe(_sandbox_exec, profile, _target="/usr/bin/true"):
        calls.append(profile)
        return next(probes)

    monkeypatch.setattr(sandbox_macos, "_probe", probe)
    return calls


@pytest.mark.parametrize(
    "failure",
    [
        subprocess.CompletedProcess(["sandbox-exec"], 1, b"", b"profile error"),
        subprocess.CompletedProcess(
            ["sandbox-exec"], -signal.SIGABRT, b"", b"unexpected stderr"
        ),
    ],
)
def test_unexpected_restrictive_failure_never_uses_broad_fallback(
    tmp_path, monkeypatch, failure
):
    calls = _setup(
        monkeypatch,
        iter([failure, subprocess.CompletedProcess(["sandbox-exec"], 0, b"", b"")]),
    )

    with pytest.raises(SandboxUnavailable, match="profile could not launch a probe"):
        sandbox_macos.run_confined(["python", "-c", "pass"], workspace=tmp_path)

    assert calls == ["restrictive"]


def test_cached_probe_must_match_known_host_failure(tmp_path, monkeypatch):
    calls = _setup(
        monkeypatch,
        iter([
            subprocess.CompletedProcess(
                ["sandbox-exec"], -signal.SIGABRT, b"", b""
            ),
            subprocess.CompletedProcess(["sandbox-exec"], 0, b"", b""),
        ]),
    )
    support = _support()
    support["restrictive_abort"] = False
    monkeypatch.setattr(sandbox_macos, "_support", lambda: support)

    with pytest.raises(SandboxUnavailable, match="profile could not launch a probe"):
        sandbox_macos.run_confined(["python", "-c", "pass"], workspace=tmp_path)

    assert calls == ["restrictive"]


def test_only_known_sigabrt_can_use_broad_profile(tmp_path, monkeypatch):
    calls = _setup(
        monkeypatch,
        iter([
            subprocess.CompletedProcess(
                ["sandbox-exec"], -signal.SIGABRT, b"", b""
            ),
            subprocess.CompletedProcess(["sandbox-exec"], 0, b"", b""),
        ]),
    )

    class Process:
        returncode = 0

        def communicate(self, timeout=None):
            return b"ok", b""

    command = []

    def popen(args, **_kwargs):
        command.extend(args)
        return Process()

    monkeypatch.setattr(sandbox_macos.subprocess, "Popen", popen)
    result = sandbox_macos.run_confined(
        ["python", "-c", "print('ok')"], workspace=tmp_path
    )

    assert result.ok
    assert result.mechanism.endswith("(read-isolation BLOCKED)")
    assert calls == ["restrictive", "broad"]
    assert command[2] == "broad"


def test_unexpected_probe_failure_is_not_reported_as_known_host_block(
    monkeypatch,
):
    support = _support()
    support["restrictive_abort"] = False
    monkeypatch.setattr(
        sandbox_macos,
        "sys",
        SimpleNamespace(platform="darwin"),
    )
    monkeypatch.setattr(sandbox_macos.shutil, "which",
                        lambda _name: "/usr/bin/sandbox-exec")
    monkeypatch.setattr(sandbox_macos, "_support", lambda: support)

    caps = sandbox_macos.capabilities()

    assert caps["read_isolation"] == "UNAVAILABLE"
    assert any("unexpected reason" in item for item in caps["limitations"])
