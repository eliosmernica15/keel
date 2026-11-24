"""HTTP endpoint latency under normal / increased / burst load.

Uses the real keel.webapp ThreadingHTTPServer with a token, and the real
fleet store pointed at a temp DB. Client opens a fresh HTTP/1.0 connection
per request (the server's default protocol), so numbers include connect.
"""
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = r"C:\Users\Admin\AppData\Local\Temp\opencode\prod-perf"
sys.path.insert(0, HERE)
from benchcommon import stats, use_worktree
use_worktree()

os.environ["KEEL_TOKEN"] = "benchtoken"

import http.client
import keel.webapp as webapp
from keel.fleet import routes as fleet_routes

DB = Path(tempfile.mkdtemp(prefix="perfhttp_")) / "fleet.db"
store = fleet_routes.reset_store_for_tests(DB)
for i in range(20):
    store.create_bot(name=f"bot{i}", engine="echo")
for i in range(50):
    store.create_task(title=f"task{i}")

srv = webapp.make_server(0)
PORT = srv.server_address[1]
th = threading.Thread(target=srv.serve_forever, daemon=True)
th.start()
HOST = "127.0.0.1"


def request(method, path, *, token=True, body=None):
    t = time.perf_counter()
    conn = http.client.HTTPConnection(HOST, PORT, timeout=10)
    headers = {}
    if token:
        headers["X-Keel-Token"] = "benchtoken"
    headers["Origin"] = f"http://{HOST}:{PORT}"
    try:
        if body is None:
            conn.request(method, path, headers=headers)
        else:
            conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        resp.read()
        status = resp.status
        err = None
    except Exception as exc:
        status, err = None, f"{type(exc).__name__}: {exc}"
    finally:
        conn.close()
    return (time.perf_counter() - t) * 1000, status, err


ENDPOINTS = ["/api/health", "/api/providers", "/api/fleet/bots", "/api/fleet/tasks"]
results = {}

# --- warmup + sequential per-endpoint ---
for endpoint in ENDPOINTS:
    for _ in range(10):
        request("GET", endpoint)
    lat = [request("GET", endpoint)[0] for _ in range(200)]
    results["sequential_" + endpoint] = stats(lat)

# --- load scenarios (mixed endpoints) ---
def run_load(name, threads, per_thread):
    lat, statuses, errors = [], [], []
    lock = threading.Lock()

    def worker(idx):
        local = []
        local_st, local_err = [], []
        for i in range(per_thread):
            ep = ENDPOINTS[(idx + i) % len(ENDPOINTS)]
            ms, st, err = request("GET", ep)
            local.append(ms)
            local_st.append(st)
            if err:
                local_err.append(err)
        with lock:
            lat.extend(local); statuses.extend(local_st); errors.extend(local_err)

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
    t0 = time.perf_counter()
    for t in ts: t.start()
    for t in ts: t.join()
    elapsed = time.perf_counter() - t0
    ok = sum(1 for s in statuses if s == 200)
    results[name] = {
        "threads": threads, "requests": len(lat),
        "elapsed_s": round(elapsed, 3),
        "throughput_req_s": round(len(lat) / elapsed, 1),
        "ok": ok, "errors": len(errors),
        "latency_ms": stats(lat),
        "error_samples": errors[:5],
    }
    st = results[name]
    print(f"{name:16s} req={st['requests']:5d} ok={ok:5d} err={len(errors):3d} "
          f"rps={st['throughput_req_s']:8.1f} p50={st['latency_ms']['p50']:.2f} "
          f"p95={st['latency_ms']['p95']:.2f} p99={st['latency_ms']['p99']:.2f} ms")


run_load("normal_8x100", 8, 100)
run_load("increased_32x100", 32, 100)
run_load("burst_100x20", 100, 20)

# unauthorized path
lat = [request("GET", "/api/health", token=False)[0] for _ in range(100)]
statuses = [request("GET", "/api/health", token=False)[1] for _ in range(20)]
results["unauthorized_health"] = {"latency_ms": stats(lat), "statuses": statuses}

srv.shutdown()
srv.server_close()
store.close()

with open(HERE + r"\result_http.json", "w") as f:
    json.dump(results, f, indent=2)
print("wrote result_http.json")
