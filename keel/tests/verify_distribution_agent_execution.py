"""Distribution round — gate enforcement after the origin/main merge.

Split by evidence type:

* ``test_permission_*`` / ``test_approval_*`` exercise the authoritative Python
  permission gate and Fleet approval broker directly with real objects (no
  network). These cover the merge edits in ``permissions.py`` (deny verdict)
  and ``fleet/approvals.py`` (argument redaction).

* ``test_workspace_trust_*`` drives the *real HTTP bridge* against a temp
  project folder and verifies the merge's route-level trust enforcement.

* ``test_real_python_runtime_smoke`` POSTs to ``/api/run`` and reads the real
  NDJSON emitted by a real ``python -m keel`` child process with no provider
  credentials. IMPORTANT: with no key configured, the runtime honestly falls
  back to its built-in scripted fake (`apiKeySource: "none"`,
  `model: "keel-fake-1"`). The process, bridge, event stream and permission
  machinery are real; the *model reply* is scripted by design. This is not
  presented as a live-provider turn.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request

import pytest

import keel.webapp as webapp
from keel.fleet import routes as fleet_routes
from keel.fleet.service import FleetStore
from keel.permissions import Decision, evaluate
from keel.runner import RealTools
from keel.tools import create_native_registry

TOKEN = webapp.token()
PROVIDER_KEY_VARS = (
    "KEEL_OPENROUTER_API_KEY", "KEEL_GOOGLE_API_KEY", "KEEL_NVIDIA_API_KEY",
    "KEEL_ANTHROPIC_API_KEY", "KEEL_COMPAT_API_KEY",
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
)


@pytest.fixture()
def bridge(tmp_path):
    old = fleet_routes._store
    fleet_routes.reset_store_for_tests(tmp_path / "execution-fleet.db")
    server = webapp.make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
    fleet_routes._store = old


def _post(server, path, body, token=TOKEN):
    req = urllib.request.Request(
        f"http://127.0.0.1:{server.server_address[1]}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"X-Keel-Token": token, "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, raw
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def _json_post(server, path, body, token=TOKEN):
    status, raw = _post(server, path, body, token)
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, {"raw": raw}


def _get(server, path, token=TOKEN):
    req = urllib.request.Request(
        f"http://127.0.0.1:{server.server_address[1]}{path}",
        headers={"X-Keel-Token": token}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# authoritative permission gate (real objects, no network)
# ---------------------------------------------------------------------------

def test_permission_mode_gate_still_enforces_deny_and_ask():
    registry = create_native_registry(RealTools())
    rules = ([], [], [])
    write = {"path": "notes.txt", "content": "x"}

    plan = evaluate(tool_name="write_file", tool_input=write, rules=rules,
                    mode="dontAsk", interactive=True, tool_registry=registry)
    assert isinstance(plan, Decision)
    # Merge fix: an explicit mode-table deny is reported as a deny, not an ask.
    assert plan.decision == "deny"
    assert plan.reason_type == "mode"

    default = evaluate(tool_name="write_file", tool_input=write, rules=rules,
                       mode="default", interactive=True, tool_registry=registry)
    assert default.decision == "ask"
    assert default.reason_type == "mode"

    # Non-interactive asks still fail closed.
    noninteractive = evaluate(tool_name="write_file", tool_input=write,
                              rules=rules, mode="default", interactive=False,
                              tool_registry=registry)
    assert noninteractive.decision == "deny"


def test_approval_card_redacts_credentials_and_decision_is_audited(tmp_path):
    from keel.fleet import approvals

    key = "sk-or-v1-" + "a" * 28
    summary = approvals.args_summary(
        "run_shell", {"command": f"curl -H 'Authorization: Bearer {key}' https://x"})
    assert "[REDACTED]" in summary
    assert key not in summary

    store = FleetStore(db_path=tmp_path / "approvals.db")
    try:
        bot = store.create_bot(name="Gate Bot", engine="provider")
        broker = store.approvals
        approval = broker.request(bot=bot, tool_name="run_shell",
                                  tool_input={"command": "echo approved"},
                                  tool_use_id="call-1")
        aid = approval["approval_id"]
        rows = store.list_rows(bot["id"], 0, 100)
        card = next(r for r in rows if r["kind"] == "approval")
        assert card["body"]["status"] == "pending"

        changed, decided, error = broker.decide(
            bot_id=bot["id"], approval_id=aid, decision="never")
        assert changed is True and error is None
        assert decided["status"] == "denied"
        rows = store.list_rows(bot["id"], 0, 100)
        resolved = [r for r in rows if r["kind"] == "approval"
                    and r["body"].get("status") == "denied"]
        assert resolved, "no denied approval card was persisted"
        audit = store.list_audit(bot["id"], 50)
        assert any(a["event"] == "decided" and a["outcome"] == "refused"
                   for a in audit)
        # 'never' pins a standing policy, so a later call is refused outright.
        assert any(p["tool_name"] == "run_shell" and p["decision"] == "never"
                   for p in store.list_policies(bot["id"])) is True
    finally:
        store.close()


# ---------------------------------------------------------------------------
# workspace trust at the HTTP boundary (merge change in fleet/routes.py)
# ---------------------------------------------------------------------------

def test_workspace_trust_is_enforced_at_http_boundary(bridge, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "note.txt").write_text("private-note", encoding="utf-8")

    status, created = _json_post(bridge, "/api/fleet/projects",
                                 {"path": str(workspace), "name": "ws"})
    assert status == 201, created
    pid = created["project"]["id"]
    assert created["project"]["trusted"] == 0

    guards = [
        ("GET", f"/api/fleet/projects/{pid}/tree", None),
        ("GET", f"/api/fleet/projects/{pid}/file/read?path=note.txt", None),
        ("GET", f"/api/fleet/projects/{pid}/review", None),
        ("POST", f"/api/fleet/projects/{pid}/file/write",
         {"path": "new.txt", "content": "payload"}),
        ("POST", f"/api/fleet/projects/{pid}/terminal/exec",
         {"command": "echo should-not-run"}),
    ]
    for method, path, body in guards:
        status, doc = (_json_post(bridge, path, body) if method == "POST"
                       else _get(bridge, path))
        assert status == 403, (path, status, doc)
        assert doc.get("error") == "workspace_not_trusted", (path, doc)

    # Explicit trust unlocks read/review/write; revocation immediately relocks.
    status, trusted = _json_post(bridge, f"/api/fleet/projects/{pid}/trust",
                                 {"trusted": True})
    assert status == 200 and trusted["project"]["trusted"] == 1
    status, tree = _get(bridge, f"/api/fleet/projects/{pid}/tree")
    assert status == 200 and any(e["name"] == "note.txt" for e in tree["entries"])
    status, content = _get(bridge, f"/api/fleet/projects/{pid}/file/read?path=note.txt")
    assert status == 200 and "private-note" in str(content)
    status, written = _json_post(bridge, f"/api/fleet/projects/{pid}/file/write",
                                 {"path": "written.txt", "content": "ok"})
    assert status == 200 and (workspace / "written.txt").read_text() == "ok"
    status, review = _get(bridge, f"/api/fleet/projects/{pid}/review")
    assert status == 200 and review["is_git"] is False

    status, revoked = _json_post(bridge, f"/api/fleet/projects/{pid}/trust",
                                 {"trusted": False})
    assert status == 200 and revoked["project"]["trusted"] == 0
    status, doc = _get(bridge, f"/api/fleet/projects/{pid}/tree")
    assert status == 403 and doc["error"] == "workspace_not_trusted"


# ---------------------------------------------------------------------------
# real local runtime smoke through /api/run
# ---------------------------------------------------------------------------

def test_real_python_runtime_smoke_streams_ndjson_without_credentials(
        bridge, tmp_path, monkeypatch):
    # Isolate settings and strip provider credentials for the child process.
    monkeypatch.setenv("KEEL_STATE_DIR", str(tmp_path / "keel-state"))
    for name in PROVIDER_KEY_VARS:
        monkeypatch.delenv(name, raising=False)
    assert os.environ.get("KEEL_FAKE_SCRIPT") is None

    status, raw = _post(bridge, "/api/run",
                        {"prompt": "local runtime smoke", "provider": "auto"})
    assert status == 200
    lines = [line for line in raw.splitlines() if line.strip()]
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pytest.fail(f"non-JSON NDJSON line: {line[:200]!r}")

    init = next(e for e in events if e.get("type") == "system"
                and e.get("subtype") == "init")
    assert init["session_id"] and isinstance(init["tools"], list)
    assert init["apiKeySource"] == "none"
    assert init["model"] == "keel-fake-1"  # honest no-credential fallback

    result = next(e for e in events if e.get("type") == "result")
    assert result.get("subtype") == "success" and result.get("is_error") is False
    assert any(e.get("type") == "bridge" and e.get("subtype") == "done"
               and e.get("exit_code") == 0 for e in events)

    # The runtime is real: it spawned a child with the full native tool set.
    assert "run_shell" in init["tools"] and "write_file" in init["tools"]
