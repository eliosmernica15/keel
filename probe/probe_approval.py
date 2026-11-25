import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "int" / "keel" / "src"))

from keel import backend_workflows as bw

root = Path(tempfile.mkdtemp(prefix="probe-approval-"))
base = {
    "state_root": str(root),
    "operation": "fs_write",
    "scope": "workflow:write",
    "subject": "victim",
    "ttl_seconds": 60,
    "now": 1_700_000_000,
}

req = bw.run_approval_workflow({**base, "action": "request", "idempotency_key": "req"})
print("REQUEST ok:", req["ok"], "expires_at:", req["result"].get("expires_at"))
rid = req["result"]["request_id"]
token = req["result"]["token"]

# Real current time is far beyond the 60-second TTL. Caller supplies an
# in-window timestamp to unseal/verify/consume instead.
for label, now in (("real-time", 1_900_000_000), ("caller-claimed", 1_700_000_030)):
    res = bw.run_approval_workflow({
        **base, "action": "resolve", "request_id": rid, "token": token,
        "now": now, "idempotency_key": "resolve-" + label,
    })
    print(label, "ok:", res["ok"], "code:", res["code"],
          "granted:", res["result"].get("grant", {}).get("granted"))
    if not res["ok"]:
        print("   result:", res["result"])

ledger = root / "backend-workflows" / "approval-events.jsonl"
print("--- approval ledger ---")
for line in ledger.read_text(encoding="utf-8").splitlines():
    rec = json.loads(line)
    print(rec["action"], "token_dict=" + repr(rec.get("token_dict")),
          "sealed=" + repr(rec.get("token", ""))[:40])
