"""Additive, stdlib-only contracts for the W3.x P0 permission-engine features.

This module is *additive by design*. It never imports, patches or reorders the
live Tier-1 evaluator in :mod:`keel.permissions`, and it never touches
``exec_policy`` / ``policy_enforcement``. The authoritative Keel evaluator keeps
``deny -> ask -> allow -> mode`` with **first match wins**, exactly as pinned by
DECISIONS.md D-001 and implemented in ``keel.permissions.evaluate``.

W3.2 SEMANTIC CONSTRAINT (critical)
-----------------------------------
The source plan asks for OpenCode-style "last matching rule wins". Keel's
APPROVED semantics are FIRST-MATCH. We do **not** change live precedence.
Instead :func:`evaluate_rules_last_match` is a clearly marked,
*non-authoritative* reference adapter used only to MODEL last-match behaviour
in the policy simulator / comparison analysis. :data:`KEEL_IS_AUTHORITATIVE`
and :data:`LAST_MATCH_IS_AUTHORITATIVE` are exported so callers cannot confuse
the two, and :func:`simulate` reports both side by side. Changing the live
evaluator to last-match would be a critical defect: a broad ``allow`` listed
after a scoped ``deny`` would silently override the deny (permission-order
confusion, D-001).

Integration seams for the lead (what is intentionally NOT wired in here)
-----------------------------------------------------------------------
* **W3.1/W3.2** :func:`evaluate_rules_keel` mirrors the precedence already
  implemented in ``keel.permissions.evaluate`` (deny/ask/allow lists, first
  match). To adopt the richer ``Rule`` shape live, a caller would translate
  ``permission_contracts.Rule`` into ``permissions.Rule`` via ``parse_rules``;
  this module deliberately does not do that translation, so live precedence is
  untouched.
* **W3.3** :func:`wildcard_match` is a superset of
  ``permissions.path_glob_match`` (``*`` also crosses ``/``, plus shell
  trailing-``*`` behaviour). It is offered as a helper, not swapped into the
  live matcher.
* **W3.6** :func:`check_external_directory` is a pre-check callers may invoke
  *before* read/edit rule evaluation; Tier-2 protected-path checks in
  ``policy_enforcement`` remain above and independent of it.
* **W3.7** :func:`scan_shell_command` does NOT reimplement shell parsing. It
  delegates all lexing, wrapper unwrapping and effect classification to the
  existing ``keel.shell_ast.analyze`` and only adds a typed fail-closed wrapper
  plus ``cd``-target extraction. The returned ``ScannedCommand`` has the same
  ``(name, canonical, operations, args, extent)`` shape as
  ``shell_ast.Command`` so the existing scanner/``operations()`` can consume
  it unchanged. zsh is mapped to the POSIX scanner because ``shell_ast`` has
  no separate zsh grammar.
* **W3.8** :func:`default_policy_decision` is the authoritative base-default
  helper; the ``.env.example`` exception is expressible here but not as a
  first-match rule list (ASK is evaluated before ALLOW), which is why
  :func:`default_policy_rules` is documentation/simulator-only.
* **W3.9** :class:`ApprovalStore` persists to a JSON file under ``state_root``
  with project scoping and a cross-process file lock. It never writes into the
  configured deny rules; callers pass those via ``configured_rules`` and the
  store treats them as a hard floor.
* **W3.10** :func:`apply_policy_floor` / :func:`apply_policy_floors` layer
  hard-deny policies on top of any decision; they can only restrict.
* **W3.12** :func:`resolve_noninteractive` implements the ``keel run``
  ``--approve=never|rules-only`` contract; with no responder an ASK becomes a
  fail-closed DENY.
* **W3.13** :data:`SHELL_AUTHORITY_WARNING` and :data:`CAUTIOUS_PRESET` are
  documentation/simulation constants for the shipped allowlist-style preset.

All dataclasses are frozen: results are typed and never silently mutated.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Iterator, Optional


# ---------------------------------------------------------------------------
# Shared vocabulary
# ---------------------------------------------------------------------------

EFFECT_DENY = "deny"
EFFECT_ASK = "ask"
EFFECT_ALLOW = "allow"
DEFAULT_EFFECT = EFFECT_ASK
VALID_EFFECTS = frozenset({EFFECT_DENY, EFFECT_ASK, EFFECT_ALLOW})

APPROVE_NEVER = "never"
APPROVE_RULES_ONLY = "rules-only"
VALID_APPROVE_MODES = frozenset({APPROVE_NEVER, APPROVE_RULES_ONLY})

MODE_CAUTIOUS = "cautious"
MODE_BALANCED = "balanced"
MODE_TRUSTED = "trusted"

#: The authoritative evaluator is the shipped Tier-1 evaluator, not the adapter.
AUTHORITATIVE_EVALUATOR = "keel.permissions.evaluate"
KEEL_IS_AUTHORITATIVE = True
LAST_MATCH_IS_AUTHORITATIVE = False
SIMULATOR_NOTE = (
    "W3.2: last-match is a NON-AUTHORITATIVE comparison adapter for analysis "
    "only. Keel's authoritative evaluator keeps first-match "
    "deny->ask->allow->mode (DECISIONS.md D-001)."
)

SHELL_AUTHORITY_WARNING = (
    "Shell commands run with the user's full host authority. Prefer narrow "
    "allowlists over trying to recognise every dangerous command. Keel ships "
    "allowlist-style presets (Cautious), never denylist-style presets."
)

CAUTIOUS_PRESET = {
    "style": "allowlist",
    "default": EFFECT_ASK,
    "allowed": ("cat", "ls", "pwd", "git status", "git diff", "npm test"),
    "denylist": (),
}


class Effect(str, Enum):
    """Typed permission effect (string-compatible for readability)."""

    DENY = EFFECT_DENY
    ASK = EFFECT_ASK
    ALLOW = EFFECT_ALLOW

    @property
    def restrictiveness(self) -> int:
        """0 = most permissive, 2 = most restrictive (policy-floor ordering)."""
        return {Effect.ALLOW: 0, Effect.ASK: 1, Effect.DENY: 2}[self]


def _effect_enum(value: str) -> Effect:
    if value not in VALID_EFFECTS:
        raise ValueError(f"invalid effect: {value!r}")
    return Effect(value)


# ---------------------------------------------------------------------------
# W3.1 - rule shape and typed evaluation result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Rule:
    """A permission rule ``{action, resource, effect}`` (W3.1)."""

    action: str
    resource: str
    effect: str

    def __post_init__(self) -> None:
        if not isinstance(self.action, str) or not self.action:
            raise ValueError("rule action must be a non-empty string")
        if not isinstance(self.resource, str) or not self.resource:
            raise ValueError("rule resource must be a non-empty string")
        if self.effect not in VALID_EFFECTS:
            raise ValueError(
                f"invalid rule effect {self.effect!r}; expected one of "
                f"{sorted(VALID_EFFECTS)}"
            )

    def matches(self, action: str, resource: str, *,
                case_sensitive: bool | None = None) -> bool:
        """True when this rule's action and resource patterns match the input."""
        return (
            wildcard_match(self.action, action, case_sensitive=case_sensitive)
            and wildcard_match(self.resource, resource, case_sensitive=case_sensitive)
        )


@dataclass(frozen=True)
class Evaluation:
    """Typed result of any permission evaluation. Never silently mutated."""

    effect: Effect
    matched_rule: Optional[Rule] = None
    reason: str = ""
    #: Only populated by the non-authoritative last-match adapter (W3.2).
    winner: Optional[Rule] = None
    #: Per-resource results for multi-resource operations (W3.4).
    details: tuple["Evaluation", ...] = ()
    authoritative: bool = True

    @property
    def is_allow(self) -> bool:
        return self.effect is Effect.ALLOW

    @property
    def is_deny(self) -> bool:
        return self.effect is Effect.DENY

    @property
    def is_ask(self) -> bool:
        return self.effect is Effect.ASK


def select_matching_rules(rules: Iterable[Rule], action: str, resource: str, *,
                          case_sensitive: bool | None = None) -> tuple[Rule, ...]:
    """Return the rules whose action/resource patterns match, in input order."""
    return tuple(
        rule for rule in rules
        if rule.matches(action, resource, case_sensitive=case_sensitive)
    )


def _candidates(rules: Iterable[Rule], action: Optional[str], resource: Optional[str],
                case_sensitive: bool | None) -> tuple[Rule, ...]:
    if action is None and resource is None:
        return tuple(rules)
    return tuple(
        rule for rule in rules
        if (action is None or wildcard_match(rule.action, action,
                                             case_sensitive=case_sensitive))
        and (resource is None or wildcard_match(rule.resource, resource,
                                                case_sensitive=case_sensitive))
    )


def evaluate_rules_keel(rules: Iterable[Rule], *, action: Optional[str] = None,
                        resource: Optional[str] = None,
                        case_sensitive: bool | None = None) -> Evaluation:
    """Authoritative Keel evaluation: first match, deny -> ask -> allow -> ask.

    ``rules`` is the ordered candidate set. ``action``/``resource``, when
    supplied, filter it down to the matching rules. Within each effect class,
    the first matching rule in input order wins. No match means ASK.
    """
    candidates = _candidates(rules, action, resource, case_sensitive)
    for effect in (EFFECT_DENY, EFFECT_ASK, EFFECT_ALLOW):
        for rule in candidates:
            if rule.effect == effect:
                return Evaluation(
                    Effect(effect), matched_rule=rule,
                    reason=f"{effect} rule matched: {rule.action}/{rule.resource}",
                    authoritative=True,
                )
    return Evaluation(Effect.ASK, reason="default-ask: no rule matched",
                      authoritative=True)


def evaluate_rules_last_match(rules: Iterable[Rule], *, action: Optional[str] = None,
                              resource: Optional[str] = None,
                              case_sensitive: bool | None = None) -> Evaluation:
    """NON-AUTHORITATIVE reference adapter modelling OpenCode last-match.

    This exists only so the policy simulator can compare Keel's approved
    first-match semantics against the reference "last matching rule wins"
    behaviour. It is never used by the live evaluator. ``winner`` exposes the
    winning rule for the simulator display.
    """
    candidates = _candidates(rules, action, resource, case_sensitive)
    if not candidates:
        return Evaluation(Effect.ASK,
                          reason="default-ask (last-match adapter): no rule matched",
                          authoritative=False)
    winner = candidates[-1]
    return Evaluation(
        Effect(winner.effect), matched_rule=winner, winner=winner,
        reason=f"NON-AUTHORITATIVE last-match winner: "
               f"{winner.action}/{winner.resource} ({winner.effect})",
        authoritative=False,
    )


def simulate(rules: Iterable[Rule], action: str, resource: str, *,
             case_sensitive: bool | None = None) -> dict:
    """Show authoritative and adapter outcomes side by side (policy simulator)."""
    materialised = tuple(rules)

    def _view(evaluation: Evaluation) -> dict:
        return {
            "effect": evaluation.effect.value,
            "matched_rule": (
                f"{evaluation.matched_rule.action}/"
                f"{evaluation.matched_rule.resource}({evaluation.matched_rule.effect})"
                if evaluation.matched_rule else None
            ),
            "winner": (
                f"{evaluation.winner.action}/"
                f"{evaluation.winner.resource}({evaluation.winner.effect})"
                if evaluation.winner else None
            ),
            "reason": evaluation.reason,
            "authoritative": evaluation.authoritative,
        }

    return {
        "authoritative_evaluator": AUTHORITATIVE_EVALUATOR,
        "note": SIMULATOR_NOTE,
        "keel": _view(evaluate_rules_keel(
            materialised, action=action, resource=resource,
            case_sensitive=case_sensitive)),
        "last_match": _view(evaluate_rules_last_match(
            materialised, action=action, resource=resource,
            case_sensitive=case_sensitive)),
    }


# ---------------------------------------------------------------------------
# W3.3 - wildcards
# ---------------------------------------------------------------------------

def wildcard_match(pattern: str, value: str, *,
                   case_sensitive: bool | None = None) -> bool:
    """Whole-value glob match: ``*`` any chars incl. ``/``, ``?`` one char.

    * Backslashes are normalized to ``/`` in both pattern and value.
    * Matching is anchored at both ends (whole-value, not substring).
    * Default case sensitivity follows the host: case-insensitive on Windows.
    * A shell pattern ending in ``" *"`` also matches the bare command, e.g.
      ``npm run *`` matches both ``npm run build`` and ``npm run``.
    """
    if not isinstance(pattern, str) or not isinstance(value, str):
        raise TypeError("wildcard_match expects string pattern and value")
    if case_sensitive is None:
        case_sensitive = os.name != "nt"

    norm_pattern = pattern.replace("\\", "/")
    norm_value = value.replace("\\", "/")
    flags = re.DOTALL | (0 if case_sensitive else re.IGNORECASE)

    def _full_match(pat: str) -> bool:
        out: list[str] = []
        for ch in pat:
            if ch == "*":
                out.append(".*")
            elif ch == "?":
                out.append(".")
            else:
                out.append(re.escape(ch))
        return re.fullmatch("".join(out), norm_value, flags) is not None

    if _full_match(norm_pattern):
        return True
    if norm_pattern.endswith(" *"):
        bare = norm_pattern[:-2].rstrip()
        if bare and _full_match(bare):
            return True
    return False


# ---------------------------------------------------------------------------
# W3.4 - multi-resource aggregation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResourceCheck:
    """One resource of a compound operation (W3.4)."""

    action: str
    resource: str
    rules: tuple[Rule, ...] = ()


def _coerce_check(item: object, rules: tuple[Rule, ...]) -> ResourceCheck:
    if isinstance(item, ResourceCheck):
        return item
    if isinstance(item, (tuple, list)) and len(item) >= 2:
        return ResourceCheck(str(item[0]), str(item[1]), rules)
    raise TypeError(
        "resources must contain ResourceCheck or (action, resource) pairs; "
        f"got {type(item).__name__}"
    )


def evaluate_multi(resources: Iterable[object], *, rules: Iterable[Rule] = (),
                   case_sensitive: bool | None = None) -> Evaluation:
    """Aggregate per-resource decisions: any deny, else any ask, else allow."""
    default_rules = tuple(rules)
    evaluations: list[Evaluation] = []
    for item in resources:
        if isinstance(item, Evaluation):
            evaluations.append(item)
            continue
        check = _coerce_check(item, default_rules)
        effective_rules = check.rules or default_rules
        evaluations.append(evaluate_rules_keel(
            effective_rules, action=check.action, resource=check.resource,
            case_sensitive=case_sensitive))

    if any(e.effect is Effect.DENY for e in evaluations):
        effect, reason = Effect.DENY, "multi-resource: at least one resource denied"
    elif any(e.effect is Effect.ASK for e in evaluations):
        effect, reason = Effect.ASK, "multi-resource: at least one resource requires consent"
    else:
        effect, reason = Effect.ALLOW, "multi-resource: every resource allowed"
    return Evaluation(effect, reason=reason, details=tuple(evaluations),
                      authoritative=True)


# ---------------------------------------------------------------------------
# W3.6 - external_directory containment
# ---------------------------------------------------------------------------

def _norm_abs(path: object) -> str:
    return os.path.normcase(
        os.path.normpath(os.path.abspath(os.path.expanduser(str(path))))
    )


def path_is_within(path: object, root: object) -> bool:
    """True when *path* is contained in *root* after resolution (no traversal).

    Both sides are resolved to canonical absolute paths first, so
    ``root/../outside`` resolves outside the root and is not contained. On
    Windows ``normcase`` makes the comparison case-insensitive. A path equal
    to the root is considered contained.
    """
    try:
        resolved_path = Path(path).resolve()
        resolved_root = Path(root).resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    try:
        return os.path.commonpath([_norm_abs(resolved_path),
                                   _norm_abs(resolved_root)]) == _norm_abs(resolved_root)
    except ValueError:
        return False  # e.g. different Windows drives


def check_external_directory(path: object, *, project_root: object,
                             mode: str = MODE_CAUTIOUS,
                             rules: Iterable[Rule] = ()) -> Evaluation:
    """Check an ``external_directory`` access before read/edit rules (W3.6).

    Inside the project root -> allow. Outside -> ask by default (Cautious and
    Balanced), allow only in Trusted mode. Configured deny rules are a hard
    floor and always win, even in Trusted mode.
    """
    if mode not in (MODE_CAUTIOUS, MODE_BALANCED, MODE_TRUSTED):
        raise ValueError(f"unknown permission mode: {mode!r}")
    matching = select_matching_rules(rules, "external_directory", str(path))
    for rule in matching:
        if rule.effect == EFFECT_DENY:
            return Evaluation(Effect.DENY, matched_rule=rule,
                              reason="configured deny on external_directory")
    if path_is_within(path, project_root):
        return Evaluation(Effect.ALLOW, reason="path is inside the project root")
    for rule in matching:
        if rule.effect == EFFECT_ASK:
            return Evaluation(Effect.ASK, matched_rule=rule,
                              reason="ask rule on external_directory")
    for rule in matching:
        if rule.effect == EFFECT_ALLOW:
            return Evaluation(Effect.ALLOW, matched_rule=rule,
                              reason="allow rule on external_directory")
    if mode == MODE_TRUSTED:
        return Evaluation(Effect.ALLOW,
                          reason="trusted mode allows external directories")
    return Evaluation(Effect.ASK,
                      reason="external directory outside project root; "
                             "Keel default is ask (Cautious/Balanced)")


# ---------------------------------------------------------------------------
# W3.7 - shell scanner extension (delegates to keel.shell_ast)
# ---------------------------------------------------------------------------

_SHELL_FAMILIES = {
    "bash": "posix", "sh": "posix", "zsh": "posix", "dash": "posix",
    "ksh": "posix", "posix": "posix",
    "powershell": "powershell", "pwsh": "powershell", "ps1": "powershell",
    "cmd": "cmd", "cmd.exe": "cmd",
}
_CD_CANONICALS = frozenset({"cd", "chdir", "pushd", "set-location", "sl", "st"})


class ScannerError(Exception):
    """Raised by strict callers when a command cannot be analyzed completely."""


@dataclass(frozen=True)
class ScannedCommand:
    """Same shape as ``shell_ast.Command`` so the existing scanner can consume it."""

    name: str
    canonical: str
    operations: frozenset[str]
    args: tuple[str, ...] = ()
    extent: str = ""


@dataclass(frozen=True)
class ShellScan:
    """Typed result of :func:`scan_shell_command`. ``ok=False`` fails closed."""

    shell: str
    subcommands: tuple[ScannedCommand, ...] = ()
    cd_targets: tuple[str, ...] = ()
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _extract_cd_target(args: tuple[str, ...]) -> Optional[str]:
    for token in args:
        if token.startswith("-"):
            # PowerShell supports both "-Path C:\ops" and "-Path:C:\ops".
            if ":" in token:
                return token.split(":", 1)[1]
            continue
        return token
    return None


def scan_shell_command(command: str, shell: str = "posix") -> ShellScan:
    """Decompose *command* into subcommands + ``cd`` targets using shell_ast.

    All lexing, wrapper unwrapping and effect classification is delegated to
    the existing ``keel.shell_ast.analyze``. This function only (a) maps zsh to
    the POSIX family, (b) extracts ``cd``/``Set-Location`` targets and (c)
    returns a typed, fail-closed result. A malformed or dynamically evaluated
    command yields ``error`` (never an allow), per W3.7.
    """
    from . import shell_ast  # integration seam: existing scanner, no logic copied

    family = _SHELL_FAMILIES.get(str(shell).lower())
    if family is None:
        return ShellScan(shell=shell, error=f"unsupported shell: {shell!r}")
    try:
        analysis = shell_ast.analyze(command, family)
    except shell_ast.Decline as exc:
        return ShellScan(shell=shell, error=f"scanner declined: {exc}")
    except Exception as exc:  # fail closed on any unexpected scanner failure
        return ShellScan(shell=shell, error=f"scanner error: {exc}")

    subcommands = tuple(
        ScannedCommand(c.name, c.canonical, c.operations, c.args, c.extent)
        for c in analysis.commands
    )
    targets: list[str] = []
    for command_obj in analysis.commands:
        if command_obj.canonical.lower() in _CD_CANONICALS:
            target = _extract_cd_target(command_obj.args)
            if target is not None:
                targets.append(target)
    return ShellScan(shell=shell, subcommands=subcommands,
                     cd_targets=tuple(targets), error=None)


def scan_to_checks(scan: ShellScan, *, rules: Iterable[Rule] = ()) -> tuple[ResourceCheck, ...]:
    """Turn a successful scan into per-subcommand and per-cd-target checks.

    A failed scan returns no checks, so a caller cannot accidentally allow a
    command it could not analyze.
    """
    if not scan.ok:
        return ()
    materialised = tuple(rules)
    checks: list[ResourceCheck] = []
    for command in scan.subcommands:
        checks.append(ResourceCheck("execute", command.extent or command.canonical,
                                    materialised))
    for target in scan.cd_targets:
        checks.append(ResourceCheck("external_directory", target, materialised))
    return tuple(checks)


# ---------------------------------------------------------------------------
# W3.8 - default policy helper
# ---------------------------------------------------------------------------

_KEY_BASENAMES = frozenset({
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "credentials", "htpasswd",
})
_KEY_SUFFIXES = (".pem", ".key", ".pfx", ".p12")


def is_sensitive_env_read(action: str, resource: str) -> bool:
    """True for reads of .env / .env.* and key files, except .env.example."""
    if str(action).lower() != "read":
        return False
    base = os.path.basename(str(resource).replace("\\", "/")).lower()
    if base == ".env.example":  # explicit exception (W3.8)
        return False
    if base == ".env" or base.startswith(".env."):
        return True
    if base in _KEY_BASENAMES or base.endswith(_KEY_SUFFIXES):
        return True
    return False


def default_policy_rules() -> tuple[Rule, ...]:
    """Documentation/simulator form of the base default policy (W3.8).

    Note: the ``.env.example`` exception is NOT expressible as a first-match
    rule list (ASK is evaluated before ALLOW), so the authoritative helper is
    :func:`default_policy_decision`, not these rules.
    """
    return (
        Rule("read", ".env.example", EFFECT_ALLOW),
        Rule("read", ".env", EFFECT_ASK),
        Rule("read", ".env.*", EFFECT_ASK),
        Rule("read", "*", EFFECT_ALLOW),
        Rule("*", "*", EFFECT_ALLOW),
    )


def default_policy_decision(action: str, resource: str, *,
                            case_sensitive: bool | None = None) -> Evaluation:
    """Base default policy: allow all, ask on .env/.env.* reads except .env.example."""
    if is_sensitive_env_read(action, resource):
        return Evaluation(Effect.ASK, reason="sensitive env/key file read (W3.8)")
    return Evaluation(Effect.ALLOW, reason="default allow (W3.8)")


# ---------------------------------------------------------------------------
# W3.9 - approval replies + project-scoped persistence
# ---------------------------------------------------------------------------

class ApprovalReply(str, Enum):
    ONCE = "once"
    ALWAYS = "always"
    REJECT = "reject"


@dataclass(frozen=True)
class ApprovalRequest:
    action: str
    resource: str
    proposed_pattern: str = ""
    project_id: str = "default"
    session_id: str = ""


@dataclass(frozen=True)
class ApprovalOutcome:
    decision: Evaluation
    reply: ApprovalReply
    persisted: bool = False
    feedback: str = ""


class ApprovalStoreError(RuntimeError):
    """Raised when the approval store cannot be safely read or written."""


_APPROVAL_VERSION = 1
_LOCK_TIMEOUT_S = 5.0
_LOCK_STALE_S = 30.0

# Cross-instance correctness: several ApprovalStore objects in the same process
# may target one approval file.  A file lock alone is fragile under load (a
# holder stalled > _LOCK_STALE_S has its lock stolen) and a fixed .tmp path can
# be shared by two writers.  Serialise the whole read-modify-write per resolved
# path in-process; the on-disk lock still coordinates other processes.
_APPROVAL_PATH_LOCKS: dict[str, threading.RLock] = {}
_APPROVAL_PATH_LOCKS_GUARD = threading.Lock()


def _path_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _APPROVAL_PATH_LOCKS_GUARD:
        lock = _APPROVAL_PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _APPROVAL_PATH_LOCKS[key] = lock
        return lock


def _request_to_dict(request: ApprovalRequest) -> dict:
    return {
        "action": request.action,
        "resource": request.resource,
        "proposed_pattern": request.proposed_pattern,
        "project_id": request.project_id,
        "session_id": request.session_id,
    }


def _request_from_dict(data: dict) -> ApprovalRequest:
    return ApprovalRequest(
        action=str(data.get("action", "")),
        resource=str(data.get("resource", "")),
        proposed_pattern=str(data.get("proposed_pattern", "")),
        project_id=str(data.get("project_id", "default")),
        session_id=str(data.get("session_id", "")),
    )


class ApprovalStore:
    """Project-scoped, concurrency-safe store for W3.9 approval replies.

    Writes go to ``state_root/permission-approvals/<project-hash>.json``. The
    project id is hashed so it can never escape the state root via traversal.
    A per-instance ``RLock`` plus a cross-process ``O_EXCL`` lock file make
    concurrent writes lossless. Configured deny rules are passed in per call
    and act as a hard floor: no approval can grant what config denies.
    """

    def __init__(self, state_root: str | Path, project_id: str = "default"):
        self.state_root = Path(state_root)
        self.project_id = str(project_id)
        digest = hashlib.sha256(self.project_id.encode("utf-8")).hexdigest()[:16]
        self.path = self.state_root / "permission-approvals" / f"{digest}.json"
        self._lock = threading.RLock()
        self._doc = self._load()

    # -- persistence primitives -------------------------------------------

    def _empty_doc(self) -> dict:
        return {
            "version": _APPROVAL_VERSION,
            "project": self.project_id,
            "allow_patterns": [],
            "pending": [],
            "rejections": [],
        }

    def _load(self) -> dict:
        try:
            raw = self.path.read_bytes()
        except (FileNotFoundError, OSError):
            return self._empty_doc()
        try:
            doc = json.loads(raw.decode("utf-8"))
        except Exception:
            return self._empty_doc()  # corrupt -> fail closed (no saved allows)
        if not isinstance(doc, dict) or doc.get("version") != _APPROVAL_VERSION:
            return self._empty_doc()
        for key in ("allow_patterns", "pending", "rejections"):
            if not isinstance(doc.get(key), list):
                doc[key] = []
        return doc

    def _write_atomic(self, doc: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=self.path.name + ".", suffix=".tmp", dir=str(self.path.parent))
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(doc, handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise ApprovalStoreError("failed to persist approvals") from None

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        lock_path = self.path.with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + _LOCK_TIMEOUT_S
        fd: Optional[int] = None
        while fd is None:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                try:
                    age = time.time() - lock_path.stat().st_mtime
                except OSError:
                    age = 0.0
                if age > _LOCK_STALE_S:
                    try:
                        lock_path.unlink()
                    except OSError:
                        pass
                if time.monotonic() >= deadline:
                    raise ApprovalStoreError("timed out acquiring approval store lock")
                time.sleep(0.005)
        try:
            yield
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                lock_path.unlink()
            except OSError:
                pass

    # -- queries -----------------------------------------------------------

    def saved_patterns(self) -> tuple[tuple[str, str], ...]:
        """Return ``(action, pattern)`` pairs saved by ``always`` replies."""
        with self._lock:
            doc = self._load()
            return tuple(
                (str(e.get("action", "")), str(e.get("pattern", "")))
                for e in doc["allow_patterns"]
                if isinstance(e, dict) and e.get("action") and e.get("pattern")
            )

    def pending_for(self, session_id: str) -> tuple[ApprovalRequest, ...]:
        with self._lock:
            doc = self._load()
            return tuple(
                _request_from_dict(p) for p in doc["pending"]
                if isinstance(p, dict) and p.get("session_id") == session_id
            )

    def feedback_for(self, session_id: str) -> str:
        with self._lock:
            doc = self._load()
            for record in reversed(doc["rejections"]):
                if isinstance(record, dict) and record.get("session_id") == session_id:
                    return str(record.get("feedback", ""))
            return ""

    def _has_saved_allow(self, request: ApprovalRequest) -> bool:
        for entry in self._load()["allow_patterns"]:
            if not isinstance(entry, dict):
                continue
            if (wildcard_match(str(entry.get("action", "")), request.action,
                               case_sensitive=False)
                    and wildcard_match(str(entry.get("pattern", "")), request.resource)):
                return True
        return False

    @staticmethod
    def _configured_deny(request: ApprovalRequest,
                         configured_rules: Iterable[Rule]) -> Optional[Rule]:
        for rule in configured_rules:
            if rule.effect == EFFECT_DENY and rule.matches(request.action, request.resource):
                return rule
        return None

    @staticmethod
    def _pattern_denied(action: str, pattern: str,
                        configured_rules: Iterable[Rule]) -> Optional[Rule]:
        for rule in configured_rules:
            if (rule.effect == EFFECT_DENY
                    and wildcard_match(rule.action, action)
                    and wildcard_match(rule.resource, pattern)):
                return rule
        return None

    # -- mutations ---------------------------------------------------------

    def add_pending(self, request: ApprovalRequest) -> None:
        with self._lock:
            with self._file_lock():
                doc = self._load()
                doc["pending"].append(_request_to_dict(request))
                self._write_atomic(doc)
            self._doc = doc

    def reject_pending(self, session_id: str, feedback: str = "") -> tuple[ApprovalRequest, ...]:
        """Reject every pending request in the session (W3.9 ``reject``)."""
        with self._lock:
            with self._file_lock():
                doc = self._load()
                kept, rejected = [], []
                for entry in doc["pending"]:
                    if isinstance(entry, dict) and entry.get("session_id") == session_id:
                        rejected.append(_request_from_dict(entry))
                    else:
                        kept.append(entry)
                doc["pending"] = kept
                doc["rejections"].append({
                    "session_id": session_id,
                    "feedback": feedback,
                    "count": len(rejected),
                })
                self._write_atomic(doc)
            self._doc = doc
            return tuple(rejected)

    def decide(self, request: ApprovalRequest, reply: ApprovalReply | str, *,
               configured_rules: Iterable[Rule] = (),
               non_interactive: bool = False) -> ApprovalOutcome:
        """Resolve one approval request, persisting only tool-proposed patterns.

        Precedence: configured deny (hard floor) -> saved ``always`` pattern ->
        non-interactive fail-closed deny -> the user's ``once``/``always``/
        ``reject`` reply. ``always`` records only ``request.proposed_pattern``.
        """
        rules = tuple(configured_rules)
        try:
            reply_enum = ApprovalReply(reply)
        except ValueError as exc:
            raise ValueError(f"unknown approval reply: {reply!r}") from exc

        with self._lock:
            deny_rule = self._configured_deny(request, rules)
            if deny_rule is not None:
                return ApprovalOutcome(
                    Evaluation(Effect.DENY, matched_rule=deny_rule,
                               reason="configured deny rule; approval cannot grant"),
                    reply_enum)

            if self._has_saved_allow(request):
                return ApprovalOutcome(
                    Evaluation(Effect.ALLOW, reason="saved always-approval "
                                                  "(project-scoped pattern)"),
                    reply_enum)

            if non_interactive:
                return ApprovalOutcome(
                    Evaluation(Effect.DENY,
                               reason="no interactive responder; fail closed"),
                    reply_enum)

            if reply_enum is ApprovalReply.REJECT:
                return ApprovalOutcome(
                    Evaluation(Effect.DENY, reason="approval rejected by user"),
                    reply_enum)

            pattern = request.proposed_pattern.strip()
            if reply_enum is ApprovalReply.ONCE or not pattern:
                reason = ("allowed once" if reply_enum is ApprovalReply.ONCE
                          else "always reply had no tool-proposed pattern; "
                               "allowed once, nothing persisted")
                return ApprovalOutcome(Evaluation(Effect.ALLOW, reason=reason),
                                       reply_enum, persisted=False)

            # ALWAYS with a tool-proposed pattern: never override a deny.
            deny_rule = self._pattern_denied(request.action, pattern, rules)
            if deny_rule is not None:
                return ApprovalOutcome(
                    Evaluation(Effect.DENY, matched_rule=deny_rule,
                               reason="proposed pattern matches a configured deny"),
                    reply_enum)

            with _path_lock(self.path), self._file_lock():
                doc = self._load()
                key = (request.action, pattern)
                already = any(
                    isinstance(e, dict) and (e.get("action"), e.get("pattern")) == key
                    for e in doc["allow_patterns"]
                )
                if not already:
                    doc["allow_patterns"].append({
                        "action": request.action,
                        "pattern": pattern,
                        "project": self.project_id,
                        "source": "always",
                    })
                    self._write_atomic(doc)
            self._doc = doc
            return ApprovalOutcome(
                Evaluation(Effect.ALLOW, reason="always approval persisted "
                                                "(tool-proposed pattern)"),
                reply_enum, persisted=True)


# ---------------------------------------------------------------------------
# W3.10 - policy hard-deny layer
# ---------------------------------------------------------------------------

def apply_policy_floor(decision: Evaluation, policy_decision: Evaluation) -> Evaluation:
    """Return the more restrictive of two decisions; policy can never grant.

    ``allow -> ask -> deny`` is the restrictiveness ladder. The returned
    result keeps the authoritative decision's rule/reason metadata so a policy
    permit can never be mistaken for a grant.
    """
    effect = (policy_decision.effect
              if policy_decision.effect.restrictiveness > decision.effect.restrictiveness
              else decision.effect)
    reason = decision.reason
    if policy_decision.effect is Effect.DENY:
        reason = f"{reason}; policy hard-deny applied"
    elif policy_decision.effect is Effect.ASK and decision.effect is Effect.ALLOW:
        reason = f"{reason}; policy requires ask"
    return Evaluation(effect, matched_rule=decision.matched_rule, reason=reason,
                      authoritative=decision.authoritative)


def apply_policy_floors(decision: Evaluation, *policies: Evaluation) -> Evaluation:
    """Layer floors in order; pass managed/global policy last to override config."""
    result = decision
    for policy in policies:
        result = apply_policy_floor(result, policy)
    return result


# ---------------------------------------------------------------------------
# W3.12 - non-interactive approval behaviour
# ---------------------------------------------------------------------------

def resolve_noninteractive(decision: Evaluation, *,
                           approve_mode: str = APPROVE_NEVER) -> Evaluation:
    """Resolve an ASK when no human responder exists (``keel run``).

    Default ``never`` never auto-approves. ``rules-only`` permits an explicit
    allow rule to stand but still denies unanswered asks. Deny always survives.
    """
    if approve_mode not in VALID_APPROVE_MODES:
        raise ValueError(
            f"unknown approve mode {approve_mode!r}; "
            f"expected one of {sorted(VALID_APPROVE_MODES)}"
        )
    if decision.effect is not Effect.ASK:
        return decision
    if (approve_mode == APPROVE_RULES_ONLY
            and decision.matched_rule is not None
            and decision.matched_rule.effect == EFFECT_ALLOW):
        return Evaluation(Effect.ALLOW, matched_rule=decision.matched_rule,
                          reason="rules-only auto-approval",
                          authoritative=decision.authoritative)
    return Evaluation(Effect.DENY,
                      reason="no interactive responder; fail closed",
                      authoritative=decision.authoritative)
