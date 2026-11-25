"""Read-only live HTTP probe of the Keel Python bridge.

Starts the real bridge on an ephemeral port (same code path as the pytest
`compat_server` fixture), issues GET requests for the supplied safe/read-only
paths, and prints a JSON map of path -> HTTP status on stdout.

No state is mutated: only GET endpoints are probed, and the caller supplies
an explicit allowlist. The bridge token is set by the caller (Node harness).
"""
from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
KEEL = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(KEEL, "src"))

TOKEN = os.environ.get("KEEL_TOKEN", "qa-static-probe-token")
os.environ["KEEL_TOKEN"] = TOKEN

paths = json.load(sys.stdin)
if not isinstance(paths, list):
    raise SystemExit("expected a JSON array of paths")

import keel.webapp as webapp  # noqa: E402

srv = webapp.make_server(0)
port = srv.server_address[1]
t = threading.Thread(target=srv.serve_forever, daemon=True)
t.start()
out: dict[str, int] = {}
try:
    for suffix in paths:
        url = f"http://127.0.0.1:{port}/api/fleet/{suffix}"
        req = urllib.request.Request(
            url,
            headers={"X-Keel-Token": TOKEN, "Origin": f"http://127.0.0.1:{port}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                out[suffix] = resp.status
                resp.read()
        except urllib.error.HTTPError as exc:
            out[suffix] = exc.code
            exc.read()
        except Exception:  # noqa: BLE001
            out[suffix] = 0
finally:
    srv.shutdown()
    srv.server_close()
    t.join(timeout=5)

json.dump(out, sys.stdout, indent=2)
print()
