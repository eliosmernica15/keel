import sys, json
sys.path.insert(0, r"C:\Users\Admin\AppData\Local\Temp\opencode\prod-perf")
from benchcommon import use_worktree
use_worktree()
from keel import backend_hub as h
for m,f in [("e5_backend","validate_app_id"),("y3_backend","build_route"),("w4_backend","normalize_tool_name")]:
    print(m, f, json.dumps(h.function_schema(m,f)))
