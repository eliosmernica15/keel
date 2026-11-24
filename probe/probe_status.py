import http.client
import json
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "int" / "keel" / "src"))
from keel import webapp

root = Path(tempfile.mkdtemp(prefix="probe-status-"))
srv = webapp.make_server(0)
t = threading.Thread(target=srv.serve_forever, daemon=True)
t.start()

cases = [
    ("approval policy denial", "/api/backend-workflows/approval",
     {"state_root": str(root / "a"), "operation": "network_egress", "profile": "no_network"}),
    ("approval bad ttl", "/api/backend-workflows/approval",
     {"state_root": str(root / "b"), "operation": "fs_read", "ttl_seconds": 0}),
    ("approval csrf denial", "/api/backend-workflows/approval",
     {"state_root": str(root / "c"), "operation": "fs_read",
      "headers": {"Origin": "https://evil.test"},
      "expected_origin": "https://good.test"}),
    ("request path escape", "/api/backend-workflows/request",
     {"state_root": str(root / "d"), "project_root": str(root / "d"),
      "file_path": "../secret.txt"}),
    ("delegation bound", "/api/backend-workflows/delegation",
     {"state_root": str(root / "e"), "child_tasks": ["a", "b", "c"], "max_children": 1}),
    ("mcp invalid manifest", "/api/backend-workflows/mcp",
     {"state_root": str(root / "f"), "manifest": 123}),
]
for label, path, params in cases:
    body = json.dumps({"confirm": True, "params": params}).encode()
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=30)
    conn.request("POST", path, body=body, headers={"Content-Type": "application/json",
                 "X-Keel-Token": webapp.token()})
    r = conn.getresponse()
    raw = r.read().decode()
    conn.close()
    try:
        out = json.loads(raw)
    except ValueError:
        out = raw[:100]
    print(f"{label:26s} -> {r.status} code={out.get('code') if isinstance(out, dict) else out}")

srv.shutdown(); srv.server_close(); t.join(timeout=5)
