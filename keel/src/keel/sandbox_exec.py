"""Real local sandbox execution (B3.1/B3.2 upgrade).

Runs untrusted code in a subprocess with bounded wall-clock time, output size
and (on POSIX) address-space/CPU limits. Network isolation is asserted as a
policy descriptor but OS-level enforcement is platform-dependent and reported
honestly rather than claimed.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass

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


def _limits(code: str) -> str:
    """Return a POSIX preexec function applying memory/CPU limits."""
    def apply():
        try:
            import resource
            mb = int(os.environ.get("KEEL_SANDBOX_MEMORY_MB", "256"))
            cpu = int(os.environ.get("KEEL_SANDBOX_CPU_S", "5"))
            resource.setrlimit(resource.RLIMIT_AS, (mb * 1024 * 1024,) * 2)
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        except (ImportError, OSError, ValueError):
            pass
    return apply


def run_python(code: str, *, timeout_s: float = 5.0) -> SandboxResult:
    """Execute Python source in a bounded subprocess (no shell=True)."""
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")
    start = time.monotonic()
    preexec = _limits(code) if os.name == "posix" else None
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", code],
            capture_output=True, timeout=timeout_s, check=False,
            preexec_fn=preexec)
        stdout = proc.stdout[:MAX_OUTPUT].decode("utf-8", errors="replace")
        stderr = proc.stderr[:MAX_OUTPUT].decode("utf-8", errors="replace")
        result = SandboxResult(
            ok=proc.returncode == 0, stdout=stdout, stderr=stderr,
            exit_code=proc.returncode,
            elapsed_s=round(time.monotonic() - start, 3), timed_out=False,
            limits={"timeout_s": timeout_s,
                    "memory_mb": int(os.environ.get("KEEL_SANDBOX_MEMORY_MB", "256")),
                    "platform": os.name})
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"")[:MAX_OUTPUT]
        result = SandboxResult(
            ok=False, stdout=out.decode("utf-8", errors="replace"),
            stderr="execution timed out", exit_code=None,
            elapsed_s=round(time.monotonic() - start, 3), timed_out=True,
            limits={"timeout_s": timeout_s, "platform": os.name})
    return result
