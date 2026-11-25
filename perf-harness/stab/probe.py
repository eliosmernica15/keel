import sys, time, os
SRC = r"C:\Users\Admin\.local\share\opencode\worktree\stab\perf\keel\src"
sys.path.insert(0, SRC)
t0 = time.perf_counter()
import keel
t1 = time.perf_counter()
print("keel", keel.__file__, "import_ms", round((t1-t0)*1000, 3))
import keel.capabilities as caps
t2 = time.perf_counter()
print("capabilities import_ms", round((t2-t1)*1000, 3))
from keel import backend_hub as hub
t3 = time.perf_counter()
print("backend_hub import_ms", round((t3-t2)*1000, 3))
print("modules", len(hub.modules()), "features", len(hub.feature_ids()), "schemas", len(hub.function_schemas()))
print("capabilities count", len(caps.list_capabilities()))
print("sys.modules after", len(sys.modules))
