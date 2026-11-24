import sys, time, importlib
SRC = r"C:\Users\Admin\.local\share\opencode\worktree\production\perf\keel\src"
sys.path.insert(0, SRC)
mods = ["d3_backend","d6_reliability_backend","d7_workflow_backend","e3_backend",
"e5_backend","e6_x5_x6_backend","e7_runtime_backend","small_groups_backend",
"v_series_backend","w1_security_backend","w4_backend","w7_x1_y5_d1_backend",
"x2_orchestration_backend","x3_memory_backend","x8_backend","y1_config_backend",
"y2_backend","y3_backend","y4_d4_x7_backend","z_backend"]
for m in mods:
    t = time.perf_counter()
    mod = importlib.import_module("keel." + m)
    dt = (time.perf_counter()-t)*1000
    print(f"{m:28s} {dt:9.2f} ms")
