"""Golden-file and chaos test helpers (B7.2).

A tiny deterministic snapshot utility: render a prompt, normalise it, and
compare against a stored golden file with an explicit update path. Chaos tests
can inject a mid-turn failure via a deterministic fault hook.
"""

from __future__ import annotations

import difflib
import hashlib
from pathlib import Path


def normalise(text: str) -> str:
    return "\n".join(line.rstrip() for line in str(text).strip().splitlines())


def digest(text: str) -> str:
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


def check_golden(text: str, path: str | Path, *, update: bool = False) -> bool:
    target = Path(path)
    rendered = normalise(text) + "\n"
    if update:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
        return True
    if not target.is_file():
        return False
    expected = target.read_text(encoding="utf-8")
    return normalise(expected) == normalise(rendered)


def golden_diff(text: str, path: str | Path) -> str:
    target = Path(path)
    expected = target.read_text(encoding="utf-8").splitlines() if target.is_file() else []
    actual = normalise(text).splitlines()
    return "\n".join(difflib.unified_diff(expected, actual, "golden", "actual"))


class ChaosFault(RuntimeError):
    """Raised by an injected fault to simulate a mid-turn failure."""


def maybe_inject(fail_on_call: int, call_index: int) -> None:
    if fail_on_call and call_index == fail_on_call:
        raise ChaosFault(f"injected failure at call {call_index}")
