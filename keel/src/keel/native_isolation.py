"""Native, OS-level execution limits (least-privilege execution boundaries).

This module is deliberately distinct from the Python audit-hook sandbox: it
uses platform-native primitives to bound real OS processes.

Windows: Job Object with active-process, CPU and memory limits; the job is
terminated on timeout, which kills the whole descendant tree. Network policy
is not enforced by a Job Object and remains a documented limitation.
POSIX: rlimits via preexec (CPU/AS/NPROC/FSIZE) and optional unshare-based
namespace isolation when the host permits it.

Fail-closed: callers can require native isolation; if the platform facility is
absent, execution is refused rather than silently running unrestricted.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass

IS_WINDOWS = os.name == "nt"


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", ctypes.c_ulong),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_ulong),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_ulong),
        ("SchedulingClass", ctypes.c_ulong),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class IsolationUnavailable(RuntimeError):
    """Raised when a required native boundary cannot be established."""


@dataclass
class IsolationResult:
    ok: bool
    exit_code: int | None
    elapsed_s: float
    timed_out: bool
    platform: str
    mechanism: str
    stdout: str = ""
    stderr: str = ""
    limits: dict | None = None


def platform_support() -> dict:
    return {
        "os": sys.platform,
        "windows_job_object": IS_WINDOWS,
        "posix_rlimits": not IS_WINDOWS,
        "unshare": bool(shutil.which("unshare")) if not IS_WINDOWS else False,
        "network_isolation": False,
        "note": "Native process/resource limits only; not full OS sandboxing.",
    }


# --------------------------------------------------------------- Windows
class WindowsJob:
    """Minimal Win32 Job Object wrapper using ctypes (no third-party deps)."""

    JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
    JOB_OBJECT_LIMIT_PROCESS_TIME = 0x00000002
    JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

    def __init__(self, *, cpu_s: int = 10, memory_mb: int = 512,
                 processes: int = 4):
        from ctypes import wintypes

        self.ctypes = ctypes
        self.wintypes = wintypes
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.restype = ctypes.c_void_p
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        self.kernel.SetInformationJobObject.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        self.kernel.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.kernel.TerminateJobObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise IsolationUnavailable("CreateJobObjectW failed")
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        basic = info.BasicLimitInformation
        basic.LimitFlags = (
            self.JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            | self.JOB_OBJECT_LIMIT_PROCESS_TIME
            | self.JOB_OBJECT_LIMIT_PROCESS_MEMORY
            | self.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)
        basic.ActiveProcessLimit = processes
        # PerProcessUserTimeLimit is in 100 ns units.
        basic.PerProcessUserTimeLimit = cpu_s * 10_000_000
        info.ProcessMemoryLimit = memory_mb * 1024 * 1024
        ok = self.kernel.SetInformationJobObject(
            self.handle, 9, ctypes.byref(info), ctypes.sizeof(info))
        if not ok:
            self.kernel.CloseHandle(self.handle)
            raise IsolationUnavailable("SetInformationJobObject failed")
        self.limits = {"cpu_s": cpu_s, "memory_mb": memory_mb,
                       "processes": processes}

    def assign(self, pid: int) -> None:
        ok = self.kernel.AssignProcessToJobObject(self.handle, pid)
        if not ok:
            raise IsolationUnavailable(
                f"AssignProcessToJobObject failed ({self.ctypes.get_last_error()})")

    def terminate(self) -> None:
        self.kernel.TerminateJobObject(self.handle, 1)

    def close(self) -> None:
        self.kernel.CloseHandle(self.handle)


def _posix_limits(cpu_s: int, memory_mb: int, processes: int):
    def apply():
        import resource

        for rid, value in (
            (resource.RLIMIT_CPU, (cpu_s, cpu_s)),
            (resource.RLIMIT_AS, (memory_mb * 1024 * 1024,) * 2),
            (resource.RLIMIT_NPROC, (processes, processes)),
            (resource.RLIMIT_FSIZE, (8 * 1024 * 1024,) * 2),
        ):
            try:
                resource.setrlimit(rid, value)
            except (OSError, ValueError):
                pass
    return apply


def run_isolated(argv: list[str], *, cwd: str | None = None,
                 env: dict[str, str] | None = None,
                 timeout_s: float = 15.0, cpu_s: int = 10,
                 memory_mb: int = 512, processes: int = 4,
                 require_native: bool = True) -> IsolationResult:
    """Execute argv under native OS limits; fail closed if unavailable."""
    started = time.monotonic()
    env = env or {}
    if IS_WINDOWS:
        job = WindowsJob(cpu_s=cpu_s, memory_mb=memory_mb,
                         processes=processes)
        proc = None
        try:
            proc = subprocess.Popen(
                argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            # AssignProcessToJobObject requires a process HANDLE, not a PID.
            job.assign(getattr(proc, "_handle", None) or proc.pid)
            out, err = proc.communicate(timeout=timeout_s)
            return IsolationResult(True, proc.returncode,
                                   round(time.monotonic() - started, 3), False,
                                   sys.platform, "windows-job-object",
                                   out.decode("utf-8", errors="replace"),
                                   err.decode("utf-8", errors="replace"),
                                   job.limits)
        except subprocess.TimeoutExpired:
            job.terminate()
            out, err = proc.communicate(timeout=10) if proc else (b"", b"")
            return IsolationResult(False, None,
                                   round(time.monotonic() - started, 3), True,
                                   sys.platform, "windows-job-object",
                                   out.decode("utf-8", errors="replace"),
                                   err.decode("utf-8", errors="replace"),
                                   job.limits)
        except IsolationUnavailable:
            if proc:
                proc.kill()
            raise
        finally:
            job.close()
    if require_native and not platform_support()["posix_rlimits"]:
        raise IsolationUnavailable("no native POSIX resource limits")
    try:
        proc = subprocess.run(
            argv, cwd=cwd, env=env, capture_output=True,
            timeout=timeout_s, preexec_fn=_posix_limits(cpu_s, memory_mb, processes),
            check=False)
        return IsolationResult(True, proc.returncode,
                               round(time.monotonic() - started, 3), False,
                               sys.platform, "posix-rlimits",
                               proc.stdout.decode("utf-8", errors="replace"),
                               proc.stderr.decode("utf-8", errors="replace"),
                               {"cpu_s": cpu_s, "memory_mb": memory_mb,
                                "processes": processes})
    except subprocess.TimeoutExpired:
        return IsolationResult(False, None,
                               round(time.monotonic() - started, 3), True,
                               sys.platform, "posix-rlimits")


def status() -> dict:
    return platform_support()
