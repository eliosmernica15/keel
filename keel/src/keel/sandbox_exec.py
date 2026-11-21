"""Real local sandbox execution with a Python audit-hook boundary.

Runs untrusted code in a subprocess with:
- an isolated temporary working directory (relative file ops are confined);
- a ``sys.addaudithook`` policy that denies file access outside the workspace
  and Python library dirs, process creation, native loading, and network
  access by default (see ``sandbox_policy``);
- a scrubbed environment with no credential-like variables;
- bounded wall-clock time, output size and (on POSIX) memory/CPU limits;
- guaranteed cleanup of the temporary workspace.

Honest limits: this is a Python-level boundary, not OS-level containment.
Native code and kernel-level attacks are not prevented; real isolation
requires containers/seccomp/AppArmor or Windows restricted tokens. Callers
must consult ``sandbox_policy.sandbox_status()`` before trusting it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass

from . import sandbox_policy

MAX_OUTPUT = 1 * 1024 * 1024


@dataclass
class SandboxResult:
    ok: bool
    stdout: str
    stderr: str
    exit_code: int | None
    elapsed_s: float
    timed_out: bool
    limits: dict


def _limits() -> object:
    """POSIX memory/CPU limits applied before exec."""
    def apply():
        try:
            import resource
            mb = int(os.environ.get("KEEL_SANDBOX_MEMORY_MB", "256"))
            cpu = int(os.environ.get("KEEL_SANDBOX_CPU_S", "5"))
            resource.setrlimit(resource.RLIMIT_AS, (mb * 1024 * 1024,) * 2)
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
            resource.setrlimit(resource.RLIMIT_NPROC, (16, 16))
            resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT, MAX_OUTPUT))
        except (ImportError, OSError, ValueError):
            pass
    return apply


def run_python(code: str, *, timeout_s: float = 5.0,
               allow_network: bool = False) -> SandboxResult:
    """Execute Python source under the audit-hook sandbox policy."""
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")
    start = time.monotonic()
    workdir = tempfile.mkdtemp(prefix="keel-sandbox-")
    try:
        bootstrap, user = sandbox_policy.prepare_workspace(workdir, code)
        env = sandbox_policy.child_env(allow_network=allow_network)
        env["KEEL_SANDBOX_ROOT"] = workdir
        env["PYTHONPATH"] = ""  # no user/site packages beyond stdlib
        preexec = _limits() if os.name == "posix" else None
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(bootstrap)],
                capture_output=True, timeout=timeout_s, check=False,
                cwd=workdir, env=env, preexec_fn=preexec)
            stdout = proc.stdout[:MAX_OUTPUT].decode("utf-8", errors="replace")
            stderr = proc.stderr[:MAX_OUTPUT].decode("utf-8", errors="replace")
            denied = "sandbox:" in stderr or "PermissionError" in stderr
            result = SandboxResult(
                ok=proc.returncode == 0, stdout=stdout, stderr=stderr,
                exit_code=proc.returncode,
                elapsed_s=round(time.monotonic() - start, 3), timed_out=False,
                limits={
                    "timeout_s": timeout_s,
                    "isolated_cwd": True,
                    "audit_hook": True,
                    "credential_env_scrubbed": True,
                    "network": "allowed" if allow_network else "denied",
                    "memory_mb": int(os.environ.get(
                        "KEEL_SANDBOX_MEMORY_MB", "256")),
                    "platform": os.name,
                    "policy_violation": denied,
                })
        except subprocess.TimeoutExpired as exc:
            out = (exc.stdout or b"")[:MAX_OUTPUT]
            err = (exc.stderr or b"")[:MAX_OUTPUT]
            result = SandboxResult(
                ok=False, stdout=out.decode("utf-8", errors="replace"),
                stderr=err.decode("utf-8", errors="replace") or "execution timed out",
                exit_code=None,
                elapsed_s=round(time.monotonic() - start, 3), timed_out=True,
                limits={"timeout_s": timeout_s, "isolated_cwd": True,
                        "audit_hook": True, "network":
                        "allowed" if allow_network else "denied",
                        "platform": os.name, "policy_violation": False})
        return result
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
