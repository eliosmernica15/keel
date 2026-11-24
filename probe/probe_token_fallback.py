import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "int" / "keel" / "src"))
from keel import backend_workflows as bw

root = Path(tempfile.mkdtemp(prefix="probe-fallback-"))
base = {"state_root": str(root), "operation": "fs_write", "scope": "workflow:write",
        "subject": "victim", "now": 1_700_000_000, "ttl_seconds": 300}
req = bw.run_approval_workflow({**base, "action": "request",
                                "idempotency_key": "req"})
rid = req["result"]["request_id"]
print("issued request_id:", rid, "sealed token withheld from caller")

# Attacker supplies only request_id; the workflow silently falls back to the
# sealed token stored in the shared ledger.
res = bw.run_approval_workflow({
    **base, "action": "resolve", "request_id": rid,
    "idempotency_key": "attacker-resolve",
})
print("resolve without token:", res["ok"], res["code"],
      res["result"].get("grant"))
