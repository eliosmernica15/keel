"""Declarative command/network execution policy (A1.6, B3.4, B7.1).

Clean-room Python adaptation of the semantics of OpenAI Codex's
``codex-rs/execpolicy`` engine (Apache-2.0, inspected at commit
``ef33e43a159beeeb95dddf7cde05926cc9871929``). Rust/Starlark cannot be linked
into Keel's Python-authoritative runtime, so the algorithms are reimplemented
here with a local JSON policy format instead of the upstream Starlark syntax.

Semantics preserved:
- decisions ``allow < prompt < forbidden``; the most restrictive matching rule wins;
- rules keyed by the first command token; ordered prefix patterns with per-token
  alternatives;
- optional host-executable path constraints (basename resolution);
- network rules with protocol + host decisions and compiled allow/deny domains;
- load-time ``match`` / ``not_match`` self-tests;
- order-independent fingerprint and overlay merging.

No upstream source file was copied. Attribution is in docs/THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time

_POLICY_IO_LOCK = threading.Lock()
import shlex
from dataclasses import dataclass, field
from pathlib import Path

ALLOW = "allow"
PROMPT = "prompt"
FORBIDDEN = "forbidden"
DECISIONS = (ALLOW, PROMPT, FORBIDDEN)
_RANK = {ALLOW: 0, PROMPT: 1, FORBIDDEN: 2}
_PROTOCOLS = ("http", "https", "socks5_tcp", "socks5_udp")
_NAME = re.compile(r"[A-Za-z0-9_.-]{1,120}")
_WIN_PATH = re.compile(r"^[A-Za-z]:[\\/]")


class PolicyError(ValueError):
    """Invalid policy document or example."""


def tokenize(command: str | list[str] | tuple[str, ...]) -> list[str]:
    """Return shell tokens for a command string (or pass through tokens)."""
    if isinstance(command, (list, tuple)):
        return [str(t) for t in command]
    try:
        return shlex.split(command)
    except ValueError:
        # Unbalanced quotes: keep a conservative token list rather than
        # silently dropping part of the command.
        return command.split()


def normalize_host(raw: str) -> str:
    host = str(raw).strip()
    if not host:
        raise PolicyError("network host cannot be empty")
    if "://" in host or any(c in host for c in "/?#"):
        raise PolicyError("network host must be a hostname or IP literal")
    if host.startswith("[") and "]" in host:
        host = host[1:host.index("]")]
    elif host.count(":") == 1:
        host = host.split(":", 1)[0]
    return host.lower().rstrip(".")


@dataclass(frozen=True)
class PrefixPattern:
    first: str
    rest: tuple[tuple[str, ...], ...]

    def matches(self, tokens: list[str]) -> list[str] | None:
        length = len(self.rest) + 1
        if len(tokens) < length or tokens[0] != self.first:
            return None
        for alternatives, token in zip(self.rest, tokens[1:length]):
            if token not in alternatives:
                return None
        return tokens[:length]

    def render(self) -> str:
        parts = [self.first]
        parts += [a[0] if len(a) == 1 else "[" + "|".join(a) + "]"
                  for a in self.rest]
        return " ".join(parts)


@dataclass(frozen=True)
class PrefixRule:
    pattern: PrefixPattern
    decision: str = ALLOW
    justification: str | None = None

    @property
    def program(self) -> str:
        return self.pattern.first

    def matches(self, tokens: list[str]) -> RuleMatch | None:
        prefix = self.pattern.matches(tokens)
        if prefix is None:
            return None
        return RuleMatch(kind="prefix", matched_prefix=prefix,
                         decision=self.decision,
                         justification=self.justification,
                         resolved_program=None, command=list(tokens))


@dataclass(frozen=True)
class NetworkRule:
    host: str
    protocol: str
    decision: str
    justification: str | None = None


@dataclass
class RuleMatch:
    kind: str
    matched_prefix: list[str] = field(default_factory=list)
    decision: str = ALLOW
    justification: str | None = None
    resolved_program: str | None = None
    command: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind, "matchedPrefix": self.matched_prefix,
            "decision": self.decision, "justification": self.justification,
            "resolvedProgram": self.resolved_program, "command": self.command,
        }


@dataclass
class Evaluation:
    decision: str
    matched_rules: list[RuleMatch] = field(default_factory=list)

    @property
    def is_match(self) -> bool:
        return any(r.kind != "heuristics" for r in self.matched_rules)

    def to_dict(self) -> dict:
        return {"decision": self.decision,
                "matchedRules": [r.to_dict() for r in self.matched_rules],
                "isMatch": self.is_match}


class ExecPolicy:
    def __init__(self, rules: list[PrefixRule] | None = None,
                 network: list[NetworkRule] | None = None,
                 host_executables: dict[str, list[str]] | None = None):
        self.rules_by_program: dict[str, list[PrefixRule]] = {}
        for rule in rules or []:
            self.rules_by_program.setdefault(rule.program, []).append(rule)
        self.network_rules = list(network or [])
        self.host_executables = dict(host_executables or {})

    def check(self, command: str | list[str], *,
              resolve_host_executables: bool = False,
              heuristics=None) -> Evaluation:
        # Host-executable checks receive a path as the first token; on Windows
        # shlex would consume the backslashes, so keep it intact.
        if (isinstance(command, str) and resolve_host_executables
                and _WIN_PATH.match(command)):
            tokens = [command]
        else:
            tokens = tokenize(command)
        matches: list[RuleMatch] = []
        if tokens:
            for rule in self.rules_by_program.get(tokens[0], []):
                match = rule.matches(tokens)
                if match:
                    matches.append(match)
            if not matches and resolve_host_executables:
                matches = self._host_matches(tokens)
        if not matches and heuristics is not None:
            matches = [RuleMatch(kind="heuristics", command=tokens,
                                 decision=heuristics(tokens))]
        if not matches:
            matches = [RuleMatch(kind="heuristics", command=tokens,
                                 decision=ALLOW)]
        decision = max((m.decision for m in matches),
                       key=lambda d: _RANK.get(d, 0))
        return Evaluation(decision=decision, matched_rules=matches)

    def _host_matches(self, tokens: list[str]) -> list[RuleMatch]:
        first = tokens[0]
        path = Path(first)
        basename = path.name if first not in ("", ".") else ""
        if not basename or basename not in self.rules_by_program:
            return []
        allowed = self.host_executables.get(basename)
        if allowed is not None:
            try:
                resolved = str(path.resolve())
            except OSError:
                return []
            if resolved not in allowed:
                return []
        basename_command = [basename, *tokens[1:]]
        out = []
        for rule in self.rules_by_program[basename]:
            match = rule.matches(basename_command)
            if match:
                match.resolved_program = resolved
                out.append(match)
        return out

    def compiled_network_domains(self) -> tuple[list[str], list[str]]:
        allowed: list[str] = []
        denied: list[str] = []
        for rule in self.network_rules:
            if rule.decision == ALLOW:
                denied = [d for d in denied if d != rule.host]
                if rule.host not in allowed:
                    allowed.append(rule.host)
            elif rule.decision == FORBIDDEN:
                allowed = [d for d in allowed if d != rule.host]
                if rule.host not in denied:
                    denied.append(rule.host)
        return allowed, denied

    def merge_overlay(self, overlay: "ExecPolicy") -> "ExecPolicy":
        rules = [r for group in self.rules_by_program.values() for r in group]
        for group in overlay.rules_by_program.values():
            rules.extend(group)
        hosts = {**self.host_executables, **overlay.host_executables}
        return ExecPolicy(rules, self.network_rules + overlay.network_rules, hosts)

    def fingerprint(self) -> list[str]:
        entries = [f"{prog}:{rule.pattern.render()}:{rule.decision}"
                   for prog, rules in self.rules_by_program.items()
                   for rule in rules]
        entries += [f"network:{r.protocol}:{r.host}:{r.decision}"
                    for r in self.network_rules]
        return sorted(entries)

    def allowed_prefixes(self) -> list[str]:
        return sorted(rule.pattern.render()
                      for rules in self.rules_by_program.values()
                      for rule in rules if rule.decision == ALLOW)

    def evaluate_network(self, host: str, protocol: str = "https") -> str:
        """Decision for a host + protocol (last matching rule wins).

        ``compiled_network_domains()`` is a host-level summary used by the UI;
        evaluation itself is protocol-aware so an HTTP allowance does not
        silently authorise HTTPS. ``*`` rules apply to every protocol. A host
        with no matching rule defaults to ``prompt``.
        """
        host = normalize_host(host)
        matching = [r for r in self.network_rules
                    if r.host == host and r.protocol in (protocol, "*")]
        if not matching:
            return PROMPT
        return matching[-1].decision


def _tokens(value, label: str) -> list[str]:
    if isinstance(value, str):
        return tokenize(value)
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    raise PolicyError(f"{label} must be a string or list")


def from_dict(doc: dict) -> ExecPolicy:
    """Parse a JSON policy document and run its embedded self-tests."""
    if not isinstance(doc, dict):
        raise PolicyError("policy must be an object")
    rules: list[PrefixRule] = []
    self_tests: list[tuple[list[PrefixRule], list[str], list[str]]] = []
    for raw in doc.get("prefix_rules", []):
        if not isinstance(raw, dict):
            raise PolicyError("prefix_rules entries must be objects")
        pattern = raw.get("pattern")
        if not isinstance(pattern, list) or not pattern:
            raise PolicyError("pattern must be a non-empty list")
        first = tokenize(pattern[0])
        if len(first) != 1:
            raise PolicyError("pattern first token must be a single token")
        rest = []
        for token in pattern[1:]:
            if isinstance(token, (list, tuple)):
                alternatives = tuple(str(a) for a in token)
                if not alternatives:
                    raise PolicyError("pattern alternatives cannot be empty")
                rest.append(alternatives)
            else:
                rest.append((str(token),))
        decision = str(raw.get("decision", ALLOW))
        if decision not in DECISIONS:
            raise PolicyError(f"invalid decision: {decision}")
        justification = raw.get("justification")
        if justification is not None:
            justification = str(justification)
        rule = PrefixRule(PrefixPattern(first[0], tuple(rest)),
                          decision, justification)
        rules.append(rule)
        self_tests.append(([rule],
                           [_tokens(x, "match") for x in raw.get("match", [])],
                           [_tokens(x, "not_match") for x in raw.get("not_match", [])]))

    network: list[NetworkRule] = []
    for raw in doc.get("network_rules", []):
        protocol = str(raw.get("protocol", "https"))
        if protocol not in _PROTOCOLS and protocol != "*":
            raise PolicyError(f"invalid network protocol: {protocol}")
        decision = str(raw.get("decision", PROMPT))
        if decision not in DECISIONS:
            raise PolicyError(f"invalid decision: {decision}")
        justification = raw.get("justification")
        network.append(NetworkRule(normalize_host(str(raw.get("host", ""))),
                                   protocol, decision,
                                   str(justification) if justification else None))

    hosts = {}
    for name, paths in (doc.get("host_executables") or {}).items():
        if not _NAME.fullmatch(str(name)):
            raise PolicyError("invalid host executable name")
        hosts[str(name)] = [str(p) for p in paths]

    policy = ExecPolicy(rules, network, hosts)
    for rule_group, matches, not_matches in self_tests:
        isolated = ExecPolicy(rule_group)
        for example in matches:
            if not any(r.matches(example) for r in rule_group):
                raise PolicyError(
                    f"self-test failed: {example!r} should match "
                    f"{rule_group[0].pattern.render()!r}")
        for example in not_matches:
            if isolated.check(example).is_match:
                raise PolicyError(
                    f"self-test failed: {example!r} should not match "
                    f"{rule_group[0].pattern.render()!r}")
    return policy


def read_policy_doc(path: str | Path) -> dict | None:
    """Read a policy document under the shared IO lock (atomic snapshot)."""
    target = Path(path)
    if not target.is_file():
        return None
    with _POLICY_IO_LOCK:
        return json.loads(target.read_text(encoding="utf-8"))


def load_policy(path: str | Path) -> ExecPolicy:
    return from_dict(read_policy_doc(path) or {})


class ExecPolicyStore:
    """Persist named execution policies in local state (no secret values)."""

    def __init__(self, state_root: str | Path):
        self.root = Path(state_root) / "exec-policies"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, name: str) -> Path:
        if not _NAME.fullmatch(name):
            raise PolicyError("invalid policy name")
        return self.root / f"{name}.json"

    def save(self, name: str, doc: dict) -> Path:
        from_dict(doc)  # validate before persisting
        path = self._path(name)
        with _POLICY_IO_LOCK:
            # Atomic replace avoids a half-written policy being read by other
            # threads. The lock serializes writers; readers use a snapshot.
            for attempt in range(5):
                tmp = path.with_suffix(path.suffix + ".tmp-"
                                       + secrets.token_hex(4))
                try:
                    tmp.write_text(json.dumps(doc, indent=2) + "\n",
                                   encoding="utf-8")
                    os.replace(tmp, path)
                    return path
                except OSError:
                    tmp.unlink(missing_ok=True)
                    if attempt == 4:
                        raise
                    time.sleep(0.01 * (attempt + 1))
        return path

    def load(self, name: str) -> ExecPolicy:
        path = self._path(name)
        if not path.is_file():
            raise KeyError(name)
        return load_policy(path)

    def document(self, name: str) -> dict:
        return json.loads(self._path(name).read_text(encoding="utf-8"))

    def list(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.json"))
