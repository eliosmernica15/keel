"""Per-vendor cost caps with daily and monthly windows (A3.10).

All state is local JSON under the Keel state directory. Costs are estimates
from token counts; no billing API or hosted service is involved.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

# Approximate USD per token (input, output). Override with set_cap-derived
# pricing later; labelled as an estimate wherever it is reported.
DEFAULT_RATES: dict[str, tuple[float, float]] = {
    "openrouter": (1e-6, 3e-6),
    "openai-compatible": (1e-6, 3e-6),
    "anthropic": (3e-6, 15e-6),
    "google": (0.25e-6, 1e-6),
    "nvidia": (0.5e-6, 1.5e-6),
}


def estimate_cost(provider: str, input_tokens: int = 0,
                  output_tokens: int = 0) -> float:
    rate_in, rate_out = DEFAULT_RATES.get(
        str(provider).lower(), (1e-6, 3e-6))
    return round(int(input_tokens) * rate_in + int(output_tokens) * rate_out, 8)


class CostCaps:
    def __init__(self, state_root: str):
        self.root = Path(state_root)
        self.caps_path = self.root / "cost-caps.json"
        self.usage_path = self.root / "cost-usage.jsonl"

    def caps(self) -> dict:
        if not self.caps_path.is_file():
            return {}
        try:
            doc = json.loads(self.caps_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return doc if isinstance(doc, dict) else {}

    def set_cap(self, provider: str, *, daily: float | None = None,
                monthly: float | None = None) -> dict:
        doc = self.caps()
        entry = dict(doc.get(provider, {}) or {})
        if daily is not None:
            entry["daily"] = float(daily)
        if monthly is not None:
            entry["monthly"] = float(monthly)
        doc[provider] = entry
        self.root.mkdir(parents=True, exist_ok=True)
        self.caps_path.write_text(
            json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return entry

    def record(self, provider: str, cost_usd: float, *, model: str = "",
               input_tokens: int = 0, output_tokens: int = 0) -> dict:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "provider": provider,
            "model": model,
            "cost_usd": round(float(cost_usd), 8),
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
        }
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.usage_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        return entry

    def totals(self, provider: str, window: str = "daily") -> float:
        now = time.gmtime()
        prefix = (time.strftime("%Y-%m-%d", now) if window == "daily"
                  else time.strftime("%Y-%m", now))
        if not self.usage_path.is_file():
            return 0.0
        total = 0.0
        for line in self.usage_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("provider") != provider:
                continue
            if not str(entry.get("ts", "")).startswith(prefix):
                continue
            total += float(entry.get("cost_usd", 0))
        return round(total, 8)

    def check(self, provider: str) -> tuple[bool, str]:
        caps = self.caps().get(provider, {}) or {}
        for window in ("daily", "monthly"):
            limit = caps.get(window)
            if limit is None:
                continue
            spent = self.totals(provider, window)
            if spent >= float(limit):
                return False, (f"{provider} {window} cost cap reached: "
                               f"${spent:.6f} >= ${float(limit):.6f}")
        return True, ""
