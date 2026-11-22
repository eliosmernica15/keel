"""Native Linux confinement for real child processes (kernel-enforced).

Applied primitives, in the exact order used in the forked child:

1. ``prctl(PR_SET_NO_NEW_PRIVS, 1)`` -- prevents gaining privileges later.
2. Best-effort capability bounding-set drop.
3. **Landlock**: a ruleset with an ABI-correct ``struct landlock_ruleset_attr``
   size and only *runtime-verified supported* access bits; path-beneath rules
   grant full control of the workspace and read+traverse of the system paths
   required to load an interpreter and its shared libraries; then
   ``landlock_restrict_self`` makes it irrevocable and inherited by exec.
4. **seccomp-BPF**: a filter that returns ``SECCOMP_RET_ERRNO | EPERM`` for
   every network-capable syscall (socket/connect/DNS) and ``SECCOMP_RET_ALLOW``
   otherwise.  Network IPC is denied by default; the explicitly-approved IPC
   set is empty unless a caller opts in with ``allow_network=True``.
5. CPU / address-space / process-count / file-size / open-file / core rlimits.

Fail closed: ``SandboxUnavailable`` is raised if any primitive cannot be
applied, and no unrestricted process is launched.

Root cause of the original ``os_sandbox.py`` EINVAL (reproduced on
6.6.87.2-microsoft-standard-WSL2): ``landlock_add_rule`` has signature
``(ruleset_fd, rule_type, rule_attr, __u32 flags)``.  The old code passed
``ctypes.sizeof(rule)`` (16) as the fourth argument.  That argument is *flags*
and must be 0; passing 16 yields ``EINVAL`` on every Landlock kernel.  The old
code also used a shifted/incorrect access-bit table, a `reserved` kwarg that
is not a struct field, and a broken seccomp filter (BPF_IMM instead of
BPF_ABS, offset 4 = arch instead of 0 = nr, inverted branches, and a return
action of 1 = SECCOMP_RET_KILL_THREAD rather than ERRNO|EPERM).
"""

from __future__ import annotations

import ctypes
import errno
import os
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from keel.os_sandbox import ConfinementResult, SandboxUnavailable

try:  # pragma: no cover - resource is absent on Windows; guarded by platform
    import resource
except ImportError:  # pragma: no cover
    resource = None  # type: ignore[assignment]

LINUX = sys.platform.startswith("linux")

# ---------------------------------------------------------------------------
# Kernel ABI constants (include/uapi/linux/landlock.h, linux/seccomp.h,
# linux/prctl.h, asm-generic/unistd.h).  Stable across architectures.
# ---------------------------------------------------------------------------
SYS_LANDLOCK_CREATE_RULESET = 444
SYS_LANDLOCK_ADD_RULE = 445
SYS_LANDLOCK_RESTRICT_SELF = 446
LANDLOCK_CREATE_RULESET_VERSION = 1
LANDLOCK_RULE_PATH_BENEATH = 1

# Filesystem access rights -- real UAPI bit positions (verified against
# include/uapi/linux/landlock.h and by runtime probing on Linux 6.6).
FS_EXECUTE = 1 << 0
FS_WRITE_FILE = 1 << 1
FS_READ_FILE = 1 << 2
FS_READ_DIR = 1 << 3
FS_REMOVE_DIR = 1 << 4
FS_REMOVE_FILE = 1 << 5
FS_MAKE_CHAR = 1 << 6
FS_MAKE_DIR = 1 << 7
FS_MAKE_REG = 1 << 8
FS_MAKE_SOCK = 1 << 9
FS_MAKE_FIFO = 1 << 10
FS_MAKE_BLOCK = 1 << 11
FS_MAKE_SYM = 1 << 12
FS_REFER = 1 << 13
FS_TRUNCATE = 1 << 14
FS_IOCTL_DEV = 1 << 15

# Candidate access bits per Landlock ABI.  Each candidate is *additionally*
# verified with a live create_ruleset + add_rule probe before use, so a kernel
# that rejects a bit is never handed it (F7).
_FS_CANDIDATES_BY_ABI = {
    1: 0x1FFF,  # bits 0..12
    2: 0x3FFF,  # + REFER
    3: 0x7FFF,  # + TRUNCATE
    4: 0x7FFF,
    5: 0x7FFF,
    6: 0xFFFF,  # + IOCTL_DEV
}

# sizeof(struct landlock_ruleset_attr) for each ABI generation:
#   v1/v2: handled_access_fs only (8)
#   v3/v4: + handled_access_net (16)
#   v5/v6: + scoped (24)
_RULESET_ATTR_SIZE_BY_ABI = {1: 8, 2: 8, 3: 16, 4: 16, 5: 24, 6: 24}

NET_BIND_TCP = 1 << 0
NET_CONNECT_TCP = 1 << 1

PR_SET_KEEPCAPS = 8
PR_CAPBSET_DROP = 24
PR_SET_NO_NEW_PRIVS = 38
PR_SET_SECCOMP = 22
SECCOMP_MODE_FILTER = 2

SECCOMP_RET_ERRNO = 0x00050000
SECCOMP_RET_ALLOW = 0x7FFF0000
EPERM = errno.EPERM

# Classic BPF opcodes.
BPF_LD_W_ABS = 0x20          # BPF_LD | BPF_W | BPF_ABS
BPF_JMP_JEQ_K = 0x15         # BPF_JMP | BPF_JEQ | BPF_K
BPF_RET_K = 0x06             # BPF_RET | BPF_K

def _network_syscalls() -> frozenset[int]:
    """Network-capable syscall numbers for the running architecture.

    x86_64 uses 41..55; asm-generic (aarch64, riscv64, ...) uses 198..212.
    Both tables come from the installed kernel headers.  Other 32-bit ABIs
    (e.g. i386's multiplexed ``socketcall``) are not supported -- we fail
    closed rather than leave network access open.
    """
    machine = os.uname().machine
    if machine in ("x86_64", "amd64"):
        return frozenset({
            41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55,
            170, 171,  # sethostname, setdomainname
        })
    if machine in ("aarch64", "arm64", "riscv64", "loongarch64",
                   "ppc64le", "s390x"):
        return frozenset({
            198, 199, 200, 201, 202, 203, 204, 205, 206, 207, 208, 209,
            210, 211, 212, 161, 162,  # ... + sethostname/setdomainname
        })
    raise SandboxUnavailable(
        f"unsupported architecture for seccomp network denial: {machine}")


_NETWORK_SYSCALLS: frozenset[int] = (frozenset() if not LINUX
                                     else _network_syscalls())

# Explicitly-approved IPC.  Empty: network IPC is denied by default.
_APPROVED_IPC_SYSCALLS: frozenset[int] = frozenset()

try:
    # Created at import time: calling ctypes.CDLL() inside a forked preexec_fn
    # can deadlock against another thread holding the loader lock.
    _LIBC = ctypes.CDLL(None, use_errno=True)
    _LIBC.syscall.restype = ctypes.c_long
except Exception:  # pragma: no cover - non-Linux import safety
    _LIBC = None  # type: ignore[assignment]

_SPAWN_LOCK = threading.Lock()
_PREFLIGHT_CACHE: tuple[bool, bool, str] | None = None


class _SockFilter(ctypes.Structure):
    _fields_ = [
        ("code", ctypes.c_ushort),
        ("jt", ctypes.c_ubyte),
        ("jf", ctypes.c_ubyte),
        ("k", ctypes.c_uint32),
    ]


class _SockFprog(ctypes.Structure):
    _fields_ = [
        ("len", ctypes.c_ushort),
        ("filter", ctypes.POINTER(_SockFilter)),
    ]


# ---------------------------------------------------------------------------
# Low-level syscall helpers
# ---------------------------------------------------------------------------
def _raw_syscall(nr: int, *args: object) -> tuple[int, int]:
    ctypes.set_errno(0)
    ret = int(_LIBC.syscall(nr, *args))
    return ret, ctypes.get_errno()


def landlock_abi() -> int:
    """Return the kernel's Landlock ABI version, or 0 if unsupported."""
    if not LINUX or _LIBC is None:
        return 0
    try:
        ret, err = _raw_syscall(SYS_LANDLOCK_CREATE_RULESET, None, 0,
                                LANDLOCK_CREATE_RULESET_VERSION)
    except Exception:
        return 0
    return int(ret) if ret > 0 and not err else 0


def _seccomp_supported() -> bool:
    if not LINUX:
        return False
    try:
        return "Seccomp:" in Path("/proc/self/status").read_text(
            encoding="utf-8", errors="replace")
    except OSError:
        return False


def _ruleset_attr_size(abi: int) -> int:
    if abi >= 6:
        return _RULESET_ATTR_SIZE_BY_ABI[6]
    return _RULESET_ATTR_SIZE_BY_ABI.get(abi, 8)


def _supported_fs_bits(abi: int) -> int:
    """Return the access bits the kernel actually accepts (F7).

    The ABI version supplies the candidate set; every candidate is then
    verified with a live create_ruleset + add_rule probe.  Unsupported bits
    are dropped individually and reported -- never silently applied.
    """
    if abi <= 0:
        raise SandboxUnavailable("Landlock unavailable")
    candidates = _FS_CANDIDATES_BY_ABI.get(min(abi, 6), 0x1FFF)
    size = _ruleset_attr_size(abi)
    probe_dir = Path(tempfile.gettempdir())
    try:
        pfd = os.open(str(probe_dir), os.O_RDONLY | os.O_DIRECTORY)
    except OSError as exc:
        raise SandboxUnavailable(f"cannot probe Landlock bits: {exc}") from exc
    supported = 0
    try:
        for bit in range(64):
            if not (candidates >> bit) & 1:
                continue
            rbuf = bytearray(size)
            struct.pack_into("<Q", rbuf, 0, 1 << bit)
            rcbuf = (ctypes.c_char * size).from_buffer_copy(bytes(rbuf))
            rfd, rerr = _raw_syscall(SYS_LANDLOCK_CREATE_RULESET, rcbuf, size, 0)
            if rfd < 0 or rerr:
                continue
            try:
                abuf = bytearray(16)
                struct.pack_into("<Q", abuf, 0, 1 << bit)
                struct.pack_into("<i", abuf, 8, pfd)
                acbuf = (ctypes.c_char * 16).from_buffer_copy(bytes(abuf))
                ret, aerr = _raw_syscall(SYS_LANDLOCK_ADD_RULE, rfd,
                                         LANDLOCK_RULE_PATH_BENEATH, acbuf, 0)
                if ret == 0 and not aerr:
                    supported |= 1 << bit
            finally:
                os.close(rfd)
    finally:
        os.close(pfd)
    if not supported:
        raise SandboxUnavailable("Landlock accepted no filesystem access bits")
    return supported


# ---------------------------------------------------------------------------
# Landlock
# ---------------------------------------------------------------------------
def _create_ruleset(abi: int, fs_mask: int) -> int:
    size = _ruleset_attr_size(abi)
    buf = bytearray(size)
    struct.pack_into("<Q", buf, 0, fs_mask)
    if size >= 16:
        # Intentionally zero: some kernels (notably WSL2 6.6, which reports
        # ABI 3) reject nonzero handled_access_net with E2BIG even though the
        # version query succeeds.  Network denial is enforced by seccomp-BPF,
        # which is consistent on every kernel.  Keeping this field zero also
        # keeps the ruleset ABI-correct (field only exists for ABI >= 3).
        struct.pack_into("<Q", buf, 8, 0)
    if size >= 24:
        struct.pack_into("<Q", buf, 16, 0)  # scoped: none
    cbuf = (ctypes.c_char * size).from_buffer_copy(bytes(buf))
    fd, err = _raw_syscall(SYS_LANDLOCK_CREATE_RULESET, cbuf, size, 0)
    if fd < 0:
        raise SandboxUnavailable(
            f"landlock_create_ruleset failed (errno={err}, "
            f"{os.strerror(err)}, abi={abi}, size={size})")
    return fd


def _add_path_rule(ruleset_fd: int, path: Path, allowed: int) -> None:
    if not allowed or not path.exists():
        return
    flags = os.O_RDONLY | os.O_CLOEXEC
    if path.is_dir():
        flags |= os.O_DIRECTORY
    try:
        dir_fd = os.open(str(path), flags)
    except OSError as exc:
        raise SandboxUnavailable(
            f"cannot open Landlock rule path {path}: {exc}") from exc
    try:
        # struct landlock_path_beneath_attr: __u64 allowed_access; __s32
        # parent_fd; 4 bytes padding -> 16 bytes on 64-bit.
        buf = bytearray(16)
        struct.pack_into("<Q", buf, 0, int(allowed))
        struct.pack_into("<i", buf, 8, dir_fd)
        attr = (ctypes.c_char * 16).from_buffer_copy(bytes(buf))
        # 4th arg is `flags` and MUST be 0 -- the original defect.
        ret, err = _raw_syscall(SYS_LANDLOCK_ADD_RULE, ruleset_fd,
                                LANDLOCK_RULE_PATH_BENEATH, attr, 0)
        if ret < 0:
            raise SandboxUnavailable(
                f"landlock_add_rule failed for {path} allowed=0x{allowed:x} "
                f"(errno={err}, {os.strerror(err)})")
    finally:
        os.close(dir_fd)


def _apply_landlock(workspace: Path, abi: int, fs_bits: int,
                    extra_dirs: tuple[str, ...] = ()) -> None:
    rfd = _create_ruleset(abi, fs_bits)
    try:
        # Traversal of absolute paths.
        _add_path_rule(rfd, Path("/"), FS_EXECUTE)
        # Full control inside the workspace.
        _add_path_rule(rfd, workspace, fs_bits)
        # Read + traverse of system paths needed to exec an interpreter and
        # load its shared libraries/configuration.
        read_exec = FS_EXECUTE | FS_READ_FILE | FS_READ_DIR
        for candidate in ("/usr", "/bin", "/sbin", "/lib", "/lib64",
                          "/lib32", "/etc", "/opt"):
            _add_path_rule(rfd, Path(candidate), read_exec)
        for candidate in extra_dirs:
            _add_path_rule(rfd, Path(candidate), read_exec)
        # Character devices every process needs.
        for candidate in ("/dev/null", "/dev/zero", "/dev/urandom",
                          "/dev/random"):
            _add_path_rule(rfd, Path(candidate), FS_READ_FILE | FS_WRITE_FILE)
        _add_path_rule(rfd, Path("/dev"), FS_EXECUTE | FS_READ_DIR)

        ret, err = _raw_syscall(SYS_LANDLOCK_RESTRICT_SELF, rfd, 0)
        if ret < 0:
            raise SandboxUnavailable(
                f"landlock_restrict_self failed (errno={err}, "
                f"{os.strerror(err)})")
    finally:
        os.close(rfd)


# ---------------------------------------------------------------------------
# seccomp-BPF
# ---------------------------------------------------------------------------
def build_network_filter() -> list[tuple[int, int, int, int]]:
    """Correct BPF: load nr at offset 0, EPERM for network, ALLOW otherwise.

    F1 evidence: ``BPF_LD|BPF_W|BPF_ABS = 0x20`` at offset 0 (``seccomp_data.nr``),
    JEQ branches with jt=0/jf=1, ``SECCOMP_RET_ERRNO|EPERM = 0x00050001``, and
    default ``SECCOMP_RET_ALLOW = 0x7fff0000``.
    """
    insns: list[tuple[int, int, int, int]] = [
        (BPF_LD_W_ABS, 0, 0, 0),
    ]
    for nr in sorted(_NETWORK_SYSCALLS):
        insns.append((BPF_JMP_JEQ_K, 0, 1, nr))
        insns.append((BPF_RET_K, 0, 0, SECCOMP_RET_ERRNO | EPERM))
    for nr in sorted(_APPROVED_IPC_SYSCALLS):
        insns.append((BPF_JMP_JEQ_K, 0, 1, nr))
        insns.append((BPF_RET_K, 0, 0, SECCOMP_RET_ALLOW))
    insns.append((BPF_RET_K, 0, 0, SECCOMP_RET_ALLOW))
    return insns


def install_network_filter() -> None:
    """Install the network-deny filter in the *current* process."""
    insns = build_network_filter()
    arr = (_SockFilter * len(insns))()
    for i, (code, jt, jf, k) in enumerate(insns):
        arr[i] = _SockFilter(code, jt, jf, k)
    prog = _SockFprog(len(arr), arr)
    ctypes.set_errno(0)
    if _LIBC.prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, ctypes.byref(prog),
                   0, 0) != 0:
        err = ctypes.get_errno()
        raise SandboxUnavailable(
            f"seccomp filter install failed (errno={err}, {os.strerror(err)})")


# ---------------------------------------------------------------------------
# Child-side restrictions
# ---------------------------------------------------------------------------
def _drop_capabilities() -> list[str]:
    notes: list[str] = []
    if not hasattr(_LIBC, "prctl"):
        return notes
    ctypes.set_errno(0)
    if _LIBC.prctl(PR_SET_KEEPCAPS, 0, 0, 0, 0) != 0:
        notes.append("PR_SET_KEEPCAPS(0) unavailable")
    dropped = 0
    for cap in range(64):
        ctypes.set_errno(0)
        if _LIBC.prctl(PR_CAPBSET_DROP, cap, 0, 0, 0) == 0:
            dropped += 1
    if dropped == 0:
        notes.append("capability bounding set could not be dropped "
                     "(unprivileged process)")
    return notes


def _apply_rlimits(cpu_s: int, memory_mb: int) -> list[str]:
    notes: list[str] = []
    if resource is None:
        return ["rlimits unavailable on this platform"]
    limits = (
        (resource.RLIMIT_CPU, (max(1, int(cpu_s)), max(1, int(cpu_s)))),
        (resource.RLIMIT_AS, (memory_mb * 1024 * 1024,) * 2),
        # 256, not 16: RLIMIT_NPROC counts *all* processes of the real uid on
        # the host, so a small value breaks ordinary shells on busy runners.
        (resource.RLIMIT_NPROC, (256, 256)),
        (resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024)),
        (resource.RLIMIT_NOFILE, (64, 64)),
        (resource.RLIMIT_CORE, (0, 0)),
    )
    for rid, value in limits:
        try:
            resource.setrlimit(rid, value)
        except (OSError, ValueError) as exc:
            notes.append(f"rlimit {rid} unavailable: {exc}")
    return notes


def _child_restrictions(workspace: Path, abi: int, fs_bits: int, cpu_s: int,
                        memory_mb: int, allow_network: bool,
                        extra_dirs: tuple[str, ...] = ()) -> list[str]:
    """Run in the forked child before execve(); raises on any failure."""
    notes: list[str] = []
    if _LIBC is None:
        raise SandboxUnavailable("libc unavailable for confinement")
    # 1. no_new_privs BEFORE Landlock restrict_self and seccomp.
    if _LIBC.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        err = ctypes.get_errno()
        raise SandboxUnavailable(
            f"prctl(PR_SET_NO_NEW_PRIVS) failed (errno={err})")
    # 2. Drop capabilities opportunistically.
    notes.extend(_drop_capabilities())
    # 3. Landlock filesystem confinement (inheritable across fork+exec).
    _apply_landlock(workspace, abi, fs_bits, extra_dirs)
    # 4. seccomp network denial (inheritable across fork+exec).  Do NOT probe
    # /proc here: Landlock has already removed access to it.  The parent gates
    # on seccomp support, and prctl itself fails closed if unsupported.
    if not allow_network:
        install_network_filter()
    # 5. rlimits last so restriction setup itself is not capped.
    notes.extend(_apply_rlimits(cpu_s, memory_mb))
    return notes


# ---------------------------------------------------------------------------
# Real pre-flight (F7): report capabilities from an ACTUAL restricted child
# ---------------------------------------------------------------------------
def _preflight() -> tuple[bool, bool, str]:
    """Fork a child, apply the full boundary, and verify it actually works.

    Returns ``(filesystem_enforced, network_enforced, evidence)``.  No feature
    detection is trusted: a failure to apply or a failure to *deny* makes the
    corresponding flag False.
    """
    if not LINUX or _LIBC is None:
        return False, False, "not Linux"
    abi = landlock_abi()
    if not abi:
        return False, False, "Landlock ABI query returned 0"
    try:
        fs_bits = _supported_fs_bits(abi)
    except SandboxUnavailable as exc:
        return False, False, str(exc)

    read_fd, write_fd = os.pipe()
    try:
        with _SPAWN_LOCK:
            pid = os.fork()
        if pid == 0:  # child
            try:
                os.close(read_fd)
                ws = Path(tempfile.mkdtemp(prefix="keel-preflight-"))
                secret = ws.parent / f"keel-preflight-secret-{os.getpid()}"
                Path(secret).write_text("SECRET")
                _child_restrictions(ws, abi, fs_bits, 1, 256,
                                    allow_network=False)
                fs_ok = False
                try:
                    Path(secret).read_text()
                except OSError:
                    fs_ok = True
                net_ok = False
                try:
                    import socket as _socket
                    _socket.socket()
                except OSError:
                    net_ok = True
                evidence = (f"abi={abi} fs_bits=0x{fs_bits:x} "
                            f"fs_denied={fs_ok} net_denied={net_ok}")
                os.write(write_fd, ("OK:" + evidence).encode())
                os._exit(0)
            except BaseException as exc:  # noqa: BLE001 - report everything
                try:
                    os.write(write_fd, ("ERR:" + repr(exc)).encode())
                finally:
                    os._exit(1)
        os.close(write_fd)
        chunks = []
        while True:
            part = os.read(read_fd, 4096)
            if not part:
                break
            chunks.append(part)
        os.close(read_fd)
        _, status = os.waitpid(pid, 0)
        data = b"".join(chunks).decode("utf-8", errors="replace")
        if os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0 and \
                data.startswith("OK:") and "fs_denied=True" in data and \
                "net_denied=True" in data:
            return True, True, data[3:]
        return False, False, f"preflight failed: {data.strip()!r}"
    except OSError as exc:
        return False, False, f"preflight error: {exc}"


def capabilities() -> dict:
    """Report enforcement flags derived from a real successful pre-flight."""
    global _PREFLIGHT_CACHE
    linux = LINUX
    abi = landlock_abi() if linux else 0
    seccomp = _seccomp_supported() if linux else False
    fs_ok = net_ok = False
    evidence = ""
    if linux and abi and seccomp:
        if _PREFLIGHT_CACHE is None:
            _PREFLIGHT_CACHE = _preflight()
        fs_ok, net_ok, evidence = _PREFLIGHT_CACHE

    darwin = sys.platform == "darwin"
    windows = os.name == "nt"
    sandbox_exec = darwin and bool(shutil.which("sandbox-exec"))
    landlock = bool(abi)
    limitations: list[str] = []
    if linux and not landlock:
        limitations.append("Landlock unavailable: kernel < 5.13 or syscall blocked")
    if linux and landlock and abi < 3:
        limitations.append("Landlock ABI < 3: native net rules unavailable; "
                           "network denial is enforced by seccomp only")
    if linux and not net_ok:
        limitations.append(
            "Network enforcement could not be verified by pre-flight: "
            + (evidence or "seccomp unavailable"))
    if linux and not fs_ok:
        limitations.append(
            "Filesystem enforcement could not be verified by pre-flight: "
            + (evidence or "Landlock unavailable"))
    if windows:
        limitations.append("Windows network denial requires an administrator-"
                           "configured firewall rule; not enforced by this module")
    limitations.append("This is process-level OS isolation, not a complete VM "
                       "boundary; bwrap/unshare are not used by this backend")

    return {
        "os": sys.platform,
        "linux_landlock": landlock,
        "linux_seccomp": seccomp,
        "linux_landlock_abi": abi,
        "linux_network_denial": net_ok,
        "preflight_evidence": evidence,
        "macos_sandbox_exec": sandbox_exec,
        "windows_restricted_token": windows,
        "windows_job_object": windows,
        "filesystem_enforcement": bool(fs_ok or (sandbox_exec or windows)),
        "network_enforcement": bool(net_ok or sandbox_exec),
        "limitations": limitations,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def run_confined(argv: list[str], *, workspace: str | Path | None = None,
                 timeout_s: float = 15.0, cpu_s: int = 10,
                 memory_mb: int = 256, env: dict[str, str] | None = None,
                 allow_network: bool = False) -> ConfinementResult:
    """Run *argv* under genuine kernel-enforced Linux isolation.

    Raises ``SandboxUnavailable`` (fail-closed) whenever Landlock or seccomp
    cannot be applied; there is no unrestricted fallback.
    """
    if not LINUX:
        raise SandboxUnavailable("sandbox_linux requires Linux")
    caps = capabilities()
    abi = caps["linux_landlock_abi"]
    if not abi or not caps["filesystem_enforcement"]:
        raise SandboxUnavailable(
            "Landlock filesystem enforcement not available: "
            + caps.get("preflight_evidence", ""))
    if not allow_network and not caps["network_enforcement"]:
        raise SandboxUnavailable(
            "seccomp network enforcement not available: "
            + caps.get("preflight_evidence", ""))

    own_temp = workspace is None
    if own_temp:
        workspace_path = Path(tempfile.mkdtemp(prefix="keel-confined-"))
    else:
        workspace_path = Path(workspace).expanduser().resolve()
    workspace_path.mkdir(parents=True, exist_ok=True)
    limitations = list(caps["limitations"])
    fs_bits = _supported_fs_bits(abi)

    # Allow read+exec of an interpreter that lives outside the standard dirs
    # (e.g. a project-local virtualenv).  Kept local so concurrent calls
    # cannot clobber each other's rule set.
    extra: set[str] = set()
    for value in (sys.executable, argv[0] if argv else ""):
        if not value:
            continue
        try:
            p = Path(value).resolve()
        except OSError:
            continue
        if p.is_file():
            p = p.parent
        if not p.is_dir():
            continue
        s = str(p)
        if s.startswith(("/usr", "/bin", "/lib", "/sbin", "/etc", "/opt")):
            continue
        if workspace_path != p and workspace_path not in p.parents:
            extra.add(s)
    extra_dirs = tuple(sorted(extra))
    child_env = env if env is not None else {}

    def preexec() -> None:
        notes = _child_restrictions(workspace_path, abi, fs_bits, cpu_s,
                                    memory_mb, allow_network, extra_dirs)
        limitations.extend(notes)

    started = time.monotonic()
    proc: subprocess.Popen | None = None
    try:
        with _SPAWN_LOCK:
            proc = subprocess.Popen(
                argv, cwd=str(workspace_path), env=child_env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True, close_fds=True,
                preexec_fn=preexec,
            )
        out, err = proc.communicate(timeout=timeout_s)
        code = proc.returncode
        timed_out = False
    except subprocess.TimeoutExpired:
        timed_out = True
        code = None
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.kill()
            except OSError:
                pass
        out, err = proc.communicate()
    except (subprocess.SubprocessError, OSError) as exc:
        raise SandboxUnavailable(
            f"could not launch confined process: {exc}") from exc
    finally:
        if own_temp:
            shutil.rmtree(workspace_path, ignore_errors=True)

    return ConfinementResult(
        ok=(code == 0),
        exit_code=code,
        timed_out=timed_out,
        elapsed_s=round(time.monotonic() - started, 3),
        mechanism="landlock+seccomp+nnp+capdrop+rlimits",
        stdout=(out or b"").decode("utf-8", errors="replace"),
        stderr=(err or b"").decode("utf-8", errors="replace"),
        limitations=limitations,
    )
