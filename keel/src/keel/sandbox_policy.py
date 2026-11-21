"""Python-level sandbox policy injected into untrusted child processes.

The strongest isolation available in pure Python is ``sys.addaudithook``:
hooks are installed at startup, cannot be removed, and fire for the risky
operations (open, socket, subprocess, ctypes.dlopen). This module builds the
bootstrap source that is written into the sandbox workdir and executed before
the submitted code.

Honest scope: this is a Python-level boundary. It stops ordinary file, network
and process misuse by untrusted Python code. It does NOT defend against native
code that bypasses the interpreter, kernel-level attacks, or a malicious
already-loaded C extension. OS-level isolation (containers, seccomp,
AppArmor, Windows restricted tokens/Job Objects) is a separate external
requirement and is reported by ``sandbox_status()`` as not enforced locally.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BOOTSTRAP_NAME = "_keel_sandbox_bootstrap.py"
USER_CODE_NAME = "_keel_user_code.py"

# Environment keys that must never be visible to untrusted code.
_SECRET_ENV_FRAGMENTS = (
    "KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL", "COOKIE",
    "AUTH", "PROXY", "KEEL_",
)

# Environment keys retained (allow-list) for a usable Python process.
_SAFE_ENV = (
    "PATH", "SystemRoot", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR",
    "LANG", "LC_ALL", "PYTHONIOENCODING", "HOME", "USERPROFILE",
)

_BOOTSTRAP = r'''"""Keel sandbox bootstrap — installs an immutable audit hook."""
import os as _os
import sys as _sys

_ROOT = _os.path.realpath(_os.environ.get("KEEL_SANDBOX_ROOT", _os.getcwd()))
_LIB_DIRS = tuple(
    _os.path.realpath(p) for p in _sys.path
    if p and _os.path.isdir(p)
)
_NETWORK_ALLOWED = _os.environ.get("KEEL_SANDBOX_NETWORK") == "1"

_MUTATING_EVENTS = frozenset({
    "os.mkdir", "os.makedirs", "os.remove", "os.rmdir", "os.rename",
    "os.replace", "os.symlink", "os.link", "os.truncate", "os.chmod",
    "os.chown", "os.utime", "os.putenv", "os.unsetenv", "os.setuid",
    "os.setgid", "os.kill", "os.fork", "os.forkpty", "os.exec",
    "os.spawn", "os.posix_spawn", "subprocess.Popen",
})
_PROCESS_EVENTS = frozenset({
    "os.fork", "os.forkpty", "os.exec", "os.spawn", "os.posix_spawn",
    "os.system", "os.kill", "subprocess.Popen",
})
_NATIVE_EVENTS = frozenset({
    "ctypes.dlopen", "ctypes.dlsym", "ctypes.get_func", "sys.addaudithook",
})


def _within(path, bases):
    try:
        real = _os.path.realpath(_os.fspath(path))
    except (TypeError, ValueError, OSError):
        return False
    for base in bases:
        if real == base or real.startswith(base + _os.sep):
            return True
    return False


def _deny(event, args):
    if event == "open":
        path = args[0] if args else None
        if isinstance(path, int):
            raise PermissionError("sandbox: raw file-descriptor access denied")
        mode = args[1] if len(args) > 1 else "r"
        flags = args[2] if len(args) > 2 else None
        write = isinstance(mode, str) and any(c in mode for c in "wax+")
        if flags is not None:
            flags = int(flags)
            write = write or bool(flags & (
                _os.O_WRONLY | _os.O_RDWR | _os.O_CREAT |
                _os.O_APPEND | _os.O_TRUNC))
        if not _within(path, (_ROOT,) + _LIB_DIRS):
            raise PermissionError(
                "sandbox: path outside workspace/library denied: " + str(path))
        if write and not _within(path, (_ROOT,)):
            raise PermissionError(
                "sandbox: write outside workspace denied: " + str(path))
        return
    if event in _NATIVE_EVENTS or event in _PROCESS_EVENTS:
        raise PermissionError("sandbox: event denied: " + event)
    if event in _MUTATING_EVENTS:
        path = args[0] if args else None
        if isinstance(path, str) and not _within(path, (_ROOT,)):
            raise PermissionError(
                "sandbox: mutating path outside workspace denied: " + str(path))
        return
    if event.startswith(("socket.", "urllib.", "http.client.",
                         "smtplib.", "ftplib.", "asyncio.")):
        if not _NETWORK_ALLOWED:
            raise PermissionError("sandbox: network access denied: " + event)
        return


_sys.addaudithook(_deny)

# Execute the submitted code in this restricted interpreter.
_code_path = _os.path.join(_ROOT, "__USER_CODE_NAME__")
with open(_code_path, "rb") as _fh:
    _source = _fh.read()
_compiled = compile(_source, "<sandbox-user-code>", "exec")
exec(_compiled, {"__name__": "__main__", "__file__": _code_path})
'''


def bootstrap_source() -> str:
    """Return the bootstrap source with the user-code filename substituted."""
    return _BOOTSTRAP.replace("__USER_CODE_NAME__", USER_CODE_NAME)


def prepare_workspace(workdir: str | Path, code: str) -> tuple[Path, Path]:
    """Write the bootstrap and user code into the isolated workdir."""
    root = Path(workdir)
    root.mkdir(parents=True, exist_ok=True)
    bootstrap = root / BOOTSTRAP_NAME
    user = root / USER_CODE_NAME
    bootstrap.write_bytes(bootstrap_source().encode("utf-8"))
    user.write_bytes(code.encode("utf-8"))
    return bootstrap, user


def child_env(*, allow_network: bool = False) -> dict[str, str]:
    """Build a scrubbed environment for the child process."""
    env = {key: value for key, value in os.environ.items()
           if key in _SAFE_ENV}
    env["KEEL_SANDBOX_ROOT"] = ""  # set by caller to the real workdir
    env["KEEL_SANDBOX_NETWORK"] = "1" if allow_network else "0"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def credential_keys_present(env: dict[str, str] | None = None) -> list[str]:
    """Report which credential-like environment keys exist (names only)."""
    env = env if env is not None else os.environ
    return sorted(
        key for key in env
        if any(fragment in key.upper() for fragment in _SECRET_ENV_FRAGMENTS))


def sandbox_status() -> dict:
    """Honest report of what is enforced locally."""
    return {
        "filesystem": {
            "workspace_read_write": True,
            "library_read": True,
            "outside_read_write": "denied for Python file APIs",
            "native_bypass": "NOT prevented (Python-level boundary)",
        },
        "process": {"spawn_denied": True,
                    "native_bypass": "NOT prevented"},
        "network": {"denied_by_default": True,
                    "opt_in": "KEEL_SANDBOX_NETWORK=1"},
        "resources": {
            "timeout": True,
            "output_cap": True,
            "posix_memory_cpu": os.name == "posix",
            "windows_job_objects": False,
        },
        "os_level_isolation": {
            "seccomp_apparmor_containers": False,
            "windows_restricted_token": False,
            "note": "requires an external environment / owner decision",
        },
        "python": sys.version.split()[0],
    }
