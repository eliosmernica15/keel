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

_BOOTSTRAP = r'''"""Keel sandbox bootstrap — installs a sealed, immutable audit hook.

Policy state lives only in the hook's closure. No module-level policy names
survive hook installation, so untrusted code cannot reach them through
``__main__``, ``sys.modules`` or frame/global introspection. Python audit hooks
cannot be removed once installed; ``sys.addaudithook`` itself is denied.
"""
import os as _os
import sys as _sys


def _make_guard(_root, _libs, _network_allowed, _os_mod):
    _root_real = _os_mod.path.realpath(_root)
    _libs_real = tuple(_os_mod.path.realpath(p) for p in _libs if p)
    _sep = _os_mod.sep
    _mutating = frozenset({
        "os.mkdir", "os.makedirs", "os.remove", "os.rmdir", "os.rename",
        "os.replace", "os.symlink", "os.link", "os.truncate", "os.chmod",
        "os.chown", "os.utime", "os.putenv", "os.unsetenv", "os.setuid",
        "os.setgid", "os.kill", "os.fork", "os.forkpty", "os.exec",
        "os.spawn", "os.posix_spawn", "subprocess.Popen",
    })
    _MUTATING_PATH_ARGS = {
        "os.mkdir": (0,), "os.makedirs": (0,), "os.remove": (0,),
        "os.rmdir": (0,), "os.rename": (0, 1), "os.replace": (0, 1),
        "os.symlink": (0, 1), "os.link": (0, 1), "os.truncate": (0,),
        "os.chmod": (0,), "os.chown": (0,), "os.utime": (0,),
    }
    _process = frozenset({
        "os.fork", "os.forkpty", "os.exec", "os.spawn", "os.posix_spawn",
        "os.system", "os.kill", "subprocess.Popen",
    })
    _native = frozenset({
        "ctypes.dlopen", "ctypes.dlsym", "ctypes.get_func", "sys.addaudithook",
    })

    def _within(path, bases):
        try:
            real = _os_mod.path.realpath(_os_mod.fspath(path))
        except (TypeError, ValueError, OSError):
            return False
        return any(real == base or real.startswith(base + _sep)
                   for base in bases)

    def _deny(event, args):
        if event == "open":
            path = args[0] if args else None
            if isinstance(path, int):
                raise PermissionError("sandbox: raw fd access denied")
            mode = args[1] if len(args) > 1 else "r"
            flags = args[2] if len(args) > 2 else None
            write = isinstance(mode, str) and any(c in mode for c in "wax+")
            if flags is not None:
                flags = int(flags)
                write = write or bool(flags & (
                    _os_mod.O_WRONLY | _os_mod.O_RDWR | _os_mod.O_CREAT |
                    _os_mod.O_APPEND | _os_mod.O_TRUNC))
            if not _within(path, (_root_real,) + _libs_real):
                raise PermissionError(
                    "sandbox: path outside workspace/library denied: " + str(path))
            if write and not _within(path, (_root_real,)):
                raise PermissionError(
                    "sandbox: write outside workspace denied: " + str(path))
            return
        if event in _native or event in _process:
            raise PermissionError("sandbox: event denied: " + event)
        if event in _mutating:
            # Multi-path mutations (rename/replace/link/symlink) must validate
            # EVERY path and reject raw dir_fd arguments — checking only
            # args[0] allowed writing outside the workspace via the target.
            indices = _MUTATING_PATH_ARGS.get(event, (0,))
            for index in indices:
                if index >= len(args):
                    continue
                value = args[index]
                if isinstance(value, int):
                    raise PermissionError(
                        "sandbox: directory-fd mutation denied: " + event)
                if isinstance(value, (str, bytes, _os_mod.PathLike)) and \
                        not _within(value, (_root_real,)):
                    raise PermissionError(
                        "sandbox: mutating path outside workspace denied: "
                        + str(value))
            return
        if event.startswith(("socket.", "urllib.", "http.client.",
                             "smtplib.", "ftplib.", "asyncio.")):
            if not _network_allowed:
                raise PermissionError("sandbox: network access denied: " + event)
            return

    return _deny


_root = _os.environ.get("KEEL_SANDBOX_ROOT", _os.getcwd())
_libs = tuple(_sys.path)
_network = _os.environ.get("KEEL_SANDBOX_NETWORK") == "1"
_code_path = _os.path.join(_root, "__USER_CODE_NAME__")
_source = None
with open(_code_path, "rb") as _fh:
    _source = _fh.read()

# Install the sealed hook, then remove every installation-time name from the
# module namespace before user code runs. The hook keeps what it needs in its
# closure; __main__ becomes an empty namespace to untrusted code.
_sys.addaudithook(_make_guard(_root, _libs, _network, _os))
for _name in ("_root", "_libs", "_network", "_fh", "_make_guard",
              "_os", "_sys", "_name"):
    globals().pop(_name, None)

exec(compile(_source, "<sandbox-user-code>", "exec"),
     {"__name__": "__main__", "__file__": _code_path})
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


def _native_support() -> dict:
    try:
        from .native_isolation import platform_support

        return platform_support()
    except Exception as exc:
        return {"available": False, "reason": type(exc).__name__}


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
        "policy_state": {
            "sealed_in_closure": True,
            "main_namespace_cleared": True,
            "note": "__main__/sys.modules introspection cannot rewrite the hook policy",
        },
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
        "native_process_limits": _native_support(),
        "python": sys.version.split()[0],
    }
