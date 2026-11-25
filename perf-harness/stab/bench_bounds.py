"""Unbounded-queue / recursion-bound checks (read-only, in-process)."""
import json, sys, time, tracemalloc
HERE = r"C:\Users\Admin\AppData\Local\Temp\opencode\stab-perf"
sys.path.insert(0, HERE)
from benchcommon import rss_bytes, use_worktree
use_worktree()
from keel.steering import SteeringController, SteeringMode
from keel import tool_contracts as tc

out = {}

# SteeringController retains every message and never drains in QUEUE mode.
c = SteeringController()
rss0 = rss_bytes()
tracemalloc.start()
t0 = time.perf_counter()
N = 20000
for i in range(N):
    c.submit_message(f"message-{i}-" + "x" * 80, SteeringMode.QUEUE)
elapsed = time.perf_counter() - t0
cur, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()
rss1 = rss_bytes()
snap = c.snapshot()
out["steering_unbounded_retention"] = {
    "submitted": N, "elapsed_s": round(elapsed, 3),
    "all_messages": len(c.all_messages()),
    "queued": len(snap.queued), "boundary": len(snap.boundary),
    "resume_pending": len(snap.resume_pending), "delivered": len(snap.delivered),
    "rss_before_bytes": rss0, "rss_after_bytes": rss1,
    "rss_delta_bytes": (rss1 - rss0) if rss0 and rss1 else None,
    "tracemalloc_current_bytes": cur, "tracemalloc_peak_bytes": peak,
    "queue_is_bounded": False,
}
print("steering retention:", out["steering_unbounded_retention"])

# Recursion/node/string bounds on tool args.
def bounded(fn):
    try:
        fn(); return "accepted"
    except Exception as exc:
        return f"{type(exc).__name__}:{getattr(exc, 'code', '')}"

deep = 1
for _ in range(200): deep = [deep]
wide = list(range(20000))
longstr = "z" * 100000
out["tool_arg_bounds"] = {
    "depth_10": bounded(lambda: tc.to_jsonable([[[[[1]]]]])),
    "depth_200": bounded(lambda: tc.to_jsonable(deep)),
    "nodes_20000": bounded(lambda: tc.to_jsonable(wide)),
    "string_100000": bounded(lambda: tc.to_jsonable(longstr)),
}
print("tool arg bounds:", out["tool_arg_bounds"])

with open(HERE + r"\result_bounds.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
print("wrote result_bounds.json")
