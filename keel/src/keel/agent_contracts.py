"""Agent contracts — W2.x P0 (W2.1/2/3/4/6/8/9/11).

A self-contained, stdlib-only *policy layer* for agents. Nothing here calls a
model, spawns a subprocess or touches the network: the module produces inert
descriptors, decisions and prompt text that the runtime integrates.

Implemented features
--------------------
W2.1  Markdown agent files with YAML frontmatter at ``.keel/agents/**/*.md``.
      A stdlib-safe minimal parser reads a strict subset of YAML; unsafe tags
      (``!!python/...``, ``!custom``) and expressions (``${...}``, ``$(...)``,
      backticks, ``{{...}}``, anchors/aliases) are rejected. The file body is
      the agent's ``system`` prompt. Nested paths become nested IDs
      (``team/reviewer``); global + project roots are supported.
W2.2  Modes ``primary`` / ``subagent`` / ``all``. Subagents run in child
      sessions with *fresh context*: only the child descriptor, a lifecycle
      contract and the operator's task are carried across — never the parent
      transcript.
W2.3  Built-ins ``build``, ``plan``, ``general`` (no further subagents),
      ``explore`` (read-only, incl. web), plus hidden maintenance agents
      (``compaction``, ``title``, ``summary``) mapped to model roles
      (``summarizer`` / ``title``). Hidden agents are not user-selectable.
W2.4  ``steps`` budget: on the final step tools are removed and the model is
      asked to summarize in text. A new user turn resets the tracker.
W2.6  Launch permissions come from the *parent's* ``subagent`` rules;
      deny cannot be overridden (monotonic). The child keeps its own
      permissions — they are never intersected with the parent's.
W2.8  ``system`` replaces the provider base prompt for that agent, while
      project instructions, skills, references and lifecycle text are still
      appended in a documented order.
W2.9  Merge semantics: later scalars replace, maps merge by key, permission
      rules append; global rules are applied before agent rules.
W2.11 The plan agent may write only plan files under ``.keel/plans/``.
      Shell access is *not* widened — it remains governed by the normal
      permission system. This is a pure policy descriptor.

Integration seams (not wired here, to preserve file ownership)
---------------------------------------------------------------
* :mod:`keel.agent_profiles` / :mod:`keel.agent_roles` — descriptor source.
* :mod:`keel.permissions` — ``PermissionRule`` / ``parse_permission`` output
  maps onto ``Rule(action, resource, effect)``; ``shell_rules()`` deliberately
  returns nothing so the existing evaluator stays authoritative.
* :mod:`keel.subagent` — ``build_subagent_launch()`` supplies the launch
  decision and fresh-context lifecycle; the existing child-session builder
  decides how to materialise the child.
* :mod:`keel.instructions` / :mod:`keel.skills` — ``compose_system_prompt``
  accepts the rendered project-instruction and skill strings as inputs.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

__all__ = [
    "AgentContractError", "PermissionRule", "AgentDescriptor",
    "parse_permission", "decide_launch", "can_launch",
    "MODES", "normalize_mode", "can_be_primary", "can_be_subagent",
    "parse_agent_markdown", "agent_id_from_path", "discover_agent_files",
    "load_agents", "descriptor_from_config", "merge_configs",
    "merge_descriptors", "BUILTIN_IDS", "HIDDEN_BUILTIN_IDS",
    "BUILTIN_ROLE_MAP", "builtin_agents", "is_hidden",
    "is_user_selectable", "model_role", "StepDirective", "StepTracker",
    "step_directive", "ComposedPrompt", "PROMPT_ORDER",
    "compose_system_prompt", "LifecycleContract", "SubagentLaunch",
    "LIFECYCLE_CONTRACT", "build_subagent_launch", "PLAN_DIR", "PlanPolicy",
    "PLAN_AGENT_POLICY",
]


class AgentContractError(ValueError):
    """Raised for invalid agent frontmatter, modes, steps or descriptors."""


# ---------------------------------------------------------------------------
# W3.1-shaped permission rules: {action, resource, effect}
# ---------------------------------------------------------------------------

_EFFECTS = frozenset({"allow", "deny", "ask"})
_PERMISSION_KEYS = frozenset({"allow", "deny", "ask", "subagent"})


@dataclass(frozen=True)
class PermissionRule:
    action: str
    resource: str
    effect: str

    def __post_init__(self) -> None:
        if self.effect not in _EFFECTS:
            raise AgentContractError(f"unknown rule effect: {self.effect!r}")
        if not str(self.action).strip() or not str(self.resource).strip():
            raise AgentContractError("permission rule needs an action and a resource")

    def as_dict(self) -> dict:
        return {"action": self.action, "resource": self.resource,
                "effect": self.effect}


def _glob_match(pattern: str, value: str) -> bool:
    """Minimal glob (``*``, ``**``, ``?``) used for agent IDs and resources."""
    pat = str(pattern).replace("\\", "/")
    val = str(value).replace("\\", "/")
    out: list[str] = []
    i = 0
    while i < len(pat):
        if pat.startswith("**", i):
            out.append(".*")
            i += 2
            if i < len(pat) and pat[i] == "/":
                i += 1
            continue
        if pat[i] == "*":
            out.append("[^/]*")
        elif pat[i] == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(pat[i]))
        i += 1
    return bool(re.fullmatch("".join(out), val, re.IGNORECASE))


def parse_permission(cfg: Mapping | None) -> dict[str, tuple[PermissionRule, ...]]:
    """Normalise a permission config into rule tuples keyed by category.

    Accepts both the canonical ``{action, resource, effect}`` dict form and a
    shorthand where the category key implies the effect (e.g. ``subagent:
    [{deny: '*'}, {allow: reviewer}]`` from frontmatter).
    """
    result: dict[str, tuple[PermissionRule, ...]] = {
        key: () for key in ("allow", "deny", "ask", "subagent")}
    if not cfg:
        return result
    for category, items in cfg.items():
        if category not in result or not isinstance(items, (list, tuple)):
            continue
        parsed: list[PermissionRule] = []
        for item in items:
            if isinstance(item, PermissionRule):
                parsed.append(item)
                continue
            if isinstance(item, Mapping):
                action = item.get("action")
                resource = item.get("resource", item.get("tool", "*"))
                effect = item.get("effect")
                if effect is None:
                    # shorthand: {deny: '*'} / {allow: reviewer}
                    shorthand = [e for e in _EFFECTS if e in item]
                    if shorthand:
                        effect = shorthand[0]
                        resource = item[effect]
                    elif category == "subagent":
                        effect = "allow"
                    else:
                        effect = category
                if action is None:
                    action = "subagent" if category == "subagent" else "*"
                parsed.append(PermissionRule(str(action), str(resource), str(effect)))
                continue
            text = str(item).strip()
            if ":" in text and not text.startswith(("domain:", "http")):
                action, resource = text.split(":", 1)
            else:
                action = "subagent" if category == "subagent" else "*"
                resource = text
            effect = category if category in _EFFECTS else "allow"
            parsed.append(PermissionRule(action, resource, effect))
        result[category] = tuple(parsed)
    return result


def decide_launch(rules: Iterable[PermissionRule], target_id: str) -> str:
    """Parent-side launch decision: deny -> ask -> allow -> default ask.

    Deny is monotonic: once any matching rule denies, no later allow can
    override it. ``ask`` is the default when nothing matches (W3.1 baseline).
    """
    matched = [r for r in rules
               if r.action in ("subagent", "*") and _glob_match(r.resource, target_id)]
    for effect in ("deny", "ask", "allow"):
        if any(r.effect == effect for r in matched):
            return effect
    return "ask"


def can_launch(parent: "AgentDescriptor", target_id: str) -> bool:
    return decide_launch(parent.permission.get("subagent", ()), target_id) == "allow"


# ---------------------------------------------------------------------------
# W2.2 — modes
# ---------------------------------------------------------------------------

MODES = frozenset({"primary", "subagent", "all"})


def normalize_mode(mode: str) -> str:
    value = str(mode or "primary").strip().lower()
    if value not in MODES:
        raise AgentContractError(
            f"unknown agent mode: {mode!r} (accepted: {sorted(MODES)})")
    return value


def can_be_primary(mode: str) -> bool:
    return normalize_mode(mode) in ("primary", "all")


def can_be_subagent(mode: str) -> bool:
    return normalize_mode(mode) in ("subagent", "all")


# ---------------------------------------------------------------------------
# W2.1 — stdlib-safe frontmatter parser
# ---------------------------------------------------------------------------

_KEYVAL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$")

# Rejected: YAML tags, template/interpolation expressions, command
# substitution, anchors/aliases and embedded code openers. The parser never
# evaluates any of them; it simply refuses to load the file.
_UNSAFE_PATTERNS = (
    re.compile(r"!!"),                      # !!python/object/apply:...
    re.compile(r"(?:^|:)\s*![A-Za-z_]"),    # !custom tags
    re.compile(r"\$\{|\$\("),               # ${...} / $(...)
    re.compile(r"`"),                       # backticks
    re.compile(r"\{\{|\}\}"),               # {{...}} templates
    re.compile(r"<\?|<%"),                  # embedded code openers
    re.compile(r"(?:^|\s)[&*][A-Za-z_]\w*"),  # YAML anchors / aliases
)


def _check_frontmatter_line(line: str) -> None:
    for pattern in _UNSAFE_PATTERNS:
        if pattern.search(line):
            raise AgentContractError(
                f"unsafe YAML frontmatter rejected: {line.strip()[:120]!r}")


def _indent_of(line: str) -> int:
    prefix = line[:len(line) - len(line.lstrip())]
    if "\t" in prefix:
        raise AgentContractError("tabs are not allowed for frontmatter indentation")
    return len(prefix)


def _next_content(lines: Sequence[str], i: int) -> int:
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped and not stripped.startswith("#"):
            return i
        i += 1
    return i


def _split_inline(text: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    for ch in text:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf).strip())
    return [p for p in parts if p]


def _parse_scalar(value: str):
    text = value.strip()
    if not text:
        return ""
    if text.startswith("[") and text.endswith("]"):
        return [_parse_scalar(piece) for piece in _split_inline(text[1:-1])]
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in ("null", "~", "none"):
        return None
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


def _parse_block(lines: Sequence[str], i: int, indent: int):
    """Parse one indentation level into a list or dict; return (value, next_i)."""
    j = _next_content(lines, i)
    is_list = j < len(lines) and lines[j][indent:].startswith("- ")
    container = [] if is_list else {}
    while True:
        i = _next_content(lines, i)
        if i >= len(lines):
            break
        line = lines[i]
        current = _indent_of(line)
        if current < indent:
            break
        if current > indent:
            i += 1  # defensive: orphan deeper line, ignore
            continue
        content = line[current:]
        if is_list:
            if not content.startswith("- "):
                break
            item_text = content[2:].strip()
            i += 1
            if not item_text:
                nxt = _next_content(lines, i)
                if nxt < len(lines) and _indent_of(lines[nxt]) > current:
                    sub, i = _parse_block(lines, i, _indent_of(lines[nxt]))
                    container.append(sub)
                else:
                    container.append({})
                continue
            match = _KEYVAL_RE.match(item_text)
            if not match:
                container.append(_parse_scalar(item_text))
                continue
            key, value = match.group(1), match.group(2).strip()
            item: dict = {}
            if value:
                item[key] = _parse_scalar(value)
            else:
                nxt = _next_content(lines, i)
                if nxt < len(lines) and _indent_of(lines[nxt]) > current:
                    sub, i = _parse_block(lines, i, _indent_of(lines[nxt]))
                    item[key] = sub
                else:
                    item[key] = {}
            # multi-key list item: "- action: read\n  resource: '**'"
            nxt = _next_content(lines, i)
            if nxt < len(lines) and _indent_of(lines[nxt]) > current:
                extra, i = _parse_block(lines, i, _indent_of(lines[nxt]))
                if isinstance(extra, dict):
                    item.update(extra)
                else:
                    container.append(item)
                    container.append(extra)
                    continue
            container.append(item)
            continue
        match = _KEYVAL_RE.match(content)
        if not match:
            raise AgentContractError(
                f"unparseable frontmatter line: {line.strip()[:120]!r}")
        key, value = match.group(1), match.group(2).strip()
        i += 1
        if not value:
            nxt = _next_content(lines, i)
            if nxt < len(lines) and _indent_of(lines[nxt]) > current:
                sub, i = _parse_block(lines, i, _indent_of(lines[nxt]))
                container[key] = sub
            else:
                container[key] = {}
        else:
            container[key] = _parse_scalar(value)
    return container, i


def _split_frontmatter_safe(text: str) -> tuple[dict, str]:
    lines = str(text).splitlines()
    if not lines or lines[0].strip() != "---":
        raise AgentContractError("agent markdown is missing YAML frontmatter fence")
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end = index
            break
    if end is None:
        raise AgentContractError("unterminated agent frontmatter fence")
    for raw in lines[1:end]:
        _check_frontmatter_line(raw)
    frontmatter_lines = lines[1:end]
    frontmatter, _ = _parse_block(frontmatter_lines, 0, 0)
    if not isinstance(frontmatter, dict):
        raise AgentContractError("agent frontmatter must be a mapping")
    body = "\n".join(lines[end + 1:]).lstrip("\n")
    return frontmatter, body


# ---------------------------------------------------------------------------
# W2.1 — descriptors, discovery, loading
# ---------------------------------------------------------------------------

@dataclass
class AgentDescriptor:
    id: str
    system: str | None = None
    description: str = ""
    mode: str = "primary"
    model: str | None = None
    steps: int | None = None
    hidden: bool = False
    disabled: bool = False
    color: str | None = None
    web: bool = False
    read_only: bool = False
    role: str | None = None
    permission: dict[str, tuple[PermissionRule, ...]] = field(default_factory=dict)
    tools: dict = field(default_factory=dict)
    skills: tuple[str, ...] = ()
    scope: str = "project"
    source: str | None = None

    def to_config(self) -> dict:
        """Serialise to the mergeable config shape used by W2.9."""
        config = {
            "id": self.id,
            "system": self.system,
            "description": self.description,
            "mode": self.mode,
            "model": self.model,
            "steps": self.steps,
            "hidden": self.hidden,
            "disabled": self.disabled,
            "color": self.color,
            "web": self.web,
            "read_only": self.read_only,
            "role": self.role,
            "skills": list(self.skills),
            "tools": dict(self.tools),
            "scope": self.scope,
            "source": self.source,
            "permission": {
                category: [rule.as_dict() for rule in rules]
                for category, rules in self.permission.items() if rules
            },
        }
        # Unset scalars must not replace a value supplied by an earlier layer.
        return {key: value for key, value in config.items() if value is not None}


def _coerce_steps(value) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise AgentContractError("steps must be a positive integer")
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.strip().isdigit() and int(value) > 0:
        return int(value)
    raise AgentContractError(f"invalid steps budget: {value!r}")


def descriptor_from_config(agent_id: str, cfg: Mapping, *, scope: str = "project",
                           source: str | None = None) -> AgentDescriptor:
    return AgentDescriptor(
        id=str(agent_id),
        system=cfg.get("system"),
        description=str(cfg.get("description") or ""),
        mode=normalize_mode(cfg.get("mode", "primary")),
        model=cfg.get("model"),
        steps=_coerce_steps(cfg.get("steps")),
        hidden=bool(cfg.get("hidden", False)),
        disabled=bool(cfg.get("disabled", False)),
        color=cfg.get("color"),
        web=bool(cfg.get("web", False)),
        read_only=bool(cfg.get("read_only", False)),
        role=cfg.get("role"),
        permission=parse_permission(cfg.get("permission")),
        tools=dict(cfg.get("tools") or {}),
        skills=tuple(str(s) for s in (cfg.get("skills") or ())),
        scope=scope,
        source=source,
    )


def parse_agent_markdown(text: str, *, agent_id: str | None = None,
                         source: str | Path | None = None,
                         scope: str = "project",
                         root: str | Path | None = None) -> AgentDescriptor:
    """Parse one markdown agent file; its body becomes the system prompt."""
    frontmatter, body = _split_frontmatter_safe(text)
    resolved_id = agent_id
    if not resolved_id and source is not None:
        resolved_id = agent_id_from_path(source, root)
    if not resolved_id:
        raise AgentContractError("agent id is required (agent_id= or source=)")
    cfg = dict(frontmatter)
    if "prompt" in cfg and "system" not in cfg:
        cfg["system"] = cfg.pop("prompt")
    cfg["system"] = body.strip()
    return descriptor_from_config(
        resolved_id, cfg, scope=scope,
        source=str(source) if source is not None else None)


def agent_id_from_path(path: str | Path, root: str | Path | None = None) -> str:
    """Nested path -> nested ID: ``team/reviewer.md`` -> ``team/reviewer``."""
    target = Path(path)
    if root is not None:
        try:
            relative = target.resolve().relative_to(Path(root).resolve())
        except (ValueError, OSError):
            relative = Path(target.name)
    else:
        parts = target.parts
        if len(parts) >= 2 and parts[0] in (".keel", "keel") and parts[1] == "agents":
            relative = Path(*parts[2:])
        else:
            relative = target
    if relative.suffix.lower() == ".md":
        relative = relative.with_suffix("")
    return "/".join(part for part in relative.parts if part not in (".", ""))


def discover_agent_files(root: str | Path) -> list[Path]:
    directory = Path(root)
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.rglob("*.md") if path.is_file())


# ---------------------------------------------------------------------------
# W2.9 — merge semantics
# ---------------------------------------------------------------------------

def merge_configs(base: Mapping, overlay: Mapping) -> dict:
    """Scalars replace, maps merge by key, permission rules append."""
    merged = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if key in _PERMISSION_KEYS and isinstance(value, (list, tuple)):
            merged[key] = list(current or ()) + list(value)
        elif isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = merge_configs(current, value)
        else:
            merged[key] = value
    return merged


def merge_descriptors(base: AgentDescriptor, overlay: AgentDescriptor) -> AgentDescriptor:
    merged = merge_configs(base.to_config(), overlay.to_config())
    return descriptor_from_config(overlay.id, merged,
                                  scope=overlay.scope, source=overlay.source)


def load_agents(global_root: str | Path | None = None,
                project_root: str | Path | None = None, *,
                include_builtins: bool = True) -> dict[str, AgentDescriptor]:
    """Load built-ins, then global agents, then project agents (W2.9 order)."""
    agents: dict[str, AgentDescriptor] = {}
    if include_builtins:
        agents.update(builtin_agents())
    for root, scope in ((global_root, "global"), (project_root, "project")):
        if root is None:
            continue
        for path in discover_agent_files(root):
            agent_id = agent_id_from_path(path, root)
            agent = parse_agent_markdown(
                path.read_text(encoding="utf-8"), agent_id=agent_id,
                source=path, scope=scope)
            agents[agent_id] = (merge_descriptors(agents[agent_id], agent)
                                if agent_id in agents else agent)
    return agents


# ---------------------------------------------------------------------------
# W2.3 — built-ins and hidden maintenance agents
# ---------------------------------------------------------------------------

BUILTIN_IDS = frozenset({"build", "plan", "general", "explore"})
HIDDEN_BUILTIN_IDS = frozenset({"compaction", "title", "summary"})
BUILTIN_ROLE_MAP = {
    "compaction": "summarizer",
    "summary": "summarizer",
    "title": "title",
}


def _r(action: str, resource: str, effect: str = "allow") -> dict:
    return {"action": action, "resource": resource, "effect": effect}


def _builtin_configs() -> dict[str, dict]:
    return {
        "build": {
            "description": "Default coding agent.",
            "mode": "primary",
            "system": "You are the build agent. Implement changes and verify them.",
            "permission": {
                "allow": [_r("read", "**"), _r("write", "**"),
                          _r("edit", "**"), _r("bash", "*")],
                "subagent": [_r("subagent", "*")],
            },
        },
        "plan": {
            "description": "Planning agent; writes plans only.",
            "mode": "primary",
            "system": "You are the plan agent. Write plans only; never edit code.",
            "permission": PLAN_AGENT_POLICY.permission_config(),
            "role": "planner",
        },
        "general": {
            "description": "General-purpose agent; cannot launch subagents.",
            "mode": "all",
            "system": "You are a general-purpose agent. Work carefully and report evidence.",
            "permission": {
                "allow": [_r("read", "**"), _r("write", "**"),
                          _r("edit", "**"), _r("bash", "*"),
                          _r("webfetch", "domain:**")],
                "subagent": [_r("subagent", "*", "deny")],
            },
        },
        "explore": {
            "description": "Read-only exploration agent (including the web).",
            "mode": "subagent",
            "system": "You are an exploration agent. Read only; never modify files.",
            "read_only": True,
            "web": True,
            "permission": {
                "allow": [_r("read", "**"), _r("glob", "**"), _r("grep", "**"),
                          _r("webfetch", "domain:**"), _r("websearch", "*")],
                "deny": [_r("write", "*", "deny"), _r("edit", "*", "deny"),
                         _r("bash", "*", "deny"), _r("shell", "*", "deny")],
                "subagent": [_r("subagent", "*", "deny")],
            },
        },
        "compaction": {
            "description": "Hidden maintenance agent: context compaction.",
            "mode": "subagent", "hidden": True,
            "system": "Produce a faithful, bounded compaction summary.",
            "role": BUILTIN_ROLE_MAP["compaction"],
            "permission": {
                "allow": [_r("summarize", "*")],
                "deny": [_r("*", "*", "deny")],
            },
        },
        "title": {
            "description": "Hidden maintenance agent: session titles.",
            "mode": "subagent", "hidden": True,
            "system": "Produce a short session title.",
            "role": BUILTIN_ROLE_MAP["title"],
            "permission": {
                "allow": [_r("title", "*")],
                "deny": [_r("*", "*", "deny")],
            },
        },
        "summary": {
            "description": "Hidden maintenance agent: session summaries.",
            "mode": "subagent", "hidden": True,
            "system": "Produce a concise, evidence-based session summary.",
            "role": BUILTIN_ROLE_MAP["summary"],
            "permission": {
                "allow": [_r("summarize", "*")],
                "deny": [_r("*", "*", "deny")],
            },
        },
    }


def builtin_agents() -> dict[str, AgentDescriptor]:
    """Return fresh copies of the shipped built-in descriptors."""
    return {
        name: descriptor_from_config(name, config, scope="builtin")
        for name, config in _builtin_configs().items()
    }


def is_hidden(agent: AgentDescriptor) -> bool:
    """``hidden`` is visibility only, never a security boundary."""
    return bool(agent.hidden) or agent.id in HIDDEN_BUILTIN_IDS


def is_user_selectable(agent: AgentDescriptor) -> bool:
    return (not is_hidden(agent) and not agent.disabled
            and can_be_primary(agent.mode))


def model_role(agent: AgentDescriptor) -> str | None:
    return agent.role or BUILTIN_ROLE_MAP.get(agent.id)


# ---------------------------------------------------------------------------
# W2.4 — steps budget
# ---------------------------------------------------------------------------

FINAL_STEP_INSTRUCTION = (
    "This is the final step of this turn. Do not call any tools; "
    "summarize your work and findings in text now."
)


def _validated_max_steps(max_steps) -> int | None:
    if max_steps is None:
        return None
    if isinstance(max_steps, bool):
        raise ValueError("max_steps must be a positive integer or None")
    if isinstance(max_steps, int) and max_steps > 0:
        return max_steps
    if isinstance(max_steps, str) and max_steps.isdigit() and int(max_steps) > 0:
        return int(max_steps)
    raise ValueError("max_steps must be a positive integer or None")


@dataclass(frozen=True)
class StepDirective:
    step: int
    max_steps: int | None

    @property
    def is_final(self) -> bool:
        return self.max_steps is not None and self.step >= self.max_steps

    @property
    def tools_available(self) -> bool:
        return not self.is_final

    @property
    def must_summarize(self) -> bool:
        return self.is_final

    @property
    def instruction(self) -> str:
        return FINAL_STEP_INSTRUCTION if self.is_final else ""


def step_directive(max_steps, step: int) -> StepDirective:
    return StepDirective(step=step, max_steps=_validated_max_steps(max_steps))


class StepTracker:
    """Per-turn model-step budget; ``reset()`` on every new user input."""

    def __init__(self, max_steps=None):
        self.max_steps = _validated_max_steps(max_steps)
        self._step = 0

    @property
    def step(self) -> int:
        return self._step

    def peek(self) -> StepDirective:
        return step_directive(self.max_steps, self._step + 1)

    def advance(self) -> StepDirective:
        self._step += 1
        return step_directive(self.max_steps, self._step)

    def reset(self) -> None:
        self._step = 0


# ---------------------------------------------------------------------------
# W2.8 — prompt composition
# ---------------------------------------------------------------------------

PROMPT_ORDER = ("system", "project_instructions", "skills", "references", "lifecycle")


@dataclass(frozen=True)
class ComposedPrompt:
    text: str
    order: tuple[str, ...]
    base_source: str  # "agent" | "provider"


def _section(tag: str, content: str | Sequence[str] | None) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        body = content.strip()
    else:
        body = "\n".join(str(item).strip() for item in content if str(item).strip())
    return f"<{tag}>\n{body}\n</{tag}>" if body else ""


def compose_system_prompt(descriptor: AgentDescriptor, *,
                          provider_base_prompt: str = "",
                          project_instructions: Sequence[str] = (),
                          skills: Sequence[str] = (),
                          references: Sequence[str] = (),
                          lifecycle: str | None = None) -> ComposedPrompt:
    """Assemble the system prompt in the documented ``PROMPT_ORDER``.

    An agent ``system`` prompt replaces the provider base prompt entirely;
    project instructions, skills, references and lifecycle text are still
    appended (they are context, not provider persona).
    """
    base_source = "agent" if descriptor.system else "provider"
    base = descriptor.system if descriptor.system else provider_base_prompt
    pieces = (
        ("system", _section("agent-system", base)),
        ("project_instructions", _section("project-instructions", project_instructions)),
        ("skills", _section("skills", skills)),
        ("references", _section("references", references)),
        ("lifecycle", _section("lifecycle-contract", lifecycle)),
    )
    text = "\n\n".join(body for _, body in pieces if body)
    return ComposedPrompt(text=text,
                          order=tuple(name for name, body in pieces if body),
                          base_source=base_source)


# ---------------------------------------------------------------------------
# W2.2 / W2.6 — fresh-context subagent launch
# ---------------------------------------------------------------------------

LIFECYCLE_CONTRACT = """\
<lifecycle-contract>
You are a subagent in a fresh child session. Your context contains only this
agent descriptor, this contract and the operator's current task. You do not
inherit the parent's conversation history. Follow your agent's steps budget:
on the final step, call no tools and summarize in text. Your own permissions
apply to you; the parent's launch rules only decided whether you could start.
</lifecycle-contract>"""


@dataclass(frozen=True)
class LifecycleContract:
    fresh_context: bool = True
    inherits_parent_history: bool = False
    descriptor_only_context: bool = True
    max_steps: int | None = None


@dataclass(frozen=True)
class SubagentLaunch:
    descriptor: AgentDescriptor
    lifecycle: LifecycleContract
    launch_decision: str
    task: str = ""
    history: tuple = ()  # always empty: child context is fresh

    @property
    def allowed(self) -> bool:
        return self.launch_decision == "allow"

    def build_context(self, **kwargs) -> ComposedPrompt:
        return compose_system_prompt(
            self.descriptor, lifecycle=LIFECYCLE_CONTRACT, **kwargs)


def build_subagent_launch(parent: AgentDescriptor, child: AgentDescriptor, *,
                          prompt: str = "", parent_history=()) -> SubagentLaunch:
    """Build the child session contract.

    ``parent_history`` is accepted and deliberately discarded — a subagent's
    context is fresh. The child keeps its own permission rules; only the
    *decision* to launch is taken from the parent's ``subagent`` rules.
    """
    _ = parent_history  # intentionally dropped (fresh-context contract)
    decision = decide_launch(parent.permission.get("subagent", ()), child.id)
    return SubagentLaunch(
        descriptor=child,                       # child's own permissions, not a subset
        lifecycle=LifecycleContract(max_steps=child.steps),
        launch_decision=decision,
        task=prompt,
        history=(),
    )


# ---------------------------------------------------------------------------
# W2.11 — plan agent write policy (pure descriptor)
# ---------------------------------------------------------------------------

PLAN_DIR = ".keel/plans"


@dataclass(frozen=True)
class PlanPolicy:
    plan_dir: str = PLAN_DIR
    allowed_extensions: tuple[str, ...] = (".md",)

    def permits_write(self, path: str | Path) -> bool:
        norm = str(path).replace("\\", "/").strip()
        while norm.startswith("./"):
            norm = norm[2:]
        norm = "/".join(part for part in norm.split("/") if part)
        parts = norm.split("/")
        if ".." in parts or not parts:
            return False
        plan_parts = [part for part in self.plan_dir.replace("\\", "/").split("/")
                      if part]
        start = None
        for index in range(len(parts) - len(plan_parts) + 1):
            if parts[index:index + len(plan_parts)] == plan_parts:
                start = index
                break
        if start is None:
            return False
        tail = parts[start + len(plan_parts):]
        if not tail:
            return False
        return Path(tail[-1]).suffix.lower() in self.allowed_extensions

    def permission_config(self) -> dict:
        """Allow plan writes only; everything else falls through to default-ask."""
        target = self.plan_dir.rstrip("/") + "/**"
        return {"allow": [_r("write", target), _r("edit", target),
                          _r("create", target)]}

    def shell_rules(self) -> tuple:
        """Shell stays governed by the ordinary permission evaluator."""
        return ()


PLAN_AGENT_POLICY = PlanPolicy()
