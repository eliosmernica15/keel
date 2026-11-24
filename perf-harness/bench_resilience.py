"""Resource limits, concurrent sessions/tasks, failure recovery, slow provider,
long-running tasks, worker failure, and DB write blocking."""
import json, os, sqlite3, sys, tempfile, threading, time
from pathlib import Path
HERE = r"C:\Users\Admin\AppData\Local\Temp\opencode\prod-perf"
sys.path.insert(0, HERE)
from benchcommon import stats, use_worktree
use_worktree()
from keel.fleet.service import FleetStore
from keel.resource_caps import ResourceMeter
from keel.resource_limits import ResourceManager, ResourceLimitError
from keel.fleet import scheduler, turn_core

TMP = Path(tempfile.mkdtemp(prefix="perfres_"))
results = {}

# ---------- resource cap concurrency (atomic check-then-increment) ----------
def cap_race(threads=8, attempts=200, cap=4):
    m = ResourceMeter()
    m.caps["browser"] = cap
    m._used["browser"] = 0
    successes, errs = [0], []
    barrier = threading.Barrier(threads)
    def w(i):
        local = 0
        barrier.wait()
        for _ in range(attempts):
            if m.acquire("browser"):
                local += 1
                # simulate held resource briefly
        successes[0] += local
    ts = [threading.Thread(target=w, args=(i,)) for i in range(threads)]
    t0 = time.perf_counter()
    for t in ts: t.start()
    for t in ts: t.join()
    el = time.perf_counter()-t0
    used = m.meters()[0].used
    return {"threads":threads,"attempts_each":attempts,"cap":cap,
            "granted":successes[0],"final_used":used,
            "cap_respected":successes[0] <= cap and used == successes[0],
            "elapsed_s":round(el,4)}

results["resource_cap_concurrency"] = cap_race()
print("resource cap race:", results["resource_cap_concurrency"])

# acquire latency under no contention
m = ResourceMeter()
lat = []
for _ in range(20000):
    t=time.perf_counter(); m.acquire("browser"); m.release("browser")
    lat.append((time.perf_counter()-t)*1000)
results["resource_acquire_latency_ms"] = stats(lat)
print("acquire+release p50:", results["resource_acquire_latency_ms"]["p50"])

# ---------- ResourceManager limits under concurrency ----------
def rm_limits(threads=16):
    rm = ResourceManager(max_tabs=8, max_workspace_bytes=1024*1024)
    errs, ok_tabs = [], [0]
    barrier = threading.Barrier(threads)
    def w(i):
        barrier.wait()
        for j in range(20):
            try:
                rm.open_tab(f"t{i}_{j}")
                ok_tabs[0]+=1
            except ResourceLimitError:
                pass
        try: rm.attach_workspace(200_000)
        except ResourceLimitError as e: errs.append(str(e))
    ts=[threading.Thread(target=w,args=(i,)) for i in range(threads)]
    for t in ts:t.start()
    for t in ts:t.join()
    st = rm.status()
    return {"threads":threads,"tabs_opened":ok_tabs[0],"status":st,
            "tab_limit_respected":st["tabs"] <= st["tab_limit"],
            "workspace_limit_respected":st["workspace_bytes"] <= st["workspace_limit"],
            "workspace_denials":len(errs)}

results["resource_manager_limits"] = rm_limits()
print("resource manager:", results["resource_manager_limits"])

# ---------- concurrent session/task creation on one store ----------
st = FleetStore(TMP/"concurrent.db")
def create_many(threads=16, each=20):
    errs=[]; bots=[0]; tasks=[0]; lock=threading.Lock(); barrier=threading.Barrier(threads)
    def w(i):
        barrier.wait()
        lb, lt, le = 0,0,[]
        for j in range(each):
            try:
                st.create_bot(name=f"bot{i}_{j}", engine="echo"); lb+=1
                st.create_task(title=f"task{i}_{j}"); lt+=1
            except Exception as exc: le.append(f"{type(exc).__name__}: {exc}")
        with lock: bots[0]+=lb; tasks[0]+=lt; errs.extend(le)
    ts=[threading.Thread(target=w,args=(i,)) for i in range(threads)]
    t0=time.perf_counter()
    for t in ts:t.start()
    for t in ts:t.join()
    el=time.perf_counter()-t0
    return {"threads":threads,"bots_created":bots[0],"tasks_created":tasks[0],
            "expected_bots":threads*each,"expected_tasks":threads*each,
            "errors":len(errs),"error_samples":errs[:5],"elapsed_s":round(el,3),
            "ops_s":round((bots[0]+tasks[0])/el,1)}

results["concurrent_sessions_tasks"] = create_many()
print("concurrent sessions/tasks:", results["concurrent_sessions_tasks"])

# bot-name collision race (same slug from many threads)
def name_collision(threads=16):
    st2 = FleetStore(TMP/"collision.db")
    errs=[]; ok=[0]; barrier=threading.Barrier(threads)
    def w(i):
        barrier.wait()
        try: st2.create_bot(name="same", engine="echo"); ok[0]+=1
        except Exception as exc: errs.append(f"{type(exc).__name__}: {exc}")
    ts=[threading.Thread(target=w,args=(i,)) for i in range(threads)]
    for t in ts:t.start()
    for t in ts:t.join()
    ids = [b["id"] for b in st2.list_bots()]
    st2.close()
    return {"threads":threads,"succeeded":ok[0],"errors":len(errs),
            "error_samples":errs[:5],"distinct_bot_ids":len(set(ids)),
            "ids":sorted(ids)}

results["bot_name_collision_race"] = name_collision()
print("bot-name collision:", results["bot_name_collision_race"])

# chat_for_project race
def chat_project_race(threads=8):
    st3 = FleetStore(TMP/"chatproj.db")
    p = st3.create_project(path=str(TMP))
    barrier=threading.Barrier(threads); errs=[]; ok=[0]
    def w(i):
        barrier.wait()
        try: st3.chat_for_project(p["id"]); ok[0]+=1
        except Exception as exc: errs.append(f"{type(exc).__name__}: {exc}")
    ts=[threading.Thread(target=w,args=(i,)) for i in range(threads)]
    for t in ts:t.start()
    for t in ts:t.join()
    bots=[b for b in st3.list_bots(kind=None) if b.get("project_id")==p["id"]]
    st3.close()
    return {"threads":threads,"succeeded":ok[0],"errors":len(errs),
            "error_samples":errs[:5],"bots_for_project":len(bots),
            "exactly_one_bot":len(bots)==1}

results["chat_for_project_race"] = chat_project_race()
print("chat_for_project race:", results["chat_for_project_race"])

# ---------- recovery after induced failure (simulated restart) ----------
def setup_recovery_state(n=1):
    db = TMP/f"recovery_{n}_{int(time.perf_counter()*1000)}.db"
    s = FleetStore(db)
    b = s.create_bot(name="b", engine="echo")
    for i in range(n):
        s.create_approval(approval_id=f"ap{i}", bot_id=b["id"], tool_name="run_shell",
                          fingerprint="f"*16, args_summary="a", expires_at="2099-01-01T00:00:00.000Z")
        s.append_row(b["id"], "ask", {"status":"pending","question":"q"})
        r = s.create_routine(name=f"r{i}", bot_id=b["id"], prompt="p", cron_expr="0 0 * * *")
        task = s.create_task(title=f"t{i}")
        s.create_routine_run(r["id"], scheduled_at=s._utc_iso(s._now_dt() if hasattr(s,'_now_dt') else __import__('datetime').datetime.now(__import__('datetime').timezone.utc)), task_id=task["id"])
        with s._lock:
            s._conn.execute("UPDATE fleet_routines SET running=1 WHERE id=?", (r["id"],))
            s._conn.commit()
    s.close()
    return db

def recover(db):
    t0=time.perf_counter()
    s=FleetStore(db)
    ms=(time.perf_counter()-t0)*1000
    return round(ms,3), s

for n in (1, 100):
    db = setup_recovery_state(n)
    ms, s = recover(db)
    approvals = s._conn.execute("SELECT status, decision FROM fleet_approvals").fetchall()
    asks = s._conn.execute("SELECT body FROM rows WHERE kind='ask'").fetchall()
    runs = s._conn.execute("SELECT status, error FROM fleet_routine_runs").fetchall()
    routines = s._conn.execute("SELECT running FROM fleet_routines").fetchall()
    tasks = s._conn.execute("SELECT status FROM fleet_tasks").fetchall()
    results[f"recovery_after_restart_{n}"] = {
        "pending_items":n,"recovery_ms":ms,
        "approvals_expired":sum(1 for a in approvals if a["status"]=="expired"),
        "asks_interrupted":sum(1 for a in asks if '"interrupted"' in str(a["body"])),
        "asks_still_pending":sum(1 for a in asks if '"pending"' in str(a["body"])),
        "runs_failed":sum(1 for r in runs if r["status"]=="failed"),
        "runs_with_restart_error":sum(1 for r in runs if "restart" in (r["error"] or "")),
        "routines_released":sum(1 for r in routines if r["running"]==0),
        "tasks_failed":sum(1 for t in tasks if t["status"]=="failed")}
    s.close()
    print(f"recovery n={n}: {ms} ms", results[f"recovery_after_restart_{n}"])

# ---------- slow provider / long-running task / worker failure ----------
def routine_case(name, fake, timeout):
    os.environ["KEEL_FLEET_ROUTINE_TIMEOUT_S"] = str(timeout)
    orig = turn_core.execute_turn
    turn_core.execute_turn = fake
    try:
        db = TMP/f"routine_{name}.db"
        s = FleetStore(db)
        b = s.create_bot(name="b", engine="echo")
        r = s.create_routine(name="r", bot_id=b["id"], prompt="p", cron_expr="0 0 * * *")
        routine = s.get_routine(r["id"])
        t0=time.perf_counter()
        out = scheduler.execute_routine(s, routine)
        ms=(time.perf_counter()-t0)*1000
        runs = s.list_routine_runs(r["id"])
        task = s.get_task(out.get("task_id")) if out.get("task_id") else None
        rec = {"elapsed_ms":round(ms,1),"outcome":out,
               "run_status":runs[0]["status"] if runs else None,
               "task_status":task["status"] if task else None,
               "routine_running":s.get_routine(r["id"])["running"]}
        s.close()
        return rec
    finally:
        turn_core.execute_turn = orig
        os.environ.pop("KEEL_FLEET_ROUTINE_TIMEOUT_S", None)

def slow_fake(*args, **kwargs):
    time.sleep(2.0)
    return {"ok":True,"assistant_text":"slow done"}

def fail_fake(*args, **kwargs):
    raise RuntimeError("provider exploded")

results["slow_provider_timeout"] = routine_case("slow", slow_fake, 0.4)
print("slow provider:", results["slow_provider_timeout"]["elapsed_ms"], "ms",
      results["slow_provider_timeout"]["outcome"].get("error"))
results["worker_failure"] = routine_case("fail", fail_fake, 2.0)
print("worker failure:", results["worker_failure"]["elapsed_ms"], "ms",
      results["worker_failure"]["outcome"].get("error"))

# ---------- DB write blocking under exclusive lock ----------
def write_blocking():
    db = TMP/"blocking.db"
    s = FleetStore(db); s.create_bot(name="b", engine="echo")
    hold_ms = 0.3
    box = {}
    def hold():
        holder = sqlite3.connect(str(db), check_same_thread=False)
        holder.execute("PRAGMA journal_mode=WAL")
        holder.execute("BEGIN EXCLUSIVE")
        box["holder"] = holder
        time.sleep(hold_ms)
        holder.commit()
    th = threading.Thread(target=hold); th.start()
    while "holder" not in box:
        time.sleep(0.001)
    time.sleep(0.05)
    t0=time.perf_counter()
    s.append_row("b","message",{"content":"blocked"})
    ms=(time.perf_counter()-t0)*1000
    th.join(); box["holder"].close(); s.close()
    return {"hold_s":hold_ms,"write_latency_ms":round(ms,1),
            "blocked_ms_approx":round(ms-hold_ms*0,1)}

results["db_write_blocking_exclusive"] = write_blocking()
print("DB write blocking:", results["db_write_blocking_exclusive"])

with open(HERE+r"\result_resilience.json","w") as f: json.dump(results,f,indent=2)
print("wrote result_resilience.json")
