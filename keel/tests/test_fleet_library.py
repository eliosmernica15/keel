"""keel.fleet — F2 library: saving, isolation, path safety, provenance.

Agent flows run through the tool loop with a scripted plan adapter; HTTP
flows (upload/list/preview/download/delete) run against the real bridge
and a real temp library root (KEEL_FLEET_LIBRARY).
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time

import pytest

import keel.webapp as webapp
from keel.fleet import routes as fleet_routes
from keel.fleet import library as library_fs
from keel.providers import registry as provider_registry
from keel.providers.base import CapabilityRecord


class PlanAdapter:
    plans: list[list] = []
    instances: list["PlanAdapter"] = []

    def __init__(self, cap, *, api_key, transport=None):
        self.cap = cap
        self.api_key = api_key
        self.requests = []
        self.plan = PlanAdapter.plans.pop(0) if PlanAdapter.plans else [
            [{"kind": "text", "text": "end of plan"}]]
        self._turn = 0
        PlanAdapter.instances.append(self)

    @classmethod
    def from_env(cls, cap, *, transport=None):
        return cls(cap, api_key=os.environ.get(cap.env_var, ""),
                   transport=transport)

    def describe(self):
        return self.cap

    def complete(self, request):
        self.requests.append(request)
        turn = self.plan[min(self._turn, len(self.plan) - 1)]
        self._turn += 1
        if len(self.requests) > len(self.plan):
            turn = [{"kind": "text", "text": "end of plan"}]
        for block in turn:
            if block["kind"] == "text":
                yield {"event": "block_start", "index": 0,
                       "block": {"type": "text", "text": ""}}
                yield {"event": "text_delta", "index": 0,
                       "text": block["text"]}
                yield {"event": "block_stop", "index": 0}
                yield {"event": "message_stop", "stop_reason": "end_turn"}
            elif block["kind"] == "tool":
                yield {"event": "block_start", "index": 0,
                       "block": {"type": "tool_use",
                                 "id": block.get("id", "tool_1"),
                                 "name": block["name"],
                                 "input": block["input"]}}
                yield {"event": "block_stop", "index": 0}
                yield {"event": "message_stop", "stop_reason": "tool_use"}


OPENROUTER = CapabilityRecord(
    name="openrouter",
    base_url="https://openrouter.ai/api/v1",
    env_var="KEEL_OPENROUTER_API_KEY",
    default_model="openrouter/auto",
    supports_tools=True, supports_streaming=True,
)

PNG_1PX = bytes([
    0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
    0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
    0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
    0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
    0x89, 0x00, 0x00, 0x00, 0x0D, 0x49, 0x44, 0x41,
    0x54, 0x78, 0x9C, 0x62, 0x00, 0x01, 0x00, 0x00,
    0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00,
    0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,
    0x42, 0x60, 0x82,
])


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    PlanAdapter.plans = []
    PlanAdapter.instances = []
    monkeypatch.setenv("KEEL_FLEET_APPROVAL_TIMEOUT_S", "30")
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("KEEL_FLEET_LIBRARY", str(tmp_path / "library"))
    monkeypatch.setattr("keel.providers.registry._PROVIDERS",
                        {"openrouter": OPENROUTER})
    monkeypatch.setattr("keel.providers.registry._key_for",
                        lambda cap: "test-key")
    monkeypatch.setattr("keel.providers.registry.build_adapter",
                        lambda name, *a, **k: PlanAdapter(OPENROUTER,
                                                          api_key="test-key"))
    db_path = tmp_path / "fleet.db"
    fleet_routes.reset_store_for_tests(db_path)
    server = webapp.make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    server.db_path = db_path
    server.library_root = tmp_path / "library"
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


import http.client


def _req(server, method, path, body=None, token=None, raw=False):
    conn = http.client.HTTPConnection("127.0.0.1",
                                      server.server_address[1], timeout=30)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"X-Keel-Token": token or webapp.token(),
               "Content-Type": "application/json"}
    conn.request(method, path, body=data, headers=headers)
    resp = conn.getresponse()
    raw_bytes = resp.read()
    conn.close()
    if raw:
        return resp.status, resp.getheader("Content-Type"), raw_bytes
    try:
        doc = json.loads(raw_bytes.decode("utf-8")) if raw_bytes else {}
    except json.JSONDecodeError:
        doc = {"raw": raw_bytes.decode("utf-8", "replace")}
    return resp.status, doc


def _post(server, path, body, token=None):
    return _req(server, "POST", path, body, token)


def _get(server, path, token=None, raw=False):
    return _req(server, "GET", path, None, token, raw=raw)


def _wait(predicate, timeout=10.0, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _create_bot(server, name, engine="provider", **over):
    status, created = _post(server, "/api/fleet/bots",
                            {"name": name, "engine": engine, **over})
    assert status == 201
    return created["bot"]


def _rows(server, bot_id):
    _, body = _get(server, f"/api/fleet/bots/{bot_id}/rows")
    return body.get("rows", [])


def _pending(rows):
    states = {}
    for row in rows:
        if row["kind"] == "approval" and row["body"].get("approval_id"):
            states[row["body"]["approval_id"]] = row["body"]
    return {aid: b for aid, b in states.items() if b.get("status") == "pending"}


def _approve_once(server, bot_id):
    assert _wait(lambda: len(_pending(_rows(server, bot_id))) >= 1, timeout=8)
    approval_id = next(iter(_pending(_rows(server, bot_id))))
    status, _ = _post(server,
                      f"/api/fleet/bots/{bot_id}/approvals/{approval_id}/decide",
                      {"decision": "once"})
    assert status == 200


def _wait_turn_end(server, bot_id, count=1, timeout=10):
    assert _wait(lambda: sum(1 for r in _rows(server, bot_id)
                             if r["kind"] == "turn_end") >= count,
                timeout=timeout)


def _save_plan(server, bot_id, filename, content, task_id=None,
               encoding="utf8", mime=None):
    plan = [[{"kind": "tool", "name": "save_file",
              "input": {"filename": filename, "content": content,
                        **({"task_id": task_id} if task_id else {}),
                        **({"encoding": encoding} if encoding else {}),
                        **({"mime": mime} if mime else {})},
              "id": "save_1"}],
            [{"kind": "text", "text": "saved"}]]
    PlanAdapter.plans = [plan]
    _post(server, f"/api/fleet/bots/{bot_id}/messages", {"content": "save it"})
    _approve_once(server, bot_id)
    _wait_turn_end(server, bot_id)


# ------------------------------------------------------------ agent saving

def test_agent_saves_file_and_it_lists(bridge):
    agent = _create_bot(bridge, "Scribe")
    _save_plan(bridge, agent["id"], "notes.md", "# Findings\n\nKey facts here.")

    status, body = _get(bridge, f"/api/fleet/library?bot_id={agent['id']}")
    assert status == 200
    assert len(body["files"]) == 1
    f = body["files"][0]
    assert f["name"] == "notes.md"
    assert f["mime"].startswith("text/markdown")
    assert f["source"] == "agent"
    assert f["bot_id"] == agent["id"]
    assert f["size"] == len("# Findings\n\nKey facts here.".encode("utf-8"))
    assert f["sha256"] == hashlib.sha256(
        "# Findings\n\nKey facts here.".encode("utf-8")).hexdigest()

    # the DM shows the save notice
    texts = [r["body"].get("text", "")
             for r in _rows(bridge, agent["id"]) if r["kind"] == "notice"]
    assert any("Saved notes.md" in t for t in texts)


def test_agent_saves_binary_base64(bridge):
    agent = _create_bot(bridge, "Pixel")
    import base64
    b64 = base64.b64encode(PNG_1PX).decode("ascii")
    _save_plan(bridge, agent["id"], "pixel.png", b64,
               encoding="base64", mime="image/png")

    status, body = _get(bridge, f"/api/fleet/library?bot_id={agent['id']}")
    assert len(body["files"]) == 1
    assert body["files"][0]["mime"] == "image/png"
    assert body["files"][0]["size"] == len(PNG_1PX)

    status, ctype, raw = _get(bridge, f"/api/fleet/library/{body['files'][0]['id']}/download",
                              raw=True)
    assert status == 200
    assert raw == PNG_1PX


def test_agent_save_requires_approval(bridge):
    agent = _create_bot(bridge, "Cautious")
    PlanAdapter.plans = [
        [[{"kind": "tool", "name": "save_file",
           "input": {"filename": "nope.txt", "content": "secret"},
           "id": "s1"}],
         [{"kind": "text", "text": "after denial"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{agent['id']}/messages", {"content": "save"})
    assert _wait(lambda: len(_pending(_rows(bridge, agent["id"]))) >= 1,
                timeout=8)
    approval_id = next(iter(_pending(_rows(bridge, agent["id"]))))
    status, _ = _post(bridge,
                      f"/api/fleet/bots/{agent['id']}/approvals/{approval_id}/decide",
                      {"decision": "never"})
    assert status == 200
    _wait_turn_end(bridge, agent["id"])
    status, body = _get(bridge, f"/api/fleet/library?bot_id={agent['id']}")
    assert body["files"] == []


# ------------------------------------------------------------ path security

@pytest.mark.parametrize("bad", [
    "../escape.txt",
    "..\\escape.txt",
    "a/b.txt",
    "a\\b.txt",
    "/abs/path.txt",
    "C:\\Windows\\system32\\drivers\\etc\\hosts",
    ".hidden",
    "..",
    "",
    "x" * 121,
])
def test_filename_traversal_rejected(bridge, tmp_path, bad):
    agent = _create_bot(bridge, "Attacker")
    PlanAdapter.plans = [
        [[{"kind": "tool", "name": "save_file",
           "input": {"filename": bad, "content": "x"}, "id": "s1"}],
         [{"kind": "text", "text": "done"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{agent['id']}/messages", {"content": "save"})
    _approve_once(bridge, agent["id"])
    _wait_turn_end(bridge, agent["id"])
    status, body = _get(bridge, f"/api/fleet/library?bot_id={agent['id']}")
    assert body["files"] == []
    # and nothing escaped onto disk
    assert not (tmp_path / "library" / "escape.txt").exists()


def test_user_upload_path_traversal_rejected(bridge, tmp_path):
    agent = _create_bot(bridge, "Keeper")
    status, _ = _post(bridge, "/api/fleet/library", {
        "filename": "../../etc/passwd",
        "content": "root:x:0:0:",
        "bot_id": agent["id"],
    })
    assert status == 400
    status, _ = _post(bridge, "/api/fleet/library", {
        "filename": "legit.md",
        "content": "hello",
        "bot_id": agent["id"],
    })
    assert status == 201


# --------------------------------------------------------------- isolation

def test_files_are_owned_and_filtered(bridge):
    a = _create_bot(bridge, "Agent-A")
    b = _create_bot(bridge, "Agent-B")
    _save_plan(bridge, a["id"], "a_file.txt", "alice's work")
    _save_plan(bridge, b["id"], "b_file.txt", "bob's work")

    status, body = _get(bridge, f"/api/fleet/library?bot_id={a['id']}")
    assert [f["name"] for f in body["files"]] == ["a_file.txt"]
    status, body = _get(bridge, f"/api/fleet/library?bot_id={b['id']}")
    assert [f["name"] for f in body["files"]] == ["b_file.txt"]
    status, body = _get(bridge, "/api/fleet/library?assigned=all")
    assert {f["name"] for f in body["files"]} == {"a_file.txt", "b_file.txt"}


def test_agent_has_no_delete_or_cross_bot_tool(bridge):
    from keel.runner import RealTools
    executor = RealTools()
    with pytest.raises(KeyError):
        executor.invoke("delete_file", {"file_id": "f_whatever"})
    with pytest.raises(KeyError):
        executor.invoke("read_library", {"file_id": "f_whatever"})


def test_bot_delete_removes_library_files(bridge, tmp_path):
    agent = _create_bot(bridge, "Doomed")
    _save_plan(bridge, agent["id"], "doomed.txt", "about to vanish")

    status, body = _get(bridge, f"/api/fleet/library?bot_id={agent['id']}")
    file_id = body["files"][0]["id"]
    on_disk = tmp_path / "library" / agent["id"] / file_id
    assert on_disk.exists()

    _post(bridge, f"/api/fleet/bots/{agent['id']}/delete", {})
    assert not on_disk.exists()


# ------------------------------------------------------------- read paths

def test_download_hash_matches(bridge):
    agent = _create_bot(bridge, "Hashy")
    content = "verify me byte-for-byte: π ≈ 3.14"
    _save_plan(bridge, agent["id"], "hash.txt", content)
    _, body = _get(bridge, f"/api/fleet/library?bot_id={agent['id']}")
    file_id = body["files"][0]["id"]
    status, ctype, raw = _get(bridge,
                              f"/api/fleet/library/{file_id}/download",
                              raw=True)
    assert status == 200
    assert raw.decode("utf-8") == content
    assert hashlib.sha256(raw).hexdigest() == body["files"][0]["sha256"]


def test_preview_image_and_text(bridge):
    agent = _create_bot(bridge, "Previewer")
    import base64
    b64 = base64.b64encode(PNG_1PX).decode("ascii")
    _save_plan(bridge, agent["id"], "pic.png", b64, encoding="base64")
    _save_plan(bridge, agent["id"], "doc.md", "# Hello preview")
    # the second turn must actually finish — the first turn_end would satisfy count=1
    assert _wait(lambda: sum(1 for r in _rows(bridge, agent["id"])
                             if r["kind"] == "turn_end") >= 2, timeout=10)

    files = _get(bridge, f"/api/fleet/library?bot_id={agent['id']}")[1]["files"]
    by_name = {f["name"]: f for f in files}

    status, ctype, raw = _get(bridge,
                              f"/api/fleet/library/{by_name['pic.png']['id']}/preview",
                              raw=True)
    assert status == 200
    assert ctype == "image/png"
    assert raw == PNG_1PX

    status, ctype, raw = _get(bridge,
                              f"/api/fleet/library/{by_name['doc.md']['id']}/preview",
                              raw=True)
    assert status == 200
    assert b"# Hello preview" in raw


def test_delete_returns_gone(bridge):
    agent = _create_bot(bridge, "DeleteMe")
    _save_plan(bridge, agent["id"], "short-lived.txt", "temp")
    files = _get(bridge, f"/api/fleet/library?bot_id={agent['id']}")[1]["files"]
    fid = files[0]["id"]

    status, body = _post(bridge, f"/api/fleet/library/{fid}/delete", {})
    assert status == 200 and body["deleted"] is True
    status, _ = _get(bridge, f"/api/fleet/library/{fid}")
    assert status == 404
    status, _, _ = _get(bridge, f"/api/fleet/library/{fid}/download", raw=True)
    assert status == 404


def test_missing_file_on_disk_is_410(bridge, tmp_path):
    agent = _create_bot(bridge, "Ghost")
    _save_plan(bridge, agent["id"], "ghost.txt", "boo")
    files = _get(bridge, f"/api/fleet/library?bot_id={agent['id']}")[1]["files"]
    fid = files[0]["id"]
    os.remove(tmp_path / "library" / agent["id"] / fid)
    status, _, _ = _get(bridge, f"/api/fleet/library/{fid}/download", raw=True)
    assert status == 410


# ------------------------------------------------------------- security

def test_preview_forces_text_plain_for_active_types(bridge):
    agent = _create_bot(bridge, "Vexil")
    _save_plan(bridge, agent["id"], "evil.html",
               "<script>sessionStorage.getItem('keel_fleet_token')</script>",
               mime="text/html")
    _, body = _get(bridge, f"/api/fleet/library?bot_id={agent['id']}")
    fid = body["files"][0]["id"]
    status, ctype, raw = _req(bridge, "GET",
                              f"/api/fleet/library/{fid}/preview",
                              raw=True)
    assert status == 200
    assert ctype.startswith("text/plain"), ctype
    assert b"script" in raw


def test_preview_keeps_image_and_pdf_mimes(bridge):
    agent = _create_bot(bridge, "Vexil2")
    import base64
    b64 = base64.b64encode(PNG_1PX).decode("ascii")
    _save_plan(bridge, agent["id"], "pic.png", b64,
               encoding="base64", mime="image/png")
    _, body = _get(bridge, f"/api/fleet/library?bot_id={agent['id']}")
    fid = body["files"][0]["id"]
    status, ctype, raw = _req(bridge, "GET",
                              f"/api/fleet/library/{fid}/preview",
                              raw=True)
    assert status == 200
    assert ctype == "image/png"
    assert raw == PNG_1PX


def test_preview_sets_sandbox_csp(bridge):
    agent = _create_bot(bridge, "Vexil3")
    _save_plan(bridge, agent["id"], "notes.md", "# hi")
    _, body = _get(bridge, f"/api/fleet/library?bot_id={agent['id']}")
    fid = body["files"][0]["id"]
    conn = http.client.HTTPConnection("127.0.0.1",
                                      bridge.server_address[1], timeout=10)
    conn.request("GET", f"/api/fleet/library/{fid}/preview",
                 headers={"X-Keel-Token": webapp.token()})
    resp = conn.getresponse()
    resp.read()
    csp = resp.getheader("Content-Security-Policy") or ""
    conn.close()
    assert "default-src 'none'" in csp


def test_fleet_pages_carry_security_headers(bridge):
    conn = http.client.HTTPConnection("127.0.0.1",
                                      bridge.server_address[1], timeout=10)
    conn.request("GET", f"/fleet?t={webapp.token()}")
    resp = conn.getresponse()
    resp.read()
    csp = resp.getheader("Content-Security-Policy") or ""
    nosniff = resp.getheader("X-Content-Type-Options") or ""
    conn.close()
    assert "default-src 'none'" in csp or csp  # fleet shell must declare a policy
    assert nosniff == "nosniff"


# ---------------------------------------------------------- quota + limits

def test_agent_quota_enforced(bridge, monkeypatch):
    monkeypatch.setattr("keel.fleet.library._BOT_QUOTA_BYTES", 90)
    agent = _create_bot(bridge, "Hoarder")
    _save_plan(bridge, agent["id"], "big1.txt", "x" * 80)
    PlanAdapter.plans = [
        [[{"kind": "tool", "name": "save_file",
           "input": {"filename": "big2.txt", "content": "y" * 20},
           "id": "s2"}],
         [{"kind": "text", "text": "hit quota"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{agent['id']}/messages", {"content": "more"})
    _approve_once(bridge, agent["id"])
    _wait_turn_end(bridge, agent["id"])
    files = _get(bridge, f"/api/fleet/library?bot_id={agent['id']}")[1]["files"]
    assert [f["name"] for f in files] == ["big1.txt"]


def test_file_size_cap(bridge, monkeypatch):
    monkeypatch.setattr("keel.fleet.library.MAX_FILE_BYTES", 10)
    agent = _create_bot(bridge, "Tiny")
    PlanAdapter.plans = [
        [[{"kind": "tool", "name": "save_file",
           "input": {"filename": "too_big.txt", "content": "x" * 11},
           "id": "s1"}],
         [{"kind": "text", "text": "rejected"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{agent['id']}/messages", {"content": "save"})
    _approve_once(bridge, agent["id"])
    _wait_turn_end(bridge, agent["id"])
    status, body = _get(bridge, f"/api/fleet/library?bot_id={agent['id']}")
    assert body["files"] == []


def test_user_upload_cap(bridge):
    agent = _create_bot(bridge, "Uploader")
    status, _ = _post(bridge, "/api/fleet/library", {
        "filename": "huge.txt",
        "content": "x" * (2 * 1024 * 1024 + 1),
        "bot_id": agent["id"],
    })
    assert status == 413


# ------------------------------------------------------- task link + restart

def test_file_links_to_task(bridge):
    agent = _create_bot(bridge, "Worker")
    _, created = _post(bridge, "/api/fleet/tasks",
                       {"title": "produce artifact",
                        "assigned_bot_id": agent["id"]})
    tid = created["task"]["id"]

    _save_plan(bridge, agent["id"], "artifact.txt", "the deliverable",
               task_id=tid)
    files = _get(bridge,
                 f"/api/fleet/library?bot_id={agent['id']}&task_id={tid}")[1]["files"]
    assert [f["name"] for f in files] == ["artifact.txt"]

    status, body = _get(bridge, f"/api/fleet/tasks/{tid}")
    notes = [e for e in body["events"] if "saved artifact.txt" in e["note"]]
    assert notes, "task history should record the save"


def test_library_survives_restart(bridge, tmp_path):
    agent = _create_bot(bridge, "Durable")
    _save_plan(bridge, agent["id"], "durable.txt", "persistence check")

    fleet_routes.reset_store_for_tests(bridge.db_path)

    status, body = _get(bridge, f"/api/fleet/library?bot_id={agent['id']}")
    assert [f["name"] for f in body["files"]] == ["durable.txt"]
    fid = body["files"][0]["id"]
    status, ctype, raw = _get(bridge, f"/api/fleet/library/{fid}/download",
                              raw=True)
    assert raw.decode("utf-8") == "persistence check"
