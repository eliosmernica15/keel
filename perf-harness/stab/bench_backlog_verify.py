"""Verify current make_server() backlog: control(queue=5) vs make_server vs explicit 128."""
import json, os, sys, threading, time, tempfile, http.client
from http.server import ThreadingHTTPServer
from pathlib import Path
HERE = r"C:\Users\Admin\AppData\Local\Temp\opencode\stab-perf"
sys.path.insert(0, HERE)
from benchcommon import stats, use_worktree
use_worktree()
os.environ["KEEL_TOKEN"] = "benchtoken"
import keel.webapp as webapp
from keel.fleet import routes as fleet_routes

DB = Path(tempfile.mkdtemp(prefix="stabbacklog_")) / "fleet.db"
store = fleet_routes.reset_store_for_tests(DB)
store.create_bot(name="b", engine="echo")

srv_current = webapp.make_server(0)
handler = srv_current.RequestHandlerClass

class SmallBacklog(ThreadingHTTPServer):
    request_queue_size = 5
    daemon_threads = True

class BigBacklog(ThreadingHTTPServer):
    request_queue_size = 128
    daemon_threads = True

servers = {
    "control_queue_5": SmallBacklog(("127.0.0.1", 0), handler),
    "current_make_server": srv_current,
    "explicit_queue_128": BigBacklog(("127.0.0.1", 0), handler),
}
for s in servers.values():
    threading.Thread(target=s.serve_forever, daemon=True).start()

def burst(port, threads=100, per=20):
    lat, ok, refused = [], [0], [0]
    lock = threading.Lock()
    def worker():
        l, o, r = [], 0, 0
        for _ in range(per):
            t = time.perf_counter()
            c = None
            try:
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                c.request("GET", "/api/health", headers={
                    "X-Keel-Token": "benchtoken",
                    "Origin": f"http://127.0.0.1:{port}"})
                resp = c.getresponse(); resp.read()
                if resp.status == 200: o += 1
                l.append((time.perf_counter() - t) * 1000)
            except Exception:
                r += 1
            finally:
                if c is not None:
                    try: c.close()
                    except Exception: pass
        with lock:
            lat.extend(l); ok[0] += o; refused[0] += r
    ts = [threading.Thread(target=worker) for _ in range(threads)]
    t0 = time.perf_counter()
    for t in ts: t.start()
    for t in ts: t.join()
    el = time.perf_counter() - t0
    return {"threads": threads, "requests": threads * per, "ok": ok[0],
            "failed": refused[0], "elapsed_s": round(el, 3),
            "rps": round(threads * per / el, 1), "latency_ms": stats(lat)}

out = {"server_class": type(srv_current).__name__,
       "current_request_queue_size": srv_current.request_queue_size,
       "current_daemon_threads": srv_current.daemon_threads}
for name, s in servers.items():
    r = burst(s.server_address[1])
    r["request_queue_size"] = s.request_queue_size
    out[name] = r
    print(f"{name:22s} queue={s.request_queue_size:3d} ok={r['ok']:5d} "
          f"failed={r['failed']:4d} rps={r['rps']:8.1f} "
          f"p50={r['latency_ms']['p50']:.2f} p99={r['latency_ms']['p99']:.2f}")
for s in servers.values():
    s.shutdown(); s.server_close()
store.close()
with open(HERE + r"\result_backlog_verify.json", "w") as f:
    json.dump(out, f, indent=2)
print("wrote result_backlog_verify.json")
