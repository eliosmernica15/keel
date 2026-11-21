"""A3.10 — per-vendor cost caps with daily and monthly windows."""

from __future__ import annotations

import json

from keel.cli.main import main
from keel.cost_caps import CostCaps, estimate_cost


def test_estimate_cost_uses_provider_rates():
    assert estimate_cost("google", 1_000_000, 0) == 0.25
    assert estimate_cost("anthropic", 0, 1_000_000) == 15.0
    assert estimate_cost("unknown-provider", 0, 0) == 0.0


def test_caps_and_windows(tmp_path):
    manager = CostCaps(str(tmp_path))
    manager.set_cap("openrouter", daily=1.0, monthly=10.0)
    assert manager.caps()["openrouter"] == {"daily": 1.0, "monthly": 10.0}
    manager.record("openrouter", 0.4)
    manager.record("openrouter", 0.5)
    manager.record("google", 5.0)
    assert manager.totals("openrouter", "daily") == 0.9
    assert manager.totals("openrouter", "monthly") == 0.9
    assert manager.totals("google", "daily") == 5.0
    assert manager.check("openrouter")[0] is True
    manager.record("openrouter", 0.2)
    allowed, reason = manager.check("openrouter")
    assert allowed is False and "daily" in reason
    assert manager.check("google")[0] is True  # no cap configured


def test_cli_costs_commands(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("KEEL_STATE_DIR", str(tmp_path))
    assert main(["costs", "cap", "openrouter", "--daily", "2",
                 "--monthly", "20"]) == 0
    capsys.readouterr()
    assert main(["costs", "status"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["openrouter"]["caps"]["daily"] == 2.0
    assert main(["costs", "bogus"]) == 1
