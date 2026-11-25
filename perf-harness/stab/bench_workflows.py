"""Concurrent execution of the five real backend workflow types + worker budget."""
import json, os, sys, tempfile, threading, time
from collections import Counter
from pathlib import Path
HERE = r"C:\Users\Admin\AppData\Local\Temp\opencode\stab-perf"
sys.path.insert(0, HERE)
from benchcommon import stats, use_worktree
use_worktree()

BASE = Path(tempfile.mkdtemp(prefix="stabwf_"))
os.environ["KEEL_STATE_DIR"] = str(BASE)
from keel import backend_workflows as bw
from keel import d7_workflow_backend as d7

out = {"state_base": str(BASE), "workflow_names": list(bw.WORKFLOW_NAMES)}

def params_for(name, idx, root):
    root.mkdir(parents=True, exist_ok=True)
    if name == "request":
        note = root / "runbook.md"
        note.write_text("deployment runbook recovery marker", encoding="utf-8")
        return {"state_root": str(root), "project_root": str(root),
                "file_path": str(note), "query": "runbook", "prompt": "read the runbook"}
    if name == "approval":
        return {"state_root": str(root), "operation": "fs_write", "scope": "workflow:write",
                "subject": f"tester{idx}", "profile": "no_network",
                "now": 1_700_000_000, "ttl_seconds": 300}
    if name == "delegation":
        return {"state_root": str(root), "child_tasks": ["alpha", "beta"]}
    if name == "mcp":
        return {"state_root": str(root), "manifest": {"name": "demo", "surfaces": ["server"]},
                "server_name": "demo", "tools": ["echo", "secret"],
                "deny_tools": ["secret"], "tool": "echo"}
    if name == "recovery":
        return {"state_root": str(root), "query": "recovery",
                "content": "recovery marker for interruption\n", "user": "test-user"}
    raise ValueError(name)

RUNNER = {
    "request": bw.run_request_workflow,
    "approval": bw.run_approval_workflow,
    "delegation": bw.run_delegation_workflow,
    "mcp": bw.run_mcp_workflow,
    "recovery": bw.run_recovery_workflow,
}

def once(name, fn):
    root = BASE / f"{name}_single_{int(time.perf_counter_ns())}"
    p = params_for(name, 0, root)
    t = time.perf_counter()
    res = fn(p)
    ms = (time.perf_counter() - t) * 1000
    return {"elapsed_ms": round(ms, 2), "ok": bool(res.get("ok")),
            "code": res.get("code"), "result_keys": sorted(res.keys())[:12]}

for name, fn in RUNNER.items():
    out[f"single_{name}"] = once(name, fn)
    print(f"single {name:11s} {out[f'single_{name}']['elapsed_ms']:8.2f} ms "
          f"ok={out[f'single_{name}']['ok']} code={out[f'single_{name}']['code']}")

def concurrent(name, fn, threads=8, each=2):
    lat, codes, errs = [], Counter(), []
    lock = threading.Lock()
    barrier = threading.Barrier(threads)
    def worker(tid):
        local_ms, local_codes, local_errs = [], [], []
        barrier.wait()
        for j in range(each):
            idx = tid * each + j
            root = BASE / f"{name}_{idx}_{int(time.perf_counter_ns())}"
            p = params_for(name, idx, root)
            t = time.perf_counter()
            try:
                res = fn(p)
                local_codes.append(str(res.get("code")))
            except Exception as exc:
                local_errs.append(f"{type(exc).__name__}: {exc}")
            local_ms.append((time.perf_counter() - t) * 1000)
        with lock:
            lat.extend(local_ms); codes.update(local_codes); errs.extend(local_errs)
    ts = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
    t0 = time.perf_counter()
    for t in ts: t.start()
    for t in ts: t.join()
    el = time.perf_counter() - t0
    n = threads * each
    return {"threads": threads, "calls_each": each, "calls": n,
            "elapsed_s": round(el, 3), "calls_s": round(n / el, 1),
            "codes": dict(codes), "exceptions": len(errs), "error_samples": errs[:3],
            "latency_ms": stats(lat)}

for name, fn in RUNNER.items():
    r = concurrent(name, fn)
    out[f"concurrent_{name}"] = r
    print(f"concurrent {name:11s} calls={r['calls']:3d} calls/s={r['calls_s']:7.2f} "
          f"p50={r['latency_ms']['p50']:8.2f} p99={r['latency_ms']['p99']:9.2f} "
          f"codes={r['codes']} exc={r['exceptions']}")

# worker-budget computation (bounded workers), measured in-process
budgets = {
    "local_16cpus_cap8": d7.make_worker_budget(16, False, 8, None),
    "ci_16cpus_cap8": d7.make_worker_budget(16, True, 8, None),
    "ci_16cpus_cgroup2_5": d7.make_worker_budget(16, True, 8, 2.5),
    "local_1cpu_cgroup0_5": d7.make_worker_budget(1, False, 8, 0.5),
}
out["worker_budget_effective"] = {
    k: {"budget": v.as_dict(), "effective_workers": d7.effective_workers(v)}
    for k, v in budgets.items()}
print("worker budgets:", out["worker_budget_effective"])

with open(HERE + r"\result_workflows.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
print("wrote result_workflows.json")
