"""A1.6/B3.4 — Settings → Policies UI wired to real capability operations."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TREES = [
    (ROOT / "desktop" / "ui" / "index.html", ROOT / "desktop" / "ui" / "app.js"),
    (ROOT / "site" / "app.html", ROOT / "site" / "ui" / "app.js"),
]
IDS = ("pane-policies", "policy-refresh", "policy-active", "policy-status",
       "policy-editor", "policy-validate", "policy-save", "policy-activate",
       "policy-deactivate", "policy-result", "policy-validation",
       "policy-test-command", "policy-test-run", "policy-test-result",
       "policy-egress")
CAPS = ("core.execpolicy.document", "core.execpolicy.validate",
        "core.execpolicy.save", "core.execpolicy.activate",
        "core.execpolicy.deactivate", "core.execpolicy.evaluate")


def test_both_trees_have_policy_panel():
    for html, js in TREES:
        h = html.read_text(encoding="utf-8")
        j = js.read_text(encoding="utf-8")
        assert 'data-section="policies"' in h, html.name
        for cid in IDS:
            assert f'id="{cid}"' in h, f"{html.name}: {cid}"
        assert "if (name === \"policies\") loadPolicy();" in j, js.name
        for cap in CAPS:
            assert cap in j, f"{js.name}: {cap}"


def test_policy_panel_has_real_states():
    for _, js in TREES:
        j = js.read_text(encoding="utf-8")
        for token in ("Invalid JSON", "Validation failed", "Save failed",
                      "Activation failed", "Could not read policy state",
                      "No active policy", "A policy is active"):
            assert token in j, token


def test_js_syntax():
    for _, js in TREES:
        result = subprocess.run(["node", "--check", str(js)],
                                cwd=ROOT, capture_output=True, text=True)
        assert result.returncode == 0, js.name + ": " + result.stderr


def test_no_placeholder_actions():
    for _, js in TREES:
        j = js.read_text(encoding="utf-8")
        assert "todo" not in j.lower()
        assert "alert(" not in j
