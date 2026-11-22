"""A3.9 — Operator Admin page data aggregator.

Collects real local state from the existing runtime modules into one payload
for the Settings → Admin UI: startup health, resource budgets/meters, idle
state, feature flags, a bounded capability-audit tail and diagnostics status.
Nothing is simulated; if a subsystem has no data yet the field is empty and
the UI renders an explicit empty state.
"""

from __future__ import annotations

import json
import time
from pathlib import Path


def _alerts(health: dict, meters: list[dict], limits: dict) -> list[dict]:
    alerts = []
    failures = 0
    for value in (health or {}).values():
        if isinstance(value, dict):
            if value.get("ok") is False or value.get("last") == "failed":
                failures += int(value.get("failures", 1) or 1)
            else:
                failures += int(value.get("failures", 0) or 0)
        elif value is False:
            failures += 1
    if failures:
        alerts.append({"level": "warning", "title": "Failed starts recorded",
                       "detail": f"{failures} failed start outcome(s) in local health state."})
    for meter in meters:
        if meter.get("used", 0) > meter.get("cap", 0):
            alerts.append({"level": "warning", "title": "Resource cap exceeded",
                           "detail": f"{meter.get('feature')}: {meter['used']}/{meter['cap']}"})
    if isinstance(limits, dict) and limits.get("exceeded"):
        alerts.append({"level": "warning", "title": "Resource budget exceeded",
                       "detail": str(limits.get("exceeded"))})
    if not alerts:
        alerts.append({"level": "ok", "title": "No local alerts",
                       "detail": "All checked local subsystems report normally."})
    return alerts


def admin_overview(state_root: str | Path) -> dict:
    root = Path(state_root)
    from .admin_ops import IdleSuspend
    from .capabilities import audit_path
    from .diagnostics import collect
    from .feature_flags import FeatureFlags
    from .resource_caps import ResourceMeter
    from .resource_limits import ResourceManager
    from .start_health import _load as load_health

    health = load_health(str(root))
    meters = [m.__dict__ for m in ResourceMeter().meters()]
    limits = ResourceManager().status()
    idle = IdleSuspend(timeout_s=300)
    flags = FeatureFlags(root).all()
    audit_path_obj = audit_path(str(root))
    entries = []
    if audit_path_obj.is_file():
        try:
            entries = [json.loads(line) for line in
                       audit_path_obj.read_text(encoding="utf-8").splitlines()
                       if line.strip()][-50:]
        except (OSError, ValueError):
            entries = []
    bundles = collect()
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "health": health,
        "alerts": _alerts(health, meters, limits),
        "resources": {"meters": meters, "limits": limits},
        "background": {"timeout_s": idle.timeout_s, "suspended": idle.suspended},
        "flags": flags,
        "audit": {"count": len(entries), "entries": entries[-10:]},
        "diagnostics": {"available": bool(bundles), "note": "local diagnostics"},
        "local_only": True,
    }
