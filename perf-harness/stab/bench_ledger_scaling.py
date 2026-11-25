"""Per-call cost of growing backend-workflow JSONL ledgers (read-back scan)."""
import json, os, sys, tempfile, time, statistics
from pathlib import Path
HERE = r"C:\Users\Admin\AppData\Local\Temp\opencode\stab-perf"
sys.path.insert(0, HERE)
from benchcommon import stats, use_worktree
use_worktree()
BASE = Path(tempfile.mkdtemp(prefix="stabledger_"))
os.environ["KEEL_STATE_DIR"] = str(BASE)
from keel import backend_workflows as bw

note = BASE / "runbook.md"
note.write_text("deployment runbook recovery marker", encoding="utf-8")

def params(i):
    return {"state_root": str(BASE), "project_root": str(BASE),
            "file_path": str(note), "query": "runbook",
            "prompt": "read the runbook", "idempotency_key": f"key-{i}"}

lat = []
for i in range(300):
    t = time.perf_counter()
    res = bw.run_request_workflow(params(i))
    lat.append((time.perf_counter() - t) * 1000)
    if res.get("code") != "ok":
        raise SystemExit(f"unexpected code at {i}: {res.get('code')}")
ledger = BASE / "backend-workflows" / "request-results.jsonl"
out = {
    "calls": len(lat),
    "ledger_bytes": ledger.stat().st_size,
    "first_50_p50_ms": round(statistics.median(lat[:50]), 3),
    "middle_50_p50_ms": round(statistics.median(lat[125:175]), 3),
    "last_50_p50_ms": round(statistics.median(lat[-50:]), 3),
    "last_50_p95_ms": round(stats(lat[-50:])["p95"], 3),
    "latency_ms": stats(lat),
}
print(json.dumps(out, indent=2))
with open(HERE + r"\result_ledger_scaling.json", "w") as f:
    json.dump(out, f, indent=2)
print("wrote result_ledger_scaling.json")
