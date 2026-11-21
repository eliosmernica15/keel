"""Agent intelligence helpers (C3.x).

Local heuristics for effort controls, pre-run estimates with confidence,
uncertainty policy, style learning, and failure postmortems. No hosted
service is involved; all records stay local.
"""

from __future__ import annotations

import json
import time
from pathlib import Path


def think_harder_effort(level: int) -> str:
    """Map a slider 0-3 to a reasoning effort label."""
    return {0: "minimal", 1: "low", 2: "medium", 3: "high"}.get(
        max(0, min(3, int(level))), "medium")


def estimate_run(prompt: str, *, tokens_per_second: float = 50.0) -> dict:
    words = len((prompt or "").split())
    est_tokens = max(1, int(words * 1.4))
    seconds = round(est_tokens / max(1.0, tokens_per_second), 2)
    # Confidence falls with size (longer tasks are less predictable).
    confidence = round(max(0.4, 1.0 - est_tokens / 10000), 3)
    return {"tokens": est_tokens, "seconds": seconds,
            "confidence": confidence, "basis": "local-token-heuristic"}


def uncertainty_policy(confidence: float, *, threshold: float = 0.6) -> str:
    if confidence >= threshold:
        return "proceed"
    if confidence >= threshold / 2:
        return "proceed_with_caveat"
    return "ask_user"


def record_postmortem(state_root: str | Path, task: str, error: str) -> dict:
    path = Path(state_root) / "postmortems.jsonl"
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "task": str(task)[:500], "error": str(error)[:1000]}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
    return entry


def learn_style(state_root: str | Path, sample: str) -> dict:
    """Derive lightweight style signals from an accepted sample."""
    path = Path(state_root) / "style-profile.json"
    profile = {"samples": 0, "avg_sentence_words": 0.0, "bullet_style": False}
    if path.is_file():
        try:
            profile = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    sentences = [s for s in sample.split(".") if s.strip()]
    avg = sum(len(s.split()) for s in sentences) / max(1, len(sentences))
    profile["samples"] = int(profile.get("samples", 0)) + 1
    profile["avg_sentence_words"] = round(avg, 2)
    profile["bullet_style"] = "\n- " in sample or sample.strip().startswith("- ")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    return profile
