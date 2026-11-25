"""Cold first backend-capability call cost (lazy import shifts cost to first use)."""
import json, subprocess, sys, statistics
HERE = r"C:\Users\Admin\AppData\Local\Temp\opencode\stab-perf"
SRC = r"C:\Users\Admin\.local\share\opencode\worktree\stab\perf\keel\src"
CODE = (
"import sys,time,json\n"
"sys.path.insert(0, r'" + SRC + "')\n"
"t0=time.perf_counter()\n"
"import keel.capabilities as caps\n"
"import_ms=(time.perf_counter()-t0)*1000\n"
"out={}\n"
"for name,args in [('backend.modules',()),('backend.describe',({'module':'e5_backend'},)),\n"
"                  ('backend.invoke',({'module':'e5_backend','function':'validate_app_id',\n"
"                                      'params':{'app_id':'com.nice.app'}},))]:\n"
"    t=time.perf_counter()\n"
"    caps.invoke(name,*args)\n"
"    out[name]=round((time.perf_counter()-t)*1000,3)\n"
"print(json.dumps({'import_ms':round(import_ms,3),'first_call_ms':out}))\n")

runs = []
for i in range(7):
    p = subprocess.run([sys.executable, "-P", "-c", CODE], capture_output=True,
                       text=True, cwd=HERE, timeout=120)
    if p.returncode != 0:
        raise SystemExit(p.stderr[-1000:])
    runs.append(json.loads(p.stdout.strip().splitlines()[-1]))
res = {"repeats": len(runs), "runs": runs}
for k in ("import_ms", "backend.modules", "backend.describe", "backend.invoke"):
    vals = ([r["import_ms"] for r in runs] if k == "import_ms"
            else [r["first_call_ms"][k] for r in runs])
    res[k] = {"p50": round(statistics.median(vals), 3),
              "min": round(min(vals), 3), "max": round(max(vals), 3)}
print(json.dumps({k: v for k, v in res.items() if k != "runs"}, indent=2))
with open(HERE + r"\result_first_call.json", "w") as f:
    json.dump(res, f, indent=2)
print("wrote result_first_call.json")
