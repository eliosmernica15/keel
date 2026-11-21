"""Voice-to-task handoff (A2.1/A2.2 upgrade).

A durable local queue where dictated transcripts become tasks for the same
agent/session, with confirmation before execution and status tracking.
"""

from __future__ import annotations

import json
import time
from pathlib import Path


class VoiceTaskQueue:
    def __init__(self, state_root: str | Path):
        self.path = Path(state_root) / "voice-tasks.json"

    def _load(self) -> list[dict]:
        if not self.path.is_file():
            return []
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
            return doc if isinstance(doc, list) else []
        except (OSError, ValueError):
            return []

    def _save(self, items: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(items, indent=2) + "\n", encoding="utf-8")

    def enqueue(self, transcript: str, *, session_id: str,
                confidence: float = 1.0) -> dict:
        task = {"id": f"vt-{int(time.time() * 1000)}",
                "transcript": str(transcript)[:4000],
                "session_id": session_id,
                "confidence": round(float(confidence), 3),
                "status": "pending_confirmation",
                "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        items = self._load()
        items.append(task)
        self._save(items)
        return task

    def confirm(self, task_id: str) -> dict | None:
        items = self._load()
        for task in items:
            if task.get("id") == task_id:
                task["status"] = "ready"
                task["confirmed"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                  time.gmtime())
                self._save(items)
                return task
        return None

    def pending(self) -> list[dict]:
        return [task for task in self._load()
                if task.get("status") == "pending_confirmation"]

    def take_ready(self, session_id: str) -> dict | None:
        items = self._load()
        for task in items:
            if task.get("status") == "ready" and task.get("session_id") == session_id:
                task["status"] = "running"
                self._save(items)
                return task
        return None

    def complete(self, task_id: str, *, result: str = "") -> bool:
        items = self._load()
        for task in items:
            if task.get("id") == task_id:
                task["status"] = "completed"
                task["result"] = result[:2000]
                self._save(items)
                return True
        return False
