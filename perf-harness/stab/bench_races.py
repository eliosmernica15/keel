"""Duplicate-submission races and cancellation races (read-only measurement)."""
import json, os, sys, tempfile, threading, time
from collections import Counter
from pathlib import Path
HERE = r"C:\Users\Admin\AppData\Local\Temp\opencode\stab-perf"
sys.path.insert(0, HERE)
from benchcommon import stats, use_worktree
use_worktree()

BASE = Path(tempfile.mkdtemp(prefix="stabrace_"))
os.environ["KEEL_STATE_DIR"] = str(BASE)
from keel import backend_workflows as bw
from keel.fleet.service import FleetStore
from keel.fleet import scheduler, turn_core
from keel.steering import SteeringController, SteeringMode
import keel.tool_contracts as tc

out = {}

# --- duplicate submission race: identical workflow params + key, 16 threads ---
def duplicate_submission(threads=16):
    root = BASE / "dupe_submission"
    p = {"state_root": str(root), "idempotency_key": "same-key",
         "manifest": {"name": "demo", "surfaces": ["server"]},
         "tools": ["echo"], "tool": "echo"}
    barrier = threading.Barrier(threads)
    codes, errs = Counter(), []
    lock = threading.Lock()
    def w():
        barrier.wait()
        try:
            res = bw.run_mcp_workflow(p)
            with lock: codes[str(res.get("code"))] += 1
        except Exception as exc:
            with lock: errs.append(f"{type(exc).__name__}: {exc}")
    ts = [threading.Thread(target=w) for _ in range(threads)]
    t0 = time.perf_counter()
    for t in ts: t.start()
    for t in ts: t.join()
    el = time.perf_counter() - t0
    ledger = root / "backend-workflows" / "mcp-results.jsonl"
    lines = len(ledger.read_text(encoding="utf-8").splitlines()) if ledger.exists() else 0
    return {"threads": threads, "elapsed_s": round(el, 3), "codes": dict(codes),
            "exceptions": len(errs), "error_samples": errs[:3],
            "ledger_records": lines,
            "single_winner": lines == 1}

out["duplicate_submission_race"] = duplicate_submission()
print("duplicate submission:", out["duplicate_submission_race"])

# --- same-name bot creation race (32 threads) ---
def bot_race(threads=32):
    st = FleetStore(BASE / "botrace.db")
    barrier = threading.Barrier(threads); ok = [0]; errs = []
    lock = threading.Lock()
    def w():
        barrier.wait()
        try:
            st.create_bot(name="same", engine="echo")
            with lock: ok[0] += 1
        except Exception as exc:
            with lock: errs.append(f"{type(exc).__name__}: {exc}")
    ts = [threading.Thread(target=w) for _ in range(threads)]
    for t in ts: t.start()
    for t in ts: t.join()
    ids = [b["id"] for b in st.list_bots()]
    st.close()
    return {"threads": threads, "succeeded": ok[0], "errors": len(errs),
            "error_samples": errs[:3], "distinct_bots": len(set(ids)), "ids": sorted(ids)}

out["bot_create_race_32"] = bot_race()
print("bot create race:", out["bot_create_race_32"])

# --- cancellation race: timed-out routine workers keep running ---
def cancellation_race(n=5):
    os.environ["KEEL_FLEET_ROUTINE_TIMEOUT_S"] = "0.4"
    orig = turn_core.execute_turn
    def slow(*a, **kw):
        time.sleep(2.0)
        return {"ok": True, "assistant_text": "slow done"}
    turn_core.execute_turn = slow
    st = FleetStore(BASE / "cancel.db")
    b = st.create_bot(name="b", engine="echo")
    outcomes = []
    try:
        for i in range(n):
            r = st.create_routine(name=f"r{i}", bot_id=b["id"], prompt="p",
                                  cron_expr="0 0 * * *")
            routine = st.get_routine(r["id"])
            t0 = time.perf_counter()
            result = scheduler.execute_routine(st, routine)
            live = [t.name for t in threading.enumerate()
                    if t.name.startswith("fleet-routine-")]
            outcomes.append({"elapsed_ms": round((time.perf_counter()-t0)*1000, 1),
                             "error": result.get("error"),
                             "terminal_reason": result.get("terminal_reason"),
                             "live_routine_workers_right_after_timeout": len(live)})
        time.sleep(2.3)
        live_after = [t.name for t in threading.enumerate()
                      if t.name.startswith("fleet-routine-")]
    finally:
        turn_core.execute_turn = orig
        os.environ.pop("KEEL_FLEET_ROUTINE_TIMEOUT_S", None)
        st.close()
    return {"cases": n, "results": outcomes,
            "live_workers_after_2_3s": len(live_after),
            "workers_stranded": any(o["live_routine_workers_right_after_timeout"] > 0
                                    for o in outcomes)}

out["cancellation_race"] = cancellation_race()
print("cancellation race:", out["cancellation_race"])

# --- steering submit vs cancel race: no message lost, no exception ---
def steering_race(threads=8, each=200):
    c = SteeringController()
    errs = []
    submitted = [0]
    lock = threading.Lock()
    barrier = threading.Barrier(threads + 1)  # workers + canceller
    def w(tid):
        barrier.wait()
        for j in range(each):
            try:
                c.submit_message(f"m{tid}_{j}",
                                 SteeringMode.QUEUE if j % 2 else SteeringMode.STEER_AT_BOUNDARY)
                with lock: submitted[0] += 1
            except Exception as exc:
                with lock: errs.append(f"{type(exc).__name__}: {exc}")
    def canceller():
        barrier.wait()
        for _ in range(20):
            c.abort()
            time.sleep(0.001)
    ts = [threading.Thread(target=w, args=(i,)) for i in range(threads)]
    ct = threading.Thread(target=canceller)
    for t in ts: t.start()
    ct.start()
    for t in ts: t.join()
    ct.join()
    snap = c.snapshot()
    all_count = len(c.all_messages())
    retained = (len(snap.queued) + len(snap.boundary) + len(snap.resume_pending)
                + len(snap.delivered))
    return {"threads": threads, "submitted": submitted[0], "all_messages": all_count,
            "retained_in_queues": retained, "abort_count": snap.abort_count,
            "cancelled": snap.cancelled,
            "exceptions": len(errs), "error_samples": errs[:3]}

out["steering_cancel_race"] = steering_race()
print("steering race:", out["steering_cancel_race"])

# --- recursion / depth bound check on tool args ---
def recursion_bounds():
    res = {}
    for depth in (10, 50, 200, 1000):
        v = 1
        for _ in range(depth): v = [v]
        try:
            tc.to_jsonable(v)
            res[str(depth)] = "accepted"
        except Exception as exc:
            res[str(depth)] = f"{type(exc).__name__}: {getattr(exc, 'code', '')}"
    return res

out["recursion_bounds"] = recursion_bounds()
print("recursion bounds:", out["recursion_bounds"])

with open(HERE + r"\result_races.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
print("wrote result_races.json")
