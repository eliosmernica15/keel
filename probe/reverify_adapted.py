"""Adapted re-verification probes for fixes landed after the original review.

Thrown-away script; imports the current integration tree from probe/int.
"""

import http.client
import json
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "int" / "keel" / "src"))

from keel import backend_workflows as bw
from keel import webapp

root = Path(tempfile.mkdtemp(prefix="reverify-"))

# --- H2: trusted clock ------------------------------------------------------
state = root / "trusted-clock"
state.mkdir()
orig_now = bw._now
bw._now = lambda: 1_700_000_000  # only during issue
req = bw.run_approval_workflow({
    "state_root": str(state), "action": "request", "operation": "fs_read",
    "scope": "workflow:read", "subject": "clock-test", "ttl_seconds": 60,
})
bw._now = orig_now  # real clock is now far past the issued expiry
res = bw.run_approval_workflow({
    "state_root": str(state), "action": "resolve",
    "request_id": req["result"]["request_id"],
    "token": req["result"]["token"],
    "now": 1_700_000_030,  # attacker-claimed in-window time: must be ignored
    "idempotency_key": "clock-resolve",
})
print("H2 expired token with claimed in-window time:",
      res["ok"], res["code"], res["result"].get("error"))

# --- M1: path confinement / no arbitrary write -----------------------------
paths_root = root / "paths"
paths_root.mkdir()
state_root = paths_root / "state"
state_root.mkdir()
secret_dir = paths_root / "victim"
secret_dir.mkdir()
secret_file = secret_dir / "credentials.txt"
secret_file.write_text("API_KEY=supersecret123\n", encoding="utf-8")

read = bw.run_request_workflow({
    "state_root": str(state_root), "project_root": str(secret_dir),
    "file_path": str(secret_file), "query": "credentials",
})
print("M1 read outside state root:", read["ok"], read["code"])
print("   content leaked:", "supersecret123" in json.dumps(read))

startup = paths_root / "startup"
startup.mkdir()
recovery = bw.run_recovery_workflow({
    "state_root": str(paths_root / "state2"), "folder": str(startup),
    "content": "PERSISTED-BY-WORKFLOW",
})
marker = startup / "recovery-note.md"
print("M1 write outside state root:", recovery["ok"], recovery["code"],
      "marker exists:", marker.exists())

# --- M2: redaction of persisted/returned file content ----------------------
redact_root = root / "redact"
redact_root.mkdir()
note = redact_root / "notes.md"
note.write_text("API_KEY=supersecret123\n", encoding="utf-8")
redacted = bw.run_request_workflow({
    "state_root": str(redact_root), "file_path": str(note), "query": "notes",
})
ledger = redact_root / "backend-workflows" / "request-results.jsonl"
print("M2 redaction: result ok:", redacted["ok"],
      "plaintext in response:", "supersecret123" in json.dumps(redacted),
      "plaintext in ledger:", "supersecret123" in ledger.read_text(encoding="utf-8"))

# --- M3 / webapp: status hints ---------------------------------------------
srv = webapp.make_server(0)
t = threading.Thread(target=srv.serve_forever, daemon=True)
t.start()


def post(path, params, tag):
    body = json.dumps({"confirm": True, "params": params}).encode()
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=30)
    conn.request("POST", path, body=body, headers={
        "Content-Type": "application/json", "X-Keel-Token": webapp.token()})
    r = conn.getresponse()
    raw = r.read().decode()
    conn.close()
    try:
        out = json.loads(raw)
    except ValueError:
        out = {}
    print(f"M3 {tag}: status={r.status} code={out.get('code')}")


post("/api/backend-workflows/approval",
     {"state_root": str(root / "web1"), "operation": "network_egress",
      "profile": "no_network"}, "operation_denied")
post("/api/backend-workflows/approval",
     {"state_root": str(root / "web2"), "operation": "fs_read",
      "headers": {"Origin": "https://evil.test"},
      "expected_origin": "https://good.test"}, "csrf_denied")
post("/api/backend-workflows/mcp",
     {"state_root": str(root / "web3"), "manifest": 123}, "bad_manifest")
post("/api/backend-workflows/approval",
     {"state_root": str(root / "web4"), "operation": "fs_read", "ttl_seconds": 0},
     "ttl_zero")
post("/api/backend-workflows/request",
     {"state_root": str(root / "web5"), "project_root": str(secret_dir),
      "file_path": str(secret_file)}, "path_escape")
srv.shutdown()
srv.server_close()
t.join(timeout=5)

# --- M5: honest MCP dry-run -------------------------------------------------
mcp_root = root / "mcp"
mcp_root.mkdir()
manifest = {"name": "demo", "surfaces": ["server"]}
ok_run = bw.run_mcp_workflow({
    "state_root": str(mcp_root), "manifest": manifest,
    "tools": ["echo"], "tool": "echo",
})
failed = bw.run_mcp_workflow({
    "state_root": str(mcp_root), "idempotency_key": "fail",
    "manifest": manifest, "tools": ["echo"], "tool": "echo", "fail": True,
})
print("M5 MCP dry-run: ok:", ok_run["ok"], "code:", ok_run["code"],
      "dry_run:", ok_run["result"].get("dry_run"),
      "command_executed:", ok_run["result"].get("command_executed"))
print("M5 MCP failure: ok:", failed["ok"], "code:", failed["code"],
      "outcome:", failed["result"].get("outcome"))
