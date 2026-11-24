"""Parent: cold-process startup + shutdown timing for import targets."""
import json
import statistics
import subprocess
import sys
import time
sys.path.insert(0, r"C:\Users\Admin\AppData\Local\Temp\opencode\prod-perf")
from benchcommon import stats, use_worktree

use_worktree()
PY = sys.executable
HERE = r"C:\Users\Admin\AppData\Local\Temp\opencode\prod-perf"
CHILD = HERE + r"\child_startup.py"
REPEATS = 7
MODES = ["none", "keel", "backend_hub", "capabilities", "webapp", "full"]


def one(mode):
    t0 = time.perf_counter()
    p = subprocess.Popen([PY, "-P", CHILD, mode], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, cwd=HERE)
    import_ms = None
    modules = None
    t_ready = None
    for line in p.stdout:
        line = line.strip()
        if line.startswith("IMPORT_MS "):
            import_ms = float(line.split()[1])
        elif line.startswith("MODULES "):
            modules = int(line.split()[1])
        elif line == "READY":
            t_ready = time.perf_counter()
    _, err = p.communicate()
    t_end = time.perf_counter()
    return {
        "import_ms_child": import_ms,
        "modules_loaded": modules,
        "shutdown_ms": round((t_end - t_ready) * 1000, 3) if t_ready else None,
        "total_process_ms": round((t_end - t0) * 1000, 3),
        "returncode": p.returncode,
        "stderr": err.strip()[:200],
    }


results = {}
for mode in MODES:
    runs = [one(mode) for _ in range(REPEATS)]
    imports = [r["import_ms_child"] for r in runs if r["import_ms_child"] is not None]
    shutdowns = [r["shutdown_ms"] for r in runs if r["shutdown_ms"] is not None]
    totals = [r["total_process_ms"] for r in runs]
    results[mode] = {
        "repeats": REPEATS,
        "import_ms": stats(imports),
        "shutdown_ms": stats(shutdowns),
        "total_process_ms": stats(totals),
        "modules_loaded": runs[0]["modules_loaded"],
        "all_returncodes_ok": all(r["returncode"] == 0 for r in runs),
        "raw": runs,
    }
    im = results[mode]["import_ms"]
    sd = results[mode]["shutdown_ms"]
    print(f"{mode:14s} import median={im['p50']:.1f}ms  shutdown median={sd['p50']:.3f}ms  "
          f"total median={results[mode]['total_process_ms']['p50']:.1f}ms  modules={runs[0]['modules_loaded']}")

with open(HERE + r"\result_startup.json", "w") as f:
    json.dump(results, f, indent=2)
print("wrote result_startup.json")
