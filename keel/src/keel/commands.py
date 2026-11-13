"""keel.commands — the print-mode command surface (Phase 2, M6 shape).

Two kinds:
- builtins: local executors, handled entirely here, never call the model;
- custom: prompt templates from markdown files ($ARGUMENTS substitution),
  rendered into a normal turn.

File layout: <project>/.keel/commands/*.md or ~/.keel/commands/*.md
Frontmatter: name, description, argument-hint; body = the template.
"""

from __future__ import annotations

import json
import os
import platform
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .context import BYTES_PER_TOKEN, estimate_tokens
from .instructions import CAP_BYTES
from .skills import SkillError, _parse_frontmatter


@dataclass(frozen=True)
class Command:
    name: str
    description: str
    argument_hint: str = ""
    source: str = "builtin"  # builtin | user | project
    template: str = ""       # custom commands: the body


class CommandError(Exception):
    pass


_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


def _builtin_commands() -> list[Command]:
    return [
        Command("help", "List available commands (built-in and custom).",
                "", "builtin"),
        Command("version", "Print keel and component versions.", "",
                "builtin"),
        Command("context", "Token accounting report for the current prompt "
                           "and the budget configuration.", "",
                "builtin"),
        Command("cost", "Usage and cost ledger (zeros in this environment).",
                "", "builtin"),
        Command("doctor", "Readiness check: interpreter, platform, required "
                          "tools, provider keys (masked).", "",
                "builtin"),
    ]


def custom_command_roots(project_root: Path) -> list[tuple[Path, str]]:
    roots = [(Path(project_root) / ".keel" / "commands", "project"),
             (Path.home() / ".keel" / "commands", "user")]
    return roots


def _load_custom_file(path: Path, scope: str) -> Command:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        fm, body = _parse_frontmatter(text)
    except SkillError as exc:
        raise CommandError(f"{path}: {exc}") from None
    name = str(fm.get("name", path.stem)).strip().lower()
    if not _NAME_RE.match(name):
        raise CommandError(f"{path}: invalid command name {name!r}")
    description = str(fm.get("description", "")).strip() or "(no description)"
    hint = str(fm.get("argument-hint", fm.get("argument_hint", ""))).strip()
    return Command(name=name, description=description,
                   argument_hint=hint, source=scope, template=body)


def discover(project_root: Path) -> list[Command]:
    found: list[Command] = list(_builtin_commands())
    for root, scope in custom_command_roots(project_root):
        if not root.is_dir():
            continue
        for entry in sorted(root.glob("*.md")):
            try:
                found.append(_load_custom_file(entry, scope))
            except CommandError:
                continue  # a broken custom command is not fatal
    return found


def find(name: str, project_root: Path) -> Command | None:
    key = name.lower()
    for command in discover(project_root):
        if command.name == key:
            return command
    return None


def render_custom(command: Command, arguments: str) -> str:
    template = command.template
    if "$ARGUMENTS" in template:
        return template.replace("$ARGUMENTS", arguments)
    if "{{args}}" in template:
        return template.replace("{{args}}", arguments)
    return f"{template.rstrip()}\n\n{arguments}".strip()


# ---------------------------------------------------------------- builtins

def cmd_help(args: str, project_root: Path) -> str:
    rows = discover(project_root)
    lines = ["keel commands:"]
    for row in sorted(rows, key=lambda c: (c.source != "builtin", c.name)):
        hint = f" {row.argument_hint}" if row.argument_hint else ""
        lines.append(f"  /{row.name:<14} [{row.source}]{hint}  {row.description}")
    lines.append("")
    lines.append("Custom commands: "
                 ".keel/commands/<name>.md or ~/.keel/commands/<name>.md "
                 "with $ARGUMENTS.")
    return "\n".join(lines)


def cmd_version(args: str, project_root: Path) -> str:
    return (f"keel {__version__} (clean-room harness; print mode)\n"
            f"python {sys.version.split()[0]} - platform {platform.system()} "
            f"{platform.release()}")


def cmd_context(args: str, project_root: Path) -> str:
    from .settings import resolve, default_state_root
    resolved = resolve(state_root=default_state_root(), cwd=project_root,
                       flags={})
    est = estimate_tokens([{"role": "user", "content": args}]) if args else 0
    from .context import Budget
    budget = Budget()
    return (
        "context budget (deterministic estimate):\n"
        f"  context window   : {budget.context_window} tokens\n"
        f"  reserved output  : {budget.reserved_output} tokens\n"
        f"  usable           : {budget.usable} tokens\n"
        f"  soft limit       : {budget.soft_limit} tokens\n"
        f"  preserved allow  : {budget.preserved_allowance} tokens\n"
        f"  bytes/token      : {BYTES_PER_TOKEN}\n"
        f"  prompt estimate  : {est} tokens ({len(args)} bytes)\n"
        f"  settings source  : "
        + ", ".join(sorted(_collect_scopes(resolved.provenance)) or ["defaults"])
    )


def _collect_scopes(provenance) -> set[str]:
    scopes: set[str] = set()
    if isinstance(provenance, dict):
        for value in provenance.values():
            if isinstance(value, dict):
                if "scope" in value:
                    scopes.add(str(value["scope"]))
                else:
                    scopes |= _collect_scopes(value)
    return scopes


def cmd_cost(args: str, project_root: Path) -> str:
    return ("cost ledger:\n"
            "  total_cost_usd: 0.0  (no priced provider calls recorded)\n"
            "  note: this ledger is populated only from providers with a "
            "known price; with the built-in fake or costBasis:unknown it "
            "stays zero. See `keel provider smoke <name>`.")


def _mask(value: str) -> str:
    return f"<set {len(value)} chars>" if value else "<unset>"


def cmd_doctor(args: str, project_root: Path) -> str:
    import shutil

    keys = {v: _mask(os.environ.get(v, ""))
            for v in ("KEEL_OPENROUTER_API_KEY", "KEEL_GOOGLE_API_KEY",
                      "KEEL_NVIDIA_API_KEY", "KEEL_ANTHROPIC_API_KEY",
                      "KEEL_COMPAT_API_KEY")}
    tools = {name: shutil.which(name) or "MISSING"
             for name in ("git", "pwsh", "powershell", "python", "node")}
    lines = [
        f"keel doctor - {platform.system()} {platform.release()} "
        f"(python {sys.version.split()[0]})",
        f"keel version: {__version__}",
        "tools:",
    ]
    for name, path in tools.items():
        lines.append(f"  {name:<12} {path}")
    lines.append("provider keys:")
    for name, masked in keys.items():
        lines.append(f"  {name:<28} {masked}")
    lines.append("state dirs:")
    lines.append(f"  ~/.keel exists  : {(Path.home() / '.keel').is_dir()}")
    lines.append(f"  project .keel   : {(project_root / '.keel').is_dir()}")
    return "\n".join(lines)


BUILTIN_HANDLERS = {
    "help": cmd_help,
    "version": cmd_version,
    "context": cmd_context,
    "cost": cmd_cost,
    "doctor": cmd_doctor,
}


def execute_builtin(name: str, args: str, project_root: Path) -> str:
    handler = BUILTIN_HANDLERS.get(name.lower())
    if handler is None:
        raise CommandError(f"unknown builtin: {name}")
    return handler(args, project_root)
