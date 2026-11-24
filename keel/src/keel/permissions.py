"""keel.permissions — Tier-1 permission evaluator (Phase 1, thin).

Order pinned to interface-spec.md §5.5: deny → ask → allow → mode policy.
First match wins within a category; scope never reorders; the mode never
widens a rule. NOTE: implementation-plan.md's Phase-1 summary omits `ask`
and disagrees with this order — the spec wins here, flagged for the gate.

Tier 2 (non-configurable safety layer) is Phase 3 and deliberately absent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from .shell_ast import Decline, operations

MODE_DEFAULT = "default"          # manual
MODE_ACCEPT_EDITS = "acceptEdits"
MODE_DONT_ASK = "dontAsk"
MODE_BYPASS = "bypassPermissions"
KNOWN_MODES = frozenset({MODE_DEFAULT, MODE_ACCEPT_EDITS, MODE_DONT_ASK, MODE_BYPASS})
_MODE_ALIASES = {"manual": MODE_DEFAULT}

READ = "read"
MUTATE_LOCAL = "mutate_local"
EXECUTE = "execute"
NETWORK = "network"
PROCESS_CONTROL = "process_control"
IRREVERSIBLE = "irreversible"

# most-restrictive-first ranking used to collapse a compound command to one class
_RANK = {IRREVERSIBLE: 0, NETWORK: 1, EXECUTE: 2, PROCESS_CONTROL: 3,
         MUTATE_LOCAL: 4, READ: 5}

READ_TOOLS = frozenset({"read_file", "glob", "grep",
                        "ask_user", "list_tasks"})
WRITE_TOOLS = frozenset({"write_file", "edit_file"})
SHELL_TOOLS = frozenset({"run_shell"})


class RuleSyntaxError(ValueError):
    pass


@dataclass(frozen=True)
class Rule:
    category: str            # deny | ask | allow
    tool: str
    specifier: Optional[str]  # None => bare rule (schema removal for deny)
    raw: str

    @property
    def bare(self) -> bool:
        return self.specifier is None


def parse_rule(raw: str) -> Rule:
    text = raw.strip()
    m = re.fullmatch(r"([A-Za-z][A-Za-z0-9_-]*)\s*(\((.*)\))?", text)
    if not m:
        raise RuleSyntaxError(f"rule has no recognisable tool name: {raw!r}")
    tool, _, spec = m.group(1), m.group(2), m.group(3)
    category = None
    # category prefix is carried by the list the rule came from, not the text;
    # the caller supplies it via parse_rules().
    spec = (spec or "").strip() or None
    if spec is not None and len(spec) > 512:
        raise RuleSyntaxError("rule specifier exceeds 512 characters")
    return Rule(category or "", tool, spec, raw)


def parse_rules(category: str, items: list[str]) -> tuple[list[Rule], list[str]]:
    """Parse a scope's rule list; bad rules are dropped with a diagnostic."""
    good: list[Rule] = []
    diagnostics: list[str] = []
    for raw in items:
        try:
            rule = parse_rule(raw)
        except RuleSyntaxError as exc:
            diagnostics.append(f"rule_syntax_error: {exc}")
            continue
        good.append(Rule(category, rule.tool, rule.specifier, rule.raw))
    return good, diagnostics


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    i, out = 0, []
    while i < len(pattern):
        ch = pattern[i]
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            if i < len(pattern) and pattern[i] == "/":
                i += 1
            continue
        if ch == "*":
            out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(ch))
        i += 1
    return re.compile("^" + "".join(out) + "$", re.IGNORECASE)


def path_glob_match(pattern: str, path: str) -> bool:
    norm = path.replace("\\", "/")
    return bool(_glob_to_regex(pattern.replace("\\", "/")).match(norm))


def command_prefix_match(prefix: str, command: str) -> bool:
    """Bash(specifier) semantics: prefix match on token sequences."""
    pre = prefix.split()
    cmd = command.split()
    return len(cmd) >= len(pre) and cmd[: len(pre)] == pre


def _tool_match(rule: Rule, tool_name: str) -> bool:
    return rule.tool.lower() == tool_name.lower()


def _specifier_match(rule: Rule, tool_name: str, tool_input: dict,
                     operation_hint: Optional[str],
                     tool_registry=None) -> bool:
    if rule.bare:
        return True
    spec = rule.specifier or ""
    _shell_tools = (tool_registry.shell_tools() if tool_registry is not None
                    else SHELL_TOOLS)
    _read_tools = (tool_registry.read_tools() if tool_registry is not None
                   else READ_TOOLS)
    _write_tools = (tool_registry.write_tools() if tool_registry is not None
                    else WRITE_TOOLS)
    if tool_name in _shell_tools:
        command = str(tool_input.get("command", ""))
        return command_prefix_match(spec, command)
    path = None
    if tool_name in _read_tools or tool_name in _write_tools:
        path = tool_input.get("path") or tool_input.get("file_path")
    if path is not None:
        return path_glob_match(spec, str(path))
    if spec.startswith("domain:"):
        domain = str(tool_input.get("url", "")).split("/")[2] \
            if "://" in str(tool_input.get("url", "")) else str(tool_input.get("domain", ""))
        return path_glob_match(spec[len("domain:"):], domain)
    return command_prefix_match(spec, str(tool_input))


def _operation_class(tool_name: str, tool_input: dict,
                    tool_registry=None) -> tuple[Optional[str], bool]:
    # Consult registry first (authoritative source)
    if tool_registry is not None:
        level = tool_registry.operation_class(tool_name)
        if level is not None:
            if level == "read":
                return READ, False
            if level == "write":
                return MUTATE_LOCAL, False
            if level == "execute":
                # Shell-like tools get command analysis
                if tool_registry.is_shell_like(tool_name):
                    shell = str(tool_input.get("shell", "posix"))
                    try:
                        ops = operations(str(tool_input.get("command", "")), shell)
                    except Decline:
                        return MUTATE_LOCAL, True
                    ranked = sorted(ops, key=lambda op: _RANK.get(op, 0))
                    return ranked[0], False
                return EXECUTE, False
            if level == "network":
                return NETWORK, False
            if level == "process_control":
                return PROCESS_CONTROL, False
            if level == "irreversible" or level == "destructive":
                return IRREVERSIBLE, False
    # Fallback to hardcoded sets for backward compat
    _read = tool_registry.read_tools() if tool_registry is not None else READ_TOOLS
    _write = tool_registry.write_tools() if tool_registry is not None else WRITE_TOOLS
    _shell = tool_registry.shell_tools() if tool_registry is not None else SHELL_TOOLS
    if tool_name in _read:
        return READ, False
    if tool_name in _write:
        return MUTATE_LOCAL, False
    if tool_name in _shell:
        shell = str(tool_input.get("shell", "posix"))
        try:
            ops = operations(str(tool_input.get("command", "")), shell)
        except Decline:
            return MUTATE_LOCAL, True
        ranked = sorted(ops, key=lambda op: _RANK.get(op, 0))
        return ranked[0], False
    # Unknown tool: fail closed (deny by default for safety)
    return None, False


@dataclass(frozen=True)
class Decision:
    decision: str        # allow | deny (ask resolved before return) | accept recorded separately
    reason_type: str     # rule | mode | consent_required
    reason: str
    source: str          # config | mode
    matched_rule: Optional[str]
    operation_class: Optional[str]
    indeterminate: bool

    def record_meta(self, tool_use_id: str) -> dict:
        # spec §5.4: recorded decision uses `accept` spelling; all three keys required
        return {
            "id": tool_use_id,
            "permission_decision": {
                "decision": "accept" if self.decision == "allow" else "deny",
                "source": self.source,
                "reason_type": self.reason_type,
            },
        }


_MODE_TABLE = {
    MODE_DEFAULT:      {READ: "allow", MUTATE_LOCAL: "ask", EXECUTE: "ask",
                        NETWORK: "ask", PROCESS_CONTROL: "ask", IRREVERSIBLE: "ask"},
    MODE_ACCEPT_EDITS: {READ: "allow", MUTATE_LOCAL: "allow", EXECUTE: "ask",
                        NETWORK: "ask", PROCESS_CONTROL: "ask", IRREVERSIBLE: "ask"},
    MODE_DONT_ASK:     {READ: "allow", MUTATE_LOCAL: "deny", EXECUTE: "deny",
                        NETWORK: "deny", PROCESS_CONTROL: "deny", IRREVERSIBLE: "deny"},
    MODE_BYPASS:       {READ: "allow", MUTATE_LOCAL: "allow", EXECUTE: "allow",
                        NETWORK: "allow", PROCESS_CONTROL: "allow", IRREVERSIBLE: "allow"},
}


def normalize_mode(mode: str) -> str:
    m = _MODE_ALIASES.get(mode, mode)
    if m not in KNOWN_MODES:
        raise RuleSyntaxError(f"unknown permission mode: {mode!r} "
                              f"(accepted: {sorted(KNOWN_MODES | set(_MODE_ALIASES))})")
    return m


def evaluate(*, tool_name: str, tool_input: dict,
             rules: tuple[list[Rule], list[Rule], list[Rule]],
             mode: str, interactive: bool,
             tool_registry=None) -> Decision:
    """rules is (deny, ask, allow). Interactive is False in print/CI mode."""
    deny, ask, allow = rules
    op_class, indeterminate = _operation_class(tool_name, tool_input, tool_registry)

    # Config deny rules are the first hard floor (DECISIONS.md D-001): a
    # matching deny wins over a saved policy allow. A policy forbid still wins
    # over any config ask/allow grant, which is checked immediately below.
    for rule in deny:
        if _tool_match(rule, tool_name) and _specifier_match(
                rule, tool_name, tool_input, op_class, tool_registry):
            return Decision("deny", "rule", f"denied by rule {rule.raw!r}",
                            "config", rule.raw, op_class, indeterminate)

    # Saved execution policies are binding at this boundary: a forbidden
    # command or denied egress host cannot be widened by ask/allow rules or
    # by bypassPermissions mode. Only an explicit policy ALLOW is permissive;
    # a deny/ask verdict is returned before any config grant is considered.
    #
    # Production fix: previously this check ran *after* the rule loop, so an
    # exact/broad config allow (or ask) rule returned early and silently
    # bypassed a forbidden exec/egress policy.
    from .policy_enforcement import enforce as _enforce_policy

    policy_decision = _enforce_policy(tool_name, tool_input or {},
                                      interactive=interactive)
    if policy_decision is not None and policy_decision.decision != "allow":
        return policy_decision

    for category_rules, label in ((ask, "ask"), (allow, "allow")):
        for rule in category_rules:
            if _tool_match(rule, tool_name) and _specifier_match(
                    rule, tool_name, tool_input, op_class, tool_registry):
                if label == "ask":
                    if not interactive:
                        return Decision("deny", "consent_required",
                                        f"rule {rule.raw!r} requires consent; "
                                        "no interactive callback in this mode",
                                        "mode", rule.raw, op_class, indeterminate)
                    return Decision("ask", "rule", f"ask rule {rule.raw!r}",
                                    "config", rule.raw, op_class, indeterminate)
                return Decision("allow", "rule", f"allowed by rule {rule.raw!r}",
                                "config", rule.raw, op_class, indeterminate)

    # An explicit policy allow overrides the mode baseline (but never a config
    # deny, which returned above).
    if policy_decision is not None:
        return policy_decision

    table = _MODE_TABLE[normalize_mode(mode)]
    if op_class is None:
        # Unknown tool: fail closed (deny by default)
        return Decision("deny", "mode", f"unknown tool {tool_name!r} has no permission classification",
                        "mode", None, op_class, indeterminate)
    verdict = table.get(op_class, "ask")
    if mode == MODE_BYPASS and verdict == "allow":
        # allow has no force here; deny/ask already returned above. Mode baseline only.
        return Decision("allow", "mode", "bypassPermissions mode baseline",
                        "mode", None, op_class, indeterminate)
    if verdict == "allow":
        return Decision("allow", "mode", f"{mode} mode baseline ({op_class})",
                        "mode", None, op_class, indeterminate)
    if not interactive:
        return Decision("deny", "consent_required",
                        f"{mode} mode requires consent for {op_class}; "
                        "no interactive callback in this mode",
                        "mode", None, op_class, indeterminate)
    return Decision("ask", "mode", f"{mode} mode asks for {op_class}",
                    "mode", None, op_class, indeterminate)


def evaluate_noninteractive(tool_name: str, tool_input: dict, *,
                            project_root=None) -> Decision:
    """Evaluate one tool call against resolved settings with no UI approval.

    Shared by the desktop workflow API and print-mode workflow steps so both
    paths use the same Tier-1 rules, modes and tool registry. Tier-2 is applied
    separately by the tool executor and is never weakened here.
    """
    from pathlib import Path

    from . import settings
    from .runner import RealTools
    from .tools import create_native_registry

    resolved = settings.resolve(
        state_root=settings.default_state_root(),
        cwd=Path(project_root) if project_root else Path.cwd())
    deny, ask, allow = settings.as_rule_lists(resolved)
    rules = (parse_rules("deny", deny)[0],
             parse_rules("ask", ask)[0],
             parse_rules("allow", allow)[0])
    registry = create_native_registry(RealTools())
    return evaluate(
        tool_name=tool_name, tool_input=tool_input or {}, rules=rules,
        mode=str(resolved.value.get("permissionMode", MODE_DEFAULT)),
        interactive=False, tool_registry=registry)


def manifest_tools(all_tools: list[str], deny_rules: list[Rule]) -> list[str]:
    """Bare-name deny removes the tool from the manifest entirely."""
    bare_denied = {r.tool.lower() for r in deny_rules if r.bare}
    return [t for t in all_tools if t.lower() not in bare_denied]


def dont_ask_tools(tools: list[str], allow_rules: list[Rule]) -> list[str]:
    """dontAsk mode: prompting tools are subtracted from the schema.

    Only read-class tools and tools covered by an explicit allow rule survive.
    """
    allowed_bare = {r.tool.lower() for r in allow_rules}
    return [t for t in tools
            if t in READ_TOOLS or t.lower() in allowed_bare]
