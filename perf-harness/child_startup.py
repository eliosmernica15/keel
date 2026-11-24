"""Child process: time a target import, signal READY, then exit immediately."""
import sys
import time
sys.path.insert(0, r"C:\Users\Admin\AppData\Local\Temp\opencode\prod-perf")
from benchcommon import use_worktree
use_worktree()

mode = sys.argv[1]
t0 = time.perf_counter()
if mode == "none":
    pass
elif mode == "keel":
    import keel
elif mode == "capabilities":
    import keel.capabilities
elif mode == "backend_hub":
    import keel.backend_hub
elif mode == "webapp":
    import keel.webapp
elif mode == "full":
    import keel.capabilities
    import keel.webapp
    import keel.fleet.service
    import keel.fleet.routes
    import keel.events
    import keel.runner
    import keel.resource_caps
    import keel.resource_limits
    import keel.resilience
    import keel.fleet.scheduler
else:
    raise SystemExit("bad mode")
dt = (time.perf_counter() - t0) * 1000
print(f"IMPORT_MS {dt:.3f}", flush=True)
print(f"MODULES {len(sys.modules)}", flush=True)
print("READY", flush=True)
