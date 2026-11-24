"""End-to-end tests for the integrated backend product workflows.

Every test calls the real backend modules through ``backend_workflows`` and
checks durable artifacts (JSONL ledgers, session files, replay HTML, sync
logs). No internal service is mocked; only the process-wide state root is
redirected to a temporary directory.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from keel import backend_workflows as bw
from keel import session_contracts
from keel import settings
from keel import webapp


@pytest.fixture
def state_root(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("KEEL_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "default_state_root", lambda: tmp_path)
    return tmp_path


def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(
        encoding="utf-8").splitlines() if line.strip()]


def _ledger(root: Path, name: str) -> Path:
    return root / "backend-workflows" / f"{name}-results.jsonl"


# ---------------------------------------------------------------------------
# request workflow
# ---------------------------------------------------------------------------

def test_request_workflow_executes_real_tool_and_persists(state_root):
    note = state_root / "runbook.md"
    content = "deployment runbook recovery marker"
    note.write_text(content, encoding="utf-8")
    params = {
        "state_root": str(state_root), "project_root": str(state_root),
        "file_path": str(note), "query": "runbook",
        "prompt": "read the runbook",
    }

    result = bw.run_request_workflow(params)

    assert result["ok"] is True, result
    assert result["code"] == "ok"
    payload = result["result"]
    assert payload["provider"] == "local"
    assert payload["model"] == "local-model"
    assert payload["tool"]["content"] == content
    assert payload["tool"]["sha256"] == hashlib.sha256(
        content.encode("utf-8")).hexdigest()
    assert payload["permission"]["permission_decision"]["decision"] == "accept"
    assert any(hit["path"] == str(note) for hit in payload["memory"]["hits"])

    session_file = Path(payload["session_path"])
    assert session_file.is_file()
    version, events = session_contracts.read_session(session_file)
    assert version == session_contracts.CURRENT_VERSION
    assert any(e.kind == "tool/call" for e in events)
    assert any(e.kind == "tool/result" and
               content in str(e.payload.get("content", "")) for e in events)

    records = _records(_ledger(state_root, "request"))
    assert len(records) == 1
    assert records[0]["ok"] is True
    assert records[0]["idempotency_key"] == result["idempotency_key"]
    assert any(step["step"] == "tool_executed" for step in records[0]["steps"])

    replay = bw.run_request_workflow(params)
    assert replay["ok"] is False
    assert replay["code"] == "replay_denied"
    assert len(_records(_ledger(state_root, "request"))) == 1


def test_request_workflow_denies_denied_tool(state_root):
    note = state_root / "secret.md"
    note.write_text("sensitive runbook", encoding="utf-8")
    result = bw.run_request_workflow({
        "state_root": str(state_root), "project_root": str(state_root),
        "file_path": str(note), "query": "sensitive",
        "deny_rules": ["read_file"], "idempotency_key": "denied-read",
    })
    assert result["ok"] is False
    assert result["code"] == "permission_denied"
    assert "denied by rule" in result["result"]["reason"]
    records = _records(_ledger(state_root, "request"))
    assert records and records[0]["code"] == "permission_denied"


# ---------------------------------------------------------------------------
# approval workflow
# ---------------------------------------------------------------------------

def test_approval_workflow_request_consume_revoke_and_replay(state_root):
    params = {
        "state_root": str(state_root), "operation": "fs_write",
        "scope": "workflow:write", "subject": "tester",
        "profile": "no_network", "now": 1_700_000_000,
        "ttl_seconds": 300,
    }
    result = bw.run_approval_workflow(params)
    assert result["ok"] is True, result
    payload = result["result"]
    assert payload["resolved"]["grant"]["granted"] is True
    assert payload["resolved"]["grant"]["reason"] == "just_in_time_granted"
    assert payload["replay_attempt"]["code"] == "replay_denied"
    assert payload["revoked"]["revoked"] is True
    assert payload["post_revoke_attempt"]["ok"] is False

    events = _records(state_root / "backend-workflows" / "approval-events.jsonl")
    actions = [event["action"] for event in events]
    assert actions.count("request") == 1
    assert actions.count("consume") == 1
    assert actions.count("revoke") == 1
    # The consumed grant id is durable evidence, not an invented success.
    assert any("grant_id" in event for event in events if event["action"] == "consume")

    records = _records(_ledger(state_root, "approval"))
    assert len(records) == 1 and records[0]["ok"] is True
    replay = bw.run_approval_workflow(params)
    assert replay["ok"] is False and replay["code"] == "replay_denied"


def test_approval_workflow_denies_second_resolve_and_revoked_token(state_root):
    common = {
        "state_root": str(state_root), "operation": "fs_write",
        "scope": "workflow:write", "subject": "tester",
        "now": 1_700_001_000, "ttl_seconds": 600,
    }
    requested = bw.run_approval_workflow({**common, "action": "request",
                                          "idempotency_key": "req"})
    assert requested["ok"] is True
    request_id = requested["result"]["request_id"]
    token = requested["result"]["token"]

    base = {**common, "request_id": request_id, "token": token}
    first = bw.run_approval_workflow({**base, "action": "resolve",
                                      "idempotency_key": "resolve-1"})
    assert first["ok"] is True and first["result"]["grant"]["granted"] is True
    second = bw.run_approval_workflow({**base, "action": "resolve",
                                       "idempotency_key": "resolve-2"})
    assert second["ok"] is False and second["code"] == "replay_denied"

    revoked = bw.run_approval_workflow({**base, "action": "revoke",
                                        "idempotency_key": "revoke-1"})
    assert revoked["ok"] is True
    after = bw.run_approval_workflow({**base, "action": "resolve",
                                      "idempotency_key": "resolve-3"})
    assert after["ok"] is False

    # A tampered sealed token must fail the W7 guard before any grant is issued.
    forged = bw.run_approval_workflow({
        **base, "action": "resolve", "idempotency_key": "resolve-forged",
        "token": token[:-2] + "xx",
    })
    assert forged["ok"] is False


def test_approval_workflow_rejects_disallowed_operation(state_root):
    result = bw.run_approval_workflow({
        "state_root": str(state_root), "operation": "network_egress",
        "profile": "no_network", "scope": "workflow:egress",
    })
    assert result["ok"] is False
    assert result["code"] == "operation_denied"


# ---------------------------------------------------------------------------
# delegation workflow
# ---------------------------------------------------------------------------

def test_delegation_workflow_runs_bounded_children_and_persists_events(state_root):
    tasks = ["alpha", "beta"]
    params = {"state_root": str(state_root), "child_tasks": tasks}
    result = bw.run_delegation_workflow(params)
    assert result["ok"] is True, result
    payload = result["result"]
    assert payload["aggregated"] == {"ok": True, "completed": 2, "failed": 0}
    assert len(payload["children"]) == 2
    for task, child in zip(tasks, payload["children"]):
        assert child["task"] == task
        assert child["status"]["returncode"] == 0
        assert child["payload"]["digest"] == hashlib.sha256(
            task.encode("utf-8")).hexdigest()
        assert child["outcome"]["ok"] is True
        assert child["inherited_context_cleared"] is True
    assert payload["children"][0]["fork_tokens"] == ["parent-task"]
    kinds = [event["kind"] for event in payload["events"]]
    assert kinds.count("subagent/start") == 3
    assert kinds.count("subagent/end") == 3
    assert payload["parent"]["tree_work"]["host_can_complete"] is True
    assert payload["disposal_order"][-1] == "lead"
    assert all(row["hidden"] for row in payload["hidden_snapshot"])

    events = _records(state_root / "backend-workflows" /
                      "delegation-events.jsonl")
    assert len(events) == 1 and len(events[0]["children"]) == 2
    assert len(_records(_ledger(state_root, "delegation"))) == 1

    replay = bw.run_delegation_workflow(params)
    assert replay["ok"] is False and replay["code"] == "replay_denied"


def test_delegation_workflow_enforces_child_bound(state_root):
    result = bw.run_delegation_workflow({
        "state_root": str(state_root),
        "child_tasks": ["a", "b", "c"], "max_children": 2,
    })
    assert result["ok"] is False
    assert result["code"] == "bound_exceeded"
    assert result["result"]["allowed"] == 2
    assert not (state_root / "backend-workflows" /
                "delegation-events.jsonl").exists()


# ---------------------------------------------------------------------------
# MCP workflow
# ---------------------------------------------------------------------------

def test_mcp_workflow_validates_discovers_invokes_and_cleans_up(state_root):
    params = {
        "state_root": str(state_root),
        "manifest": {"name": "demo", "surfaces": ["server"]},
        "server_name": "demo", "tools": ["echo", "secret"],
        "deny_tools": ["secret"], "tool": "echo",
    }
    result = bw.run_mcp_workflow(params)
    # The MCP seam is an honest dry run: no caller-supplied command is executed.
    assert result["ok"] is False, result
    assert result["code"] == "dry_run"
    payload = result["result"]
    assert payload["dry_run"] is True
    assert payload["command_executed"] is False
    assert payload["outcome"] == "dry_run_descriptor"
    assert payload["plugin"] == "demo"
    assert payload["allowed_tools"] == ["echo"]
    assert payload["invocation"]["tool"] == "echo"
    assert payload["request_meta"]["sent_session_id"] is False
    assert payload["prompt_trusted"] is False
    assert payload["cleanup"]["state"] == "disconnected"
    assert payload["cleanup"]["config_unchanged"] is True
    assert payload["config_unchanged"] is True
    assert len(payload["manifest_digest"]) == 64

    events = _records(state_root / "backend-workflows" / "mcp-events.jsonl")
    assert len(events) == 1 and events[0]["cleanup"]["config_unchanged"] is True
    replay = bw.run_mcp_workflow(params)
    assert replay["ok"] is False and replay["code"] == "replay_denied"


def test_mcp_workflow_handles_real_failure_and_denies_all_tools(state_root):
    failed = bw.run_mcp_workflow({
        "state_root": str(state_root), "idempotency_key": "fail",
        "manifest": {"name": "demo", "surfaces": ["server"]},
        "tools": ["echo"], "tool": "echo", "fail": True,
    })
    assert failed["ok"] is False, failed
    assert failed["code"] == "tool_failure"
    assert failed["result"]["outcome"] == "failure_handled"
    assert failed["result"]["dry_run"] is True
    assert failed["result"]["failure"]["reason"] == "tool_failure"
    assert failed["result"]["failure"]["status"]["returncode"] != 0
    assert failed["result"]["cleanup"]["state"] == "disconnected"

    denied = bw.run_mcp_workflow({
        "state_root": str(state_root), "idempotency_key": "deny-all",
        "manifest": {"name": "demo", "surfaces": ["server"]},
        "tools": ["echo", "secret"], "deny_tools": ["echo", "secret"],
    })
    assert denied["ok"] is False and denied["code"] == "permission_denied"
    assert denied["result"]["omitted_servers"] == ["demo"]


# ---------------------------------------------------------------------------
# recovery workflow
# ---------------------------------------------------------------------------

def test_recovery_workflow_reconstructs_from_same_state_root(state_root):
    params = {
        "state_root": str(state_root), "query": "recovery",
        "content": "recovery marker for interruption\n",
        "user": "test-user",
    }
    result = bw.run_recovery_workflow(params)
    assert result["ok"] is True, result
    payload = result["result"]
    assert payload["quarantined"]
    assert all(Path(p).is_file() for p in payload["quarantined"])
    assert payload["approved_folders"] == [payload["workspace"]]
    assert payload["original_hits"] == payload["recovered_hits"]
    assert payload["original_hits"]
    assert payload["replay"]["verified"]["ok"] is True
    assert payload["replay"]["no_network"] is True
    assert payload["sync"]["changes"] == 4
    assert payload["sync"]["status"] == {"status": "recovered"}
    assert payload["state_version"] is not None

    session_root = Path(payload["session_root"])
    assert (session_root / "replay.html").is_file()
    assert (session_root / "changes.jsonl").is_file()
    assert list(session_root.glob("x3_state.corrupt.*.json"))

    events = _records(state_root / "backend-workflows" /
                      "recovery-events.jsonl")
    assert len(events) == 1 and events[0]["changes"] == 4
    assert len(_records(_ledger(state_root, "recovery"))) == 1

    replay = bw.run_recovery_workflow(params)
    assert replay["ok"] is False and replay["code"] == "replay_denied"


# ---------------------------------------------------------------------------
# webapp POST surface
# ---------------------------------------------------------------------------

@pytest.fixture
def server():
    srv = webapp.make_server(0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()
    thread.join(timeout=5)


def _post(srv, path, body, token=None, origin=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1],
                                      timeout=30)
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["X-Keel-Token"] = token
    if origin is not None:
        headers["Origin"] = origin
    payload = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    conn.request("POST", path, body=payload, headers=headers)
    response = conn.getresponse()
    status, raw = response.status, response.read().decode("utf-8")
    conn.close()
    return status, json.loads(raw) if raw else {}


def test_webapp_backend_workflow_endpoint_auth_confirm_and_replay(state_root, server):
    path = "/api/backend-workflows/approval"
    params = {"state_root": str(state_root), "operation": "fs_write",
              "scope": "web:write", "subject": "web-user",
              "now": 1_700_002_000, "ttl_seconds": 300}
    body = {"params": params, "confirm": True}

    status, result = _post(server, path, body, webapp.token())
    assert status == 200, result
    assert result["ok"] is True and result["result"]["resolved"]["grant"]["granted"]

    status, _ = _post(server, path, body, "wrong-token")
    assert status == 403
    status, _ = _post(server, path, body, webapp.token(),
                      origin="https://evil.example")
    assert status == 403
    status, refused = _post(server, path, {"params": params}, webapp.token())
    assert status == 409 and refused["error"] == "confirmation_required"
    status, unknown = _post(server, "/api/backend-workflows/nope", body,
                            webapp.token())
    assert status == 404 and unknown["error"] == "unknown_workflow"

    status, replay = _post(server, path, body, webapp.token())
    assert status == 400 and replay["code"] == "replay_denied"


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------

def test_cli_backend_workflow_runs_and_replays(state_root, capsys):
    from keel.cli import main as cli

    params = {"state_root": str(state_root), "operation": "fs_write",
              "scope": "cli:write", "subject": "cli-user",
              "now": 1_700_003_000, "ttl_seconds": 300}
    argv = ["backend-workflow", "approval", "--params", json.dumps(params),
            "--confirm"]
    assert cli.main(argv) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert result["result"]["resolved"]["grant"]["granted"] is True

    assert cli.main(argv) == 1
    replay = json.loads(capsys.readouterr().out)
    assert replay["code"] == "replay_denied"

    assert cli.main(["backend-workflow", "approval", "--params",
                     json.dumps({**params, "idempotency_key": "cli-noconfirm"})]) == 1
    assert "requires --confirm" in capsys.readouterr().err

    assert cli.main(["backend-workflow", "approval", "--params", "{not json",
                     "--confirm"]) == 1
    assert "--params must be valid JSON" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Security regressions (independent review: REVIEW-FINAL-SECURITY.md)
# ---------------------------------------------------------------------------

def test_approval_resolve_requires_caller_token_possession(state_root):
    """H1: knowing a request_id must never be enough to consume an approval."""
    base = {"state_root": str(state_root), "operation": "fs_read",
            "scope": "workflow:read", "subject": "victim"}
    issued = bw.run_approval_workflow({**base, "action": "request",
                                       "idempotency_key": "seed"})
    assert issued["ok"] is True
    request_id = issued["result"]["request_id"]
    token = issued["result"]["token"]

    missing = bw.run_approval_workflow({
        **base, "action": "resolve", "request_id": request_id,
        "idempotency_key": "no-token"})
    assert missing["ok"] is False and missing["code"] == "missing_token"

    wrong = bw.run_approval_workflow({
        **base, "action": "resolve", "request_id": request_id,
        "token": token[:-2] + "xx", "idempotency_key": "wrong-token"})
    assert wrong["ok"] is False and wrong["code"] == "invalid_token"

    right = bw.run_approval_workflow({
        **base, "action": "resolve", "request_id": request_id,
        "token": token, "idempotency_key": "right-token"})
    assert right["ok"] is True and right["result"]["grant"]["granted"] is True

    events = _records(state_root / "backend-workflows" / "approval-events.jsonl")
    assert sum(e.get("action") == "consume" for e in events) == 1


def test_approval_uses_trusted_clock_and_bounded_ttl(state_root, monkeypatch):
    """H2/L1: caller time cannot revive an expired token; TTL is bounded."""
    clock = [1_700_000_000]
    monkeypatch.setattr(bw, "_now", lambda: clock[0])
    base = {"state_root": str(state_root), "operation": "fs_read",
            "scope": "workflow:read", "subject": "victim", "ttl_seconds": 60}

    issued = bw.run_approval_workflow({**base, "action": "request",
                                       "now": 1_900_000_000,
                                       "idempotency_key": "seed"})
    assert issued["ok"] is True
    assert issued["result"]["expires_at"] == 1_700_000_060
    request_id = issued["result"]["request_id"]
    token = issued["result"]["token"]

    clock[0] += 61
    expired = bw.run_approval_workflow({**base, "action": "resolve",
                                        "request_id": request_id, "token": token,
                                        "now": 1_700_000_030,
                                        "idempotency_key": "expired"})
    assert expired["ok"] is False
    assert expired["code"] in {"invalid_token", "permission_denied"}
    events = _records(state_root / "backend-workflows" / "approval-events.jsonl")
    assert not any(e.get("action") == "consume" for e in events)

    for bad in (0, -1, 86401):
        result = bw.run_approval_workflow({**base, "ttl_seconds": bad,
                                           "idempotency_key": f"ttl-{bad}"})
        assert result["ok"] is False and result["code"] == "bad_ttl", result


# A tiny subprocess worker used by the cross-process probe tests.  A file-based
# start gate makes every worker enter the guarded section at the same instant.
_WORKER_TEMPLATE = """\
import json, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from keel import backend_workflows as bw
payload = json.loads(sys.argv[2])
go = Path(sys.argv[3])
deadline = time.time() + 30
while not go.exists() and time.time() < deadline:
    time.sleep(0.002)
res = bw.run_workflow(payload["name"], payload["params"])
result = res.get("result") if isinstance(res.get("result"), dict) else {}
print(json.dumps({"ok": res["ok"], "code": res["code"],
                  "granted": bool(result.get("grant", {}).get("granted"))}))
"""


def _run_concurrent(state_root: Path, name: str, params_list: list[dict],
                    tmp_path: Path) -> list[dict]:
    script = tmp_path / "_wf_worker.py"
    script.write_text(_WORKER_TEMPLATE, encoding="utf-8")
    gate = tmp_path / "_wf_go"
    if gate.exists():
        gate.unlink()
    src = str(Path(bw.__file__).resolve().parents[1])
    processes = []
    for params in params_list:
        payload = json.dumps({"name": name, "params": params})
        processes.append(subprocess.Popen(
            [sys.executable, str(script), src, payload, str(gate)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
    gate.write_text("go", encoding="utf-8")
    outputs: list[dict] = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=120)
        assert process.returncode == 0, stderr[-1000:]
        outputs.append(json.loads(stdout.strip().splitlines()[-1]))
    return outputs


def test_approval_consumption_is_cross_process_atomic(state_root, tmp_path):
    """H3-A: eight processes, one single-use grant -> exactly one grant."""
    base = {"state_root": str(state_root), "operation": "fs_read",
            "scope": "workflow:read", "subject": "racer"}
    seed = bw.run_approval_workflow({**base, "action": "request",
                                     "idempotency_key": "seed"})
    request_id = seed["result"]["request_id"]
    token = seed["result"]["token"]
    params = [{**base, "action": "resolve", "request_id": request_id,
               "token": token, "idempotency_key": f"racer-{i}"}
              for i in range(8)]
    outcomes = _run_concurrent(state_root, "approval", params, tmp_path)
    assert sum(1 for row in outcomes if row["granted"]) == 1, outcomes
    events = _records(state_root / "backend-workflows" / "approval-events.jsonl")
    assert sum(e.get("action") == "consume" for e in events) == 1


def test_request_replay_guard_is_cross_process(state_root, tmp_path):
    """H3-B: six processes with identical params -> one persisted record."""
    note = state_root / "note.txt"
    note.write_text("shared payload", encoding="utf-8")
    params = {"state_root": str(state_root), "project_root": str(state_root),
              "file_path": str(note), "query": "shared"}
    outcomes = _run_concurrent(state_root, "request", [dict(params)] * 6,
                               tmp_path)
    assert sum(1 for row in outcomes if row["ok"]) == 1, outcomes
    assert len(_records(_ledger(state_root, "request"))) == 1


def test_request_and_recovery_paths_are_confined_to_state_root(state_root):
    """M1: caller-chosen roots/permissions cannot read or write outside."""
    outside = state_root.parent / (state_root.name + "-outside")
    outside.mkdir(parents=True, exist_ok=True)
    secret = outside / "credentials.txt"
    secret.write_text("API_KEY=supersecret123\n", encoding="utf-8")

    escaped = bw.run_request_workflow({
        "state_root": str(state_root), "project_root": str(outside),
        "file_path": str(secret), "query": "credentials",
        "idempotency_key": "outside-project"})
    assert escaped["ok"] is False and escaped["code"] == "path_escape"
    assert "supersecret123" not in json.dumps(escaped, ensure_ascii=False)

    widened = bw.run_request_workflow({
        "state_root": str(state_root), "project_root": str(outside),
        "file_path": str(secret), "query": "credentials",
        "allow_rules": ["read_file"], "permission_mode": "bypassPermissions",
        "idempotency_key": "widened"})
    assert widened["ok"] is False and widened["code"] == "path_escape"

    recovery = bw.run_recovery_workflow({
        "state_root": str(state_root), "folder": str(outside),
        "content": "PERSISTED-BY-WORKFLOW", "idempotency_key": "outside-write"})
    assert recovery["ok"] is False and recovery["code"] == "path_escape"
    assert not (outside / "recovery-note.md").exists()

    traversal = bw.run_request_workflow({
        "state_root": str(state_root), "project_root": str(state_root),
        "file_path": "../credentials.txt", "query": "credentials",
        "idempotency_key": "traversal"})
    assert traversal["ok"] is False and traversal["code"] == "path_escape"

    symlink = state_root / "link-out"
    try:
        symlink.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        symlink = None  # symlink creation is privileged on some Windows hosts
    if symlink is not None:
        linked = bw.run_request_workflow({
            "state_root": str(state_root), "project_root": str(symlink),
            "file_path": str(secret), "query": "credentials",
            "idempotency_key": "symlink-escape"})
        assert linked["ok"] is False and linked["code"] == "path_escape"


def test_workflow_results_are_redacted_before_persist_and_return(state_root):
    """M2: secrets in tool results never reach the ledger or the caller."""
    note = state_root / "leak.md"
    note.write_text("API_KEY=supersecret123\n", encoding="utf-8")
    result = bw.run_request_workflow({
        "state_root": str(state_root), "project_root": str(state_root),
        "file_path": str(note), "query": "leak", "idempotency_key": "leak"})
    assert result["ok"] is True
    assert "supersecret123" not in json.dumps(result, ensure_ascii=False)
    ledger = _ledger(state_root, "request").read_text(encoding="utf-8")
    assert "supersecret123" not in ledger
    assert "[REDACTED]" in ledger


def test_workflow_results_carry_http_status_hints(state_root):
    """M3: typed client failures carry a 403/400 hint for webapp.py."""
    denied = bw.run_approval_workflow({
        "state_root": str(state_root), "operation": "network_egress",
        "profile": "no_network", "idempotency_key": "status-denied"})
    assert denied["http_status"] == 403

    bad_ttl = bw.run_approval_workflow({
        "state_root": str(state_root), "operation": "fs_read",
        "ttl_seconds": 0, "idempotency_key": "status-ttl"})
    assert bad_ttl["http_status"] == 400

    csrf = bw.run_approval_workflow({
        "state_root": str(state_root), "operation": "fs_read",
        "headers": {"Origin": "https://evil.test"},
        "expected_origin": "https://good.test",
        "idempotency_key": "status-csrf"})
    assert csrf["http_status"] == 403

    bad_manifest = bw.run_mcp_workflow({
        "state_root": str(state_root), "manifest": 123,
        "idempotency_key": "status-manifest"})
    assert bad_manifest["http_status"] == 400


def test_mcp_never_executes_caller_supplied_command(state_root, tmp_path):
    """M5: no caller command runs, and the result is an honest dry run."""
    marker = tmp_path / "caller-command-ran"
    command = [sys.executable, "-c",
               f"open({str(marker)!r}, 'w', encoding='utf-8').write('x')"]
    result = bw.run_mcp_workflow({
        "state_root": str(state_root),
        "manifest": {"name": "demo", "surfaces": ["server"]},
        "server_config": {"type": "local", "command": command, "oauth": False},
        "tools": ["echo"], "tool": "echo", "idempotency_key": "no-rce"})
    assert not marker.exists()
    assert result["ok"] is False and result["code"] == "dry_run"
    assert result["result"]["dry_run"] is True
    assert result["result"]["command_executed"] is False
