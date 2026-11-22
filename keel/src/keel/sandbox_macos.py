"""macOS-native confined execution using Seatbelt (``sandbox-exec``).

This is a standalone backend.  It deliberately does not edit the shared
``keel.os_sandbox`` module; callers can opt into it on macOS and reuse the
shared ``ConfinementResult`` / ``SandboxUnavailable`` types.

Why a new module is needed
--------------------------
The previous macOS profile hard-coded read roots (``/usr``, ``/bin``,
``/System``, ...).  On GitHub ``macos-latest`` the interpreter installed by
``actions/setup-python`` lives under
``/Users/runner/hostedtoolcache/Python/<ver>/x64`` -- outside every allowed
root -- so ``sandbox-exec`` denied the executable, its dylibs and the stdlib.
A second, independent blocker was ``RLIMIT_AS=256 MB``: since macOS 11 the
kernel maps a ~1-2 GiB dyld shared cache into *every* process at exec time,
so a 256 MB address-space limit kills the interpreter before ``main()``.

This module derives the interpreter's real prefixes from ``sys.prefix`` /
``sys.base_prefix`` / ``sysconfig`` and applies a macOS-safe address-space
floor.  It grants file *content* reads only to the workspace, the interpreter
runtime and a small set of OS roots; everything else is denied by default.

Deprecation notice
------------------
``sandbox-exec(1)`` is documented as **DEPRECATED** by Apple ("Developers who
wish to sandbox an app should instead adopt the App Sandbox feature").  It is
still present and functional on macOS 15 (Sequoia), but it is not a supported
long-term API.  See ``docs/research/macos-sandbox-mechanism.md`` for the full
mechanism, evidence and limitations.  No Electron entitlement is relied upon:
a separately launched Python process is confined by this module explicitly.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import sysconfig
import tempfile
import time
from pathlib import Path

from .os_sandbox import ConfinementResult, SandboxUnavailable

# The dyld shared cache is mapped into every process and occupies roughly
# 1-2 GiB of virtual address space (3-5 GiB on disk on Apple Silicon).  A
# 256 MB RLIMIT_AS therefore makes *any* exec fail on modern macOS.  4 GiB
# leaves room for the cache, the interpreter and ordinary heap growth.
_MACOS_AS_FLOOR_MB = 4096

# Read-only OS areas required by dyld, libSystem and a POSIX shell.  These are
# system software locations, not user data.  /dev is intentionally NOT broad:
# reading a raw disk device would bypass the Seatbelt path checks entirely.
_SYSTEM_READ_ROOTS: tuple[str, ...] = (
    "/System",
    "/Library",
    "/usr",
    "/bin",
    "/sbin",
    "/usr/sbin",
    "/opt",
    "/etc",
    "/private/etc",
    "/private/var/db/dyld",
    "/private/var/db/timezone",
    "/var/db/dyld",
    "/var/db/timezone",
)

_DEVICE_READ_PATHS: tuple[str, ...] = (
    "/dev/null",
    "/dev/zero",
    "/dev/random",
    "/dev/urandom",
)

_SBPL_FORBIDDEN = ('"', "\\", "(", ")")


def _sbpl_path(value: str | Path) -> str:
    """Validate and quote a path for embedding in an SBPL profile.

    SBPL is a TinyScheme DSL; an unescaped ``)`` or quote in a caller-supplied
    path could inject additional rules.  Paths containing metacharacters or
    control characters are rejected (fail closed) instead of being escaped.
    """
    text = str(value)
    if not text.startswith("/"):
        raise SandboxUnavailable(f"SBPL path must be absolute: {text!r}")
    if any(ch in text for ch in _SBPL_FORBIDDEN) or any(
        ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text
    ):
        raise SandboxUnavailable(f"SBPL profile injection rejected in path: {text!r}")
    return text


def _runtime_read_roots(argv: list[str] | None) -> list[str]:
    """Derive interpreter roots from the *running* Python and the target argv.

    ``actions/setup-python`` on macos-latest places Python under the runner's
    toolcache, which no hard-coded profile can know.  These roots give dyld
    the Mach-O/dylibs and CPython its stdlib/site-packages/lib-dynload.
    """
    roots: list[str] = []

    def add(path: object) -> None:
        if not path:
            return
        try:
            resolved = str(Path(str(path)).resolve())
        except OSError:
            return
        if resolved not in roots:
            roots.append(resolved)

    # Host interpreter (in the normal case argv[0] == sys.executable).
    add(sys.prefix)
    add(sys.base_prefix)
    add(sys.executable)
    try:
        paths = sysconfig.get_paths()
        for key in ("data", "stdlib", "platstdlib", "purelib", "platlib", "scripts"):
            add(paths.get(key))
    except Exception:  # sysconfig can fail in exotic embeddings; stay fail-closed
        pass

    # Target executable, when it is a different interpreter/binary.
    if argv:
        target = str(argv[0])
        located = target if os.path.isabs(target) else shutil.which(target)
        if located:
            exe = Path(located).resolve()
            add(exe)
            add(exe.parent)
            add(exe.parent.parent)

    return roots


def build_profile(
    workspace: str | Path,
    *,
    read_roots: tuple[str, ...] | list[str] = (),
    allow_network: bool = False,
) -> str:
    """Build a restrictive version-1 Seatbelt profile.

    Reads of file *contents* outside the workspace and the supplied roots are
    denied.  Writes are confined to the workspace.  ``file-read-metadata`` is
    intentionally global: dyld and Python's path walker stat ancestor paths
    that cannot be enumerated in advance (this is recorded as PARTIAL).
    """
    ws = _sbpl_path(workspace)
    # Keep the rule count small: the SBPL compiler aborts (SIGABRT, no stderr)
    # on large filter sets. Merge filters into one rule per kind and drop roots
    # already covered by a broader system root.
    roots: list[str] = []
    for candidate in (*_SYSTEM_READ_ROOTS, *read_roots):
        path = _sbpl_path(candidate)
        if (path == ws or path in roots or any(
            path.startswith(other.rstrip("/") + "/") for other in roots
        )):
            # Duplicate filters are not harmless: the SBPL compiler aborts
            # (SIGABRT, empty stderr) when the same filter is repeated.
            continue
        roots.append(path)

    read_filters = " ".join(f'(subpath "{root}")' for root in roots)
    device_filters = " ".join(f'(literal "{d}")' for d in _DEVICE_READ_PATHS)
    lines = [
        "(version 1)",
        "(deny default)",
        "",
        ";; process primitives: launch the interpreter and its children",
        "(allow process-exec)",
        "(allow process-fork)",
        "(allow sysctl-read)",
        "(allow file-ioctl)",
        "",
        ";; dyld/libSystem runtime support (metadata only, no file contents)",
        "(allow file-read-metadata)",
        "(allow mach-lookup)",
        "(allow ipc-posix-shm)",
        "(allow system-socket)",
        "",
        ";; the authorized workspace is the only writable area",
        f'(allow file-read* (subpath "{ws}"))',
        f'(allow file-write* (subpath "{ws}"))',
        "",
        ";; read-only interpreter/OS roots needed to start a process",
        f"(allow file-read* {read_filters})",
        f"(allow file-read* {device_filters})",
        "",
        "(allow network*)" if allow_network else "(deny network*)",
    ]
    return "\n".join(lines) + "\n"


def _limitations(memory_mb: int, *, allow_network: bool = False) -> list[str]:
    out = [
        "sandbox-exec(1) is DEPRECATED by Apple; App Sandbox is the supported "
        "replacement. This backend works on macOS 15 but is not guaranteed "
        "on future releases.",
        "No Electron entitlement is used or assumed: the Python process is "
        "confined by an explicit sandbox-exec profile from this module.",
        "Filesystem isolation is PARTIAL: file-read-metadata is allowed "
        "globally so dyld/CPython can stat ancestors (names and sizes are "
        "visible, file contents outside the allowlist are not).",
        "mach-lookup, ipc-posix-shm* and system-socket are allowed for dyld/"
        "libSystem; system IPC is not confined.",
        "Seatbelt checks resource acquisition; descriptors already open when "
        "the profile was applied remain usable.",
        "No PID namespace: the confined tree shares the host PID space. "
        "Timeout kills the child's process group, not unrelated host jobs.",
        "RLIMIT_NPROC is not applied on macOS: it counts every process of the "
        "UID, so a low value breaks legitimate forks in the confined tree.",
        "This is process-level OS isolation, not a VM boundary.",
    ]
    if memory_mb < _MACOS_AS_FLOOR_MB:
        out.append(
            f"RLIMIT_AS raised from {memory_mb} MB to {_MACOS_AS_FLOOR_MB} MB: "
            "the dyld shared cache maps ~1-2 GiB into every process, so a "
            "256 MB address-space cap prevents interpreter startup. The "
            "memory ceiling is advisory (PARTIAL)."
        )
    if allow_network:
        out.append("Network access explicitly enabled by caller (allow_network=True).")
    return out


def capabilities() -> dict:
    """Report macOS Seatbelt support and its honest limitations."""
    present = bool(shutil.which("sandbox-exec"))
    available = sys.platform == "darwin" and present
    return {
        "os": sys.platform,
        "backend": "macos-seatbelt-sandbox-exec",
        "sandbox_exec": present,
        "available": available,
        "deprecated": True,
        "filesystem_enforcement": "PARTIAL" if available else False,
        "filesystem_write_enforcement": "FULL" if available else False,
        "network_enforcement": available,
        "process_inheritance": available,
        "rlimits": {
            "cpu": available,
            "address_space": "PARTIAL" if available else False,
            "nproc": False,
        },
        "limitations": _limitations(256),
    }


def _tail(data: bytes | None, size: int = 400) -> str:
    return (data or b"").decode("utf-8", errors="replace")[-size:]


def _diagnose_profile(sandbox_exec: str, profile: str) -> str:
    """Isolate the SBPL rule interaction that makes ``sandbox-exec`` abort.

    An invalid/conflicting SBPL rule aborts with an empty stderr on modern
    macOS. This runs only after a failed pre-flight so CI logs carry an exact
    BLOCKED reason rather than a silent signal.
    """
    def compiles(rules: list[str]) -> bool:
        try:
            result = subprocess.run(
                [sandbox_exec, "-p", "\n".join(rules) + "\n", "/usr/bin/true"],
                capture_output=True, timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

    all_rules = [
        line for line in profile.splitlines()
        if line and not line.startswith(";")
    ]
    if compiles(all_rules):
        return "the full profile compiles in isolation"

    # Which single rule, when removed, makes the profile compile?
    culprits = []
    for i, rule in enumerate(all_rules):
        if compiles(all_rules[:i] + all_rules[i + 1:]):
            culprits.append(rule)
    if culprits:
        return "removing any of these rules makes it compile: " + repr(culprits)

    # Otherwise shrink in chunks while it still fails (keep the essentials).
    essential = {"(version 1)", "(deny default)", "(allow process-exec)"}
    current = list(all_rules)
    changed = True
    while changed and len(current) > 4:
        changed = False
        chunk = max(1, (len(current) - 3) // 2)
        for i in range(0, len(current), chunk):
            trial = current[:i] + current[i + chunk:]
            if any(r in essential for r in trial) and len(trial) > 3 and not compiles(trial):
                current = trial
                changed = True
                break
    return (f"no single-rule culprit; minimal failing core "
            f"({len(current)} rules):\n" + "\n".join(current))


def run_confined(
    argv: list[str],
    *,
    workspace: str | Path | None = None,
    timeout_s: float = 15.0,
    cpu_s: int = 10,
    memory_mb: int = 256,
    env: dict[str, str] | None = None,
    allow_network: bool = False,
) -> ConfinementResult:
    """Run *argv* under a real macOS Seatbelt profile.

    Raises ``SandboxUnavailable`` (never an unrestricted fallback) when the
    platform, the tool, the profile or the pre-flight probe cannot enforce the
    boundary.  A launch failure of *argv* itself is returned as a failing
    ``ConfinementResult`` with the exact stderr; it is never a pass.
    """
    if sys.platform != "darwin":
        raise SandboxUnavailable(
            f"macOS Seatbelt backend requires darwin, got {sys.platform!r}")
    sandbox_exec = shutil.which("sandbox-exec")
    if not sandbox_exec:
        raise SandboxUnavailable("sandbox-exec unavailable")
    if not argv:
        raise SandboxUnavailable("argv must be a non-empty list")

    if workspace is None:
        workspace = Path(tempfile.mkdtemp(prefix="keel-macos-sandbox-"))
    ws_path = Path(workspace).resolve()
    ws_path.mkdir(parents=True, exist_ok=True)
    ws = _sbpl_path(ws_path)

    read_roots = tuple(_runtime_read_roots(argv))  # system roots added by build_profile
    profile = build_profile(ws, read_roots=read_roots, allow_network=allow_network)
    limitations = _limitations(memory_mb, allow_network=allow_network)
    as_cap_mb = max(int(memory_mb), _MACOS_AS_FLOOR_MB)
    started = time.monotonic()

    # Fail closed if the profile itself cannot be compiled/applied.  This
    # turns "profile denied the probe" into an explicit BLOCKED error rather
    # than a silent unrestricted run or a misleading command failure.
    try:
        probe = subprocess.run(
            [sandbox_exec, "-p", profile, "/usr/bin/true"],
            capture_output=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SandboxUnavailable(f"sandbox-exec pre-flight failed: {exc}") from exc
    if probe.returncode != 0:
        # An invalid SBPL rule makes sandbox-exec abort with an empty stderr;
        # isolate the offending rule so CI logs carry an exact BLOCKED reason.
        diag = _diagnose_profile(sandbox_exec, profile)
        raise SandboxUnavailable(
            f"sandbox-exec profile could not launch a probe "
            f"(exit={probe.returncode}, stderr={_tail(probe.stderr)!r}, "
            f"stdout={_tail(probe.stdout)!r}); {diag}; profile:\n{profile}")

    scratch = ws_path / ".tmp"
    scratch.mkdir(exist_ok=True)
    child_env = dict(env) if env is not None else {}
    # PyInstaller one-file sidecars extract to TMPDIR; keeping it inside the
    # workspace lets them start under the write allowlist.  Callers that pass
    # an explicit TMPDIR outside the workspace will get a denied extraction.
    child_env.setdefault("TMPDIR", str(scratch))

    def preexec() -> None:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (int(cpu_s), int(cpu_s)))
        # macOS_LAYOUT: shared cache needs a large virtual address space.
        cap = as_cap_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        # RLIMIT_NPROC is intentionally NOT set on macOS (see limitations).

    cmd = [sandbox_exec, "-p", profile, *[str(a) for a in argv]]
    timed_out = False
    try:
        proc = subprocess.Popen(
            cmd, cwd=ws, env=child_env, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, preexec_fn=preexec, start_new_session=True,
        )
        try:
            out, err = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            out, err = proc.communicate()
        code = proc.returncode
    except OSError as exc:
        raise SandboxUnavailable(f"could not start confined process: {exc}") from exc

    return ConfinementResult(
        ok=(code == 0 and not timed_out),
        exit_code=code,
        timed_out=timed_out,
        elapsed_s=round(time.monotonic() - started, 3),
        mechanism="macos-seatbelt-sandbox-exec",
        stdout=(out or b"").decode("utf-8", errors="replace"),
        stderr=(err or b"").decode("utf-8", errors="replace"),
        limitations=limitations,
    )
