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
import threading
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
    assert result["ok"] is True, result
    payload = result["result"]
    assert payload["outcome"] == "success"
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
    assert failed["ok"] is True, failed
    assert failed["result"]["outcome"] == "failure_handled"
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
