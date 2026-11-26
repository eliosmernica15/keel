"""macOS-native confined execution using Seatbelt (``sandbox-exec``).

This is a standalone backend. It deliberately does not edit the shared
``keel.os_sandbox`` module; callers can opt into it on macOS and reuse the
shared ``ConfinementResult`` / ``SandboxUnavailable`` types.

What was broken
---------------
The old macOS profile hard-coded read roots (``/usr``, ``/bin``, ``/System``,
...). On GitHub ``macos-latest`` the interpreter installed by
``actions/setup-python`` lives under ``/Users/runner/hostedtoolcache/...`` or
the framework directory, and a 256 MB ``RLIMIT_AS`` conflicts with the ~1-2 GiB
dyld shared cache mapped into every process. Both blocked interpreter startup.
This module derives interpreter roots from ``sys.prefix`` / ``sys.base_prefix``
/ ``sysconfig`` and applies a macOS-safe address-space floor.

**Host regression.** On the current ``macos-latest`` (macOS 26 arm64) Apple's
``sandbox-exec`` silently aborts (SIGABRT, exit -6, empty stderr) for *any*
path-filtered ``file-read*`` rule -- even ``(subpath "/usr")`` -- while an
unfiltered ``(allow file-read*)`` works. The same behaviour is independently
reported for macOS 27 (coccinella-labs/harper#926). This module therefore tries
the restrictive profile first and, only when that exact abort is reproduced,
uses a **documented fallback** that grants global reads but still confines
writes, network and rlimits. Read isolation is then reported as ``BLOCKED``;
it is never claimed as enforced. See
``docs/research/macos-sandbox-mechanism.md`` for all evidence and limitations.

Deprecation: ``sandbox-exec(1)`` is documented as **DEPRECATED** by Apple; App
Sandbox is the supported replacement. No Electron entitlement is relied upon.
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

# The dyld shared cache maps ~1-2 GiB into every process on modern macOS.
_MACOS_AS_FLOOR_MB = 4096

# Canonical spellings only: /etc -> /private/etc, /var -> /private/var,
# /bin -> /usr/bin and /sbin -> /usr/sbin (verified by profile probing).
_SYSTEM_READ_ROOTS: tuple[str, ...] = (
    "/System", "/Library", "/usr", "/opt",
    "/private/etc", "/private/var/db/dyld", "/private/var/db/timezone",
)
_DEVICE_READ_PATHS: tuple[str, ...] = (
    "/dev/null", "/dev/zero", "/dev/random", "/dev/urandom",
)
_SBPL_FORBIDDEN = ('"', "\\", "(", ")")
_PATH_ALIASES = (("/etc", "/private/etc"), ("/var", "/private/var"),
                 ("/bin", "/usr/bin"), ("/sbin", "/usr/sbin"))

_SUPPORT: dict | None = None


def _sbpl_path(value: str | Path) -> str:
    """Validate and quote a path for embedding in an SBPL profile.

    SBPL is a TinyScheme DSL; an unescaped ``)`` or quote in a caller-supplied
    path could inject rules. Such paths are rejected (fail closed).
    """
    text = str(value)
    if not text.startswith("/"):
        raise SandboxUnavailable(f"SBPL path must be absolute: {text!r}")
    if any(ch in text for ch in _SBPL_FORBIDDEN) or any(
        ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text
    ):
        raise SandboxUnavailable(f"SBPL profile injection rejected in path: {text!r}")
    return text


def _canonical_path(path: str) -> str:
    """Collapse macOS symlink aliases so SBPL never sees duplicate filters."""
    for alias, real in _PATH_ALIASES:
        if path == alias:
            return real
        if path.startswith(alias + "/"):
            return real + path[len(alias):]
    return path


def _runtime_read_roots(argv: list[str] | None) -> list[str]:
    """Derive interpreter roots from the running Python and the target argv."""
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

    add(sys.prefix)
    add(sys.base_prefix)
    add(sys.executable)
    try:
        paths = sysconfig.get_paths()
        for key in ("data", "stdlib", "platstdlib", "purelib", "platlib", "scripts"):
            add(paths.get(key))
    except Exception:
        pass
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
    restrict_reads: bool = True,
) -> str:
    """Build a Seatbelt profile.

    With ``restrict_reads=True`` (default) only the workspace, the interpreter
    runtime and a small set of OS roots are readable. With ``False`` a single
    ``(allow file-read*)`` is used -- only for the documented host-regression
    fallback, and callers must report read isolation as BLOCKED.
    Writes are always confined to the workspace.
    """
    ws = _sbpl_path(workspace)
    roots: list[str] = []
    for candidate in (*_SYSTEM_READ_ROOTS, *read_roots):
        path = _canonical_path(_sbpl_path(candidate))
        if (path == ws or path in roots or any(
            path.startswith(other.rstrip("/") + "/") for other in roots
        )):
            # Duplicate and alias filters make sandbox-exec abort with SIGABRT.
            continue
        roots.append(path)

    if restrict_reads:
        filters = " ".join(
            [f'(subpath "{ws}")']
            + [f'(subpath "{r}")' for r in roots]
            + [f'(literal "{d}")' for d in _DEVICE_READ_PATHS]
        )
        read_rule = f"(allow file-read* {filters})"
    else:
        read_rule = "(allow file-read*)"

    return "\n".join([
        "(version 1)",
        "(deny default)",
        "",
        ";; process primitives: launch the interpreter and its children",
        "(allow process-exec)",
        "(allow process-fork)",
        "(allow sysctl-read)",
        "(allow file-ioctl)",
        "",
        ";; dyld / libSystem runtime support (no file contents here)",
        "(allow file-read-metadata)",
        "(allow mach-lookup)",
        "(allow ipc-posix-shm)",
        "(allow system-socket)",
        "",
        ";; the authorized workspace is the only writable area",
        f'(allow file-write* (subpath "{ws}"))',
        "",
        ";; file reads",
        read_rule,
        "",
        "(allow network*)" if allow_network else "(deny network*)",
    ]) + "\n"


def _probe(sandbox_exec: str, profile: str, target: str = "/usr/bin/true"):
    try:
        return subprocess.run(
            [sandbox_exec, "-p", profile, target],
            capture_output=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _is_known_read_filter_abort(
    result: subprocess.CompletedProcess | None,
) -> bool:
    return (
        result is not None
        and result.returncode == -signal.SIGABRT
        and not (result.stderr or b"").strip()
    )


def _support() -> dict:
    """Probe which profile shapes this host can actually enforce (cached)."""
    global _SUPPORT
    if _SUPPORT is not None:
        return _SUPPORT
    sx = shutil.which("sandbox-exec")
    if sys.platform != "darwin" or not sx:
        _SUPPORT = {
            "available": False, "restrictive": False, "broad": False,
            "narrow_subpath": False,
            "restrictive_error": "sandbox-exec unavailable / not macOS",
        }
        return _SUPPORT
    narrow = _probe(sx, "(version 1)\n(deny default)\n(allow process-exec)\n"
                    '(allow file-read* (subpath "/usr"))\n')
    restrictive = _probe(sx, build_profile("/tmp"))
    broad = _probe(sx, build_profile("/tmp", restrict_reads=False))
    _SUPPORT = {
        "available": True,
        "narrow_subpath": bool(narrow is not None and narrow.returncode == 0),
        "restrictive": bool(restrictive is not None and restrictive.returncode == 0),
        "restrictive_abort": _is_known_read_filter_abort(restrictive),
        "broad": bool(broad is not None and broad.returncode == 0),
        "restrictive_error": (
            f"exit={restrictive.returncode if restrictive else 'timeout'}, "
            f"stderr={(restrictive.stderr if restrictive else b'')!r}"
        ),
    }
    return _SUPPORT


def _limitations(memory_mb: int, *, allow_network: bool = False,
                 support: dict | None = None) -> list[str]:
    support = support or _support()
    out = [
        "sandbox-exec(1) is DEPRECATED by Apple; App Sandbox is the supported "
        "replacement. This backend works on macOS 15 but is not guaranteed "
        "on future releases.",
        "No Electron entitlement is used or assumed: the Python process is "
        "confined by an explicit sandbox-exec profile from this module.",
        "mach-lookup, ipc-posix-shm and system-socket are allowed for dyld/"
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
    if support.get("restrictive"):
        out.append(
            "file-read-metadata is allowed globally so dyld/CPython can stat "
            "ancestors; names and sizes are visible, contents are not."
        )
    elif support.get("broad") and support.get("restrictive_abort"):
        out.append(
            "READ ISOLATION BLOCKED on this host: sandbox-exec aborts "
            f"({support['restrictive_error']}) for any path-filtered "
            "file-read rule (narrow /usr subpath probe: "
            f"{support['narrow_subpath']}). A documented fallback grants "
            "global file-read* while still confining writes, network and "
            "rlimits; host file contents remain readable."
        )
    elif support.get("broad"):
        out.append(
            "READ ISOLATION UNAVAILABLE on this host: the restrictive profile "
            "failed for an unexpected reason; the broad-read fallback is disabled."
        )
    if allow_network:
        out.append("Network access explicitly enabled by caller (allow_network=True).")
    return out


def capabilities() -> dict:
    """Report macOS Seatbelt support and its honest limitations."""
    support = _support()
    available = support["available"]
    if not available:
        read_isolation = "UNAVAILABLE"
    elif support["restrictive"]:
        read_isolation = "RESTRICTIVE"
    elif support["broad"] and support["restrictive_abort"]:
        read_isolation = "BLOCKED"
    else:
        read_isolation = "UNAVAILABLE"
    return {
        "os": sys.platform,
        "backend": "macos-seatbelt-sandbox-exec",
        "sandbox_exec": bool(shutil.which("sandbox-exec")),
        "available": available,
        "deprecated": True,
        "read_isolation": read_isolation,
        "filesystem_enforcement": "FULL" if read_isolation == "RESTRICTIVE" else "PARTIAL",
        "filesystem_write_enforcement": "FULL" if available else False,
        "network_enforcement": available,
        "process_inheritance": available,
        "rlimits": {
            "cpu": available,
            "address_space": "PARTIAL" if available else False,
            "nproc": False,
        },
        "limitations": _limitations(256, support=support),
    }


def _tail(data: bytes | None, size: int = 400) -> str:
    return (data or b"").decode("utf-8", errors="replace")[-size:]


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
    platform, the tool, the profile or a probe cannot enforce the boundary.
    A launch failure of *argv* itself is returned as a failing result with the
    exact stderr; it is never a pass.
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

    read_roots = tuple(_runtime_read_roots(argv))
    support = _support()
    started = time.monotonic()

    profile = build_profile(ws, read_roots=read_roots,
                            allow_network=allow_network, restrict_reads=True)
    probe = _probe(sandbox_exec, profile)
    if probe is None:
        raise SandboxUnavailable("sandbox-exec pre-flight timed out or failed to start")
    restrictive_ok = probe.returncode == 0
    if not restrictive_ok:
        # Only the specifically diagnosed SIGABRT for filtered reads may fall
        # back; every other failure stays fail-closed.
        if (support["restrictive"] or not support["broad"]
                or not support["restrictive_abort"]
                or not _is_known_read_filter_abort(probe)):
            raise SandboxUnavailable(
                f"sandbox-exec profile could not launch a probe "
                f"(exit={probe.returncode}, stderr={_tail(probe.stderr)!r}); "
                f"host probe={support}")
        profile = build_profile(ws, read_roots=read_roots,
                                allow_network=allow_network, restrict_reads=False)
        fallback_probe = _probe(sandbox_exec, profile)
        if fallback_probe is None or fallback_probe.returncode != 0:
            raise SandboxUnavailable(
                "both restrictive and broad-read profiles failed: "
                f"restrictive={probe.returncode}, "
                f"broad={getattr(fallback_probe, 'returncode', None)!r}")
    limitations = _limitations(memory_mb, allow_network=allow_network,
                               support=support)
    mechanism = ("macos-seatbelt-sandbox-exec" if restrictive_ok else
                 "macos-seatbelt-sandbox-exec (read-isolation BLOCKED)")

    scratch = ws_path / ".tmp"
    scratch.mkdir(exist_ok=True)
    child_env = dict(env) if env is not None else {}
    # PyInstaller one-file sidecars unpack into TMPDIR; keeping it inside the
    # workspace lets them start under the write allowlist.
    child_env.setdefault("TMPDIR", str(scratch))

    cap_mb = max(int(memory_mb), _MACOS_AS_FLOOR_MB)

    def preexec() -> None:
        import resource

        # macOS rejects some rlimit values (notably large RLIMIT_AS ceilings)
        # with ValueError; an exception here aborts Popen with SubprocessError.
        # Each limit is best-effort and the limitations list reports the
        # memory ceiling as advisory (PARTIAL). RLIMIT_NPROC is not set.
        cap = cap_mb * 1024 * 1024
        for rid, value in ((resource.RLIMIT_CPU, (int(cpu_s), int(cpu_s))),
                           (resource.RLIMIT_AS, (cap, cap))):
            try:
                resource.setrlimit(rid, value)
            except (OSError, ValueError, OverflowError):
                pass

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
        mechanism=mechanism,
        stdout=(out or b"").decode("utf-8", errors="replace"),
        stderr=(err or b"").decode("utf-8", errors="replace"),
        limitations=limitations,
    )
