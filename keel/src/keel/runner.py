"""keel.runner — print-mode runner (Phase 1).

Validation happens BEFORE any model construction: an invalid invocation
exits 1 and the model records zero requests.
"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any

from pathlib import Path

from . import events as ev, settings
from .fakes import ScriptedModel, SeededRng, VirtualClock
from .hooks import parse_hooks
from .mcp import McpManager, is_approved, parse_servers
from .permissions import (KNOWN_MODES, _MODE_ALIASES, evaluate_noninteractive,
                          normalize_mode)
from .providers import registry as provider_registry
from .providers.base import ProviderError
from .providers.model_client import ProviderModelClient
from .session import ALL_TOOLS, Session, SessionConfig
from .toolresult import Persist

OUTPUT_FORMATS = ("text", "json", "stream-json")
_FILE_CHANGE_TOOLS = frozenset({
    "write_file", "edit_file", "apply_patch", "delete_file", "move_file",
    "copy_file", "make_dir",
})
DIAG_PREFIX = "[keel"


class CliValidationError(Exception):
    pass


@dataclass
class LaunchPlan:
    prompt: str
    output_format: str = "text"
    bare: bool = True
    session_id: str = ""
    permission_mode: str = "default"
    model: str = "keel-fake-1"
    max_turns: int = 10
    seed: int = 0
    state_root: str = ""
    fake_script_path: str | None = None
    dangerous_opt_in: bool = False
    rules: tuple[list[str], list[str], list[str]] = ((), (), ())
    provider: str = "auto"
    model_override: str | None = None
    local_command: str | None = None


def diagnostic(event: str, payload: dict) -> None:
    sys.stderr.write(f"[keel:{event}] {json.dumps(payload, separators=(',', ':'))}\n")


def parse_argv(argv: list[str]) -> LaunchPlan:
    prompt = None
    output_format = "text"
    bare = False
    session_id = ""
    permission_mode = "default"
    model = "keel-fake-1"
    model_explicit = False
    max_turns = 10
    seed = 0
    state_root = ""
    fake_script = None
    dangerous = False
    deny: list[str] = []
    ask: list[str] = []
    allow: list[str] = []
    provider = "auto"

    i = 0
    positional: list[str] = []
    while i < len(argv):
        arg = argv[i]

        def take_value(flag: str) -> str:
            nonlocal i
            if i + 1 >= len(argv):
                raise CliValidationError(f"{flag} requires a value")
            i += 1
            return argv[i]

        if arg == "-p" or arg == "--print":
            prompt = take_value(arg)
        elif arg == "--output-format":
            output_format = take_value(arg)
        elif arg == "--bare":
            bare = True
        elif arg == "--session-id":
            session_id = take_value(arg)
        elif arg == "--permission-mode":
            permission_mode = take_value(arg)
        elif arg == "--model":
            model = take_value(arg)
            model_explicit = True
        elif arg == "--max-turns":
            try:
                max_turns = int(take_value(arg))
            except ValueError:
                raise CliValidationError("--max-turns must be an integer")
        elif arg == "--seed":
            try:
                seed = int(take_value(arg))
            except ValueError:
                raise CliValidationError("--seed must be an integer")
        elif arg == "--state-root":
            state_root = take_value(arg)
        elif arg == "--fake-script":
            fake_script = take_value(arg)
        elif arg == "--i-accept-the-risk":
            dangerous = True
        elif arg == "--deny-rule":
            deny.append(take_value(arg))
        elif arg == "--ask-rule":
            ask.append(take_value(arg))
        elif arg == "--allow-rule":
            allow.append(take_value(arg))
        elif arg == "--provider":
            provider = take_value(arg).lower()
        elif arg.startswith("-"):
            raise CliValidationError(f"unknown option: {arg}")
        else:
            positional.append(arg)
        i += 1

    errors: list[str] = []
    if prompt is None:
        if positional:
            prompt = " ".join(positional)
        else:
            errors.append("a prompt is required (-p/--print or a positional argument)")
    if output_format not in OUTPUT_FORMATS:
        errors.append(f"--output-format must be one of {', '.join(OUTPUT_FORMATS)}; "
                      f"got {output_format!r}")
    if session_id:
        try:
            uuid.UUID(session_id)
        except ValueError:
            errors.append(f"--session-id is not a well-formed UUID: {session_id!r}")
    try:
        permission_mode = normalize_mode(permission_mode)
    except Exception as exc:
        errors.append(str(exc))
    if max_turns < 1:
        errors.append("--max-turns must be >= 1")
    if provider not in ("auto", "openrouter", "nvidia", "google",
                        "anthropic", "openai-compatible"):
        errors.append(f"--provider must be one of auto|openrouter|nvidia|"
                      f"google|anthropic|openai-compatible; got {provider!r}")
    if permission_mode == "bypassPermissions" and not dangerous:
        errors.append("--permission-mode bypassPermissions requires "
                      "--i-accept-the-risk")
    if permission_mode == "bypassPermissions" and hasattr(os, "geteuid"):
        try:
            if os.geteuid() == 0:
                errors.append("bypassPermissions is refused for uid 0 "
                              "(dangerous-mode interlock)")
        except AttributeError:
            pass
    if errors:
        raise CliValidationError("; ".join(errors))

    return LaunchPlan(prompt=prompt or "", output_format=output_format, bare=bare,
                      session_id=session_id, permission_mode=permission_mode,
                      model=model, max_turns=max_turns, seed=seed,
                      state_root=state_root, fake_script_path=fake_script,
                      dangerous_opt_in=dangerous,
                      rules=(deny, ask, allow),
                      provider=provider,
                      model_override=model if model_explicit else None)


def _load_fake_script(path: str | None) -> list[list[dict]]:
    if path is None:
        return [[{"type": "text",
                  "text": "Keel scaffold: no model provider is wired yet. "
                          "This run used the built-in scripted fake."}]]
    with open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    script = doc.get("script", doc if isinstance(doc, list) else [])
    return [list(turn) for turn in script]


class RealTools:
    """Minimal real tool executor for the print-mode runner.

    All calls pass the Tier-1 permission gate before dispatch, so nothing
    here runs without a decision. Output is capped; writes go to disk
    verbatim.
    """

    CAP_BYTES = 5 * 1024 * 1024

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def invoke(self, name: str, tool_input: dict):
        self.calls.append((name, tool_input))
        dispatched = self._dispatch_extended(name, tool_input or {})
        if dispatched is not None:
            return dispatched
        if name == "read_file":
            path = tool_input["path"]
            with open(path, "rb") as fh:
                data = fh.read(self.CAP_BYTES + 1)
            if len(data) > self.CAP_BYTES or b"\x00" in data:
                raise ValueError("file too large or binary; refusing to read")
            text = data.decode("utf-8")  # strict: raises on invalid bytes
            payload = {"type": "text", "file": {"filePath": path,
                                                "content": text,
                                                "numLines": text.count("\n")}}
            return text, payload
        if name == "write_file":
            path = tool_input["path"]
            content = tool_input["content"]
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content)
            self._fire_file_changed("write_file", tool_input)
            return f"wrote {path} ({len(content)} chars)", \
                {"type": "text", "file": {"filePath": path, "content": content}}
        if name == "edit_file":
            path = tool_input["path"]
            old = tool_input["old_string"]
            new = tool_input["new_string"]
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
            count = text.count(old)
            if count != 1:
                raise ValueError(f"old_string matched {count} times; expected exactly 1")
            updated = text.replace(old, new, 1)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(updated)
            self._fire_file_changed("edit_file", tool_input)
            return f"edited {path}", {"type": "text",
                                      "file": {"filePath": path, "content": updated,
                                               "oldContent": text,
                                               "newContent": updated}}
        if name == "glob":
            import glob as globmod
            import os
            import fnmatch
            matches = globmod.glob(tool_input["pattern"], recursive=True)[:1000]
            # Apply ignore rules
            ignore_patterns = {".git", "node_modules", "__pycache__", ".venv"}
            filtered = []
            for m in matches:
                basename = os.path.basename(m)
                if any(fnmatch.fnmatch(basename, pat) or fnmatch.fnmatch(m, pat) for pat in ignore_patterns):
                    continue
                filtered.append(m)
            matches = filtered[:1000]
            return "\n".join(matches), {"filenames": matches, "numFiles": len(matches),
                                        "truncated": False}
        if name == "grep":
            import glob as globmod
            import os
            import re
            pattern = re.compile(tool_input["pattern"])
            root = tool_input.get("root", ".")
            hits: list[str] = []
            for base, _, files in os.walk(root):
                for fname in files:
                    if len(hits) >= 1000:
                        break
                    fpath = os.path.join(base, fname)
                    # Apply ignore rules
                    ignore_patterns = {".git", "node_modules", "__pycache__", ".venv"}
                    if any(fnmatch.fnmatch(fname, pat) or fnmatch.fnmatch(fpath, pat) for pat in ignore_patterns):
                        continue
                    try:
                        with open(fpath, "r", encoding="utf-8",
                                  errors="strict") as fh:
                            for lineno, line in enumerate(fh, 1):
                                if pattern.search(line):
                                    hits.append(f"{fpath}:{lineno}:{line.rstrip()}")
                    except (UnicodeDecodeError, OSError):
                        continue
            return "\n".join(hits), {"filenames": hits, "numFiles": len(hits),
                                     "truncated": len(hits) >= 1000}
        if name == "run_shell":
            import subprocess
            shell = tool_input.get("shell", "posix")
            command = tool_input["command"]
            if shell == "powershell":
                argv = ["powershell", "-NoProfile", "-NonInteractive",
                        "-Command", command]
            elif shell == "cmd":
                argv = ["cmd.exe", "/d", "/c", command]
            else:
                argv = ["sh", "-c", command]
            try:
                proc = subprocess.run(argv, capture_output=True, timeout=120,
                                      check=False)
                stdout = proc.stdout.decode("utf-8", errors="replace")
                stderr = proc.stderr.decode("utf-8", errors="replace")
                interrupted = False
            except subprocess.TimeoutExpired:
                stdout, stderr, interrupted = "", "command timed out after 120s", True
            output = (stdout + ("\n" if stdout and stderr else "") + stderr)
            return output, {"stdout": stdout, "stderr": stderr,
                            "interrupted": interrupted,
                            "isImage": False, "noOutputExpected": False}
        raise KeyError(f"unknown real tool {name!r}")

    _BG_PROCESSES: dict = {}

    def _fire_file_changed(self, operation: str, tool_input: dict) -> None:
        try:
            from . import settings_store
            from .hooks import fire, parse_hooks

            hooks = parse_hooks(settings_store.load().get("hooks", {}))
            if not hooks:
                return
            path = tool_input.get("path") or tool_input.get("src") or ""
            fire(hooks, "FileChanged", {
                "operation": operation,
                "path": str(path),
            })
        except Exception:
            pass  # hooks are advisory; file operations must remain reliable

    def _dispatch_extended(self, name: str, tool_input: dict):
        # Tier-2 safety check before any extended tool execution
        from .safety import tier2_check
        check = tier2_check(name, tool_input, tool_registry=None)
        if not check.allowed:
            raise ValueError(f"tier-2 refused: {check.reason}")
        handlers = {
            "delete_file": self._delete_file,
            "move_file": self._move_file,
            "list_dir": self._list_dir,
            "apply_patch": self._apply_patch,
            "diff_files": self._diff_files,
            "run_python": self._run_python,
            "run_tests": self._run_tests,
            "run_build": self._run_build,
            "install_deps": self._install_deps,
            "background_shell": self._background_shell,
            "process_list": self._process_list,
            "process_output": self._process_output,
            "process_wait": self._process_wait,
            "process_kill": self._process_kill,
            "git_status": self._git_status,
            "git_diff": self._git_diff,
            "git_log": self._git_log,
            "git_branch_list": self._git_branch_list,
            "git_add": self._git_add,
            "git_commit": self._git_commit,
            "git_checkout": self._git_checkout,
            "project_summary": self._project_summary,
            "symbol_search": self._symbol_search,
            "list_skills": self._list_skills,
            "load_skill": self._load_skill,
            "run_workflow": self._run_workflow,
            "web_fetch": self._web_fetch,
            "web_search": self._web_search,
            "copy_file": self._copy_file,
            "make_dir": self._make_dir,
            "file_info": self._file_info,
            "search_files": self._search_files,
        }
        handler = handlers.get(name)
        if handler is None:
            return None
        result = handler(tool_input or {})
        if name in _FILE_CHANGE_TOOLS:
            self._fire_file_changed(name, tool_input or {})
        return result

    def _safe_path(self, raw: str) -> str:
        import os
        from .safety import _classify_target, _expand
        path = os.path.expanduser(str(raw))
        kind = _classify_target(_expand(path))
        if kind:
            raise ValueError(f"path refused ({kind}): {raw}")
        return path

    def _delete_file(self, tool_input: dict):
        import os
        path = self._safe_path(tool_input["path"])
        if not os.path.isfile(path):
            raise FileNotFoundError(f"not a file: {path}")
        os.remove(path)
        return f"deleted {path}", {"type": "text", "file": {"filePath": path}}

    def _move_file(self, tool_input: dict):
        import os, shutil
        src = self._safe_path(tool_input["src"])
        dst = self._safe_path(tool_input["dst"])
        if not os.path.exists(src):
            raise FileNotFoundError(f"source not found: {src}")
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        if os.path.exists(dst):
            raise FileExistsError(f"destination exists: {dst}")
        shutil.move(src, dst)
        return f"moved {src} -> {dst}", {"type": "text", "from": src, "to": dst}

    def _list_dir(self, tool_input: dict):
        import fnmatch
        import os
        path = self._safe_path(tool_input.get("path", "."))
        recursive = bool(tool_input.get("recursive", False))
        max_entries = int(tool_input.get("max_entries", 500))
        ignore_patterns = {".git", "node_modules", "__pycache__", ".venv"}
        entries = []

        def _ignored(name: str, full: str) -> bool:
            return any(fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(full, pat)
                       for pat in ignore_patterns)

        if recursive:
            for base, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if not _ignored(d, os.path.join(base, d))]
                for name in dirs + files:
                    full = os.path.join(base, name)
                    if _ignored(name, full):
                        continue
                    entries.append(full)
                    if len(entries) >= max_entries:
                        break
                if len(entries) >= max_entries:
                    break
        else:
            for name in sorted(os.listdir(path)):
                full = os.path.join(path, name)
                if _ignored(name, full):
                    continue
                entries.append(full)
                if len(entries) >= max_entries:
                    break
        return "\n".join(entries), {"entries": entries, "numEntries": len(entries), "truncated": len(entries) >= max_entries}

    def _apply_patch(self, tool_input: dict):
        path = self._safe_path(tool_input["path"])
        old = tool_input["old_string"]
        new = tool_input["new_string"]
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        count = text.count(old)
        if count != 1:
            raise ValueError(f"old_string matched {count} times; expected exactly 1")
        updated = text.replace(old, new, 1)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(updated)
        return f"patched {path}", {"type": "text", "file": {"filePath": path, "content": updated, "oldContent": text, "newContent": updated}}

    def _diff_files(self, tool_input: dict):
        import difflib
        a = self._safe_path(tool_input["a"])
        b = self._safe_path(tool_input["b"])
        with open(a, "r", encoding="utf-8", errors="replace") as fh:
            la = fh.readlines()
        with open(b, "r", encoding="utf-8", errors="replace") as fh:
            lb = fh.readlines()
        diff = list(difflib.unified_diff(la, lb, fromfile=a, tofile=b))
        text = "".join(diff)
        return text, {"diff": text, "numLines": len(diff)}

    def _run_python(self, tool_input: dict):
        import subprocess, sys
        code = tool_input["code"]
        timeout = int(tool_input.get("timeout", 120))
        try:
            proc = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=timeout, check=False)
            stdout = proc.stdout.decode("utf-8", errors="replace")
            stderr = proc.stderr.decode("utf-8", errors="replace")
            interrupted = False
        except subprocess.TimeoutExpired:
            stdout, stderr, interrupted = "", "python timed out", True
        output = stdout + ("\n" if stdout and stderr else "") + stderr
        return output, {"stdout": stdout, "stderr": stderr, "interrupted": interrupted, "isImage": False, "noOutputExpected": False}

    def _run_tests(self, tool_input: dict):
        import subprocess, os
        command = tool_input.get("command") or "python -m pytest -q"
        cwd = tool_input.get("cwd")
        timeout = int(tool_input.get("timeout", 300))
        if os.name == "nt":
            argv = ["cmd.exe", "/d", "/c", command]
        else:
            argv = ["sh", "-c", command]
        try:
            proc = subprocess.run(argv, capture_output=True, timeout=timeout, check=False, cwd=cwd)
            stdout = proc.stdout.decode("utf-8", errors="replace")
            stderr = proc.stderr.decode("utf-8", errors="replace")
            interrupted = False
        except subprocess.TimeoutExpired:
            stdout, stderr, interrupted = "", "tests timed out", True
        output = stdout + ("\n" if stdout and stderr else "") + stderr
        return output, {"stdout": stdout, "stderr": stderr, "interrupted": interrupted, "exit_code": getattr(proc, "returncode", None)}

    def _run_build(self, tool_input: dict):
        return self._run_tests({"command": tool_input.get("command", ""), "cwd": tool_input.get("cwd"), "timeout": tool_input.get("timeout", 600)})

    def _install_deps(self, tool_input: dict):
        import subprocess, sys
        manager = str(tool_input.get("manager", "pip")).lower()
        packages = tool_input.get("packages") or []
        if not isinstance(packages, list) or not packages:
            raise ValueError("packages must be a non-empty list")
        for p in packages:
            if not isinstance(p, str) or not p.strip():
                raise ValueError("package names must be non-empty strings")
        if manager == "pip":
            argv = [sys.executable, "-m", "pip", "install", *packages]
        elif manager == "npm":
            argv = ["npm", "install", *packages]
        else:
            raise ValueError(f"unsupported manager: {manager}")
        proc = subprocess.run(argv, capture_output=True, timeout=int(tool_input.get("timeout", 300)), check=False)
        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")
        output = stdout + ("\n" if stdout and stderr else "") + stderr
        return output, {"stdout": stdout, "stderr": stderr, "exit_code": proc.returncode}

    def _background_shell(self, tool_input: dict):
        import subprocess, uuid
        command = tool_input["command"]
        shell = tool_input.get("shell", "posix")
        if shell == "powershell":
            argv = ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
        elif shell == "cmd":
            argv = ["cmd.exe", "/d", "/c", command]
        else:
            argv = ["sh", "-c", command]
        import os as _os
        if _os.name == "nt":
            proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        else:
            proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, start_new_session=True)
        pid = f"bg-{uuid.uuid4().hex[:8]}"
        self._BG_PROCESSES[pid] = proc
        return f"started {pid} (os pid {proc.pid})", {"process_id": pid, "pid": proc.pid, "command": command}

    def _process_list(self, tool_input: dict):
        out = []
        for pid, proc in list(self._BG_PROCESSES.items()):
            status = "running" if proc.poll() is None else f"exited({proc.returncode})"
            out.append(f"{pid}: {status}")
        return "\n".join(out), {"processes": [{"id": pid, "status": ("running" if p.poll() is None else f"exited({p.returncode})")} for pid, p in self._BG_PROCESSES.items()]}

    def _process_kill(self, tool_input: dict):
        pid = tool_input["process_id"]
        proc = self._BG_PROCESSES.get(pid)
        if proc is None:
            raise KeyError(f"unknown process: {pid}")
        _terminate_process_tree(proc)
        del self._BG_PROCESSES[pid]
        return f"killed {pid}", {"process_id": pid}

    def _git(self, args, cwd=None):
        import subprocess
        proc = subprocess.run(["git", *args], capture_output=True, timeout=120, check=False, cwd=cwd)
        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")
        output = stdout + ("\n" if stdout and stderr else "") + stderr
        if proc.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {output}")
        return output, {"stdout": stdout, "stderr": stderr, "exit_code": proc.returncode}

    def _git_status(self, tool_input: dict):
        return self._git(["status", "--short", "--branch"], tool_input.get("cwd"))

    def _git_diff(self, tool_input: dict):
        args = ["diff"]
        if tool_input.get("staged"):
            args.append("--cached")
        if tool_input.get("path"):
            args += ["--", str(tool_input["path"])]
        return self._git(args, tool_input.get("cwd"))

    def _git_log(self, tool_input: dict):
        n = int(tool_input.get("limit", 20))
        return self._git(["log", f"-{n}", "--oneline", "--decorate"], tool_input.get("cwd"))

    def _git_branch_list(self, tool_input: dict):
        return self._git(["branch", "-a"], tool_input.get("cwd"))

    def _git_add(self, tool_input: dict):
        paths = tool_input.get("paths", ["."])
        if isinstance(paths, str):
            paths = [paths]
        return self._git(["add", *paths], tool_input.get("cwd"))

    def _git_commit(self, tool_input: dict):
        return self._git(["commit", "-m", tool_input["message"]], tool_input.get("cwd"))

    def _git_checkout(self, tool_input: dict):
        return self._git(["checkout", tool_input["ref"]], tool_input.get("cwd"))

    def _project_summary(self, tool_input: dict):
        import os
        root = self._safe_path(tool_input.get("root", "."))
        counts = {}
        total = 0
        files = 0
        for base, dirs, fs in os.walk(root):
            # Load ignore rules from .keelignore or .gitignore
            ignore_patterns = set([".git", "node_modules", "__pycache__", ".venv"])
            for ignore_name in (".keelignore", ".gitignore"):
                ignore_path = os.path.join(root, ignore_name)
                if os.path.isfile(ignore_path):
                    try:
                        with open(ignore_path, "r", encoding="utf-8") as fh:
                            for line in fh:
                                line = line.strip()
                                if line and not line.startswith("#"):
                                    ignore_patterns.add(line.rstrip("/"))
                    except OSError:
                        pass
            dirs[:] = [d for d in dirs if d not in ignore_patterns and not any(
                __import__("fnmatch").fnmatch(d, pat) for pat in ignore_patterns)]

            for f in fs:
                files += 1
                ext = os.path.splitext(f)[1].lower() or "(none)"
                counts[ext] = counts.get(ext, 0) + 1
                try:
                    total += os.path.getsize(os.path.join(base, f))
                except OSError:
                    pass
        lines = [f"root: {root}", f"files: {files}", f"total_bytes: {total}", "extensions:"]
        for ext, n in sorted(counts.items(), key=lambda kv: -kv[1])[:25]:
            lines.append(f"  {ext}: {n}")
        return "\n".join(lines), {"files": files, "total_bytes": total, "extensions": counts}

    def _symbol_search(self, tool_input: dict):
        import os, re, fnmatch
        pattern = re.compile(tool_input["pattern"])
        root = self._safe_path(tool_input.get("root", "."))
        glob_pat = tool_input.get("glob")
        hits = []
        for base, _, files in os.walk(root):
            for fname in files:
                if glob_pat and not fnmatch.fnmatch(fname, glob_pat):
                    continue
                fpath = os.path.join(base, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="strict") as fh:
                        for lineno, line in enumerate(fh, 1):
                            if pattern.search(line):
                                hits.append(f"{fpath}:{lineno}:{line.rstrip()}")
                                if len(hits) >= 1000:
                                    break
                except (UnicodeDecodeError, OSError):
                    continue
            if len(hits) >= 1000:
                break
        return "\n".join(hits), {"hits": hits, "numHits": len(hits), "truncated": len(hits) >= 1000}

    def _list_skills(self, tool_input: dict):
        from pathlib import Path
        import json
        from . import skills_manager
        project_root = tool_input.get("project_root")
        managed = skills_manager.list_managed(Path(project_root) if project_root else None)
        return json.dumps(managed, indent=2, default=str), {"skills": managed, "count": len(managed)}

    def _load_skill(self, tool_input: dict):
        from pathlib import Path
        name = tool_input["name"]
        project_root = tool_input.get("project_root")
        for skill in __import__("keel.skills", fromlist=["discover"]).discover(Path(project_root) if project_root else None):
            if skill.name == name:
                return skill.body, {"name": skill.name, "description": skill.description, "path": str(skill.path)}
        raise KeyError(f"skill not found: {name}")

    def _run_workflow(self, tool_input: dict):
        from pathlib import Path
        from . import workflows
        name = tool_input["name"]
        project_root = Path(tool_input.get("project_root") or ".")
        wf = workflows.find(name, project_root)
        if wf is None:
            raise KeyError(f"workflow not found: {name}")

        def _exec_tool(tool_name, tool_input):
            # Print-mode workflows are non-interactive. Every inner step must
            # pass the same Tier-1 gate the desktop workflow API uses; Tier-2
            # remains enforced inside self.invoke.
            decision = evaluate_noninteractive(
                tool_name, tool_input, project_root=project_root)
            if decision.decision != "allow":
                raise PermissionError(f"{tool_name}: {decision.reason}")
            return self.invoke(tool_name, tool_input)

        results = workflows.execute_workflow(wf, tool_executor=_exec_tool,
                                             project_root=project_root)
        return str(results), {"workflow": name, "results": results}

    def _web_fetch(self, tool_input: dict):
        import urllib.request, urllib.parse, html, re
        url = tool_input["url"]
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("url must be http or https")
        host = parsed.hostname or ""
        # Resolve hostname and check all resulting IPs
        import socket
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            raise ValueError(f"cannot resolve hostname: {host}")
        for info in infos:
            addr = info[4][0]
            # Check for private/loopback/link-local/reserved
            import ipaddress
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                raise ValueError(f"refusing to fetch private/internal address: {addr}")
            # Block cloud metadata endpoints
            if str(ip) in ("169.254.169.254", "fd00:ec2::254"):
                raise ValueError(f"refusing to fetch cloud metadata endpoint: {addr}")
        # Also check hostname directly
        if host.lower() in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            raise ValueError(f"refusing to fetch local address: {host}")
        timeout = int(tool_input.get("timeout", 30))
        max_bytes = int(tool_input.get("max_bytes", 2_000_000))
        req = urllib.request.Request(url, headers={"User-Agent": "Keel/1.0", "Accept": "text/html,application/json,text/plain"})
        import ssl
        try:
            import certifi
            _ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            _ctx = ssl.create_default_context()
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ctx), urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as resp:
            data = resp.read(max_bytes + 1)
            content_type = resp.headers.get("Content-Type", "")
            final_url = resp.geturl()
        truncated = len(data) > max_bytes
        data = data[:max_bytes]
        text = data.decode("utf-8", errors="replace")
        if "html" in content_type.lower():
            # strip tags
            text = re.sub(r"<script.*?</script>", " ", text, flags=re.S | re.I)
            text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
            text = re.sub(r"<[^>]+>", " ", text)
            text = html.unescape(text)
            text = re.sub(r"\s+", " ", text).strip()
        return text[:20000], {"url": final_url, "content_type": content_type, "bytes": len(data), "truncated": truncated}

    def _web_search(self, tool_input: dict):
        import urllib.parse, urllib.request, re, html
        query = tool_input["query"]
        count = int(tool_input.get("count", 8))
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers={"User-Agent": "Keel/1.0"})
        import ssl
        try:
            import certifi
            _ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            _ctx = ssl.create_default_context()
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ctx), urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=30) as resp:
            raw = resp.read(2_000_000).decode("utf-8", errors="replace")
        results = []
        for m in re.finditer(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', raw, re.S | re.I):
            href = html.unescape(m.group(1))
            title = re.sub(r"<[^>]+>", "", html.unescape(m.group(2))).strip()
            # DuckDuckGo wraps links; extract uddg param
            parsed = urllib.parse.urlparse(href)
            qs = urllib.parse.parse_qs(parsed.query)
            if "uddg" in qs:
                href = qs["uddg"][0]
            results.append({"title": title, "url": href})
            if len(results) >= count:
                break
        return "\n".join(f"{r['title']} - {r['url']}" for r in results), {"results": results, "count": len(results)}

    def _copy_file(self, tool_input: dict):
        import os, shutil
        src = self._safe_path(tool_input["src"])
        dst = self._safe_path(tool_input["dst"])
        if not os.path.exists(src):
            raise FileNotFoundError(f"source not found: {src}")
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        if os.path.isdir(src):
            if os.path.exists(dst):
                raise FileExistsError(f"destination exists: {dst}")
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        return f"copied {src} -> {dst}", {"from": src, "to": dst}

    def _make_dir(self, tool_input: dict):
        import os
        path = self._safe_path(tool_input["path"])
        os.makedirs(path, exist_ok=True)
        return f"created {path}", {"path": path}

    def _file_info(self, tool_input: dict):
        import os, json
        path = self._safe_path(tool_input["path"])
        st = os.stat(path)
        return json.dumps({"path": path, "size": st.st_size, "mtime": st.st_mtime, "is_dir": os.path.isdir(path), "is_file": os.path.isfile(path)}, indent=2), {"path": path, "size": st.st_size}

    def _search_files(self, tool_input: dict):
        import os, fnmatch
        root = self._safe_path(tool_input.get("root", "."))
        pattern = tool_input.get("pattern", "*")
        content = tool_input.get("content")
        hits = []
        for base, dirs, files in os.walk(root):
            # Load ignore rules from .keelignore or .gitignore
            ignore_patterns = set([".git", "node_modules", "__pycache__", ".venv"])
            for ignore_name in (".keelignore", ".gitignore"):
                ignore_path = os.path.join(root, ignore_name)
                if os.path.isfile(ignore_path):
                    try:
                        with open(ignore_path, "r", encoding="utf-8") as fh:
                            for line in fh:
                                line = line.strip()
                                if line and not line.startswith("#"):
                                    ignore_patterns.add(line.rstrip("/"))
                    except OSError:
                        pass
            dirs[:] = [d for d in dirs if d not in ignore_patterns and not any(
                __import__("fnmatch").fnmatch(d, pat) for pat in ignore_patterns)]

            for fname in files:
                if not fnmatch.fnmatch(fname, pattern):
                    continue
                fpath = os.path.join(base, fname)
                # Apply ignore rules to files
                if any(fnmatch.fnmatch(fname, pat) or fnmatch.fnmatch(fpath, pat) for pat in ignore_patterns):
                    continue
                if content:
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="strict") as fh:
                            for lineno, line in enumerate(fh, 1):
                                if content in line:
                                    hits.append(f"{fpath}:{lineno}:{line.rstrip()}")
                    except (UnicodeDecodeError, OSError):
                        continue
                else:
                    hits.append(fpath)
                if len(hits) >= 1000:
                    break
            if len(hits) >= 1000:
                break
        return "\n".join(hits), {"hits": hits, "numHits": len(hits), "truncated": len(hits) >= 1000}


    def _process_output(self, tool_input: dict):
        pid = tool_input["process_id"]
        proc = self._BG_PROCESSES.get(pid)
        if proc is None:
            raise KeyError(f"unknown process: {pid}")
        stdout = ""
        stderr = ""
        try:
            if proc.stdout:
                stdout = proc.stdout.read() or ""
        except Exception:
            pass
        try:
            if proc.stderr:
                stderr = proc.stderr.read() or ""
        except Exception:
            pass
        status = "running" if proc.poll() is None else f"exited({proc.returncode})"
        return stdout + ("\n" if stdout and stderr else "") + stderr, {"process_id": pid, "status": status, "stdout": stdout, "stderr": stderr, "exit_code": proc.returncode}

    def _process_wait(self, tool_input: dict):
        import time
        pid = tool_input["process_id"]
        proc = self._BG_PROCESSES.get(pid)
        if proc is None:
            raise KeyError(f"unknown process: {pid}")
        timeout = int(tool_input.get("timeout", 60))
        try:
            proc.wait(timeout=timeout)
        except Exception:
            pass
        status = "running" if proc.poll() is None else f"exited({proc.returncode})"
        return status, {"process_id": pid, "status": status, "exit_code": proc.returncode}


def _terminate_process_tree(proc) -> None:
    """Terminate *proc* and every descendant it spawned."""
    import os as _os
    import signal
    import subprocess as _subprocess

    if proc.poll() is not None:
        return
    if _os.name == "nt":
        try:
            _subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                            capture_output=True, timeout=10)
        except (OSError, _subprocess.SubprocessError):
            pass
        try:
            proc.wait(timeout=5)
        except _subprocess.TimeoutExpired:
            proc.kill()
        return

    # The background process was started with start_new_session=True, so its
    # process group id equals its pid. Kill the whole group, then escalate.
    try:
        _os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        proc.terminate()
    try:
        proc.wait(timeout=3)
    except _subprocess.TimeoutExpired:
        try:
            _os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()


def cleanup_background_processes() -> int:
    """Terminate all tracked background processes. Returns count killed."""
    from keel.runner import RealTools
    killed = 0
    for pid, proc in list(RealTools._BG_PROCESSES.items()):
        try:
            if proc.poll() is None:
                _terminate_process_tree(proc)
                killed += 1
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        del RealTools._BG_PROCESSES[pid]
    return killed



def _build_model_client(plan: LaunchPlan):
    """Choose the model client: explicit fake script > configured provider > fake."""
    if plan.fake_script_path:
        return ScriptedModel(_load_fake_script(plan.fake_script_path),
                             model=plan.model), plan.model
    try:
        chain = provider_registry.resolve_chain(plan.provider)
    except ProviderError as exc:
        raise CliValidationError(str(exc)) from None
    if chain:
        cap = chain[0]
        adapter = provider_registry.build_adapter(cap.name)
        model_name = plan.model_override or cap.default_model
        return ProviderModelClient(adapter, model=model_name), model_name
    diagnostic("provider", {
        "warning": "no provider keys configured; using built-in scripted fake",
        "set": "KEEL_OPENROUTER_API_KEY | KEEL_GOOGLE_API_KEY | "
               "KEEL_NVIDIA_API_KEY"})
    return ScriptedModel(_load_fake_script(None), model="keel-fake-1"), "keel-fake-1"


def _emit_local_command(plan: LaunchPlan, output: str) -> int:
    """Print a builtin command's output through the normal envelope shape."""
    import os
    import uuid as _uuid

    session_id = plan.session_id or str(_uuid.uuid4())
    envelope = ev.result(
        subtype="success", session_id=session_id,
        uuid=str(_uuid.uuid4()), timestamp="2026-01-01T00:00:00.000Z",
        num_turns=0, duration_ms=0, duration_api_ms=0,
        stop_reason="end_turn", terminal_reason="completed",
        result_text=output, model="local",
        local_command=plan.local_command)
    out_format = plan.output_format
    if out_format == "text":
        sys.stdout.write(output + "\n")
    elif out_format == "json":
        sys.stdout.write(json.dumps(envelope, separators=(",", ":"),
                                    ensure_ascii=False) + "\n")
    else:  # stream-json: one init then the result, like any run
        init = ev.system_init(
            cwd=os.getcwd(), session_id=session_id, model="local",
            permission_mode=plan.permission_mode,
            tools=ALL_TOOLS, uuid=str(_uuid.uuid4()),
            timestamp="2026-01-01T00:00:00.000Z")
        sys.stdout.write(json.dumps(init, separators=(",", ":"),
                                    ensure_ascii=False) + "\n")
        sys.stdout.write(json.dumps(envelope, separators=(",", ":"),
                                    ensure_ascii=False) + "\n")
    return 0


def run(plan: LaunchPlan) -> int:
    """Execute a validated plan. Returns the process exit code."""
    import os
    import uuid as _uuid

    from . import commands as commands_mod

    # command surface: builtins run locally; custom commands render to a prompt
    stripped = plan.prompt.strip()
    if stripped.startswith("/") and not stripped.startswith("//"):
        parts = stripped[1:].split(maxsplit=1)
        cmd_name = parts[0].lower() if parts and parts[0] else ""
        cmd_args = parts[1] if len(parts) > 1 else ""
        cmd = commands_mod.find(cmd_name, Path(os.getcwd())) if cmd_name else None
        if cmd is None:
            diagnostic("command", {"error": f"unknown command: /{cmd_name}",
                                   "hint": "run /help to list commands"})
            return 1
        if cmd.source == "builtin":
            return _emit_local_command(
                LaunchPlan(**{**plan.__dict__, "local_command": cmd.name}),
                commands_mod.execute_builtin(cmd.name, cmd_args,
                                             Path(os.getcwd())))
        plan = LaunchPlan(**{**plan.__dict__,
                             "prompt": commands_mod.render_custom(cmd, cmd_args),
                             "local_command": cmd.name})

    clock = VirtualClock()
    rng = SeededRng(plan.seed)
    state_root = plan.state_root or os.path.join(
        os.path.expanduser("~"), ".keel")

    # resolve scoped settings: files + env + flags (flags win over files)
    flags: dict = {}
    flags["permissionMode"] = plan.permission_mode
    flags["maxTurns"] = plan.max_turns
    if plan.provider != "auto":
        flags["defaultProvider"] = plan.provider
    if plan.model_override:
        flags["model"] = plan.model_override
    if plan.rules != ((), (), ()):
        flags["permissions"] = {"allow": plan.rules[2],
                                "ask": plan.rules[1],
                                "deny": plan.rules[0]}
    resolved = settings.resolve(state_root=Path(state_root), cwd=Path(os.getcwd()),
                                flags=flags, bare=plan.bare)
    for diag in resolved.diagnostics:
        diagnostic("settings", {"severity": diag.severity, "code": diag.code,
                                "message": diag.message, "source": diag.source})

    effective_mode = str(resolved.value.get("permissionMode",
                                            plan.permission_mode))
    effective_turns = int(resolved.value.get("maxTurns", plan.max_turns))
    effective_provider = (plan.provider if plan.provider != "auto"
                          else str(resolved.value.get("defaultProvider", "auto")))
    resolved_rules = settings.as_rule_lists(resolved)
    plan = LaunchPlan(**{**plan.__dict__,
                         "permission_mode": effective_mode,
                         "max_turns": effective_turns,
                         "provider": effective_provider,
                         "rules": resolved_rules})

    model, model_name = _build_model_client(plan)
    executor = RealTools()
    session_id = plan.session_id or \
        str(uuid.UUID(int=rng.getrandbits(128)))
    config = SessionConfig(cwd=os.getcwd(), state_root=state_root,
                           bare=plan.bare, permission_mode=plan.permission_mode,
                           session_id=session_id, model=model_name,
                           max_turns=plan.max_turns, interactive=False,
                           seed=plan.seed,
                           local_command=plan.local_command)
    hook_defs = parse_hooks(resolved.value.get("hooks", {}))

    servers = parse_servers(resolved.value.get("mcpServers", {}))
    allowed = [s for s in servers
               if s.scope == "user" or is_approved(s)]
    pending = [s.name for s in servers if s not in allowed]
    if pending:
        diagnostic("mcp", {
            "info": "project-scope servers are inert until approved",
            "pending": pending,
            "hint": "keel mcp approve <name>"})
    mcp = McpManager(allowed) if allowed else None

    session = Session(model_client=model, executor=executor, config=config,
                      rules=plan.rules, clock=clock, rng=rng,
                      hooks=hook_defs, mcp=mcp)
    try:
        outcome = session.run(plan.prompt)
    finally:
        if mcp is not None:
            mcp.shutdown_all()
            if mcp.failed:
                diagnostic("mcp", {"failed": mcp.failed,
                                   "info": "server(s) did not start; "
                                           "their tools were not offered"})

    out_format = plan.output_format
    if out_format == "text":
        sys.stdout.write((outcome.envelope.get("result") or "") + "\n")
    elif out_format == "json":
        sys.stdout.write(json.dumps(outcome.envelope,
                                    separators=(",", ":"),
                                    ensure_ascii=False) + "\n")
    else:  # stream-json
        for event in outcome.events:
            sys.stdout.write(json.dumps(event, separators=(",", ":"),
                                        ensure_ascii=False) + "\n")
    return ev.EXIT_CODES[outcome.envelope["subtype"]]


import atexit as _atexit

def _cleanup_on_exit() -> None:
    try:
        cleanup_background_processes()
    except Exception:
        pass

_atexit.register(_cleanup_on_exit)
