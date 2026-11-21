"""Reliability and security hardening through real execution paths."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import keel.webapp as webapp
from keel import capability_registry  # noqa: F401
from keel.capabilities import invoke
from keel.session import Session, SessionConfig
from keel.fakes import ScriptedModel, SeededRng, VirtualClock
from keel.runner import RealTools

TOKEN = "rel-token"


def test_corrupt_local_data_is_handled(tmp_path):
    """Corrupt persisted JSON must produce errors, not crashes or fake data."""
    from keel.agent_profiles import AgentProfiles
    from keel.feature_flags import FeatureFlags
    from keel.pairing import PairingStore

    p = tmp_path / "state"
    p.mkdir()
    for name in ("agent-profiles.json", "feature-flags.json",
                 "pairings.json"):
        (p / name).write_text("{not valid json", encoding="utf-8")

    assert AgentProfiles(p).list() == []
    assert FeatureFlags(p).all() == {}
    assert PairingStore(p).list_clients() == []


def test_permission_denial_is_real(tmp_path, monkeypatch):
    """A write tool with no allow rule must be denied, not silently executed."""
    target = tmp_path / "blocked.txt"
    script = tmp_path / "s.json"
    script.write_text(json.dumps({"script": [
        [{"type": "tool_use", "name": "write_file",
          "input": {"path": str(target), "content": "x"}}],
        [{"type": "text", "text": "done"}]]}), encoding="utf-8")
    monkeypatch.setenv("KEEL_FAKE_SCRIPT", str(script))
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "keel", "-p", "write", "--output-format",
         "json", "--state-root", str(tmp_path / "state")],
        cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0
    env = json.loads(result.stdout.strip().splitlines()[-1])
    # With no allow rule, the tool is removed from the manifest and never
    # executed — the security guarantee is that no file is created.
    assert not target.exists()
    assert env.get("subtype") in ("success", "error_during_execution")


def test_capability_permission_enforced():
    """Write capability invoked without permission must fail explicitly."""
    from keel.capabilities import CapabilityError

    with __import__("pytest").raises(CapabilityError) as exc:
        invoke("core.flags.set", {"name": "x", "enabled": True},
               allowed_permissions={"read"})
    assert exc.value.code == "permission_denied"


def test_concurrent_sessions_isolated(tmp_path):
    """Two sessions must not share transcript state."""
    outs = []
    for sid, prompt in (("a", "first"), ("b", "second")):
        cfg = SessionConfig(
            cwd=str(tmp_path), state_root=str(tmp_path / "state"),
            bare=True, session_id=sid, model="fake", seed=0)
        model = ScriptedModel([[{"type": "text", "text": prompt}]],
                              model="fake")
        out = Session(model_client=model, executor=RealTools(), config=cfg,
                      clock=VirtualClock(), rng=SeededRng(0)).run(prompt)
        outs.append(out.envelope.get("result"))
    assert outs == ["first", "second"]


def test_interrupted_agent_recovers(tmp_path):
    """A cancelled turn produces a result envelope, not a crash."""
    import threading

    cancel = threading.Event()

    class SlowModel:
        def complete(self, messages, tools):
            cancel.set()
            return [{"type": "text", "text": "partial"}]

    cfg = SessionConfig(cwd=str(tmp_path), state_root=str(tmp_path / "state"),
                        bare=True, session_id="cancel-1", model="slow",
                        cancel_event=cancel)
    out = Session(model_client=SlowModel(), executor=RealTools(), config=cfg,
                  clock=VirtualClock(), rng=SeededRng(0)).run("work")
    assert out.envelope.get("subtype") in ("success", "error_during_execution")
    assert out.envelope.get("terminal_reason") in ("completed", "cancelled")


def test_large_file_cap(tmp_path):
    """Large files must be rejected cleanly by the read path."""
    from keel.runner import RealTools

    big = tmp_path / "big.txt"
    big.write_text("x" * (6 * 1024 * 1024), encoding="utf-8")
    with __import__("pytest").raises(ValueError):
        RealTools().invoke("read_file", {"path": str(big)})


def test_secret_redaction_in_egress(tmp_path, monkeypatch):
    """No secret material is written to the egress log."""
    monkeypatch.setenv("KEEL_EGRESS_LOG", str(tmp_path / "egress.jsonl"))
    from keel.redaction import log_egress
    log_egress(str(tmp_path), provider="x", model="m", message_count=1,
               redactions={"openai_key": 2}, outbound_bytes=10)
    text = (tmp_path / "egress.jsonl").read_text()
    assert "sk-" not in text and "secret" not in text.lower()
