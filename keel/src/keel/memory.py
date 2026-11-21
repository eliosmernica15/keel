"""Local memory with provenance and tainted-source tracking (C6.5).

Records are append-only JSONL under ``state_root/memory.jsonl``. Every entry
records where it came from (session, tool, source) and whether that source is
trusted. Tainted records are excluded from recall by default so untrusted
content (web pages, remote providers, group chats) cannot silently become an
agent's beliefs.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

TAINTED_SOURCES = frozenset({
    "web_fetch", "web_search", "mcp", "fleet_history", "remote_provider",
    "group_chat", "untrusted",
})


class MemoryStore:
    def __init__(self, state_root: str):
        self.path = Path(state_root) / "memory.jsonl"

    def all_records(self) -> list[dict]:
        if not self.path.is_file():
            return []
        records = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                records.append(record)
        return records

    def add(self, content: str, *, source: str = "assistant",
            session_id: str = "", tool_name: str = "",
            trust: str = "trusted", tags: list | None = None) -> dict:
        text = str(content or "").strip()
        if not text:
            raise ValueError("memory content must not be empty")
        tainted = (trust == "untrusted" or source in TAINTED_SOURCES)
        record = {
            "id": uuid.uuid4().hex[:16],
            "content": text[:4000],
            "provenance": {
                "source": source,
                "session_id": session_id,
                "tool_name": tool_name,
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            "tainted": tainted,
            "tags": [str(tag) for tag in (tags or [])][:20],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def search(self, query: str, *, include_tainted: bool = False,
               limit: int = 20) -> list[dict]:
        needle = str(query or "").strip().lower()
        found = []
        for record in self.all_records():
            if record.get("tainted") and not include_tainted:
                continue
            if needle and needle not in record["content"].lower() \
                    and needle not in " ".join(record.get("tags", [])).lower():
                continue
            found.append(record)
        return found[-max(1, min(100, limit)):]

    def mark_trusted(self, record_id: str) -> bool:
        records = self.all_records()
        for record in records:
            if record.get("id") == record_id:
                record["tainted"] = False
                record["provenance"]["reviewed"] = True
                self._rewrite(records)
                return True
        return False

    def forget(self, record_id: str) -> bool:
        records = self.all_records()
        remaining = [r for r in records if r.get("id") != record_id]
        if len(remaining) == len(records):
            return False
        self._rewrite(remaining)
        return True

    def _rewrite(self, records: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
            + ("\n" if records else ""), encoding="utf-8")
