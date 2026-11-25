"""Regressions for independent-review findings F10/F11."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from keel.exec_policy import ExecPolicyStore


def test_policy_store_atomic_saves_under_concurrency(tmp_path):
    store = ExecPolicyStore(tmp_path)
    doc = {"prefix_rules": [{"pattern": ["ls"]}], "network_rules": []}

    def writer():
        for _ in range(20):
            store.save("default", doc)

    threads = [threading.Thread(target=writer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    loaded = json.loads((tmp_path / "exec-policies" / "default.json").read_text())
    assert loaded["prefix_rules"][0]["pattern"] == ["ls"]
    assert not list((tmp_path / "exec-policies").glob("*.tmp-*"))


def test_web_confirmation_is_forwarded_to_policy_context():
    source = (Path(__file__).resolve().parents[1] / "src" / "keel" /
              "webapp.py").read_text(encoding="utf-8")
    # The web capability surface derives the strict boolean from the request
    # before building the policy context (workflow hardening renamed the local
    # variable but kept the same behavior).
    assert '"confirm": confirmed' in source
    assert '"interactive": True' in source
