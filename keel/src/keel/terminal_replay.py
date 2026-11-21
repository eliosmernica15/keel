"""Terminal recording and replay (C4.12).

Records typed commands and their outputs to a local JSONL file and replays
them deterministically. No shell is executed during replay.
"""

from __future__ import annotations

import json
import time
from pathlib import Path


class TerminalRecorder:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def record(self, command: str, output: str, *, exit_code: int = 0) -> dict:
        entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "command": str(command), "output": str(output)[:100000],
                 "exit_code": int(exit_code)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        return entry

    def entries(self) -> list[dict]:
        if not self.path.is_file():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
        return out

    def replay(self, sink) -> int:
        """Feed recorded entries to *sink*; returns the number replayed."""
        count = 0
        for entry in self.entries():
            sink(entry)
            count += 1
        return count
