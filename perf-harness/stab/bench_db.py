"""SQLite write latency, contention, event throughput, memory & CPU."""
import json, sys, tempfile, threading, time, tracemalloc
from pathlib import Path
HERE = r"C:\Users\Admin\AppData\Local\Temp\opencode\stab-perf"
sys.path.insert(0, HERE)
from benchcommon import stats, rss_bytes, use_worktree
use_worktree()
from keel.fleet.service import FleetStore

TMP = Path(tempfile.mkdtemp(prefix="perfdb_"))
results = {}

def fresh(name):
    return FleetStore(TMP / f"{name}.db")

# ---- single-thread append_row ----
s = fresh("single")
bot = s.create_bot(name="solo", engine="echo")
lat = []
for i in range(2000):
    t = time.perf_counter()
    s.append_row(bot["id"], "message", {"content": "x" * 200, "i": i})
    lat.append((time.perf_counter()-t)*1000)
results["append_row_single"] = stats(lat)
results["append_row_single"]["throughput_writes_s"] = round(2000/(sum(lat)/1000), 1)
print("append_row single:", results["append_row_single"]["p50"], "p50 /",
      results["append_row_single"]["p95"], "p95 /", results["append_row_single"]["p99"], "p99 ms")

# ---- event throughput: fan-out to subscribers ----
def throughput_with_subs(nsub, n=3000):
    st = fresh(f"sub{nsub}_{int(time.perf_counter()*1000)}")
    b = st.create_bot(name="b", engine="echo")
    qs = [st.subscribe() for _ in range(nsub)]
    t0 = time.perf_counter()
    for i in range(n):
        st.append_row(b["id"], "message", {"content": "y", "i": i})
    el = time.perf_counter()-t0
    for q in qs: st.unsubscribe(q)
    return {"subscribers": nsub, "events": n, "elapsed_s": round(el,3),
            "events_s": round(n/el,1), "ms_per_event": round(el/n*1000,4)}

results["event_append_throughput"] = [throughput_with_subs(n) for n in (0,4,16)]
for r in results["event_append_throughput"]:
    print(f"append_row + {r['subscribers']:2d} subs: {r['events_s']:9.1f} ev/s")

# ephemeral publish throughput (no DB)
st = fresh("pub")
b = st.create_bot(name="b", engine="echo")
qs = [st.subscribe() for _ in range(4)]
t0 = time.perf_counter()
for i in range(20000):
    st.publish({"type":"token","seq":i,"text":"tok"})
el = time.perf_counter()-t0
results["publish_ephemeral"] = {"events":20000,"subscribers":4,
    "elapsed_s":round(el,3),"events_s":round(20000/el,1)}
print("publish ephemeral:", results["publish_ephemeral"]["events_s"], "ev/s")

# slow subscriber drop-oldest
st2 = fresh("slowsub")
b2 = st2.create_bot(name="b", engine="echo")
qslow = st2.subscribe()
for i in range(1000):
    st2.append_row(b2["id"], "message", {"content":"z"})
results["slow_subscriber_drop_oldest"] = {
    "published":1000, "queue_maxsize":qslow.maxsize, "queue_len":qslow.qsize()}
print("slow subscriber queue:", qslow.qsize(), "/", qslow.maxsize)

# ---- shared-store concurrency ----
def shared_concurrency(threads, per, name):
    st = fresh(name)
    b = st.create_bot(name="b", engine="echo")
    lat, errs = [], []
    lock = threading.Lock()
    def w(tid):
        l, e = [], []
        for i in range(per):
            t = time.perf_counter()
            try: st.append_row(b["id"], "message", {"content":"c","t":tid,"i":i})
            except Exception as exc: e.append(f"{type(exc).__name__}: {exc}")
            l.append((time.perf_counter()-t)*1000)
        with lock: lat.extend(l); errs.extend(e)
    ts=[threading.Thread(target=w,args=(i,)) for i in range(threads)]
    t0=time.perf_counter()
    for t in ts:t.start()
    for t in ts:t.join()
    el=time.perf_counter()-t0
    return {"threads":threads,"writes_each":per,"total":len(lat),
            "elapsed_s":round(el,3),"writes_s":round(len(lat)/el,1),
            "errors":len(errs),"error_samples":errs[:3],
            "latency_ms":stats(lat)}

for n in (8,32):
    r = shared_concurrency(n, 500 if n==8 else 200, f"shared{n}")
    results[f"append_row_shared_store_{n}threads"] = r
    print(f"shared store {n} threads: writes/s={r['writes_s']} err={r['errors']} "
          f"p50={r['latency_ms']['p50']:.3f} p99={r['latency_ms']['p99']:.3f}")

# ---- multi-instance DB contention (separate connections/locks, same file) ----
def multi_instance(threads, per, name):
    db = TMP / f"{name}.db"
    seed = FleetStore(db); seed.create_bot(name="b", engine="echo"); seed.close()
    stores = [FleetStore(db) for _ in range(threads)]
    lat, errs = [], []
    lock = threading.Lock()
    def w(i):
        st = stores[i]; l, e = [], []
        for j in range(per):
            t=time.perf_counter()
            try: st.append_row("b","message",{"content":"m","i":j,"t":i})
            except Exception as exc: e.append(f"{type(exc).__name__}: {exc}")
            l.append((time.perf_counter()-t)*1000)
        with lock: lat.extend(l); errs.extend(e)
    ts=[threading.Thread(target=w,args=(i,)) for i in range(threads)]
    t0=time.perf_counter()
    for t in ts:t.start()
    for t in ts:t.join()
    el=time.perf_counter()-t0
    for st in stores: st.close()
    return {"instances":threads,"writes_each":per,"total":len(lat),
            "elapsed_s":round(el,3),"writes_s":round(len(lat)/el,1),
            "errors":len(errs),"error_samples":errs[:5],
            "latency_ms":stats(lat)}

for n in (8,32):
    r = multi_instance(n, 200, f"multi{n}")
    results[f"multi_instance_contention_{n}"] = r
    print(f"multi-instance {n}: writes/s={r['writes_s']} err={r['errors']} "
          f"p50={r['latency_ms']['p50']:.3f} p99={r['latency_ms']['p99']:.3f}")

# ---- insert_usage latency ----
st = fresh("usage")
b = st.create_bot(name="b", engine="echo")
lat=[]
for i in range(1000):
    t=time.perf_counter()
    st.insert_usage(bot_id=b["id"], provider="p", model="m", input_tokens=i,
                    output_tokens=2*i)
    lat.append((time.perf_counter()-t)*1000)
results["insert_usage_single"] = stats(lat)
print("insert_usage p50/p99:", results["insert_usage_single"]["p50"],
      results["insert_usage_single"]["p99"])

# ---- memory & CPU over a sustained mixed workload ----
st = fresh("memcpu")
b = st.create_bot(name="b", engine="echo")
qs = [st.subscribe() for _ in range(4)]
rss0 = rss_bytes(); cpu0 = time.process_time(); wall0 = time.perf_counter()
tracemalloc.start()
for i in range(20000):
    st.append_row(b["id"], "message", {"content":"z"*100,"i":i})
    if i % 10 == 0:
        st.publish({"type":"token","text":"tok","seq":i})
cur, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()
wall = time.perf_counter()-wall0; cpu = time.process_time()-cpu0
rss1 = rss_bytes()
results["memory_cpu_workload"] = {
    "operations":22000,"elapsed_s":round(wall,3),
    "cpu_process_s":round(cpu,3),"cpu_ratio":round(cpu/wall,3),
    "rss_before_bytes":rss0,"rss_after_bytes":rss1,
    "rss_delta_bytes":(rss1-rss0) if rss0 and rss1 else None,
    "tracemalloc_current_bytes":cur,"tracemalloc_peak_bytes":peak}
print("memory/CPU:", results["memory_cpu_workload"])

with open(HERE+r"\result_db.json","w") as f: json.dump(results,f,indent=2)
print("wrote result_db.json")
