"""keel.fakes — the determinism seams (Phase 1).

No production module may read the wall clock, draw randomness, open the
filesystem, or spawn a subprocess except through these seams. The slice
uses them exclusively.
"""

from __future__ import annotations

import json
import random
from typing import Any, Callable


class VirtualClock:
    def __init__(self, start_iso: str = "2026-01-01T00:00:00.000Z"):
        self._mono = 1_000_000.0
        self._iso = start_iso

    def now_iso(self) -> str:
        return self._iso

    def monotonic(self) -> float:
        return self._mono

    def sleep(self, seconds: float) -> None:
        self._mono += seconds


class SeededRng(random.Random):
    """PCG64-ish seeded generator; stable across runs on the same interpreter."""

    def __init__(self, seed: int = 0):
        super().__init__(seed)

    def getrandbits(self, k: int) -> int:  # noqa: D102 - stdlib contract
        return super().getrandbits(k)


class ScriptedModel:
    """Fake model: yields pre-scripted responses in order.

    script: list of responses; each response = list of blocks.
    A block is {"type": "text", "text": str} or
    {"type": "tool_use", "name": str, "input": dict}.
    after_script: block list appended when the script is exhausted.
    """

    def __init__(self, script: list[list[dict]], *,
                 model: str = "keel-fake-1",
                 after_script: list[dict] | None = None):
        self._script = list(script)
        self._after = after_script if after_script is not None else [
            {"type": "text", "text": "done"}
        ]
        self.model = model
        self.request_count = 0
        self.seen_messages: list[list[dict]] = []

    def complete(self, messages: list[dict], tools: list[dict]) -> list[dict]:
        self.request_count += 1
        self.seen_messages.append(list(messages))
        if self._script:
            return self._script.pop(0)
        return list(self._after)


class FakeToolExecutor:
    """Scripted tool executor.

    handlers: {tool_name: callable(input: dict) -> tuple[str, Any] | str}
    where the return is (inline_text, typed_payload) or just inline_text.
    """

    def __init__(self, handlers: dict[str, Callable[[dict], Any]] | None = None):
        self.handlers = handlers or {}
        self.calls: list[tuple[str, dict]] = []

    def invoke(self, name: str, tool_input: dict) -> tuple[str, Any]:
        self.calls.append((name, tool_input))
        handler = self.handlers.get(name)
        if handler is None:
            raise KeyError(f"no fake handler for tool {name!r}")
        out = handler(tool_input)
        if isinstance(out, tuple):
            return out
        return str(out), {"text": str(out)}


class InMemoryFileSystem:
    """Dict-backed FS. Records every opened path for the zero-ambient-reads assert."""

    def __init__(self, seed: dict[str, str] | None = None):
        self._files: dict[str, str] = dict(seed or {})
        self.opened: list[str] = []

    # normalise both separators to forward slashes for comparison
    @staticmethod
    def _norm(path: str) -> str:
        return path.replace("\\", "/")

    def makedirs(self, path: str) -> None:
        pass  # directories are implicit in the dict model

    def write_text(self, path: str, content: str) -> None:
        self.opened.append(self._norm(path))
        self._files[self._norm(path)] = content

    def read_text(self, path: str) -> str:
        self.opened.append(self._norm(path))
        return self._files[self._norm(path)]

    def exists(self, path: str) -> bool:
        self.opened.append(self._norm(path))
        return self._norm(path) in self._files

    def list_dir(self, path: str) -> list[str]:
        self.opened.append(self._norm(path))
        prefix = self._norm(path).rstrip("/") + "/"
        seen = set()
        for key in self._files:
            if key.startswith(prefix):
                rest = key[len(prefix):]
                seen.add(rest.split("/")[0])
        return sorted(seen)

    def files(self) -> dict[str, str]:
        return dict(self._files)


def dumps_compact(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
