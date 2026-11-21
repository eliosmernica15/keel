"""CLI extras (A1.17, A1.18, A1.20): stats, agent/model/auth commands, env overrides."""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from pathlib import Path


def usage_stats(state_root: str | Path) -> dict:
    """Summarise usage rows by model and day from the local usage ledger."""
    path = Path(state_root) / "cost-usage.jsonl"
    by_model: Counter = Counter()
    by_day: defaultdict[str, float] = defaultdict(float)
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            import json
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            by_model[entry.get("model", "unknown")] += 1
            day = str(entry.get("ts", ""))[:10]
            by_day[day] += float(entry.get("cost_usd", 0))
    return {"by_model": dict(by_model),
            "by_day": {k: round(v, 6) for k, v in by_day.items()}}


def env_overrides() -> dict:
    """Report which KEEL_* environment variables are set (values masked)."""
    result = {}
    for key, value in sorted(os.environ.items()):
        if key.startswith("KEEL_"):
            result[key] = "set" if value else "empty"
    return result


def create_agent_spec(name: str, *, model: str = "keel-fake-1",
                      surface: str = "code") -> dict:
    return {"name": str(name)[:64], "model": model, "surface": surface,
            "notes": ""}
