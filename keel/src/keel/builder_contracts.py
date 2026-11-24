"""keel.builder_contracts -- additive builder-process and UI-contract P0 model.

This is an *additive* module.  It does not edit any existing source file, test,
settings schema, UI stylesheet or registry.  Integration into the live runtime
is a separate lead decision (the exact seams are listed in
``master-plan-v6-builder-contracts-evidence.md``).

The six not_started P0 registry IDs are turned into real, testable Python
functionality:

  X10.1  definition-of-done template ....................... DOD_FIELDS, DefinitionOfDone, dod_template, validate_dod
  X10.2  provenance file generator ......................... CopiedSnippet, ProvenanceRecord, build_provenance, render_provenance
  X10.4  builder stop list (owner-paused actions) .......... Gate, StopListEntry, STOP_LIST, check_action, validate_stop_list
  X6.7   config validation + did-you-mean + JSONC .......... edit_distance, did_you_mean, validate_config_text, explain_key
  X8.1   local component catalog ........................... ComponentDescriptor, LOCAL_COMPONENT_CATALOG, catalog_manifest
  X8.2   design-token contract + hard-code lint ............ DEFAULT_TOKENS, validate_tokens, lint_source, tokens_json

Only the Python standard library is used.  There is no network, no subprocess,
no filesystem I/O, no SQL execution, no credential value and no import-time
side effect in this module.  There is no uuid/rng: every id and fingerprint is
a deterministic SHA-256 prefix of canonical JSON bytes.  All inputs are
validated and all outputs are immutable or freshly copied.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence


# ---------------------------------------------------------------------------
# shared helpers: canonical bytes, content hashes, typed errors
# ---------------------------------------------------------------------------


def canonical_bytes(value: Any) -> bytes:
    """Deterministic UTF-8 encoding used by every hash in this module."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class BuilderContractError(ValueError):
    """Base class for every typed builder-contract failure."""


class DoDError(BuilderContractError):
    """A definition-of-done template was malformed or incomplete."""


class ProvenanceError(BuilderContractError):
    """A provenance record omitted a spec source, license or reviewer."""


class StopListError(BuilderContractError):
    """A builder action is on the owner-paused stop list."""


class ConfigContractError(BuilderContractError):
    """A configuration document was invalid."""


class TokenContractError(BuilderContractError):
    """A token document or UI source broke the design-token contract."""


# ===========================================================================
# X10.1 -- definition-of-done template (per registry row)
# ===========================================================================

#: The six mandatory sections of a per-row definition of done (X10.1).
DOD_FIELDS: tuple[str, ...] = (
    "code_path",
    "test_path",
    "e2e_run_id",
    "docs_updated",
    "license_notice_check",
    "rollback_note",
)

DOD_FIELD_LABELS: dict[str, str] = {
    "code_path": "Code path",
    "test_path": "Test path",
    "e2e_run_id": "E2E run id",
    "docs_updated": "Docs updated",
    "license_notice_check": "License / notice check",
    "rollback_note": "Rollback note",
}


@dataclass(frozen=True)
class DefinitionOfDone:
    """A per-row definition of done.  Every field starts blank in a template."""

    feature_id: str
    code_path: str = ""
    test_path: str = ""
    e2e_run_id: str = ""
    docs_updated: str = ""
    license_notice_check: str = ""
    rollback_note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.feature_id, str) or not self.feature_id.strip():
            raise DoDError("definition of done needs a non-empty feature_id")

    @property
    def missing_fields(self) -> tuple[str, ...]:
        return tuple(name for name in DOD_FIELDS if not str(getattr(self, name)).strip())

    @property
    def complete(self) -> bool:
        return not self.missing_fields

    @property
    def fingerprint(self) -> str:
        return content_hash(self.to_dict())[:16]

    def to_dict(self) -> dict:
        doc: dict[str, Any] = {"feature_id": self.feature_id}
        for name in DOD_FIELDS:
            doc[name] = getattr(self, name)
        return doc

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DefinitionOfDone":
        d = dict(data)
        return cls(feature_id=str(d.get("feature_id") or ""),
                   **{name: str(d.get(name) or "") for name in DOD_FIELDS})

    def render_markdown(self) -> str:
        """Deterministic markdown checklist for the row."""
        lines = [f"## Definition of done — {self.feature_id}", ""]
        for name in DOD_FIELDS:
            value = str(getattr(self, name)).strip() or "(not filled)"
            box = "x" if str(getattr(self, name)).strip() else " "
            lines.append(f"- [{box}] {DOD_FIELD_LABELS[name]}: {value}")
        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class DoDValidation:
    ok: bool
    feature_id: str
    missing: tuple[str, ...] = ()
    fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "missing", tuple(self.missing))

    def to_dict(self) -> dict:
        return {"ok": self.ok, "feature_id": self.feature_id,
                "missing": list(self.missing), "fingerprint": self.fingerprint}


def dod_template(feature_id: str) -> DefinitionOfDone:
    """A blank, machine-checkable definition-of-done template for one row."""
    return DefinitionOfDone(feature_id=feature_id)


def validate_dod(dod: DefinitionOfDone) -> DoDValidation:
    if not isinstance(dod, DefinitionOfDone):
        raise DoDError("expected a DefinitionOfDone")
    missing = dod.missing_fields
    return DoDValidation(not missing, dod.feature_id, missing, dod.fingerprint)


# ===========================================================================
# X10.2 -- provenance file generator (per module)
# ===========================================================================

_UNKNOWN_LICENSES = frozenset({"", "unknown", "none", "n/a", "na", "tbd"})


@dataclass(frozen=True)
class CopiedSnippet:
    """A borrowed snippet: where it came from and under which license/notice."""

    source: str
    license: str
    excerpt: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or not self.source.strip():
            raise ProvenanceError("a copied snippet needs a source")
        if not isinstance(self.license, str) \
                or self.license.strip().lower() in _UNKNOWN_LICENSES:
            raise ProvenanceError("a copied snippet needs a concrete license/notice")
        object.__setattr__(self, "source", self.source.strip())
        object.__setattr__(self, "license", self.license.strip())

    def to_dict(self) -> dict:
        return {"source": self.source, "license": self.license,
                "excerpt": self.excerpt}


@dataclass(frozen=True)
class ProvenanceRecord:
    """Per-module provenance: spec source, copied snippets, reviewer."""

    module: str
    spec_source: str
    reviewer: str
    copied_snippets: tuple[CopiedSnippet, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        for label, value in (("module", self.module),
                             ("spec_source", self.spec_source),
                             ("reviewer", self.reviewer)):
            if not isinstance(value, str) or not value.strip():
                raise ProvenanceError(f"provenance needs a non-empty {label}")
        snippets = tuple(self.copied_snippets)
        if any(not isinstance(s, CopiedSnippet) for s in snippets):
            raise ProvenanceError("copied_snippets must be CopiedSnippet entries")
        object.__setattr__(self, "copied_snippets", snippets)

    @property
    def fingerprint(self) -> str:
        return content_hash(self.to_dict())[:16]

    def to_dict(self) -> dict:
        return {"module": self.module, "spec_source": self.spec_source,
                "reviewer": self.reviewer,
                "copied_snippets": [s.to_dict() for s in self.copied_snippets],
                "notes": self.notes}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProvenanceRecord":
        d = dict(data)
        return cls(
            module=str(d.get("module") or ""),
            spec_source=str(d.get("spec_source") or ""),
            reviewer=str(d.get("reviewer") or ""),
            copied_snippets=tuple(CopiedSnippet(
                source=str(s.get("source") or ""),
                license=str(s.get("license") or ""),
                excerpt=str(s.get("excerpt") or ""),
            ) for s in d.get("copied_snippets", ())),
            notes=str(d.get("notes") or ""),
        )


def build_provenance(module: str, spec_source: str, reviewer: str,
                     snippets: Sequence[CopiedSnippet] = (),
                     notes: str = "") -> ProvenanceRecord:
    return ProvenanceRecord(module=module, spec_source=spec_source,
                            reviewer=reviewer, copied_snippets=tuple(snippets),
                            notes=notes)


def validate_provenance(record: ProvenanceRecord) -> bool:
    if not isinstance(record, ProvenanceRecord):
        raise ProvenanceError("expected a ProvenanceRecord")
    _ = record.fingerprint  # re-validates all nested snippets
    return True


def render_provenance(record: ProvenanceRecord, *, fmt: str = "json") -> str:
    """Render a deterministic provenance file for one module."""
    validate_provenance(record)
    if fmt == "json":
        return json.dumps(record.to_dict(), sort_keys=True, indent=2,
                          ensure_ascii=False, allow_nan=False) + "\n"
    if fmt == "markdown":
        lines = [f"# Provenance — {record.module}", "",
                 f"- Spec source: {record.spec_source}",
                 f"- Reviewer: {record.reviewer}", "",
                 "## Copied snippets", ""]
        if record.copied_snippets:
            for snippet in record.copied_snippets:
                lines.append(f"- {snippet.excerpt or '(snippet)'}: "
                             f"{snippet.source} — {snippet.license}")
        else:
            lines.append("- None (original clean-room implementation).")
        if record.notes:
            lines.extend(("", record.notes))
        return "\n".join(lines) + "\n"
    raise ProvenanceError(f"unsupported provenance format: {fmt!r}")


# ===========================================================================
# X10.4 -- builder stop list: owner-paused actions mirrored from G1-G7
# ===========================================================================


class Gate(str, Enum):
    G1 = "G1"
    G2 = "G2"
    G3 = "G3"
    G4 = "G4"
    G5 = "G5"
    G6 = "G6"
    G7 = "G7"


#: Verbatim owner gates from DECISIONS.md D-034 (the authoritative decision log).
GATE_TITLES: dict[Gate, str] = {
    Gate.G1: "Changing repo visibility",
    Gate.G2: "Rewriting Git history or deleting branches/tags/releases",
    Gate.G3: "Publishing the first public binary release",
    Gate.G4: "Adding collaborators or CI deploy credentials",
    Gate.G5: "Adopting final EULA text",
    Gate.G6: "Paid service / payment / mandatory account",
    Gate.G7: "Publishing extension/SDK docs publicly",
}

GATE_DESCRIPTIONS: dict[Gate, str] = {
    Gate.G1: "Public<->private or any repo visibility change (Y6.4 stays paused).",
    Gate.G2: "Any history rewrite or deletion of branches, tags or releases.",
    Gate.G3: "First public binary release from the new distribution endpoint.",
    Gate.G4: "Adding collaborators or CI deploy credentials.",
    Gate.G5: "Owner legal name, governing law and lawyer review are required.",
    Gate.G6: "Payment, subscription, license-key enforcement or mandatory account.",
    Gate.G7: "Extension/SDK docs are private by default; publishing needs the owner.",
}

STOP_SOURCE = "DECISIONS.md D-034"
STOP_LIST_FILENAME = "builder-stop-list.json"

_CATEGORIES = frozenset({"owner_gate", "destructive_repo_action"})


@dataclass(frozen=True)
class StopListEntry:
    """One machine-readable action that always pauses for the owner."""

    id: str
    title: str
    description: str
    category: str
    requires_owner_approval: bool = True
    paused: bool = True
    source: str = STOP_SOURCE

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Z0-9-]+", str(self.id)):
            raise StopListError(f"invalid stop-list id: {self.id!r}")
        if not isinstance(self.title, str) or not self.title.strip():
            raise StopListError(f"stop-list entry {self.id} needs a title")
        if not isinstance(self.description, str) or not self.description.strip():
            raise StopListError(f"stop-list entry {self.id} needs a description")
        if self.category not in _CATEGORIES:
            raise StopListError(f"stop-list entry {self.id} has an unknown category")
        # Fail closed: a stop-list entry can never be marked auto-approved.
        if not self.requires_owner_approval or not self.paused:
            raise StopListError(f"stop-list entry {self.id} must stay paused")

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title,
                "description": self.description, "category": self.category,
                "requires_owner_approval": self.requires_owner_approval,
                "paused": self.paused, "source": self.source}


def _gate(gate: Gate) -> StopListEntry:
    return StopListEntry(id=gate.value, title=GATE_TITLES[gate],
                         description=GATE_DESCRIPTIONS[gate],
                         category="owner_gate")


def _destructive(entry_id: str, title: str, description: str) -> StopListEntry:
    return StopListEntry(id=entry_id, title=title, description=description,
                         category="destructive_repo_action")


#: The complete builder stop list: G1-G7 plus concrete destructive repo actions.
STOP_LIST: tuple[StopListEntry, ...] = (
    _gate(Gate.G1),
    _gate(Gate.G2),
    _gate(Gate.G3),
    _gate(Gate.G4),
    _gate(Gate.G5),
    _gate(Gate.G6),
    _gate(Gate.G7),
    _destructive("DR1", "Force-push or rewrite remote history",
                 "git push --force and equivalent remote history rewrites."),
    _destructive("DR2", "Hard reset that discards commits",
                 "git reset --hard or any reset that drops committed work."),
    _destructive("DR3", "Destructive working-tree cleanup",
                 "git clean -fdx, rm -rf or deletion of untracked files."),
    _destructive("DR4", "Force-remove worktrees",
                 "git worktree remove --force or removal of a dirty worktree."),
    _destructive("DR5", "Delete branches, tags or releases",
                 "git branch -D, git tag -d, or deleting a published release."),
    _destructive("DR6", "Rotate or delete production credentials / deploy keys",
                 "Any credential, signing key or deploy key removal/rotation."),
    _destructive("DR7", "Disable or delete CI / release protection config",
                 "Editing or removing the workflow that gates releases."),
)

#: Lowercase phrases that identify a gated/destructive action in a builder plan.
STOP_MATCH_TERMS: dict[str, tuple[str, ...]] = {
    "G1": ("repo visibility", "change visibility", "make repo public",
           "make repo private", "set visibility", "public repo", "private repo"),
    "G2": ("rewrite git history", "history rewrite", "delete branch",
           "delete tag", "delete release", "interactive rebase"),
    "G3": ("publish release", "public binary release", "first public release",
           "distribution endpoint"),
    "G4": ("add collaborator", "deploy credential", "ci credential",
           "grant collaborator", "add deploy key"),
    "G5": ("adopt eula", "final eula", "eula text", "governing law"),
    "G6": ("paid service", "payment", "subscription", "license key",
           "mandatory account", "paid plan"),
    "G7": ("publish extension docs", "publish sdk docs", "publish docs publicly",
           "public extension docs"),
    "DR1": ("force push", "git push --force", "force-push"),
    "DR2": ("git reset --hard", "hard reset"),
    "DR3": ("git clean -fdx", "rm -rf", "delete untracked"),
    "DR4": ("worktree remove --force", "remove worktree", "delete worktree"),
    "DR5": ("git branch -d", "git tag -d", "delete release"),
    "DR6": ("rotate credential", "delete credential", "delete deploy key",
            "rotate signing key", "revoke deploy key"),
    "DR7": ("disable ci", "delete ci", "remove release protection",
            "delete workflow"),
}


@dataclass(frozen=True)
class StopDecision:
    action: str
    paused: bool
    requires_owner_approval: bool
    matched_id: str = ""
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(self.reasons))

    def to_dict(self) -> dict:
        return {"action": self.action, "paused": self.paused,
                "requires_owner_approval": self.requires_owner_approval,
                "matched_id": self.matched_id, "reasons": list(self.reasons)}


@dataclass(frozen=True)
class StopListValidation:
    ok: bool
    errors: tuple[str, ...] = ()
    entry_count: int = 0
    fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "errors", tuple(self.errors))

    def to_dict(self) -> dict:
        return {"ok": self.ok, "errors": list(self.errors),
                "entry_count": self.entry_count, "fingerprint": self.fingerprint}


def find_stop_entry(action: str) -> StopListEntry | None:
    """Match a builder action by id first, then by a specific known phrase."""
    if not isinstance(action, str) or not action.strip():
        return None
    needle = action.strip().lower()
    by_id = {entry.id.lower(): entry for entry in STOP_LIST}
    if needle in by_id:
        return by_id[needle]
    for entry in STOP_LIST:
        if any(term in needle for term in STOP_MATCH_TERMS.get(entry.id, ())):
            return entry
    return None


def check_action(action: str) -> StopDecision:
    """Return the owner-pause decision for a proposed builder action."""
    entry = find_stop_entry(action)
    if entry is None:
        return StopDecision(action=action, paused=False,
                            requires_owner_approval=False)
    return StopDecision(
        action=action, paused=True, requires_owner_approval=True,
        matched_id=entry.id,
        reasons=(f"matched {entry.id}: {entry.title}",
                 f"owner gate / destructive action: {entry.category}",
                 "pause and request explicit owner approval before acting"))


def assert_not_paused(action: str) -> bool:
    """Raise when the builder plan contains a paused action (fail closed)."""
    decision = check_action(action)
    if decision.paused:
        raise StopListError("; ".join(decision.reasons))
    return True


def stop_list_document(entries: Sequence[StopListEntry] = STOP_LIST) -> dict:
    """The machine-readable file the builder must check before acting."""
    docs = [e.to_dict() for e in entries]
    return {"schema_version": 1, "source": STOP_SOURCE,
            "filename": STOP_LIST_FILENAME, "entries": docs,
            "fingerprint": content_hash(docs)[:16]}


def stop_list_json(entries: Sequence[StopListEntry] = STOP_LIST) -> str:
    return json.dumps(stop_list_document(entries), sort_keys=True, indent=2,
                      ensure_ascii=False, allow_nan=False) + "\n"


def validate_stop_list(entries: Sequence[StopListEntry] = STOP_LIST
                       ) -> StopListValidation:
    """Prove the stop list is complete: G1-G7 present once, all paused."""
    errors: list[str] = []
    ids = [e.id for e in entries]
    gates = {e.id for e in entries if e.category == "owner_gate"}
    expected = {g.value for g in Gate}
    if gates != expected:
        errors.append("stop list must mirror G1-G7 exactly")
    if len(ids) != len(set(ids)):
        errors.append("duplicate stop-list id")
    if not any(e.category == "destructive_repo_action" for e in entries):
        errors.append("stop list needs destructive repo actions")
    for entry in entries:
        if not entry.paused or not entry.requires_owner_approval:
            errors.append(f"{entry.id} is not fail-closed")
    fingerprint = content_hash([e.to_dict() for e in entries])[:16]
    return StopListValidation(not errors, tuple(errors), len(entries), fingerprint)


# ===========================================================================
# X6.7 -- config validation: did-you-mean, JSONC line/column, config explain
# ===========================================================================


def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance (insert / delete / substitute), case-sensitive."""
    if not isinstance(a, str) or not isinstance(b, str):
        raise TypeError("edit_distance expects two strings")
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            current.append(min(previous[j] + 1,      # deletion
                               current[j - 1] + 1,  # insertion
                               previous[j - 1] + cost))
        previous = current
    return previous[-1]


def _default_max_distance(word: str) -> int:
    return max(1, min(3, (len(word) + 1) // 2))


def did_you_mean(word: str, candidates: Iterable[str], *,
                 max_distance: int | None = None, limit: int = 3) -> tuple[str, ...]:
    """Rank typo suggestions by edit distance, then candidate name.

    Scoring is case-insensitive; the original spelling of each candidate is
    returned.  The result is deterministic and never includes the input itself.
    """
    if not isinstance(word, str):
        raise TypeError("did_you_mean expects a string word")
    limit = int(limit)
    if limit <= 0:
        return ()
    target = word.lower()
    allowed = _default_max_distance(target) if max_distance is None \
        else int(max_distance)
    scored: list[tuple[int, str, str]] = []
    seen: set[str] = set()
    for raw in candidates:
        candidate = str(raw)
        key = candidate.lower()
        if key == target or key in seen:
            continue
        seen.add(key)
        distance = edit_distance(target, key)
        if distance <= allowed:
            scored.append((distance, key, candidate))
    scored.sort(key=lambda item: (item[0], item[1]))
    return tuple(candidate for _, _, candidate in scored[:limit])


#: Known configuration keys used by the validator and by `keel config explain`.
KNOWN_CONFIG_KEYS: frozenset[str] = frozenset({
    "theme", "theme_file", "model", "small_model", "provider", "providers",
    "permissions", "tools", "max_tokens", "temperature", "top_p", "stream",
    "timeout", "retries", "context_window", "watcher", "plugins", "mcp",
    "voice", "fleet", "workspace", "editor", "telemetry", "locale",
    "keybinds", "log_level", "config_version",
})

CONFIG_KEY_DOCS: dict[str, str] = {
    "theme": "Built-in theme name used for colors, type and spacing.",
    "theme_file": "Path to a custom JSON theme file (private by default).",
    "model": "Default model id for the primary agent.",
    "small_model": "Model id used for titles, summaries and other small tasks.",
    "provider": "Default provider id for model requests.",
    "providers": "Per-provider connection settings.",
    "permissions": "Permission gates applied to tool calls.",
    "tools": "Enabled/disabled tool names.",
    "max_tokens": "Maximum output tokens per model response.",
    "temperature": "Sampling temperature for the primary model.",
    "top_p": "Nucleus-sampling probability mass.",
    "stream": "Whether model responses stream to the UI.",
    "timeout": "Request timeout in seconds.",
    "retries": "Number of retries on transient request failures.",
    "context_window": "Maximum context window size in tokens.",
    "watcher": "File-watcher ignore list and auto-update toggle.",
    "plugins": "Locally installed plugin descriptors.",
    "mcp": "MCP server registrations (private by default).",
    "voice": "Voice input/output and push-to-talk settings.",
    "fleet": "Multi-agent fleet configuration.",
    "workspace": "Per-agent workspace folder settings.",
    "editor": "Editor / $EDITOR open-in-place settings.",
    "telemetry": "Local-only usage counters; never sends data remotely.",
    "locale": "UI locale and language.",
    "keybinds": "Leader key and configurable keybindings.",
    "log_level": "Minimum log level (debug/info/warning/error).",
    "config_version": "Schema version of this configuration document.",
}


@dataclass(frozen=True)
class ConfigDiagnostic:
    key: str
    line: int
    column: int
    message: str
    suggestions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "suggestions", tuple(self.suggestions))

    def __str__(self) -> str:
        text = f"line {self.line} column {self.column}: {self.message}"
        if self.suggestions:
            text += f" (did you mean {', '.join(self.suggestions)}?)"
        return text

    def to_dict(self) -> dict:
        return {"key": self.key, "line": self.line, "column": self.column,
                "message": self.message, "suggestions": list(self.suggestions)}


@dataclass(frozen=True)
class ConfigValidation:
    ok: bool
    diagnostics: tuple[ConfigDiagnostic, ...] = ()
    key_count: int = 0
    fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    def to_dict(self) -> dict:
        return {"ok": self.ok,
                "diagnostics": [d.to_dict() for d in self.diagnostics],
                "key_count": self.key_count, "fingerprint": self.fingerprint}


@dataclass(frozen=True)
class ConfigExplanation:
    key: str
    found: bool
    description: str = ""
    suggestions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "suggestions", tuple(self.suggestions))

    @property
    def command(self) -> str:
        return f"keel config explain {self.key}"

    def render(self) -> str:
        if self.found:
            return f"{self.key}: {self.description}"
        if self.suggestions:
            return (f"unknown key {self.key!r}; did you mean "
                    f"{', '.join(self.suggestions)}? (try `{self.command}`)")
        return f"unknown key {self.key!r}"

    def to_dict(self) -> dict:
        return {"key": self.key, "found": self.found,
                "description": self.description,
                "suggestions": list(self.suggestions)}


def strip_jsonc(text: str) -> str:
    """Strip // and /* */ comments and trailing commas, preserving line/col.

    Comments are replaced by whitespace (newlines kept) so a JSON decode error
    still points at the right line and column of the original document.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    escaped = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] not in "\r\n":
                out.append(" ")
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            out.append("  ")
            i += 2
            while i < n and not (text[i] == "*" and i + 1 < n and text[i + 1] == "/"):
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            if i < n:
                out.append("  ")
                i += 2
            continue
        out.append(ch)
        i += 1
    cleaned = "".join(out)

    result: list[str] = []
    in_string = False
    escaped = False
    i = 0
    while i < len(cleaned):
        ch = cleaned[i]
        if in_string:
            result.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            result.append(ch)
            i += 1
            continue
        if ch == ",":
            j = i + 1
            while j < len(cleaned) and cleaned[j].isspace():
                j += 1
            if j < len(cleaned) and cleaned[j] in "}]":
                i += 1
                continue
        result.append(ch)
        i += 1
    return "".join(result)


def jsonc_key_positions(text: str) -> tuple[tuple[str, int, int], ...]:
    """Return (key, line, column) for every object key in a JSONC document."""
    positions: list[tuple[str, int, int]] = []
    i = 0
    line = 1
    column = 1
    n = len(text)

    def advance(ch: str) -> None:
        nonlocal line, column
        if ch == "\n":
            line += 1
            column = 1
        else:
            column += 1

    while i < n:
        ch = text[i]
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] not in "\r\n":
                i += 1
                column += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            column += 2
            while i < n and not (text[i] == "*" and i + 1 < n and text[i + 1] == "/"):
                c = text[i]
                i += 1
                advance(c)
            if i < n:
                i += 2
                column += 2
            continue
        if ch == '"':
            start_line, start_col = line, column
            raw: list[str] = []
            i += 1
            column += 1
            while i < n:
                c = text[i]
                if c == "\\" and i + 1 < n:
                    raw.append(c)
                    raw.append(text[i + 1])
                    i += 2
                    column += 2
                    continue
                if c == '"':
                    i += 1
                    column += 1
                    break
                raw.append(c)
                i += 1
                advance(c)
            j = i
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] == ":":
                key = "".join(raw)
                try:
                    key = json.loads('"' + key + '"')
                except (ValueError, TypeError):
                    pass
                positions.append((str(key), start_line, start_col))
            continue
        i += 1
        advance(ch)
    return tuple(positions)


def _collect_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(_collect_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_collect_keys(child))
    return keys


def validate_config_text(text: str, *,
                         known_keys: Iterable[str] = KNOWN_CONFIG_KEYS,
                         max_suggestions: int = 3) -> ConfigValidation:
    """Validate a JSONC config with did-you-mean and line/column diagnostics."""
    if not isinstance(text, str):
        raise ConfigContractError("config text must be a string")
    stripped = strip_jsonc(text)
    try:
        doc = json.loads(stripped)
    except json.JSONDecodeError as exc:
        diag = ConfigDiagnostic(key="", line=exc.lineno, column=exc.colno,
                                message=exc.msg)
        return ConfigValidation(
            False, (diag,), 0,
            content_hash([d.to_dict() for d in (diag,)])[:16])

    allowed = {str(k) for k in known_keys}
    positions = jsonc_key_positions(text)
    present = _collect_keys(doc)
    diagnostics: list[ConfigDiagnostic] = []
    for key, line, column in positions:
        if key in allowed:
            continue
        suggestions = did_you_mean(key, sorted(allowed), limit=max_suggestions)
        diagnostics.append(ConfigDiagnostic(
            key=key, line=line, column=column,
            message=f"unknown configuration key {key!r}" if key in present
                    else f"unparsed configuration key {key!r}",
            suggestions=suggestions))
    return ConfigValidation(
        not diagnostics, tuple(diagnostics), len(positions),
        content_hash([d.to_dict() for d in diagnostics])[:16])


def explain_key(key: str, *, docs: Mapping[str, str] = CONFIG_KEY_DOCS,
                max_suggestions: int = 3) -> ConfigExplanation:
    """Pure implementation of `keel config explain <key>`."""
    if not isinstance(key, str):
        raise ConfigContractError("config key must be a string")
    lowered = key.strip().lower()
    for name, description in docs.items():
        if name.lower() == lowered:
            return ConfigExplanation(key=key.strip(), found=True,
                                     description=description)
    suggestions = did_you_mean(lowered, sorted(docs), limit=max_suggestions)
    return ConfigExplanation(key=key.strip(), found=False,
                             suggestions=suggestions)


# ===========================================================================
# X8.2 -- design-token contract: tokens.json is the single source of style
# ===========================================================================

TOKEN_CATEGORIES: tuple[str, ...] = ("color", "type", "spacing", "radius", "motion")
_TOKEN_NAME_RE = re.compile(r"^[a-z][A-Za-z0-9._-]*$")

#: The canonical design-token document.  Only source of color/type/spacing/
#: radius/motion.  UI source must reference these names, never literal values.
DEFAULT_TOKENS: dict[str, dict[str, str]] = {
    "color": {
        "bg": "#101317",
        "surface": "#181c22",
        "fg": "#e8eaf0",
        "muted": "#9aa3b2",
        "border": "#2b313b",
        "accent": "#4c8dff",
        "success": "#2ecc71",
        "danger": "#ff5c5c",
        "warning": "#f0b429",
    },
    "type": {
        "family": "system-ui, sans-serif",
        "size.sm": "12px",
        "size.md": "14px",
        "size.lg": "18px",
        "weight.regular": "400",
        "weight.bold": "700",
        "lineHeight": "1.5",
    },
    "spacing": {
        "xs": "4px",
        "sm": "8px",
        "md": "12px",
        "lg": "16px",
        "xl": "24px",
    },
    "radius": {
        "sm": "4px",
        "md": "8px",
        "lg": "12px",
        "pill": "999px",
    },
    "motion": {
        "fast": "120ms",
        "normal": "200ms",
        "slow": "320ms",
        "easing": "ease-out",
    },
}


@dataclass(frozen=True)
class TokenDiagnostic:
    pointer: str
    message: str

    def __str__(self) -> str:
        return f"{self.pointer or '<root>'}: {self.message}"

    def to_dict(self) -> dict:
        return {"pointer": self.pointer, "message": self.message}


@dataclass(frozen=True)
class TokenValidation:
    ok: bool
    errors: tuple[TokenDiagnostic, ...] = ()
    categories: tuple[str, ...] = ()
    token_count: int = 0
    fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "errors", tuple(self.errors))

    def to_dict(self) -> dict:
        return {"ok": self.ok,
                "errors": [e.to_dict() for e in self.errors],
                "categories": list(self.categories),
                "token_count": self.token_count,
                "fingerprint": self.fingerprint}


def flatten_tokens(doc: Mapping[str, Mapping[str, str]]) -> dict[str, str]:
    """Flatten nested tokens into dotted references (e.g. color.accent)."""
    result: dict[str, str] = {}
    for category, tokens in doc.items():
        for name, value in tokens.items():
            result[f"{category}.{name}"] = value
    return result


def validate_tokens(doc: Any) -> TokenValidation:
    """Validate the design-token document's shape, categories and values."""
    errors: list[TokenDiagnostic] = []
    if not isinstance(doc, dict):
        return TokenValidation(False, (TokenDiagnostic(
            "", "tokens.json must be a JSON object"),))
    expected = set(TOKEN_CATEGORIES)
    actual = set(doc)
    for missing in sorted(expected - actual):
        errors.append(TokenDiagnostic(missing, "token category is missing"))
    for extra in sorted(actual - expected):
        errors.append(TokenDiagnostic(extra, "unknown token category"))
    token_count = 0
    for category in TOKEN_CATEGORIES:
        if category not in doc:
            continue
        tokens = doc[category]
        if not isinstance(tokens, dict):
            errors.append(TokenDiagnostic(category, "category must be an object"))
            continue
        if not tokens:
            errors.append(TokenDiagnostic(category, "category must not be empty"))
        for name, value in tokens.items():
            pointer = f"{category}.{name}"
            if not _TOKEN_NAME_RE.fullmatch(str(name)):
                errors.append(TokenDiagnostic(pointer, "invalid token name"))
            if not isinstance(value, str) or not value.strip():
                errors.append(TokenDiagnostic(pointer, "token value must be a non-empty string"))
            token_count += 1
    categories = tuple(sorted(c for c in actual if c in expected))
    fingerprint = content_hash(flatten_tokens(doc))[:16]
    return TokenValidation(not errors, tuple(errors), categories,
                           token_count, fingerprint)


def tokens_json(doc: Mapping[str, Mapping[str, str]] = DEFAULT_TOKENS) -> str:
    """Canonical `tokens.json` content (sorted keys, stable across runs)."""
    validation = validate_tokens(doc)
    if not validation.ok:
        raise TokenContractError("; ".join(str(e) for e in validation.errors))
    return json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=False,
                      allow_nan=False) + "\n"


@dataclass(frozen=True)
class HardcodedValue:
    kind: str
    value: str
    line: int
    column: int
    suggestion: str

    def __str__(self) -> str:
        return (f"line {self.line} column {self.column}: hard-coded "
                f"{self.kind} {self.value!r}; use {self.suggestion}")

    def to_dict(self) -> dict:
        return {"kind": self.kind, "value": self.value, "line": self.line,
                "column": self.column, "suggestion": self.suggestion}


@dataclass(frozen=True)
class LintReport:
    path: str
    findings: tuple[HardcodedValue, ...] = ()
    clean: bool = True
    fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", tuple(self.findings))

    def to_dict(self) -> dict:
        return {"path": self.path,
                "findings": [f.to_dict() for f in self.findings],
                "clean": self.clean, "fingerprint": self.fingerprint}


_HARDCODED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("color", re.compile(r"#[0-9a-fA-F]{3,8}\b")),
    ("color", re.compile(r"\brgba?\(\s*[^)]*\)")),
    ("length", re.compile(r"\b\d+(?:\.\d+)?(?:px|rem|em)\b")),
    ("motion", re.compile(r"\b\d+(?:\.\d+)?(?:ms|s)\b")),
)
_DEFAULT_TOKEN_FOR_KIND = {
    "color": "color.accent",
    "length": "spacing.md",
    "motion": "motion.normal",
}
_KIND_CATEGORY = {"color": "color", "length": "spacing", "motion": "motion"}


def _suggest_token(kind: str, value: str,
                   refs: Mapping[str, str],
                   first_by_value: Mapping[str, str]) -> str:
    """Prefer a same-category token whose value matches the literal exactly."""
    key = value.strip().lower()
    prefix = _KIND_CATEGORY[kind] + "."
    for ref, token_value in refs.items():
        if token_value.strip().lower() == key and ref.startswith(prefix):
            return ref
    return first_by_value.get(key, _DEFAULT_TOKEN_FOR_KIND[kind])


def lint_source(text: str, *,
                doc: Mapping[str, Mapping[str, str]] = DEFAULT_TOKENS,
                path: str = "") -> LintReport:
    """Lint rule: reject hard-coded color/type/spacing/radius/motion values.

    Every finding carries the original line/column and the token reference that
    should be used instead.  A value equal to a token's value suggests exactly
    that token; otherwise the category's default token is suggested.
    """
    if not isinstance(text, str):
        raise TokenContractError("lint source must be a string")
    refs = flatten_tokens(doc)
    first_by_value: dict[str, str] = {}
    for ref, value in refs.items():
        # First (canonical) reference wins shared values such as "12px".
        first_by_value.setdefault(value.strip().lower(), ref)
    findings: list[HardcodedValue] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in _HARDCODED_PATTERNS:
            for match in pattern.finditer(line):
                value = match.group(0)
                suggestion = _suggest_token(kind, value, refs, first_by_value)
                findings.append(HardcodedValue(
                    kind=kind, value=value, line=line_no,
                    column=match.start() + 1, suggestion=suggestion))
    findings.sort(key=lambda f: (f.line, f.column, f.kind, f.value))
    return LintReport(
        path=path, findings=tuple(findings), clean=not findings,
        fingerprint=content_hash([f.to_dict() for f in findings])[:16])


def assert_no_hardcoded_values(text: str, *,
                               doc: Mapping[str, Mapping[str, str]] = DEFAULT_TOKENS,
                               path: str = "") -> bool:
    report = lint_source(text, doc=doc, path=path)
    if not report.clean:
        raise TokenContractError("; ".join(str(f) for f in report.findings))
    return True


# ===========================================================================
# X8.1 -- local component catalog (every component in every state, tokens only)
# ===========================================================================


class ComponentState(str, Enum):
    DEFAULT = "default"
    HOVER = "hover"
    FOCUS = "focus"
    ACTIVE = "active"
    SELECTED = "selected"
    DISABLED = "disabled"
    ERROR = "error"
    LOADING = "loading"


@dataclass(frozen=True)
class ComponentDescriptor:
    name: str
    states: tuple[ComponentState, ...]
    token_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise TokenContractError("component needs a name")
        states = tuple(ComponentState(s) for s in self.states)
        if not states:
            raise TokenContractError(f"component {self.name} needs states")
        refs = tuple(str(r) for r in self.token_refs)
        if not refs:
            raise TokenContractError(f"component {self.name} needs token refs")
        object.__setattr__(self, "states", states)
        object.__setattr__(self, "token_refs", refs)

    def to_dict(self) -> dict:
        return {"name": self.name,
                "states": [s.value for s in self.states],
                "token_refs": list(self.token_refs)}


LOCAL_COMPONENT_CATALOG: tuple[ComponentDescriptor, ...] = (
    ComponentDescriptor("Button", (
        ComponentState.DEFAULT, ComponentState.HOVER, ComponentState.FOCUS,
        ComponentState.ACTIVE, ComponentState.DISABLED, ComponentState.LOADING),
        ("color.accent", "color.fg", "color.danger", "spacing.md",
         "radius.md", "motion.fast", "type.size.md")),
    ComponentDescriptor("TextField", (
        ComponentState.DEFAULT, ComponentState.HOVER, ComponentState.FOCUS,
        ComponentState.DISABLED, ComponentState.ERROR),
        ("color.surface", "color.border", "color.danger", "color.muted",
         "spacing.sm", "radius.sm", "type.size.md")),
    ComponentDescriptor("Checkbox", (
        ComponentState.DEFAULT, ComponentState.HOVER, ComponentState.FOCUS,
        ComponentState.SELECTED, ComponentState.DISABLED, ComponentState.ERROR),
        ("color.accent", "color.border", "color.fg", "spacing.xs", "radius.sm")),
    ComponentDescriptor("Tab", (
        ComponentState.DEFAULT, ComponentState.HOVER, ComponentState.ACTIVE,
        ComponentState.FOCUS, ComponentState.DISABLED),
        ("color.accent", "color.muted", "spacing.sm", "radius.sm", "type.size.md")),
    ComponentDescriptor("Menu", (
        ComponentState.DEFAULT, ComponentState.HOVER, ComponentState.FOCUS,
        ComponentState.DISABLED),
        ("color.surface", "color.border", "color.fg", "spacing.sm",
         "radius.md", "motion.fast")),
    ComponentDescriptor("Dialog", (
        ComponentState.DEFAULT, ComponentState.LOADING, ComponentState.ERROR),
        ("color.bg", "color.surface", "color.border", "color.fg",
         "spacing.lg", "radius.lg", "motion.normal")),
    ComponentDescriptor("Tooltip", (
        ComponentState.DEFAULT, ComponentState.ERROR),
        ("color.bg", "color.fg", "spacing.sm", "radius.sm",
         "motion.fast", "type.size.sm")),
    ComponentDescriptor("Badge", (
        ComponentState.DEFAULT, ComponentState.SELECTED, ComponentState.ERROR),
        ("color.muted", "color.success", "color.danger", "spacing.xs",
         "radius.pill", "type.size.sm")),
    ComponentDescriptor("Spinner", (
        ComponentState.DEFAULT, ComponentState.LOADING, ComponentState.DISABLED),
        ("color.accent", "motion.slow", "spacing.sm")),
)


@dataclass(frozen=True)
class CatalogValidation:
    ok: bool
    errors: tuple[str, ...] = ()
    component_count: int = 0
    variant_count: int = 0
    fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "errors", tuple(self.errors))

    def to_dict(self) -> dict:
        return {"ok": self.ok, "errors": list(self.errors),
                "component_count": self.component_count,
                "variant_count": self.variant_count,
                "fingerprint": self.fingerprint}


def validate_catalog(catalog: Sequence[ComponentDescriptor] = LOCAL_COMPONENT_CATALOG,
                     doc: Mapping[str, Mapping[str, str]] = DEFAULT_TOKENS
                     ) -> CatalogValidation:
    """Every state is shown and every token reference resolves in tokens.json."""
    errors: list[str] = []
    available = set(flatten_tokens(doc))
    names: set[str] = set()
    variants = 0
    for component in catalog:
        if not isinstance(component, ComponentDescriptor):
            errors.append("catalog entry is not a ComponentDescriptor")
            continue
        if component.name in names:
            errors.append(f"duplicate component {component.name}")
        names.add(component.name)
        if ComponentState.DEFAULT not in component.states:
            errors.append(f"component {component.name} lacks a default state")
        if len(set(component.states)) != len(component.states):
            errors.append(f"component {component.name} has duplicate states")
        for ref in component.token_refs:
            if ref not in available:
                errors.append(f"component {component.name} uses unknown token {ref}")
        variants += len(component.states)
    fingerprint = content_hash([c.to_dict() for c in catalog
                                if isinstance(c, ComponentDescriptor)])[:16]
    return CatalogValidation(not errors, tuple(errors), len(catalog),
                             variants, fingerprint)


def catalog_manifest(catalog: Sequence[ComponentDescriptor] = LOCAL_COMPONENT_CATALOG,
                     doc: Mapping[str, Mapping[str, str]] = DEFAULT_TOKENS) -> dict:
    """Deterministic component x state x token manifest for visual regression."""
    validation = validate_catalog(catalog, doc)
    if not validation.ok:
        raise TokenContractError("; ".join(validation.errors))
    flattened = flatten_tokens(doc)
    variants: list[dict] = []
    for component in catalog:
        for state in component.states:
            variants.append({
                "component": component.name,
                "state": state.value,
                "tokens": {ref: flattened[ref] for ref in component.token_refs},
            })
    manifest = {"schema_version": 1, "source": "tokens.json",
                "variants": variants, "component_count": len(catalog),
                "variant_count": len(variants)}
    manifest["fingerprint"] = content_hash(manifest)[:16]
    return manifest


def render_catalog_json(catalog: Sequence[ComponentDescriptor] = LOCAL_COMPONENT_CATALOG,
                        doc: Mapping[str, Mapping[str, str]] = DEFAULT_TOKENS) -> str:
    return json.dumps(catalog_manifest(catalog, doc), sort_keys=True, indent=2,
                      ensure_ascii=False, allow_nan=False) + "\n"


__all__ = [
    "BuilderContractError", "DoDError", "ProvenanceError", "StopListError",
    "ConfigContractError", "TokenContractError",
    "DOD_FIELDS", "DOD_FIELD_LABELS", "DefinitionOfDone", "DoDValidation",
    "dod_template", "validate_dod",
    "CopiedSnippet", "ProvenanceRecord", "build_provenance",
    "validate_provenance", "render_provenance",
    "Gate", "GATE_TITLES", "GATE_DESCRIPTIONS", "STOP_SOURCE",
    "STOP_LIST_FILENAME", "StopListEntry", "STOP_LIST", "STOP_MATCH_TERMS",
    "StopDecision", "StopListValidation", "find_stop_entry", "check_action",
    "assert_not_paused", "stop_list_document", "stop_list_json",
    "validate_stop_list",
    "edit_distance", "did_you_mean", "KNOWN_CONFIG_KEYS", "CONFIG_KEY_DOCS",
    "ConfigDiagnostic", "ConfigValidation", "ConfigExplanation",
    "strip_jsonc", "jsonc_key_positions", "validate_config_text", "explain_key",
    "TOKEN_CATEGORIES", "DEFAULT_TOKENS", "TokenDiagnostic",
    "TokenValidation", "flatten_tokens", "validate_tokens", "tokens_json",
    "HardcodedValue", "LintReport", "lint_source", "assert_no_hardcoded_values",
    "ComponentState", "ComponentDescriptor", "LOCAL_COMPONENT_CATALOG",
    "CatalogValidation", "validate_catalog", "catalog_manifest",
    "render_catalog_json",
]
