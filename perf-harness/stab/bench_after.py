"""Before/after benchmark for the two implemented stabilization fixes."""
import json, os, sys, tempfile, threading, time, tracemalloc
from pathlib import Path
HERE = r"C:\Users\Admin\AppData\Local\Temp\opencode\stab-perf"
sys.path.insert(0, HERE)
from benchcommon import rss_bytes, use_worktree
use_worktree()
from keel.steering import SteeringController, SteeringMode
from keel.fleet import scheduler, turn_core
from keel.fleet.service import FleetStore

OUT = {}
TMP = Path(tempfile.mkdtemp(prefix="stabafter_"))

# --- steering: same 20k-submission workload as the original benchmark ---
def steering(cap=None):
    kwargs = {} if cap is None else {"max_messages": cap, "max_protected": 16}
    c = SteeringController(**kwargs)
    rss0 = rss_bytes()
    tracemalloc.start()
    t0 = time.perf_counter()
    for i in range(20000):
        c.submit_message(f"message-{i}-" + "x" * 80, SteeringMode.QUEUE)
    elapsed = time.perf_counter() - t0
    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rss1 = rss_bytes()
    return {"submitted": 20000, "cap": c.max_messages, "retained": len(c.all_messages()),
            "overflow": c.overflow_count, "elapsed_s": round(elapsed, 3),
            "rss_delta_bytes": (rss1 - rss0) if rss0 and rss1 else None,
            "tracemalloc_current_bytes": cur, "tracemalloc_peak_bytes": peak}

OUT["steering_default"] = steering()
OUT["steering_cap_256"] = steering(256)
print("steering default:", OUT["steering_default"])
print("steering cap 256:", OUT["steering_cap_256"])

# --- cooperative cancellation (real turn_core primitive) ---
os.environ["KEEL_FLEET_ROUTINE_TIMEOUT_S"] = "0.4"
os.environ["KEEL_FLEET_ROUTINE_MAX_WORKERS"] = "2"
os.environ["KEEL_FLEET_ROUTINE_CANCEL_GRACE_S"] = "0.5"
scheduler.reset_workers_for_tests()

def cooperative_fake(store, agent, prompt, **kwargs):
    bot_id = agent["id"]
    ev = turn_core._register_active_turn(bot_id)
    deadline = time.monotonic() + 5.0
    try:
        while not ev.wait(0.01):
            if time.monotonic() > deadline:
                break
        return {"ok": True, "assistant_text": "cancelled"}
    finally:
        turn_core._unregister_active_turn(bot_id, ev)

def live():
    return [t.name for t in threading.enumerate()
            if t.name.startswith("fleet-routine-")]

def routine_for(store):
    b = store.create_bot(name="b", engine="echo")
    r = store.create_routine(name="r", bot_id=b["id"], prompt="p",
                             cron_expr="0 0 * * *")
    return store.get_routine(r["id"])

orig = turn_core.execute_turn
turn_core.execute_turn = cooperative_fake
store = FleetStore(TMP / "coop.db")
routine = routine_for(store)
cases = []
try:
    for _ in range(5):
        t0 = time.perf_counter()
        res = scheduler.execute_routine(store, routine)
        cases.append({"elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
                      "error": res.get("error"),
                      "elapsed_s_field": res.get("elapsed_s"),
                      "worker_stopped": res.get("worker_stopped"),
                      "live_workers_after_timeout": len(live()),
                      "active_workers": scheduler.active_worker_count()})
finally:
    turn_core.execute_turn = orig
    store.close()
OUT["cooperative_timeouts"] = {"cases": 5, "results": cases,
                               "live_workers_after_all": len(live())}
print("cooperative timeouts:", OUT["cooperative_timeouts"])

# --- cap under concurrent stubborn workers ---
os.environ["KEEL_FLEET_ROUTINE_TIMEOUT_S"] = "0.15"
os.environ["KEEL_FLEET_ROUTINE_MAX_WORKERS"] = "2"
os.environ["KEEL_FLEET_ROUTINE_CANCEL_GRACE_S"] = "0.05"
scheduler.reset_workers_for_tests()

def stubborn_fake(store, agent, prompt, **kwargs):
    time.sleep(0.35)
    return {"ok": True, "assistant_text": "late"}

turn_core.execute_turn = stubborn_fake
store = FleetStore(TMP / "cap.db")
routine = routine_for(store)
peak = [0]
done = threading.Event()

def monitor():
    while not done.is_set():
        peak[0] = max(peak[0], scheduler.active_worker_count())
        time.sleep(0.005)

w = threading.Thread(target=monitor, daemon=True); w.start()
try:
    ts = [threading.Thread(target=lambda: scheduler.execute_routine(store, routine))
          for _ in range(5)]
    for t in ts: t.start()
    for t in ts: t.join(timeout=15)
finally:
    done.set(); w.join(timeout=2)
    turn_core.execute_turn = orig
    store.close()
deadline = time.monotonic() + 3.0
while scheduler.active_worker_count() and time.monotonic() < deadline:
    time.sleep(0.01)
OUT["worker_cap"] = {"configured_limit": 2, "peak_active_workers": peak[0],
                     "live_workers_after_drain": len(live()),
                     "active_workers_after_drain": scheduler.active_worker_count()}
print("worker cap:", OUT["worker_cap"])

with open(HERE + r"\result_perf_after.json", "w") as f:
    json.dump(OUT, f, indent=2)
print("wrote result_perf_after.json")
