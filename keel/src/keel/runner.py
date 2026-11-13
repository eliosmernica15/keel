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
from .permissions import KNOWN_MODES, _MODE_ALIASES, normalize_mode
from .providers import registry as provider_registry
from .providers.base import ProviderError
from .providers.model_client import ProviderModelClient
from .session import ALL_TOOLS, Session, SessionConfig
from .toolresult import Persist

OUTPUT_FORMATS = ("text", "json", "stream-json")
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
            return f"edited {path}", {"type": "text",
                                      "file": {"filePath": path, "content": updated,
                                               "oldContent": text,
                                               "newContent": updated}}
        if name == "glob":
            import glob as globmod
            matches = globmod.glob(tool_input["pattern"], recursive=True)[:1000]
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
