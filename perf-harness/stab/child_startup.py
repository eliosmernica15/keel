"""Child process: time a target import, signal READY, then exit immediately."""
import sys
import time
sys.path.insert(0, r"C:\Users\Admin\AppData\Local\Temp\opencode\stab-perf")
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
elif mode == "all20":
    import importlib
    for _m in ("d3_backend", "d6_reliability_backend", "d7_workflow_backend", "e3_backend",
               "e5_backend", "e6_x5_x6_backend", "e7_runtime_backend", "small_groups_backend",
               "v_series_backend", "w1_security_backend", "w4_backend", "w7_x1_y5_d1_backend",
               "x2_orchestration_backend", "x3_memory_backend", "x8_backend", "y1_config_backend",
               "y2_backend", "y3_backend", "y4_d4_x7_backend", "z_backend"):
        importlib.import_module("keel." + _m)
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
