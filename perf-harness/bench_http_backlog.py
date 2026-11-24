"""A/B: default ThreadingHTTPServer backlog (5) vs raised backlog (128)."""
import os, sys, threading, time, tempfile, json
from pathlib import Path
HERE = r"C:\Users\Admin\AppData\Local\Temp\opencode\prod-perf"
sys.path.insert(0, HERE)
from benchcommon import stats, use_worktree
use_worktree()
os.environ["KEEL_TOKEN"] = "benchtoken"
import http.client
from http.server import ThreadingHTTPServer
import keel.webapp as webapp
from keel.fleet import routes as fleet_routes

DB = Path(tempfile.mkdtemp(prefix="perfbacklog_")) / "fleet.db"
store = fleet_routes.reset_store_for_tests(DB)
store.create_bot(name="b", engine="echo")

srv_default = webapp.make_server(0)
handler = srv_default.RequestHandlerClass

class BigBacklog(ThreadingHTTPServer):
    request_queue_size = 128
    daemon_threads = True

srv_big = BigBacklog(("127.0.0.1", 0), handler)
for s in (srv_default, srv_big):
    threading.Thread(target=s.serve_forever, daemon=True).start()

def burst(port, threads=100, per=20):
    lat, ok, refused = [], [0], [0]
    lock = threading.Lock()
    def worker(i):
        l, o, r = [], 0, 0
        for j in range(per):
            t = time.perf_counter()
            try:
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                c.request("GET", "/api/health", headers={"X-Keel-Token": "benchtoken"})
                resp = c.getresponse(); resp.read(); c.close()
                l.append((time.perf_counter()-t)*1000)
                if resp.status == 200: o += 1
            except Exception:
                r += 1
        with lock: lat.extend(l); ok[0]+=o; refused[0]+=r
    ts = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
    t0=time.perf_counter()
    for t in ts: t.start()
    for t in ts: t.join()
    el=time.perf_counter()-t0
    return {"port":port,"threads":threads,"requests":threads*per,"ok":ok[0],
            "failed":refused[0],"elapsed_s":round(el,3),
            "rps":round(threads*per/el,1),"latency_ms":stats(lat)}

out = {}
out["default_backlog_5"] = burst(srv_default.server_address[1])
out["big_backlog_128"] = burst(srv_big.server_address[1])
for k,v in out.items():
    print(f"{k:22s} queue={getattr(srv_default if 'default' in k else srv_big,'request_queue_size')} "
          f"ok={v['ok']:5d} failed={v['failed']:4d} rps={v['rps']:8.1f} "
          f"p50={v['latency_ms']['p50']:.2f} p99={v['latency_ms']['p99']:.2f}")
for s in (srv_default, srv_big): s.shutdown(); s.server_close()
store.close()
with open(HERE+r"\result_backlog.json","w") as f: json.dump(out,f,indent=2)
print("wrote result_backlog.json")
