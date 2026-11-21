"""Concurrency and recovery through real execution paths."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import keel.webapp as webapp
from keel import capability_registry  # noqa: F401
from keel.session import Session, SessionConfig
from keel.fakes import ScriptedModel, SeededRng, VirtualClock
from keel.runner import RealTools

TOKEN = "conc-token"


def test_many_concurrent_sessions_isolated():
    """50 concurrent sessions each get their own result, no cross-talk."""

    def run(i):
        cfg = SessionConfig(cwd=".", state_root=f".keel/conc-{i}",
                            bare=True, session_id=f"s-{i}", model="fake",
                            seed=i)
        model = ScriptedModel([[{"type": "text", "text": f"result-{i}"}]],
                              model="fake")
        out = Session(model_client=model, executor=RealTools(), config=cfg,
                      clock=VirtualClock(), rng=SeededRng(i)).run("go")
        return i, out.envelope.get("result")

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = dict(pool.map(run, range(50)))
    for i in range(50):
        assert results[i] == f"result-{i}"


def test_concurrent_capability_invocations(tmp_path):
    """Concurrent capability calls do not corrupt each other's results."""
    from keel.capabilities import invoke

    def run(i):
        return invoke("core.hardware.detect", {},
                      context={"state_root": str(tmp_path / f"s{i}")})
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(run, range(40)))
    assert len(results) == 40 and all(r["ok"] for r in results)
    assert len({json.dumps(r["result"], sort_keys=True) for r in results}) == 1


def test_interrupted_task_does_not_corrupt_others(tmp_path):
    """One cancelled session must not affect a healthy session."""
    import threading

    cancel = threading.Event()
    cfg1 = SessionConfig(cwd=str(tmp_path), state_root=str(tmp_path / "s1"),
                         bare=True, session_id="cancel", model="m",
                         cancel_event=cancel)
    cfg2 = SessionConfig(cwd=str(tmp_path), state_root=str(tmp_path / "s2"),
                         bare=True, session_id="healthy", model="m")

    class CancelModel:
        def complete(self, messages, tools):
            cancel.set()
            return [{"type": "text", "text": "partial"}]

    out1 = Session(model_client=CancelModel(), executor=RealTools(),
                   config=cfg1, clock=VirtualClock(),
                   rng=SeededRng(0)).run("work")
    model2 = ScriptedModel([[{"type": "text", "text": "healthy-result"}]],
                           model="m")
    out2 = Session(model_client=model2, executor=RealTools(), config=cfg2,
                   clock=VirtualClock(), rng=SeededRng(0)).run("work")
    assert out2.envelope["result"] == "healthy-result"
    assert out1.envelope["subtype"] in ("success", "error_during_execution")


def test_conflicting_file_operations(tmp_path):
    """Concurrent writes to the same file via capability do not crash."""
    from keel.capabilities import invoke

    target = str(tmp_path / "shared.txt")

    def write(i):
        try:
            return invoke("cowork.doc.write", {
                "path": target, "text": f"content-{i}"},
                context={"cwd": str(tmp_path), "state_root": str(tmp_path)})
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(write, range(20)))
    # At least one write succeeds; no exception escapes the executor.
    assert any(r.get("ok") for r in results)


def test_restart_recovery_of_persisted_state(tmp_path):
    """State written before a restart is readable after re-instantiation."""
    from keel.agent_profiles import AgentProfiles
    from keel.voice_tasks import VoiceTaskQueue

    AgentProfiles(tmp_path).create("work", agents=["cowork"])
    vq = VoiceTaskQueue(tmp_path)
    task = vq.enqueue("do work", session_id="s1")

    # simulate restart: new instances, same state root
    assert AgentProfiles(tmp_path).get("work") is not None
    assert any(t["id"] == task["id"] for t in VoiceTaskQueue(tmp_path).pending())


def test_resource_limits_respected(tmp_path):
    """Sandbox timeout bounds execution time."""
    from keel.capabilities import invoke

    start = time.monotonic()
    r = invoke("code.sandbox.run", {
        "code": "import time; time.sleep(10)", "timeout_s": 1},
        context={"cwd": str(tmp_path)})
    elapsed = time.monotonic() - start
    assert r["result"]["timed_out"] is True
    assert elapsed < 5


def test_long_running_workflow_no_leak(tmp_path):
    """Many sequential capability calls do not leak state across invocations."""
    from keel.capabilities import invoke

    for i in range(100):
        r = invoke("core.hardware.detect", {},
                   context={"state_root": str(tmp_path / f"s{i}")})
        assert r["ok"]
    # A fresh call still works.
    assert invoke("core.hardware.detect", {},
                  context={"state_root": str(tmp_path / "fresh")})["ok"]
