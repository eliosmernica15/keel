"""Stabilization: one state root, real readiness, graceful process lifecycle.

All probes here are real: state is written to disk by a real ``python -m keel``
process, a real HTTP server is signalled, and the event log is verified after
restart. No frontend changes are involved.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
OWNED_SOURCES = (
    "keel/settings.py",
    "keel/settings_store.py",
    "keel/cli/main.py",
    "keel/commands.py",
    "keel/webapp.py",
)


# --------------------------------------------------------------------------
# 1. authoritative state-root resolution
# --------------------------------------------------------------------------

def test_state_root_precedence_and_absolute_paths(tmp_path, monkeypatch):
    from keel import settings

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("KEEL_STATE_DIR", raising=False)

    default = settings.default_state_root()
    assert default.is_absolute()
    assert default == home / ".keel"

    monkeypatch.setenv("KEEL_STATE_DIR", "relative-state")
    monkeypatch.chdir(tmp_path)
    relative = settings.default_state_root()
    assert relative.is_absolute()
    assert relative == tmp_path / "relative-state"

    explicit = tmp_path / "absolute-state"
    monkeypatch.setenv("KEEL_STATE_DIR", str(explicit))
    assert settings.default_state_root() == explicit

    # An empty variable is not a state root: fall back to the home default.
    monkeypatch.setenv("KEEL_STATE_DIR", "   ")
    assert settings.default_state_root() == default


def test_no_relative_keel_fallback_in_owned_sources():
    """Regression guard: no owned module may reintroduce `.keel` as a default."""
    bad_env = re.compile(
        r"os\.environ\.get\(\s*['\"]KEEL_STATE_DIR['\"]\s*,\s*['\"]\.keel['\"]")
    bad_home = re.compile(r"Path\.home\(\)\s*/\s*['\"]\.keel['\"]")
    for relative in OWNED_SOURCES:
        path = SRC / relative
        text = path.read_text(encoding="utf-8")
        if relative == "keel/webapp.py":
            # The workflow endpoint block is owned by the workflow agent;
            # this guard covers only the lifecycle/state-root code we own.
            marker = 'if path.startswith("/api/backend-workflows/")'
            if marker in text:
                text = text.split(marker, 1)[0]
        assert not bad_env.search(text), f"relative KEEL_STATE_DIR default in {relative}"
        assert not bad_home.search(text), f"Path.home()/.keel fallback in {relative}"


def test_cli_web_and_store_share_the_same_root(tmp_path, monkeypatch):
    from keel import settings_store, settings, webapp
    from keel.cli.main import _state_root

    root = (tmp_path / "runtime-state").resolve()
    monkeypatch.setenv("KEEL_STATE_DIR", str(root))
    expected = settings.default_state_root()
    assert expected == root
    assert _state_root() == expected
    assert webapp._state_root() == expected

    # CLI writes durable user state into that root.
    source = tmp_path / "notebook.md"
    source.write_text("# lifecycle\n", encoding="utf-8")
    env = dict(os.environ, KEEL_STATE_DIR=str(root), HOME=str(tmp_path / "home"),
               USERPROFILE=str(tmp_path / "home"), PYTHONPATH=str(SRC))
    (tmp_path / "home").mkdir(exist_ok=True)

    probe = subprocess.run(
        [sys.executable, "-c",
         "from keel import settings, settings_store; "
         "print(settings_store.STATE_DIR == settings.default_state_root())"],
        env=env, cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.strip() == "True"
    result = subprocess.run(
        [sys.executable, "-m", "keel", "notebook", "save", "lifecycle",
         str(source)], env=env, cwd=tmp_path, capture_output=True, text=True,
        timeout=60)
    assert result.returncode == 0, result.stderr
    assert (root / "notebooks" / "lifecycle.json").is_file()

    # The web runtime persists settings under the same root.
    monkeypatch.setattr(settings_store, "STATE_DIR", root)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", root / "settings.json")
    monkeypatch.setattr(settings_store, "BACKUP_PATH", root / "settings.json.bak")
    srv = webapp.make_server(0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        import http.client

        conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1],
                                          timeout=10)
        body = json.dumps({"ui": {"theme": "dark"}}).encode("utf-8")
        conn.request("POST", "/api/settings", body=body,
                     headers={"X-Keel-Token": webapp.token(),
                              "Content-Type": "application/json"})
        resp = conn.getresponse()
        assert resp.status == 200, resp.read().decode("utf-8")
        resp.read()
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)
    assert (root / "settings.json").is_file()


# --------------------------------------------------------------------------
# 2. health != readiness
# --------------------------------------------------------------------------

@contextlib.contextmanager
def _health_server():
    import http.client
    import threading

    import keel.webapp as webapp

    srv = webapp.make_server(0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()

    def get(path):
        conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1],
                                          timeout=10)
        conn.request("GET", path, headers={"X-Keel-Token": webapp.token()})
        resp = conn.getresponse()
        return resp.status, json.loads(resp.read().decode("utf-8"))

    try:
        yield webapp, get
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


@pytest.fixture
def health_server(monkeypatch, tmp_path):
    root = tmp_path / "health-state"
    root.mkdir()
    monkeypatch.setenv("KEEL_STATE_DIR", str(root))
    with _health_server() as fixture:
        yield fixture


def test_health_reports_real_readiness(health_server):
    _, get = health_server
    status, doc = get("/api/health")
    assert status == 200
    assert doc["ok"] is True              # liveness: the process answered
    assert doc["ready"] is True           # readiness: real probes passed
    assert doc["status"] == "ready"
    assert set(doc["dependencies"]) >= {"database", "events", "workers"}
    assert all(value == "ok" for value in doc["dependencies"].values())

    status, ready = get("/api/ready")
    assert status == 200 and ready["ready"] is True


@pytest.mark.parametrize("broken", ["database", "events", "workers"])
def test_health_never_claims_readiness_with_broken_dependency(
        monkeypatch, tmp_path, broken):
    import keel.webapp as webapp

    root = tmp_path / "bad-state"
    root.mkdir()
    monkeypatch.setenv("KEEL_STATE_DIR", str(root))
    original = webapp._readiness_dependencies

    def deps():
        probes = original()
        probes[broken] = lambda: (_ for _ in ()).throw(
            RuntimeError("injected dependency failure"))
        return probes

    monkeypatch.setattr(webapp, "_readiness_dependencies", deps)
    with _health_server() as (_, get):
        status, doc = get("/api/health")
        assert status == 200
        assert doc["ok"] is True
        assert doc["ready"] is False, f"{broken} failed but health claimed ready"
        assert doc["status"] == "running"
        assert doc["dependencies"][broken] == "error"
        status, ready = get("/api/ready")
        assert status == 503 and ready["ready"] is False


# --------------------------------------------------------------------------
# 3. graceful shutdown / restart durability in a real process
# --------------------------------------------------------------------------

def _clean_env(tmp_path, state_root: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return dict(os.environ, HOME=str(home), USERPROFILE=str(home),
                KEEL_STATE_DIR=str(state_root), PYTHONPATH=str(SRC))


class _Bridge:
    """A real `keel serve` child with its launch URL parsed from stderr."""

    def __init__(self, proc: subprocess.Popen, lines: list[str]):
        self.proc = proc
        self.lines = lines

    @property
    def url(self) -> str:
        for line in self.lines:
            match = re.search(r"running at (http://127\.0\.0\.1:\d+/\?t=\S+)", line)
            if match:
                return match.group(1)
        raise AssertionError(f"no launch URL in stderr: {self.lines!r}")

    @property
    def token(self) -> str:
        return self.url.split("?t=", 1)[1].strip()

    def wait_ready(self, timeout: float = 15.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(self.url.split("?t=")[0]
                                            + "/api/ready?t=" + self.token,
                                            timeout=2) as resp:
                    if resp.status == 200 and json.loads(resp.read())["ready"]:
                        return
            except (OSError, ValueError, KeyError, urllib.error.HTTPError):
                pass
            if self.proc.poll() is not None:
                raise AssertionError(f"server exited early: {self.lines!r}")
            time.sleep(0.1)
        raise AssertionError(f"server never became ready: {self.lines!r}")


def _start_bridge(tmp_path: Path, state_root: Path) -> _Bridge:
    env = _clean_env(tmp_path, state_root)
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(
        [sys.executable, "-m", "keel", "serve", "--port", "0"],
        env=env, cwd=tmp_path, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, bufsize=1, **kwargs)

    lines: list[str] = []
    ready = threading.Event()

    def reader():
        assert proc.stderr is not None
        for line in proc.stderr:
            lines.append(line)
            if "running at" in line:
                ready.set()

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    bridge = _Bridge(proc, lines)
    if not ready.wait(15):
        proc.kill()
        raise AssertionError(f"server did not print its URL: {lines!r}")
    bridge.wait_ready()
    return bridge


def _graceful_signal(proc: subprocess.Popen) -> None:
    """Send the platform's graceful-stop signal."""
    if os.name == "nt":
        # Windows cannot deliver SIGTERM to a Python handler; CTRL_BREAK_EVENT
        # is delivered to a new process group and maps to signal.SIGBREAK.
        proc.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        proc.send_signal(signal.SIGTERM)


def _stop_and_check(bridge: _Bridge) -> None:
    _graceful_signal(bridge.proc)
    try:
        code = bridge.proc.wait(timeout=25)
    except subprocess.TimeoutExpired:
        bridge.proc.kill()
        raise AssertionError(f"server ignored graceful stop: {bridge.lines!r}")
    assert code == 0, f"unclean exit {code}: {bridge.lines!r}"
    assert any("keel webapp stopped" in line for line in bridge.lines), \
        f"no shutdown report: {bridge.lines!r}"


def test_real_process_shutdown_and_restart_preserve_state(tmp_path):
    from keel.backend_observability import read_events, verify_chain

    state_root = (tmp_path / "durable-state").resolve()
    bridge = _start_bridge(tmp_path, state_root)

    source = tmp_path / "lifecycle.md"
    source.write_text("# durable\n", encoding="utf-8")
    env = _clean_env(tmp_path, state_root)
    saved = subprocess.run(
        [sys.executable, "-m", "keel", "notebook", "save", "lifecycle",
         str(source)], env=env, cwd=tmp_path, capture_output=True, text=True,
        timeout=60)
    assert saved.returncode == 0, saved.stderr
    assert (state_root / "notebooks" / "lifecycle.json").is_file()

    _stop_and_check(bridge)

    log = state_root / "observability.jsonl"
    assert log.is_file(), "shutdown did not flush a durable event log"
    assert verify_chain(state_root).ok
    actions = {
        (event.get("data") or {}).get("action")
        for event in read_events(state_root)
    }
    assert {"runtime_start", "runtime_shutdown"} <= actions

    # Restart: the same state root is reused, data is intact, readiness works.
    again = _start_bridge(tmp_path, state_root)
    again.wait_ready()
    listed = subprocess.run(
        [sys.executable, "-m", "keel", "notebook", "list"],
        env=env, cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert listed.returncode == 0, listed.stderr
    assert "lifecycle" in listed.stdout
    _stop_and_check(again)


@pytest.mark.skipif(os.name == "nt",
                    reason="SIGINT cannot be sent to a Windows console child "
                           "in a new process group; SIGBREAK/SIGTERM above "
                           "exercise the same graceful-stop path")
def test_sigint_is_a_graceful_stop(tmp_path):
    state_root = (tmp_path / "sigint-state").resolve()
    bridge = _start_bridge(tmp_path, state_root)
    bridge.proc.send_signal(signal.SIGINT)
    try:
        assert bridge.proc.wait(timeout=25) == 0, bridge.lines
    except subprocess.TimeoutExpired:
        bridge.proc.kill()
        raise
    assert (state_root / "observability.jsonl").is_file()


def test_shutdown_runtime_idempotent(tmp_path, monkeypatch):
    from keel import backend_observability as obs
    from keel import webapp

    root = (tmp_path / "direct-state").resolve()
    monkeypatch.setenv("KEEL_STATE_DIR", str(root))
    assert webapp.prepare_runtime() == root
    first = webapp.shutdown_runtime()
    assert first["signalled"] is True
    assert first["db_closed"] is True
    assert first["events_flushed"] is True
    assert webapp.shutdown_runtime() == {"already_shutdown": True}
    assert obs.verify_chain(root).ok
    actions = {(e.get("data") or {}).get("action") for e in obs.read_events(root)}
    assert {"runtime_start", "runtime_shutdown"} <= actions


# --------------------------------------------------------------------------
# 4. CLI workflow confirmation is forwarded to the policy boundary
# --------------------------------------------------------------------------

def test_cli_backend_workflow_forwards_confirm_to_prompt_policy(
        tmp_path, monkeypatch):
    """A saved `prompt` policy must ask once, then allow with CLI `--confirm`.

    The authoritative boundary returns `confirmation_required` without an
    explicit confirmation and never runs the handler.  The CLI's own `--confirm`
    gate must forward that approval to `run_workflow(confirmed=True)` so the
    same command proceeds instead of failing closed after the user confirmed.
    """
    from keel import backend_workflows as bw
    from keel.exec_policy import ExecPolicyStore

    root = (tmp_path / "workflow-policy-state").resolve()
    root.mkdir()
    monkeypatch.setenv("HOME", str(root))
    monkeypatch.setenv("USERPROFILE", str(root))
    monkeypatch.setenv("KEEL_STATE_DIR", str(root))
    ExecPolicyStore(root).save("default", {"prefix_rules": [
        {"pattern": ["backend.workflow", "approval"],
         "decision": "prompt", "justification": "operator consent required"}]})

    ledger = root / "backend-workflows" / "approval-results.jsonl"
    params = {
        "state_root": str(root), "action": "request", "operation": "fs_write",
        "scope": "cli:write", "subject": "cli-user", "ttl_seconds": 300,
    }
    env = dict(os.environ, HOME=str(root), USERPROFILE=str(root),
               KEEL_STATE_DIR=str(root), PYTHONPATH=str(SRC))

    # The saved policy really asks at the authoritative boundary, and asking
    # never reaches the handler.
    unconfirmed = bw.run_workflow(
        "approval", {**params, "idempotency_key": "direct-ask"}, confirmed=False)
    assert unconfirmed["code"] == "confirmation_required", unconfirmed
    assert not ledger.exists(), "no handler side effect before confirmation"

    # The CLI without --confirm fails its explicit gate; still no side effect.
    refused = subprocess.run(
        [sys.executable, "-m", "keel", "backend-workflow", "approval",
         "--params", json.dumps({**params,
                                 "idempotency_key": "cli-no-confirm"})],
        cwd=root, env=env, capture_output=True, text=True, timeout=120)
    assert refused.returncode == 1
    assert "requires --confirm" in refused.stderr
    assert not ledger.exists()

    # ...but an explicit --confirm is forwarded and the real handler runs.
    confirmed = subprocess.run(
        [sys.executable, "-m", "keel", "backend-workflow", "approval",
         "--params", json.dumps({**params,
                                 "idempotency_key": "cli-with-confirm"}),
         "--confirm"],
        cwd=root, env=env, capture_output=True, text=True, timeout=120)
    assert confirmed.returncode == 0, confirmed.stderr
    doc = json.loads(confirmed.stdout.strip())
    assert doc["ok"] is True, doc
    assert ledger.is_file(), "confirmed workflow must reach the handler"
    assert any(json.loads(line)["ok"] is True for line in
               ledger.read_text(encoding="utf-8").splitlines() if line.strip())
