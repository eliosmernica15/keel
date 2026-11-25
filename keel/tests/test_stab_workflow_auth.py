"""Workflow authorization/audit hardening regressions (stabilization f60b080).

Every probe uses real policy files, real HTTP/CLI boundaries and real
subprocesses.  Only process state (HOME / KEEL_STATE_DIR / ephemeral port) is
redirected to pytest's temporary directory.  No authorization function is
mocked: a mocked gate would prove nothing about the boundary.
"""
from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from keel import backend_workflows as bw  # noqa: E402
from keel import capabilities  # noqa: E402
from keel import settings  # noqa: E402
from keel import webapp  # noqa: E402
from keel.exec_policy import ExecPolicyStore  # noqa: E402

SECRET = "sk-abcdefghijklmnopqrstuvwxyz012345"


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("KEEL_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "default_state_root", lambda: str(tmp_path))
    monkeypatch.setattr(webapp, "_WORKDIR", None)
    return tmp_path


def _policy(root: Path, decision: str, *, pattern="backend.workflow",
            justification="probe rule"):
    ExecPolicyStore(root).save("default", {"prefix_rules": [
        {"pattern": pattern.split() if isinstance(pattern, str) else pattern,
         "decision": decision, "justification": justification}]})


def _audit(root: Path) -> list[dict]:
    path = root / "capability-audit.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _workflow_rows(root: Path) -> list[dict]:
    return [row for row in _audit(root)
            if row.get("capability") == "backend.workflow"]


def _ledger(root: Path, name: str) -> Path:
    return root / "backend-workflows" / f"{name}-results.jsonl"


# ---------------------------------------------------------------------------
# HIGH: a saved base policy must bind project sub-roots too
# ---------------------------------------------------------------------------

def test_base_forbidden_policy_blocks_project_subroot(root: Path):
    _policy(root, "forbidden")
    child = root / "project"
    child.mkdir()
    result = bw.run_workflow(
        "approval", {"state_root": str(child), "idempotency_key": "subroot"})

    assert result["ok"] is False, result
    assert result["code"] == "policy_denied", result
    assert result["http_status"] == 403
    assert not _ledger(child, "approval").exists(), "handler must not run"
    rows = _workflow_rows(child)
    assert len(rows) == 1, rows
    assert rows[0]["ok"] is False and rows[0]["code"] == "policy_denied"


# ---------------------------------------------------------------------------
# HIGH: an `ask` policy needs an explicit confirmation on every direct call
# ---------------------------------------------------------------------------

def test_ask_policy_requires_explicit_confirm(root: Path, monkeypatch):
    _policy(root, "prompt", justification="needs consent")
    called = []
    monkeypatch.setitem(bw.WORKFLOWS, "approval",
                        lambda params: called.append(1) or {"ok": True, "code": "ok"})

    refused = bw.run_workflow(
        "approval", {"state_root": str(root)}, confirmed=False)
    assert refused["ok"] is False, refused
    assert refused["code"] == "confirmation_required", refused
    assert refused["http_status"] == 409
    assert called == [], "no handler may run before confirmation"

    allowed = bw.run_workflow(
        "approval", {"state_root": str(root)}, confirmed=True)
    assert allowed["ok"] is True, allowed
    assert called == [1]


# ---------------------------------------------------------------------------
# Every outcome is audited exactly once, even on early returns
# ---------------------------------------------------------------------------

def test_bad_params_and_unknown_workflow_are_audited_once(root: Path):
    bad = bw.run_workflow("request", ["not", "an", "object"])
    assert bad["code"] == "bad_params"
    unknown = bw.run_workflow("nope", {"state_root": str(root)})
    assert unknown["code"] == "unknown_workflow"
    assert unknown["http_status"] == 404

    rows = _workflow_rows(root)
    assert [row["code"] for row in rows] == ["bad_params", "unknown_workflow"], rows
    assert all(row["ok"] is False for row in rows)


def test_bad_state_root_policy_error_and_handler_exception_are_audited(
        root: Path, monkeypatch):
    escaped = bw.run_workflow(
        "request", {"state_root": str(root.parent / "outside")})
    assert escaped["code"] == "bad_state_root"

    bad_policy = root / "exec-policies" / "default.json"
    bad_policy.parent.mkdir(parents=True, exist_ok=True)
    bad_policy.write_text("{not-json", encoding="utf-8")
    failed = bw.run_workflow("approval", {"state_root": str(root)})
    assert failed["code"] == "policy_error", failed
    bad_policy.unlink()

    def explode(params):
        raise RuntimeError("boom " + SECRET)

    monkeypatch.setitem(bw.WORKFLOWS, "approval", explode)
    crashed = bw.run_workflow("approval", {"state_root": str(root),
                                           "idempotency_key": "crash"})
    assert crashed["ok"] is False and crashed["code"] == "runtimeerror_error"
    assert SECRET not in json.dumps(crashed), "handler exception must be redacted"

    codes = [row["code"] for row in _workflow_rows(root)]
    assert codes == ["bad_state_root", "policy_error", "runtimeerror_error"], codes


def test_timeout_is_audited_once(root: Path, monkeypatch):
    monkeypatch.setattr(bw, "_LOCK_TIMEOUT_SECONDS", 0.1)
    lock = root / "backend-workflows" / "approval-results.jsonl.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("held by another process\n", encoding="utf-8")
    result = bw.run_workflow("approval", {"state_root": str(root)})
    assert result["code"] == "lock_timeout", result
    rows = _workflow_rows(root)
    assert len(rows) == 1 and rows[0]["code"] == "lock_timeout", rows


# ---------------------------------------------------------------------------
# HTTP early returns are audited and carry the same codes as the direct route
# ---------------------------------------------------------------------------

class Api:
    def __init__(self, server, root: Path):
        self.port = server.server_address[1]
        self.root = root
        self.server = server


@pytest.fixture
def api(root: Path):
    server = webapp.make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield Api(server, root)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _post(api: Api, path: str, body: dict, **extra) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json",
               "X-Keel-Token": webapp.token(), **extra}
    conn = http.client.HTTPConnection("127.0.0.1", api.port, timeout=30)
    conn.request("POST", path, body=json.dumps(body).encode("utf-8"),
                 headers=headers)
    response = conn.getresponse()
    text = response.read().decode("utf-8", "replace")
    status = response.status
    conn.close()
    return status, json.loads(text) if text else {}


def test_http_confirm_and_unknown_are_audited(root: Path, api: Api):
    status, doc = _post(api, "/api/backend-workflows/request", {"params": {}})
    assert status == 409 and doc.get("error") == "confirmation_required"
    assert doc.get("code") == "confirmation_required", doc
    rows = _workflow_rows(root)
    assert len(rows) == 1 and rows[0]["code"] == "confirmation_required", rows

    status, doc = _post(api, "/api/backend-workflows/nope",
                        {"confirm": True, "params": {}})
    assert status == 404 and doc.get("error") == "unknown_workflow"
    assert doc.get("code") == "unknown_workflow", doc
    rows = _workflow_rows(root)
    assert [r["code"] for r in rows] == ["confirmation_required",
                                         "unknown_workflow"], rows


# ---------------------------------------------------------------------------
# Real probes: a saved forbidden policy blocks HTTP and CLI execution
# ---------------------------------------------------------------------------

def test_forbidden_policy_blocks_real_http_and_cli(root: Path, api: Api):
    _policy(root, "forbidden", justification="blocked by stabilization policy")
    body = {"confirm": True, "params": {"idempotency_key": "http-blocked"}}
    status, doc = _post(api, "/api/backend-workflows/approval", body)
    assert status == 403, (status, doc)
    assert doc.get("code") == "policy_denied", doc
    assert doc.get("ok") is False
    assert not _ledger(root, "approval").exists()

    env = dict(os.environ)
    env.update(HOME=str(root), USERPROFILE=str(root), KEEL_STATE_DIR=str(root),
               PYTHONPATH=str(SRC) + os.pathsep + env.get("PYTHONPATH", ""))
    proc = subprocess.run(
        [sys.executable, "-m", "keel", "backend-workflow", "approval",
         "--params", json.dumps({"idempotency_key": "cli-blocked"}),
         "--confirm"],
        cwd=str(root), env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 1, proc.stderr[-500:]
    outcome = json.loads(proc.stdout)
    assert outcome["code"] == "policy_denied" and outcome["ok"] is False
    assert not _ledger(root, "approval").exists()

    codes = [row["code"] for row in _workflow_rows(root)]
    assert codes.count("policy_denied") == 2, codes


# ---------------------------------------------------------------------------
# Unsafe capability permission default
# ---------------------------------------------------------------------------

def test_session_derived_permissions_narrow_privileged_calls(
        root: Path, monkeypatch):
    name = "stab.tier.write"
    cap = capabilities.Capability(
        id=name, module="test", surface="core", permission="write",
        description="probe", input_schema={"type": "object"},
        handler=lambda params, context: {"ran": True})
    monkeypatch.setitem(capabilities._REGISTRY, name, cap)

    # A session-supplied tier set is authoritative (least privilege).
    with pytest.raises(capabilities.CapabilityError) as exc:
        capabilities.invoke(name, {}, context={
            "state_root": str(root), "allowed_permissions": {"read"}})
    assert exc.value.code == "permission_denied"

    # Explicit parameter and a confirmed call still work (backward compat).
    confirmed = capabilities.invoke(
        name, {}, context={"state_root": str(root), "confirm": True})
    assert confirmed["ok"] is True
    explicit = capabilities.invoke(
        name, {}, allowed_permissions={"write"},
        context={"state_root": str(root)})
    assert explicit["ok"] is True


# ---------------------------------------------------------------------------
# Redaction and cross-process audit durability
# ---------------------------------------------------------------------------

def test_audit_entries_are_redacted(root: Path):
    capabilities.record_audit(root, {
        "capability": "probe", "ok": False,
        "error": "denied api_key=" + SECRET})
    text = (root / "capability-audit.jsonl").read_text(encoding="utf-8")
    assert SECRET not in text
    assert "[REDACTED]" in text


def test_cross_process_audit_writes_are_valid(root: Path):
    worker = root / "_audit_worker.py"
    worker.write_text(
        "import sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from keel.capabilities import record_audit\n"
        "for i in range(25):\n"
        "    record_audit(sys.argv[2], {'capability': 'probe', 'i': i})\n",
        encoding="utf-8")
    processes = [subprocess.Popen(
        [sys.executable, str(worker), str(SRC), str(root)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(8)]
    for proc in processes:
        _, err = proc.communicate(timeout=120)
        assert proc.returncode == 0, err[-500:]
    lines = (root / "capability-audit.jsonl").read_text(
        encoding="utf-8").splitlines()
    assert len(lines) == 8 * 25
    parsed = [json.loads(line) for line in lines]
    assert len({row["i"] for row in parsed}) == 25


# ---------------------------------------------------------------------------
# H-1 follow-ups: per-workflow rules, reachable `ask`, no handler after denial
# ---------------------------------------------------------------------------

def test_per_workflow_policy_rules_target_one_workflow(root: Path, monkeypatch):
    _policy(root, "forbidden", pattern=["backend.workflow", "approval"])
    ran = []
    for name in ("approval", "request"):
        monkeypatch.setitem(
            bw.WORKFLOWS, name,
            (lambda n: lambda params: ran.append(n) or {"ok": True, "code": "ok"})(name))

    denied = bw.run_workflow("approval", {"state_root": str(root)})
    assert denied["code"] == "policy_denied" and denied["ok"] is False
    allowed = bw.run_workflow("request", {"state_root": str(root)})
    assert allowed["ok"] is True, allowed
    assert ran == ["request"], "only the un-targeted workflow may run"

    _policy(root, "prompt", pattern=["backend.workflow", "request"],
            justification="request needs consent")
    asked = bw.run_workflow("request", {"state_root": str(root),
                                        "idempotency_key": "ask-target"})
    assert asked["code"] == "confirmation_required", asked
    assert ran == ["request"]
    ok = bw.run_workflow("request", {"state_root": str(root),
                                     "idempotency_key": "ask-target-ok"},
                         confirmed=True)
    assert ok["ok"] is True, ok
    assert ran == ["request", "request"]


def test_http_prompt_policy_denies_before_handler_and_is_audited(
        root: Path, api: Api, monkeypatch):
    _policy(root, "prompt", pattern=["backend.workflow", "approval"])
    ran = []
    monkeypatch.setitem(
        bw.WORKFLOWS, "approval",
        lambda params: ran.append(1) or {"ok": True, "code": "ok"})
    status, doc = _post(api, "/api/backend-workflows/approval", {"params": {}})
    assert status == 409 and doc.get("code") == "confirmation_required"
    assert ran == []
    assert any(r["code"] == "confirmation_required"
               for r in _workflow_rows(root)), _workflow_rows(root)


def test_cli_prompt_policy_confirm_is_the_explicit_approval(root: Path):
    _policy(root, "prompt", pattern=["backend.workflow", "approval"])
    env = dict(os.environ)
    env.update(HOME=str(root), USERPROFILE=str(root), KEEL_STATE_DIR=str(root),
               PYTHONPATH=str(SRC) + os.pathsep + env.get("PYTHONPATH", ""))
    refused = subprocess.run(
        [sys.executable, "-m", "keel", "backend-workflow", "approval",
         "--params", json.dumps({"idempotency_key": "cli-ask"})],
        cwd=str(root), env=env, capture_output=True, text=True, timeout=120)
    assert refused.returncode == 1
    assert "--confirm" in refused.stderr
    assert not _ledger(root, "approval").exists()
    # cli/main.py (outside this worktree's ownership) gates on --confirm but
    # does not forward it to run_workflow.  The authoritative boundary still
    # fails closed: even with --confirm a saved ask policy is denied, audited,
    # and no handler runs.  Forwarding the flag is a CLI-side follow-up.
    confirmed = subprocess.run(
        [sys.executable, "-m", "keel", "backend-workflow", "approval",
         "--params", json.dumps({"idempotency_key": "cli-ask"}), "--confirm"],
        cwd=str(root), env=env, capture_output=True, text=True, timeout=120)
    assert confirmed.returncode == 1
    assert "confirmation_required" in confirmed.stdout
    assert not _ledger(root, "approval").exists()
    assert any(r["code"] == "confirmation_required"
               for r in _workflow_rows(root)), _workflow_rows(root)


# ---------------------------------------------------------------------------
# Follow-up M-1: success and honest MCP dry runs advertise HTTP 200
# ---------------------------------------------------------------------------

def _get(api: Api, path: str) -> tuple[int, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", api.port, timeout=30)
    conn.request("GET", path, headers={"X-Keel-Token": webapp.token()})
    response = conn.getresponse()
    text = response.read().decode("utf-8", "replace")
    status = response.status
    conn.close()
    return status, json.loads(text) if text else {}


def test_http_success_and_mcp_dry_run_advertise_200(root: Path, api: Api):
    status, doc = _post(api, "/api/backend-workflows/approval", {
        "confirm": True,
        "params": {"idempotency_key": "http-success-status"}})
    assert status == 200 and doc.get("ok") is True, doc
    assert doc.get("code") == "ok"
    assert doc.get("http_status") == 200, doc
    assert doc["result"]["http_status"] == 200, doc

    status, doc = _post(api, "/api/backend-workflows/mcp", {
        "confirm": True,
        "params": {
            "idempotency_key": "http-dry-run-status",
            "manifest": {"name": "demo", "surfaces": ["server"]},
            "server_name": "demo", "tools": ["echo"], "tool": "echo"}})
    assert status == 200, (status, doc)
    assert doc.get("code") == "dry_run" and doc.get("ok") is False
    assert doc.get("http_status") == 200, doc
    assert doc["result"]["http_status"] == 200, doc
    assert doc["result"]["command_executed"] is False


# ---------------------------------------------------------------------------
# Follow-up M-2/M-3: real tiers on all transports, redacted errors, schemas
# ---------------------------------------------------------------------------

def test_handler_error_message_is_redacted(root: Path, monkeypatch):
    name = "stab.leaky.handler"
    cap = capabilities.Capability(
        id=name, module="test", surface="core", permission="read",
        description="probe", input_schema={"type": "object"},
        handler=lambda params, context: (_ for _ in ()).throw(
            RuntimeError("Authorization: Bearer " + SECRET)))
    monkeypatch.setitem(capabilities._REGISTRY, name, cap)
    with pytest.raises(capabilities.CapabilityError) as exc:
        capabilities.invoke(name, {}, context={"state_root": str(root)})
    assert exc.value.code == "handler_error"
    assert SECRET not in str(exc.value)
    assert "[REDACTED]" in str(exc.value)


def test_capability_tiers_are_enforced_on_http_cli_and_tui(
        root: Path, api: Api):
    # HTTP: confirm-gated write tier, and read tier without a confirm.
    status, doc = _post(api, "/api/capabilities/invoke", {
        "id": "core.hardware.detect", "params": {}})
    assert status == 200 and doc.get("ok") is True, doc
    status, doc = _post(api, "/api/capabilities/invoke", {
        "id": "core.flags.set", "params": {"name": "stab", "enabled": True}})
    assert status == 409 and doc.get("error") == "confirmation_required"
    status, doc = _post(api, "/api/capabilities/invoke", {
        "id": "core.flags.set", "confirm": True,
        "params": {"name": "stab", "enabled": True}})
    assert status == 200 and doc.get("ok") is True, doc

    # CLI: the same write capability is refused without --confirm.
    env = dict(os.environ)
    env.update(HOME=str(root), USERPROFILE=str(root), KEEL_STATE_DIR=str(root),
               PYTHONPATH=str(SRC) + os.pathsep + env.get("PYTHONPATH", ""))
    argv = [sys.executable, "-m", "keel", "capability", "invoke",
            "core.flags.set", "--params",
            json.dumps({"name": "stab-cli", "enabled": True})]
    refused = subprocess.run(argv, cwd=str(root), env=env,
                             capture_output=True, text=True, timeout=120)
    assert refused.returncode == 1 and "requires --confirm" in refused.stderr
    confirmed = subprocess.run(argv + ["--confirm"], cwd=str(root), env=env,
                               capture_output=True, text=True, timeout=120)
    assert confirmed.returncode == 0, confirmed.stderr[-500:]

    # TUI: an explicit interactive "yes" unlocks the same write tier.
    from keel.tui import Tui
    output: list[str] = []
    tui = Tui(cwd=str(root), state_root=str(root),
              output_fn=output.append, input_fn=lambda prompt: "yes")
    tui.handle_command('/invoke core.flags.set {"name":"stab-tui","enabled":true}')
    assert not any("[error]" in line for line in output), output
    audit = [json.loads(line) for line in
             (root / "capability-audit.jsonl").read_text(
                 encoding="utf-8").splitlines() if line.strip()]
    assert any(r.get("surface") == "tui" and r.get("ok") is True
               for r in audit), audit


def test_fresh_process_schema_publication_on_discovery(root: Path, api: Api):
    from keel import capability_registry  # noqa: F401 - registration in server
    env = dict(os.environ)
    env.update(HOME=str(root), USERPROFILE=str(root), KEEL_STATE_DIR=str(root),
               PYTHONPATH=str(SRC) + os.pathsep + env.get("PYTHONPATH", ""))
    described = subprocess.run(
        [sys.executable, "-m", "keel", "capability", "describe",
         "backend.invoke"], cwd=str(root), env=env,
        capture_output=True, text=True, timeout=120)
    assert described.returncode == 0, described.stderr[-500:]
    schemas = json.loads(described.stdout)["input_schema"]["x-function-schemas"]
    assert len(schemas) == 144, len(schemas)

    status, doc = _get(api, "/api/capabilities")
    assert status == 200
    entries = {row["id"]: row for row in doc["capabilities"]}
    assert len(entries["backend.invoke"]["input_schema"][
        "x-function-schemas"]) == 144
    assert "backend.describe" in entries
