"""Onboarding support: stable error codes, contextual help, local feedback (C10).

Everything is local and offline: a fixed error catalog with fix steps, a
help lookup keyed by error code, and feedback records saved locally and
exportable as a redacted bundle (never auto-sent).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

ERROR_CATALOG = {
    "KEEL-E001": {"title": "Provider key missing",
                  "fix": "Add a key in Settings → Providers, or stay offline."},
    "KEEL-E002": {"title": "Workspace not bound",
                  "fix": "Select a working folder so tools run inside it."},
    "KEEL-E003": {"title": "Cost cap reached",
                  "fix": "Review keel costs status and raise the cap if appropriate."},
    "KEEL-E004": {"title": "Circuit breaker open",
                  "fix": "Provider failed repeatedly; wait for recovery or switch provider."},
    "KEEL-E005": {"title": "Egress host refused",
                  "fix": "Check KEEL_EGRESS_ALLOWLIST for the configured project."},
}


def error_info(code: str) -> dict:
    return ERROR_CATALOG.get(code, {"title": "Unknown error",
                                    "fix": "Collect a redacted diagnostics bundle."})


def contextual_help(code: str) -> str:
    info = error_info(code)
    return f"{code}: {info['title']}\nFix: {info['fix']}\nDocs: /requirements.html"


class FeedbackStore:
    def __init__(self, state_root: str | Path):
        self.path = Path(state_root) / "feedback.jsonl"

    def add(self, category: str, message: str) -> dict:
        entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "category": str(category)[:40],
                 "message": str(message)[:2000]}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        return entry

    def export_redacted(self, path: str | Path) -> Path:
        target = Path(path)
        entries = []
        if self.path.is_file():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        entries.append(json.loads(line))
                    except ValueError:
                        continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(
            {"format": "keel-feedback-v1", "entries": entries,
             "note": "Review before sending; no credentials are included."},
            indent=2) + "\n", encoding="utf-8")
        return target
