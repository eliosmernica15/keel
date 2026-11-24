import json
import multiprocessing as mp
import sys
import tempfile
from pathlib import Path

SRC = str(Path(__file__).parent / "int" / "keel" / "src")
sys.path.insert(0, SRC)

from keel import backend_workflows as bw


def worker(params, q, tag):
    try:
        res = bw.run_approval_workflow(params)
        q.put((tag, res["ok"], res["code"],
               res["result"].get("grant", {}).get("granted")))
    except Exception as exc:
        q.put((tag, "EXC", type(exc).__name__, str(exc)[:120]))


if __name__ == "__main__":
    root = Path(tempfile.mkdtemp(prefix="probe-race-"))
    params = {
        "state_root": str(root), "operation": "fs_read", "scope": "workflow:read",
        "subject": "racer", "now": 1_700_000_000, "ttl_seconds": 300,
    }
    # Seed a request first (no race there).
    req = bw.run_approval_workflow({**params, "action": "request",
                                    "idempotency_key": "seed"})
    rid = req["result"]["request_id"]
    token = req["result"]["token"]

    resolve = {**params, "action": "resolve", "request_id": rid, "token": token}
    q = mp.Queue()
    procs = [mp.Process(target=worker, args=({**resolve,
             "idempotency_key": f"racer-{i}"}, q, f"p{i}")) for i in range(8)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=60)
    outcomes = []
    while not q.empty():
        outcomes.append(q.get())
    print("resolve outcomes:", sorted(outcomes))
    ledger = root / "backend-workflows" / "approval-results.jsonl"
    recs = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    print("workflow ledger records:", len(recs), "ok:", [r["ok"] for r in recs])
    events = root / "backend-workflows" / "approval-events.jsonl"
    evs = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
    print("consume events:", sum(1 for e in evs if e.get("action") == "consume"))
