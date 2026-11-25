import json
import multiprocessing as mp
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "int" / "keel" / "src"))
from keel import backend_workflows as bw


def worker(root, i, q):
    try:
        res = bw.run_approval_workflow({
            "state_root": str(root), "action": "request",
            "operation": "fs_read", "scope": "workflow:read",
            "subject": f"racer-{i}", "now": 1_700_000_000,
            "idempotency_key": f"req-{i}",
        })
        q.put((i, res["ok"], res["code"], res["result"].get("token", "")[:20],
               res["result"].get("request_id")))
    except Exception as exc:
        q.put((i, "EXC", type(exc).__name__, str(exc)[:120]))


if __name__ == "__main__":
    for trial in range(3):
        root = Path(tempfile.mkdtemp(prefix="probe-seal-race-"))
        q = mp.Queue()
        procs = [mp.Process(target=worker, args=(root, i, q)) for i in range(8)]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=60)
        outcomes = sorted([q.get() for _ in procs])
        print("trial", trial, "outcomes:", [(o[0], o[1], o[2]) for o in outcomes])
        failures = []
        for o in outcomes:
            if not o[1]:
                continue
            rid = o[4]
            res = bw.run_approval_workflow({
                "state_root": str(root), "action": "resolve",
                "request_id": rid, "now": 1_700_000_001,
                "idempotency_key": "resolve-" + rid,
            })
            if not res["ok"]:
                failures.append((rid, res["code"], res["result"]))
        print("  resolve failures:", failures)
