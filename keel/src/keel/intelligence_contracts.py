"""Pure intelligence contracts for memory provenance, taint and scope.

This module defines immutable descriptors and small policy functions for the
project's memory/intelligence layer. It is deliberately stdlib-only and pure:
no host state, no persistence layer, no message transport and no wall-clock or
chance input is consulted. Callers own every identifier and every value; the
functions here only classify, derive, filter and score.

Security invariants (enforced by the tests in ``test_intelligence_contracts``):

* provenance records the producing session and tool and is preserved through
  every derived hop, so the origin of a fact is always recoverable;
* content originating from an untrusted source (web, document, MCP, remote
  provider, injected context, ...) is flagged and cannot be laundered by
  relabeling its source, by review annotations, by derivation or by a
  serialization round-trip;
* shared memories are visible to all agents while per-agent memories are
  visible only to their owner (missing owners fail closed);
* relevance scoring and ranking are deterministic functions of the supplied
  query and descriptors, with stable tie-breakers.

No files are read or written here; ``to_dict``/``from_dict`` return plain data
so callers may persist it through their own storage layer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Iterable

TRUSTED = "trusted"
UNTRUSTED = "untrusted"

# Sources whose content must always be treated as untrusted context rather
# than as an agent belief. Prefixed forms ("mcp:git", "web:example.org") and
# case variants are recognized by ``is_untrusted_source``.
UNTRUSTED_SOURCES = frozenset({
    "web", "web_fetch", "web_search", "doc", "document", "mcp",
    "remote_provider", "group_chat", "fleet_history", "clipboard",
    "screen_capture", "untrusted", "injected", "external",
})

# Word-level markers also catch compound and tool-prefixed source names.
UNTRUSTED_TOKENS = frozenset({
    "web", "fetch", "search", "doc", "document", "mcp", "remote",
    "provider", "group", "chat", "fleet", "history", "clipboard",
    "screen", "capture", "untrusted", "injected", "external",
    "url", "http", "https",
})


class MemoryScope(str, Enum):
    """Visibility of a memory record across agents."""

    SHARED = "shared"
    PER_AGENT = "per_agent"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return self.value


SHARED = MemoryScope.SHARED
PER_AGENT = MemoryScope.PER_AGENT


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def is_untrusted_source(source: Any) -> bool:
    """Return True when a source label denotes untrusted/injected content."""
    text = _norm(source)
    if not text:
        return False
    if text in UNTRUSTED_SOURCES:
        return True
    for marker in UNTRUSTED_SOURCES:
        if text.startswith(marker + ":") or text.startswith(marker + "/"):
            return True
    tokens = {tok for tok in re.split(r"[^a-z0-9]+", text) if tok}
    return bool(tokens & UNTRUSTED_TOKENS)


def source_trust(source: Any, requested: Any = None) -> str:
    """Classify trust for a source; untrusted sources override a claim."""
    if is_untrusted_source(source):
        return UNTRUSTED
    if requested is not None and _norm(requested) != TRUSTED:
        return UNTRUSTED
    return TRUSTED


def tokenize(text: Any) -> tuple[str, ...]:
    """Deterministic lowercase word tokens (no stemming or host data)."""
    return tuple(re.findall(r"[a-z0-9]+", _norm(text)))


@dataclass(frozen=True)
class Provenance:
    """Immutable origin descriptor for a memory.

    ``derived_from`` keeps the complete ancestry, so a derived hop can never
    erase an untrusted origin. ``reviewed_by`` is an annotation only: review
    does not change the trust decision.
    """

    source: str
    session_id: str = ""
    tool_name: str = ""
    trust: str = TRUSTED
    derived_from: tuple["Provenance", ...] = ()
    reviewed_by: tuple[str, ...] = ()

    @property
    def tainted(self) -> bool:
        if self.trust != TRUSTED or is_untrusted_source(self.source):
            return True
        return any(parent.tainted for parent in self.derived_from)

    def origins(self) -> tuple["Provenance", ...]:
        """Return the leaf origins (oldest ancestors) in derivation order."""
        if not self.derived_from:
            return (self,)
        found: list[Provenance] = []
        for parent in self.derived_from:
            for origin in parent.origins():
                if origin not in found:
                    found.append(origin)
        return tuple(found)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "session_id": self.session_id,
            "tool_name": self.tool_name,
            "trust": self.trust,
            "tainted": self.tainted,
            "derived_from": [p.to_dict() for p in self.derived_from],
            "reviewed_by": list(self.reviewed_by),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Provenance":
        """Rebuild a descriptor, recomputing taint from the lineage.

        A serialized ``tainted``/``trust`` field is never trusted as an
        authority: it is derived again from the recorded sources.
        """
        data = data or {}
        derived = tuple(cls.from_dict(p) for p in data.get("derived_from", ()))
        source = str(data.get("source", "") or "")
        trust = str(data.get("trust", TRUSTED) or TRUSTED)
        if is_untrusted_source(source):
            trust = UNTRUSTED
        return cls(
            source=source,
            session_id=str(data.get("session_id", "") or ""),
            tool_name=str(data.get("tool_name", "") or ""),
            trust=trust,
            derived_from=derived,
            reviewed_by=tuple(str(x) for x in data.get("reviewed_by", ())),
        )


def make_provenance(
    source: Any,
    *,
    session_id: Any = "",
    tool_name: Any = "",
    trust: Any = None,
    derived_from: Iterable[Provenance] = (),
    reviewed_by: Iterable[Any] = (),
) -> Provenance:
    """Build a provenance descriptor with source-based trust classification."""
    return Provenance(
        source=str(source or ""),
        session_id=str(session_id or ""),
        tool_name=str(tool_name or ""),
        trust=source_trust(source, trust),
        derived_from=tuple(derived_from),
        reviewed_by=tuple(str(x) for x in reviewed_by),
    )


def derive_provenance(
    base: Provenance,
    *,
    source: Any = "derived",
    session_id: Any = "",
    tool_name: Any = "",
    trust: Any = None,
) -> Provenance:
    """Add a derived hop while retaining the whole ancestry of ``base``.

    A caller may claim a trusted source and trust level for the new hop; the
    inherited taint is unaffected because ``Provenance.tainted`` consults the
    ancestors as well as the local fields.
    """
    return make_provenance(
        source,
        session_id=session_id,
        tool_name=tool_name,
        trust=trust,
        derived_from=(base,),
    )


def with_review(base: Provenance, *, reviewer: Any) -> Provenance:
    """Annotate a review without changing the trust decision."""
    return replace(base, reviewed_by=(*base.reviewed_by, str(reviewer)))


def promote_trust(base: Provenance, *, reviewer: Any = "") -> Provenance:
    """Legacy name for a review annotation; it does not promote trust.

    Trust can only originate at a trusted source. A tainted lineage is never
    converted into a clean one, so this function deliberately has the same
    effect as ``with_review``.
    """
    if reviewer:
        return with_review(base, reviewer=reviewer)
    return base


@dataclass(frozen=True)
class MemoryRecord:
    """An immutable memory descriptor with provenance, scope and flags."""

    memory_id: str
    content: str
    provenance: Provenance
    scope: MemoryScope = SHARED
    owner_agent: str = ""
    tags: tuple[str, ...] = ()

    @property
    def tainted(self) -> bool:
        return self.provenance.tainted

    def flags(self) -> tuple[str, ...]:
        """Human-readable labels describing trust and visibility."""
        result: list[str] = []
        if self.tainted:
            result.append("tainted")
        if any(is_untrusted_source(o.source) for o in self.provenance.origins()):
            result.append("untrusted_source")
        if self.provenance.reviewed_by:
            result.append("reviewed")
        if _scope(self.scope) == PER_AGENT:
            result.append("per_agent")
        return tuple(result)

    def to_dict(self) -> dict:
        return {
            "memory_id": self.memory_id,
            "content": self.content,
            "provenance": self.provenance.to_dict(),
            "scope": _scope(self.scope).value,
            "owner_agent": self.owner_agent,
            "tags": list(self.tags),
            "tainted": self.tainted,
            "flags": list(self.flags()),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryRecord":
        data = data or {}
        prov = data.get("provenance", {})
        return cls.from_payload(
            memory_id=str(data.get("memory_id", "") or ""),
            content=str(data.get("content", "") or ""),
            provenance=prov if isinstance(prov, Provenance)
            else Provenance.from_dict(prov),
            scope=data.get("scope", SHARED),
            owner_agent=data.get("owner_agent", ""),
            tags=data.get("tags", ()),
        )

    @classmethod
    def from_payload(
        cls,
        *,
        memory_id: Any,
        content: Any,
        provenance: Provenance,
        scope: Any = SHARED,
        owner_agent: Any = "",
        tags: Iterable[Any] = (),
    ) -> "MemoryRecord":
        return cls(
            memory_id=str(memory_id or ""),
            content=str(content or ""),
            provenance=provenance,
            scope=_scope(scope),
            owner_agent=str(owner_agent or ""),
            tags=tuple(str(t) for t in tags),
        )


def _scope(value: Any) -> MemoryScope:
    if isinstance(value, MemoryScope):
        return value
    try:
        return MemoryScope(_norm(value))
    except ValueError:
        # Unknown visibility values are never treated as permissive.
        return MemoryScope.UNKNOWN


def new_memory(
    memory_id: Any,
    content: Any,
    *,
    source: Any = "user",
    session_id: Any = "",
    tool_name: Any = "",
    scope: Any = SHARED,
    owner_agent: Any = "",
    tags: Iterable[Any] = (),
    trust: Any = None,
    derived_from: Iterable[Provenance] = (),
) -> MemoryRecord:
    """Create a memory record, classifying trust from its source."""
    text = str(content or "").strip()
    if not text:
        raise ValueError("memory content must not be empty")
    prov = make_provenance(
        source, session_id=session_id, tool_name=tool_name,
        trust=trust, derived_from=derived_from)
    return MemoryRecord.from_payload(
        memory_id=memory_id, content=text, provenance=prov,
        scope=scope, owner_agent=owner_agent, tags=tags)


def derive_memory(
    memory_id: Any,
    base: MemoryRecord,
    content: Any = None,
    *,
    source: Any = "derived",
    session_id: Any = "",
    tool_name: Any = "",
    trust: Any = None,
    tags: Iterable[Any] | None = None,
) -> MemoryRecord:
    """Derive a new record from ``base`` without laundering its lineage."""
    text = base.content if content is None else str(content or "").strip()
    if not text:
        raise ValueError("memory content must not be empty")
    prov = derive_provenance(
        base.provenance, source=source, session_id=session_id,
        tool_name=tool_name, trust=trust)
    return MemoryRecord.from_payload(
        memory_id=memory_id,
        content=text,
        provenance=prov,
        scope=base.scope,
        owner_agent=base.owner_agent,
        tags=base.tags if tags is None else tags,
    )


def can_access(record: MemoryRecord, agent_id: Any) -> bool:
    """Fail-closed visibility check for shared/per-agent memories."""
    scope = _scope(record.scope)
    if scope == SHARED:
        return True
    if scope == PER_AGENT:
        owner = str(record.owner_agent or "")
        return bool(owner) and bool(agent_id) and owner == str(agent_id)
    return False


def visible_records(
    records: Iterable[MemoryRecord], *, agent_id: Any = ""
) -> tuple[MemoryRecord, ...]:
    """Filter records by the caller's agent visibility."""
    return tuple(r for r in records if can_access(r, agent_id))


def relevance_score(query: Any, record: MemoryRecord) -> float:
    """Pure, deterministic cosine-style relevance in the range [0, 1].

    Word overlap with the content dominates, matching tags give a smaller
    bonus, and untrusted lineage is penalized so flagged content cannot win a
    recall simply by repeating query words. No host state is read.
    """
    q = frozenset(tokenize(query))
    if not q:
        return 0.0
    content_tokens = frozenset(tokenize(record.content))
    tag_tokens = frozenset(tokenize(" ".join(record.tags)))
    overlap = len(q & content_tokens)
    tag_overlap = len(q & tag_tokens)
    if not overlap and not tag_overlap:
        return 0.0
    raw = (overlap + 0.5 * tag_overlap) / (
        len(q) ** 0.5 * max(1, len(content_tokens)) ** 0.5)
    score = min(1.0, raw)
    if record.tainted:
        score *= 0.25
    return round(score, 6)


def _stable_key(record: MemoryRecord) -> str:
    """Stable last-resort tie-breaker derived only from descriptor data."""
    return json.dumps(record.provenance.to_dict(), sort_keys=True,
                      ensure_ascii=False)


@dataclass(frozen=True)
class RankedMemory:
    """A scored record; returned in tuples so results are immutable."""

    record: MemoryRecord
    score: float


def rank_memories(
    query: Any,
    records: Iterable[MemoryRecord],
    *,
    agent_id: Any = "",
    include_tainted: bool = False,
    limit: int | None = None,
) -> tuple[RankedMemory, ...]:
    """Score, filter and rank memories deterministically.

    Scope visibility is always enforced. Tainted records are excluded unless
    explicitly requested; when included they are penalized and still carry
    their flags and full provenance. Ordering is independent of input order:
    score descending, then memory id, then a serialized provenance key.
    """
    candidates = [
        r for r in visible_records(records, agent_id=agent_id)
        if include_tainted or not r.tainted
    ]
    ranked = [RankedMemory(record=r, score=relevance_score(query, r))
              for r in candidates]
    ranked.sort(key=lambda item: (-item.score, item.record.memory_id,
                                  _stable_key(item.record)))
    if limit is not None:
        ranked = ranked[:max(0, int(limit))]
    return tuple(ranked)


__all__ = [
    "PER_AGENT", "SHARED", "TRUSTED", "UNTRUSTED",
    "MemoryRecord", "MemoryScope", "Provenance", "RankedMemory",
    "can_access", "derive_memory", "derive_provenance", "is_untrusted_source",
    "make_provenance", "new_memory", "promote_trust", "rank_memories",
    "relevance_score", "source_trust", "tokenize", "visible_records",
    "with_review",
]
