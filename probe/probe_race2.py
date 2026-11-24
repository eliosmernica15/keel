import json
import multiprocessing as mp
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "int" / "keel" / "src"))
from keel import backend_workflows as bw


def worker(params, q, tag):
    try:
        res = bw.run_request_workflow(params)
        q.put((tag, res["ok"], res["code"]))
    except Exception as exc:
        q.put((tag, "EXC", type(exc).__name__, str(exc)[:120]))


if __name__ == "__main__":
    root = Path(tempfile.mkdtemp(prefix="probe-race2-"))
    (root / "note.txt").write_text("hello", encoding="utf-8")
    params = {"state_root": str(root), "project_root": str(root),
              "file_path": str(root / "note.txt"), "query": "hello"}
    q = mp.Queue()
    procs = [mp.Process(target=worker, args=(params, q, f"p{i}")) for i in range(6)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=60)
    print("outcomes:", sorted([q.get() for _ in range(len(procs))]))
    path = root / "backend-workflows" / "request-results.jsonl"
    recs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    print("records:", len(recs), "sequences:", [r["sequence"] for r in recs],
          "keys equal:", len({r["idempotency_key"] for r in recs}) == 1)
