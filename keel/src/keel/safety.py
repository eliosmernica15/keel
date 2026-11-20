"""keel.safety — Tier 2, the non-configurable safety envelope.

Spec §5.5 / §6.1: runs AFTER the Tier-1 rule engine, before the executor;
its verdict OVERRIDES a Tier-1 allow. There is deliberately no settings key,
CLI flag, hook, permission mode, or environment variable that can disable
it — `tier2_check` takes no configuration input at all.

What Tier 2 refuses (outline() enumerates it):
1. Catastrophic commands by name (disk wipe, format) — always.
2. Destructive commands whose targets resolve to a protected path.
3. Recursive wildcard deletion of root-like paths.
4. Reads AND writes of secret-bearing paths (.env*, keys, .ssh, .aws, ...).
5. Writes to system directories (%SystemRoot%, /etc, /boot, /usr, ...).
6. An unparseable shell command — an unrecognised command is potentially
   destructive by construction, in every mode ("declining is safe").
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from typing import Any

from .shell_ast import Decline, IRREVERSIBLE, MUTATE_LOCAL, READ, analyze

READ_TOOLS = frozenset({"read_file", "glob", "grep",
                        "ask_user", "list_tasks",
                        "list_dir", "diff_files", "project_summary",
                        "symbol_search", "git_status", "git_diff",
                        "git_log", "git_branch_list", "process_list",
                        "list_skills", "load_skill",
                        "web_fetch", "web_search"})
WRITE_TOOLS = frozenset({"write_file", "edit_file", "delete_file",
                         "move_file", "apply_patch", "git_add",
                         "git_commit", "git_checkout"})
SHELL_TOOLS = frozenset({"run_shell", "run_python", "run_tests",
                         "run_build", "install_deps",
                         "background_shell", "process_kill"})

# catastrophic command names — refused in every mode, no path check needed
_CATASTROPHIC = frozenset({
    "format", "format.com", "diskpart", "mkfs", "fdisk", "sdelete",
    "initialize-disk", "clear-disk", "remove-partition",
    "set-volume",  # destructive volume operations
})

# destructive verbs — refused when the ARGS resolve to a protected path
_DESTRUCTIVE = frozenset({
    "rm", "del", "erase", "rmdir", "rd", "remove-item", "ri",
    "shred", "unlink", "dd",
})

_RECURSIVE_FLAGS = (
    "-r", "-rf", "-fr", "-f", "-recurse", "/s", "/q", "/r",
    "recurse", "recursive",
)

_ROOT_NU = frozenset(
    {"/", "/*", "~", "~/", "c:\\", "c:\\*", "c:\\users", "c:\\windows",
     "c:/windows", "/home", "/users", "%systemdrive%\\", "%systemdrive%\\*"}
)

_SECRET_RE = re.compile(
    r"(^|[\\/_.])"
    r"(\.env(\..+)?|id_rsa|id_dsa|id_ecdsa|id_ed25519|"
    r"[^\\/]+\.(pem|key|p12|pfx|jks|keystore)|credentials(\.json)?)$",
    re.IGNORECASE)

_SYSTEM_RE = re.compile(
    r"^([a-z]:[\\/]windows|[a-z]:[\\/]program ?files|"
    r"/(etc|boot|usr|bin|sbin|lib|lib64|proc|sys)(/|$))",
    re.IGNORECASE)

_RAW_DEVICE_RE = re.compile(
    r"^/dev/(sd[a-z]+\d*|hd\d+|nvme\d+n\d+(p\d+)?|xvd[a-z]+\d*|"
    r"vd[a-z]+\d*|mmcblk\d+(p\d+)?|dm-\d+|raw\d+|disk\d+|rdisk\d+)$",
    re.IGNORECASE)

_REMOTE_STORE_RE = re.compile(
    r"[\\/](\.ssh|\.aws|\.gnupg|\.kube|\.azure|\.config[\\/]gcloud)([\\/]|$)",
    re.IGNORECASE)


def _norm(path: str) -> str:
    p = posixpath.normpath(path.replace("\\", "/"))
    p = re.sub(r"/+", "/", p)
    return p.lower()


def _is_secret(path: str) -> bool:
    p = path.replace("\\", "/")
    return bool(_SECRET_RE.search(p)) or bool(_REMOTE_STORE_RE.search(p))


def _is_system(path: str) -> bool:
    p = path.replace("\\", "/")
    return bool(_SYSTEM_RE.match(p))


def _classify_target(path: str) -> str | None:
    p = _expand(path)
    if _RAW_DEVICE_RE.match(_norm(p)):
        return "raw device"
    if _is_secret(p):
        return "secret-bearing path"
    if _is_system(p):
        return "system path"
    if _REMOTE_STORE_RE.search(p.replace("\\", "/")):
        return "remote-store credentials path"
    return None


@dataclass(frozen=True)
class Check:
    allowed: bool
    reason: str = ""


_ALLOW = Check(True)


def outline() -> list[str]:
    return [
        "refuse catastrophic commands by name (format/diskpart/mkfs/fdisk/"
        "sdelete/initialize-disk/clear-disk/remove-partition/set-volume)",
        "refuse destructive commands targeting secret-bearing paths (.env*, "
        "keys, .ssh/.aws/.gnupg/.kube/.azure/gcloud)",
        "refuse destructive commands targeting system paths "
        "(%SystemRoot% / Program Files / /etc / /boot / /usr / ...)",
        "refuse recursive wildcard deletion of root-like paths ('/', 'C:\\', "
        "'~', '%SystemDrive%\\')",
        "refuse reads AND writes of secret-bearing paths (.env*, *.pem, *.key, "
        "id_*, .ssh/*, .aws/* ...)",
        "refuse dd with of=<protected>",
        "refuse writes via redirection to a protected path",
        "refuse an unparseable shell command (refuses rather than guesses)",
    ]


def _path_arg(token: str) -> str | None:
    if token.startswith("-"):
        return None                     # flags are not paths
    if token.startswith("/") and len(token) <= 3:
        return None                     # short /s-style flags (unix)
    token = token.strip()
    if not token or token.lower() in ("&1", "2>&1", ">>", ">", "<"):
        return None
    return token


def tier2_check(tool_name: str, tool_input: dict[str, Any], tool_registry=None) -> Check:
    _read_tools = (tool_registry.read_tools() if tool_registry is not None
                   else READ_TOOLS)
    _write_tools = (tool_registry.write_tools() if tool_registry is not None
                    else WRITE_TOOLS)
    _shell_tools = (tool_registry.shell_tools() if tool_registry is not None
                    else SHELL_TOOLS)
    if tool_name in _read_tools:
        path = str(tool_input.get("path") or tool_input.get("pattern") or "")
        if path and _classify_target(_expand(path)) == "secret-bearing path":
            return Check(False, f"read of a secret-bearing path is refused "
                                f"({path})")
        return _ALLOW

    if tool_name in _write_tools:
        path = str(tool_input.get("path") or "")
        kind = _classify_target(_expand(path)) if path else None
        if kind:
            return Check(False, f"write to a {kind} is refused ({path})")
        return _ALLOW

    if tool_name in _shell_tools:
        command = str(tool_input.get("command", ""))
        shell = str(tool_input.get("shell", "posix"))
        try:
            analysis = analyze(command, shell)
        except Decline as exc:
            return Check(False, f"unparseable command: {exc}")
        for command_ref in analysis.commands:
            canonical = command_ref.canonical.lower()
            stem = canonical.split(".", 1)[0]
            args = command_ref.args
            if canonical in _CATASTROPHIC or stem in _CATASTROPHIC:
                return Check(False,
                             f"catastrophic command refused: {canonical}")
            if canonical == "<redirection>":
                for arg in args:
                    kind = _classify_target(_expand(arg))
                    if kind:
                        return Check(False, f"redirect into a {kind} refused "
                                            f"({arg})")
                continue
            if canonical == "dd":
                for arg in args:
                    m = re.match(r"^of=(.+)$", arg, re.IGNORECASE)
                    if m:
                        kind = _classify_target(_expand(m.group(1)))
                        if kind:
                            return Check(False,
                                        f"dd output into a {kind} refused")
                continue
            if canonical in _DESTRUCTIVE:
                if _has_root_wildcard(args):
                    return Check(False,
                                 "recursive root/wildcard deletion refused")
                for arg in args:
                    pa = _path_arg(arg)   # flags return None here
                    if pa is None:
                        continue
                    kind = _classify_target(_expand(pa))
                    if kind:
                        return Check(False,
                                     f"destructive command into a {kind} "
                                     f"refused ({pa})")
                continue
        return _ALLOW

    return _ALLOW  # non-IO tools: no Tier-2 target to check


def _has_root_wildcard(args: tuple[str, ...]) -> bool:
    recursive = any(_is_recursive(a) for a in args)
    wild_target = any(_norm(a) in _ROOT_NU for a in args)
    return recursive and wild_target


def _is_recursive(arg: str) -> bool:
    low = arg.lower()
    if low in _RECURSIVE_FLAGS:
        return True
    if low.startswith("-r"):
        return True
    if "recurse" in low:
        return True
    return False


def _expand(path: str) -> str:
    p = path.strip().strip('"').strip("'")
    if p.startswith(("~", "~/")):
        import os
        p = os.path.expanduser(p)
    # %SystemDrive%/%SystemRoot% expansion for the common case
    for var, target in (("%SystemDrive%", "C:"), ("%SystemRoot%", "C:/Windows"),
                        ("$env:SystemDrive", "C:"), ("$env:SystemRoot", "C:/Windows")):
        if p.lower().startswith(var.lower()):
            p = target + p[len(var):]
    return p
