"""Kernel-enforced execution isolation (filesystem, network, process).

Distinct from `exec_policy` (authorization) and `sandbox_policy` (Python audit
hooks): this module applies OS primitives to real child processes.

Linux: Landlock (filesystem) + seccomp-BPF (network syscalls) + no_new_privs.
macOS: `sandbox-exec` profile applied to the launched process (filesystem,
       network denial, process restrictions).
Windows: restricted primary token + Job Object; network filtering requires an
       explicit administrator-configured firewall rule and is NOT enforced
       here (reported honestly by `capabilities()`).

Fail-closed: `run_confined()` raises SandboxUnavailable when a required
boundary cannot be applied; it never silently runs unrestricted.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


class SandboxUnavailable(RuntimeError):
    pass


@dataclass
class ConfinementResult:
    ok: bool
    exit_code: int | None
    timed_out: bool
    elapsed_s: float
    mechanism: str
    stdout: str
    stderr: str
    limitations: list[str]


def capabilities() -> dict:
    linux = sys.platform.startswith("linux")
    darwin = sys.platform == "darwin"
    windows = os.name == "nt"
    landlock = linux and _landlock_supported()
    # On Windows, network denial is provided by the dedicated backend via a
    # capability-less AppContainer (non-elevated, real-process verified). Ask
    # that backend for its live probe instead of hard-coding False here, so the
    # report stays honest as mechanisms change.
    if windows:
        try:
            from .sandbox_windows import capabilities as _win_caps
            win_network = bool(_win_caps().get("network_enforcement"))
            win_appcontainer = bool(_win_caps().get("windows_appcontainer"))
        except Exception:
            win_network, win_appcontainer = False, False
    else:
        win_network, win_appcontainer = False, False
    return {
        "os": sys.platform,
        "linux_landlock": landlock,
        "linux_seccomp": linux and _seccomp_supported(),
        "macos_sandbox_exec": darwin and bool(shutil.which("sandbox-exec")),
        "windows_restricted_token": windows,
        "windows_job_object": windows,
        "windows_appcontainer": win_appcontainer,
        "filesystem_enforcement": bool(landlock or (
            darwin and shutil.which("sandbox-exec")) or windows),
        "network_enforcement": bool(landlock and _seccomp_supported()) or (
            darwin and shutil.which("sandbox-exec")) or win_network,
        "limitations": _limitations(linux, darwin, windows, landlock),
    }


def _limitations(linux, darwin, windows, landlock) -> list[str]:
    out = []
    if linux and not landlock:
        out.append("Landlock unavailable: kernel < 5.13 or syscall blocked")
    if linux and not _seccomp_supported():
        out.append("seccomp unavailable: network syscalls not confined")
    if darwin and not shutil.which("sandbox-exec"):
        out.append("sandbox-exec unavailable")
    if windows:
        out.append("Windows network denial requires an administrator-configured "
                   "firewall rule; not enforced by this module")
    out.append("This is process-level OS isolation, not a complete VM boundary")
    return out


def _landlock_supported() -> bool:
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        libc.syscall.restype = ctypes.c_long
        # landlock_create_ruleset(NULL, 0, LANDLOCK_CREATE_RULESET_VERSION)
        version = libc.syscall(444, None, 0, 1)
        return version > 0
    except Exception:
        return False


def _seccomp_supported() -> bool:
    try:
        status = Path("/proc/self/status").read_text(encoding="utf-8",
                                                     errors="replace")
        return "Seccomp:" in status
    except OSError:
        return False


# --------------------------------------------------------------- Linux
class _LandlockRulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64),
                ("handled_access_net", ctypes.c_uint64),
                ("scoped", ctypes.c_uint64),
                ("reserved", ctypes.c_uint64)]


class _LandlockPathBeneathAttr(ctypes.Structure):
    # Kernel ABI: __u64 allowed_access; __s32 parent_fd; (padding)
    _fields_ = [("allowed_access", ctypes.c_uint64),
                ("parent_fd", ctypes.c_int32)]


# Landlock filesystem rights (kernel ABI).
LL_READ_FILE = 1 << 0
LL_WRITE_FILE = 1 << 1
LL_EXECUTE = 1 << 3
LL_READ_DIR = 1 << 5
LL_REMOVE_DIR = 1 << 7
LL_MAKE_DIR = 1 << 8
LL_REFER = 1 << 11
LL_ALL_FS = (1 << 13) - 1
PR_SET_NO_NEW_PRIVS = 38
PR_SET_SECCOMP = 22
SECCOMP_MODE_FILTER = 2


def _linux_confine(workspace: str) -> None:
    """Apply no_new_privs + Landlock + seccomp in the child before exec."""
    if not _landlock_supported():
        raise SandboxUnavailable("Landlock not available")
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        raise SandboxUnavailable("prctl(NO_NEW_PRIVS) failed")
    ruleset = _LandlockRulesetAttr(handled_access_fs=LL_ALL_FS,
                                   handled_access_net=0, scoped=0, reserved=0)
    ruleset_fd = libc.syscall(444, ctypes.byref(ruleset), ctypes.sizeof(ruleset), 0)
    if ruleset_fd < 0:
        raise SandboxUnavailable("landlock_create_ruleset failed")
    try:
        fd = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            rule = _LandlockPathBeneathAttr(
                parent_fd=fd, allowed_access=LL_READ_FILE | LL_WRITE_FILE |
                LL_EXECUTE | LL_READ_DIR | LL_REMOVE_DIR | LL_MAKE_DIR | LL_REFER,
                reserved=0)
            if libc.syscall(445, ruleset_fd, 1, ctypes.byref(rule),
                            ctypes.sizeof(rule)) < 0:
                raise SandboxUnavailable("landlock_add_rule failed")
        finally:
            os.close(fd)
        if libc.syscall(446, ruleset_fd, 0) < 0:
            raise SandboxUnavailable("landlock_restrict_self failed")
    finally:
        os.close(ruleset_fd)
    _seccomp_deny_network(libc)


DENIED_NETWORK_SYSCALLS = {
    41: "socket", 42: "connect", 43: "accept", 44: "sendto",
    45: "recvfrom", 46: "sendmsg", 47: "recvmsg", 49: "bind",
    50: "listen", 51: "getsockname", 52: "getpeername",
    53: "socketpair", 54: "setsockopt", 55: "getsockopt",
    86: "gethostname",
}


def build_inproc_network_filter() -> list[tuple[int, int, int, int]]:
    """Pure builder for the in-process seccomp network-deny filter.

    Exposed so the exact BPF layout can be regression-tested on any platform
    (including Windows CI) without installing a filter.
    """
    # Correct seccomp-BPF layout:
    #   BPF_LD|BPF_W|BPF_ABS (0x20) at offset 0 loads seccomp_data.nr.
    #   BPF_JMP|BPF_JEQ|BPF_K (0x15) with jt=0/jf=1 falls through to the
    #   following RET only for a matching syscall and skips it otherwise.
    #   SECCOMP_RET_ERRNO|EPERM = 0x00050001; default SECCOMP_RET_ALLOW.
    # The previous revision used opcode 0x00 at offset 4 with an intervening
    # `ja`, which inverted the branch and denied everything except the
    # intended network syscalls. Fixed here; Linux now also dispatches to
    # sandbox_linux, whose build_network_filter() has the correct layout.
    insns = []
    insns.append((0x20, 0, 0, 0))                 # ld seccomp_data.nr
    for nr in sorted(DENIED_NETWORK_SYSCALLS):
        insns.append((0x15, 0, 1, nr))             # jeq nr -> fall through
        insns.append((0x06, 0, 0, 0x00050001))     # ret ERRNO(EPERM)
    insns.append((0x06, 0, 0, 0x7fff0000))        # ret ALLOW
    return insns


def _seccomp_deny_network(libc) -> None:
    """Install the in-process network-deny filter (used by the legacy path)."""
    if not _seccomp_supported():
        raise SandboxUnavailable("seccomp not available")
    insns = build_inproc_network_filter()

    class SockFilter(ctypes.Structure):
        _fields_ = [("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte),
                    ("jf", ctypes.c_ubyte), ("k", ctypes.c_uint32)]

    arr = (SockFilter * len(insns))()
    for i, (code, jt, jf, k) in enumerate(insns):
        arr[i] = SockFilter(code, jt, jf, k)

    class SockFprog(ctypes.Structure):
        _fields_ = [("len", ctypes.c_ushort),
                    ("filter", ctypes.POINTER(SockFilter))]

    prog = SockFprog(len(arr), arr)
    if libc.prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, ctypes.byref(prog),
                  0, 0) != 0:
        raise SandboxUnavailable("seccomp filter install failed")


# --------------------------------------------------------------- macOS
def _macos_profile(workspace: str) -> str:
    return f"""(version 1)
(deny default)
(allow process*)
(allow sysctl-read)
(allow file-read* (subpath "{workspace}"))
(allow file-read* (subpath "/usr"))
(allow file-read* (subpath "/bin"))
(allow file-read* (subpath "/System"))
(allow file-read* (subpath "/opt"))
(allow file-read* (subpath "/Library"))
(allow file-read* (subpath "/etc"))
(allow file-read* (subpath "/dev"))
(allow file-read* (subpath "/private/var/db"))
(allow file-write* (subpath "{workspace}"))
(allow mach-lookup)
(allow ipc-posix-shm*)
(deny network*)
"""


# --------------------------------------------------------------- public API
def run_confined(argv: list[str], *, workspace: str | Path | None = None,
                 timeout_s: float = 15.0, cpu_s: int = 10,
                 memory_mb: int = 256, env: dict[str, str] | None = None,
                 allow_network: bool = False) -> ConfinementResult:
    """Run *argv* under real OS filesystem/network restrictions.

    Every supported platform is routed to its dedicated, reviewed backend so
    that the kernel-enforced token/ACL (Windows) or Landlock/seccomp (Linux)
    implementation is always used. There is deliberately no unrestricted
    fallback: a backend that cannot establish its boundary raises
    ``SandboxUnavailable``.
    """
    # Dedicated platform backends are authoritative. The legacy inline macOS
    # path below is retained only for platforms without a dedicated backend.
    if os.name == "nt":
        from .sandbox_windows import run_confined as _backend
        return _backend(argv, workspace=workspace, timeout_s=timeout_s,
                        cpu_s=cpu_s, memory_mb=memory_mb, env=env,
                        allow_network=allow_network)
    if sys.platform.startswith("linux"):
        from .sandbox_linux import run_confined as _backend
        return _backend(argv, workspace=workspace, timeout_s=timeout_s,
                        cpu_s=cpu_s, memory_mb=memory_mb, env=env,
                        allow_network=allow_network)
    if sys.platform == "darwin":
        from .sandbox_macos import run_confined as _backend
        return _backend(argv, workspace=workspace, timeout_s=timeout_s,
                        cpu_s=cpu_s, memory_mb=memory_mb, env=env,
                        allow_network=allow_network)

    caps = capabilities()
    workspace = str(Path(workspace or tempfile.mkdtemp()).resolve())
    Path(workspace).mkdir(parents=True, exist_ok=True)
    env = env or {}
    started = time.monotonic()
    limitations = list(caps["limitations"])

    def preexec():
        if sys.platform.startswith("linux"):
            _linux_confine(workspace)
        else:
            import resource
            for rid, value in (
                (resource.RLIMIT_CPU, (cpu_s, cpu_s)),
                (resource.RLIMIT_AS, (memory_mb * 1024 * 1024,) * 2),
                (resource.RLIMIT_NPROC, (8, 8)),
            ):
                try:
                    resource.setrlimit(rid, value)
                except (OSError, ValueError):
                    pass

    if sys.platform == "darwin":
        if not caps["macos_sandbox_exec"]:
            raise SandboxUnavailable("sandbox-exec unavailable")
        profile = _macos_profile(workspace)
        argv = ["sandbox-exec", "-p", profile, *argv]
        cmd = argv
        preexec_fn = preexec
    elif sys.platform.startswith("linux"):
        if not caps["linux_landlock"] or not caps["linux_seccomp"]:
            raise SandboxUnavailable(
                "Linux requires Landlock + seccomp for enforced confinement")
        # Pre-flight the kernel boundary in a disposable child. Landlock
        # add_rule can fail even when create_ruleset succeeds (kernel ABI
        # differences); fail closed rather than launching an unbounded task.
        probe = subprocess.run(
            [sys.executable, "-c",
             "import sys; from keel.os_sandbox import _linux_confine; "
             "_linux_confine(sys.argv[1])", workspace],
            capture_output=True, timeout=10, check=False)
        if probe.returncode != 0:
            raise SandboxUnavailable(
                "Landlock/seccomp could not be applied on this host: "
                + probe.stderr.decode("utf-8", errors="replace")[-300:])
        cmd = argv
        preexec_fn = preexec
    elif os.name == "nt":
        if not caps["windows_job_object"]:
            raise SandboxUnavailable("Windows Job Object unavailable")
        cmd = argv
        preexec_fn = None
    else:
        raise SandboxUnavailable(f"unsupported platform: {sys.platform}")

    def finish(code, timed_out, out, err):
        return ConfinementResult(
            code == 0, code, timed_out, round(time.monotonic() - started, 3),
            caps["os"], out.decode("utf-8", errors="replace"),
            err.decode("utf-8", errors="replace"), limitations)

    try:
        proc = subprocess.run(cmd, cwd=workspace, env=env, capture_output=True,
                              timeout=timeout_s, preexec_fn=preexec_fn,
                              check=False)
        return finish(proc.returncode, False, proc.stdout, proc.stderr)
    except subprocess.TimeoutExpired as exc:
        return finish(None, True, exc.stdout or b"", exc.stderr or b"")
