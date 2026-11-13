"""keel.context — token accounting + compaction (Phase 2, M5 shape).

Deterministic, no tokenizer dependency: byte-length heuristic, documented.
`estimate_tokens` is a *stable* estimator — deterministic across platforms —
not a model claim. M5's testable claims:

1. a compaction emits a boundary event naming the UUIDs of the preserved
   segment and the dropped head;
2. cumulativeDroppedTokens is monotonic within a session;
3. a thrash pattern is detected and the auto-compaction is disabled — never
   looped.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

BYTES_PER_TOKEN = 4


def estimate_tokens(messages: list[dict]) -> int:
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            text = content
        else:
            text = json.dumps(content, sort_keys=True, ensure_ascii=False)
        # provider-side framing overhead is deliberately ignored: this is an
        # internal budget heuristic, not a billing estimate
        total += math.ceil(len(text.encode("utf-8")) / BYTES_PER_TOKEN)
    return total


@dataclass
class Budget:
    context_window: int = 128_000
    reserved_output: int = 8_192
    soft_trigger_ratio: float = 0.65
    preserved_ratio: float = 0.40
    post_trigger_ratio: float = 0.50

    @property
    def usable(self) -> int:
        return max(self.context_window - self.reserved_output, 2048)

    @property
    def soft_limit(self) -> int:
        return int(self.usable * self.soft_trigger_ratio)

    @property
    def preserved_allowance(self) -> int:
        return int(self.usable * self.preserved_ratio)

    @property
    def post_limit(self) -> int:
        return int(self.usable * self.post_trigger_ratio)


@dataclass
class Selection:
    dropped: list[dict]
    preserved: list[dict]
    dropped_tokens: int
    pre_tokens: int
    index: int = 0


def select_preserved(messages: list[dict], budget: Budget) -> Selection | None:
    """Split messages into (dropped head, preserved tail).

    Preserves the longest tail whose token estimate fits the preserved
    allowance. Always preserves at least the most recent message. Returns
    None when nothing needs compacting.
    """
    pre_tokens = estimate_tokens(messages)
    if pre_tokens <= budget.soft_limit or len(messages) <= 2:
        return None
    kept: list[dict] = []
    tokens = 0
    for msg in reversed(messages):
        cost = estimate_tokens([msg])
        if kept and tokens + cost > budget.preserved_allowance:
            break
        kept.append(msg)
        tokens += cost
    kept.reverse()
    dropped = messages[: len(messages) - len(kept)]
    if not dropped:  # everything fit inside the preserved allowance anyway
        dropped = messages[:1]
        kept = messages[1:]
    dropped_tokens = estimate_tokens(dropped)
    return Selection(dropped=dropped, preserved=kept,
                     dropped_tokens=dropped_tokens, pre_tokens=pre_tokens)


@dataclass
class CompactionState:
    cumulative_dropped_tokens: int = 0
    compaction_count: int = 0
    disabled: bool = False
    disable_reason: str | None = None

    @property
    def thrash_detected(self) -> bool:
        return self.compaction_count >= 3


THRESHOLD_NOTE = (
    "auto-compact disabled: compaction fired 3+ times in one session "
    "(thrash). No further compaction will be attempted."
)
