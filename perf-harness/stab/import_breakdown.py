import sys, time, importlib
SRC = r"C:\Users\Admin\.local\share\opencode\worktree\stab\perf\keel\src"
sys.path.insert(0, SRC)

# Fresh process: time importing ONLY the 20 backend modules (no hub).
mods = ["d3_backend","d6_reliability_backend","d7_workflow_backend","e3_backend",
"e5_backend","e6_x5_x6_backend","e7_runtime_backend","small_groups_backend",
"v_series_backend","w1_security_backend","w4_backend","w7_x1_y5_d1_backend",
"x2_orchestration_backend","x3_memory_backend","x8_backend","y1_config_backend",
"y2_backend","y3_backend","y4_d4_x7_backend","z_backend"]

t = time.perf_counter()
for m in mods:
    importlib.import_module("keel." + m)
print("import20_ms", round((time.perf_counter()-t)*1000, 2))

# Fresh import of hub itself
t = time.perf_counter()
import keel.backend_hub as hub
print("hub_import_after20_ms", round((time.perf_counter()-t)*1000, 2))

# Recompute schemas (the body's dominant work) with modules cached
t = time.perf_counter()
hub._FUNCTION_SCHEMAS = None
schemas = hub.function_schemas()
print("schema_recompute_ms", round((time.perf_counter()-t)*1000, 2), "n", len(schemas))

# assert_dispatch_targets again (imports cached)
t = time.perf_counter()
hub.assert_dispatch_targets()
print("assert_cached_ms", round((time.perf_counter()-t)*1000, 2))

# sync_capability_schemas with cached schemas
t = time.perf_counter()
hub.sync_capability_schemas()
print("sync_cached_ms", round((time.perf_counter()-t)*1000, 2))
