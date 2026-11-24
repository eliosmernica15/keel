"""In-process capability-hub and backend-hub invocation latency (warm)."""
import json, sys, time
HERE = r"C:\Users\Admin\AppData\Local\Temp\opencode\prod-perf"
sys.path.insert(0, HERE)
from benchcommon import stats, use_worktree
use_worktree()
from keel import capabilities as caps
from keel import backend_hub as hub

results = {}

def bench(name, fn, n=1000):
    lats=[]
    for _ in range(n):
        t=time.perf_counter(); fn(); lats.append((time.perf_counter()-t)*1000)
    results[name]=stats(lats)
    print(f"{name:38s} p50={results[name]['p50']:.4f} p95={results[name]['p95']:.4f} p99={results[name]['p99']:.4f} ms")

bench("caps.invoke backend.modules", lambda: caps.invoke("backend.modules"))
bench("caps.invoke backend.describe", lambda: caps.invoke("backend.describe", {"module":"e5_backend"}))
bench("caps.invoke backend.invoke e5.validate_app_id",
      lambda: caps.invoke("backend.invoke", {"module":"e5_backend","function":"validate_app_id","params":{"app_id":"com.nice.app"}}))
bench("hub.invoke e5.validate_app_id",
      lambda: hub.invoke("e5_backend","validate_app_id",{"app_id":"com.nice.app"}))
bench("hub.describe(all)",
      lambda: hub.describe())
bench("hub.sync_capability_schemas", lambda: hub.sync_capability_schemas())

with open(HERE+r"\result_cap.json","w") as f: json.dump(results,f,indent=2)
print("wrote result_cap.json")
