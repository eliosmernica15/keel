"""Evaluation helpers (C11.6, C13.2, C13.3, C13.5, C4.7).

Local-only: official-build hash verification, LLM-as-judge scoring scaffold,
prompt regression snapshots, release trend storage, and a simple profiler.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


def verify_official_build(path: str | Path, expected_sha256: str) -> bool:
    data = Path(path).read_bytes()
    return hashlib.sha256(data).hexdigest().lower() == expected_sha256.lower()


def judge_trajectory(steps: list[dict], *, weights: dict | None = None) -> dict:
    weights = weights or {"success": 0.5, "efficiency": 0.3, "safety": 0.2}
    success = sum(1 for step in steps if step.get("ok")) / max(1, len(steps))
    efficiency = 1.0 / (1.0 + sum(1 for s in steps if s.get("retries", 0)))
    safety = 1.0 if not any(s.get("policy_violation") for s in steps) else 0.0
    score = (success * weights.get("success", 0.5)
             + efficiency * weights.get("efficiency", 0.3)
             + safety * weights.get("safety", 0.2))
    return {"score": round(score, 3), "success": round(success, 3),
            "efficiency": round(efficiency, 3), "safety": safety}


def prompt_regression(name: str, output: str, store: str | Path) -> bool:
    path = Path(store) / "prompt-goldens.json"
    doc = {}
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            doc = {}
    digest = hashlib.sha256(output.encode()).hexdigest()
    if name not in doc:
        doc[name] = digest
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return True
    return doc[name] == digest


class TrendStore:
    def __init__(self, state_root: str | Path):
        self.path = Path(state_root) / "release-trends.jsonl"

    def record(self, version: str, *, startup_ms: float, memory_mb: float,
               size_mb: float) -> dict:
        entry = {"version": version, "startup_ms": startup_ms,
                 "memory_mb": memory_mb, "size_mb": size_mb,
                 "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        return entry


def profile_call(fn, *args, **kwargs) -> dict:
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    return {"elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
            "result": result}
