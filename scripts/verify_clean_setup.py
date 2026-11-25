"""PR-16 clean-setup verification harness.

Run with the Python interpreter of the disposable clean venv:

    <venv>/Scripts/python.exe scripts/verify_clean_setup.py

Required environment:
    KEEL_SETUP_PROJECT  path to the checkout's `keel/` directory
    KEEL_STATE_DIR      a fresh, empty temporary state directory

The harness never modifies the user's environment. All state it creates lives
under KEEL_STATE_DIR; subprocesses run from a neutral cwd with PYTHONPATH
cleared and PYTHONNOUSERSITE=1 so imports can only resolve through the venv.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT = Path(os.environ["KEEL_SETUP_PROJECT"])
STATE = Path(os.environ["KEEL_STATE_DIR"])
NEUTRAL_CWD = STATE / "neutral-cwd"
NEUTRAL_CWD.mkdir(parents=True, exist_ok=True)

TOKEN = "prod16-clean-setup-token"
BASE_ENV = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
BASE_ENV.update({
    "PYTHONNOUSERSITE": "1",
    "KEEL_STATE_DIR": str(STATE),
    "KEEL_TOKEN": TOKEN,
})

RESULTS: list[dict] = []


def run(cmd: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=str(NEUTRAL_CWD), env=BASE_ENV,
        capture_output=True, text=True, timeout=timeout,
    )


def record(name: str, ok: bool, detail: str) -> None:
    RESULTS.append({"check": name, "ok": bool(ok), "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'} | {name} | {detail}", flush=True)


def check_import() -> None:
    code = "import keel, keel.cli.main; print(keel.__version__); print(keel.__file__)"
    p = run([sys.executable, "-c", code])
    lines = [x.strip() for x in p.stdout.splitlines() if x.strip()]
    ok = (p.returncode == 0 and len(lines) >= 2
          and str(PROJECT / "src" / "keel") in lines[-1])
    record("clean_import", ok,
           f"rc={p.returncode} version={lines[0] if lines else '?'} "
           f"module={lines[-1] if lines else '?'} stderr={p.stderr.strip()!r}")


def check_help() -> None:
    p = run([sys.executable, "-m", "keel", "--help"])
    ok = p.returncode == 0 and "usage: keel" in p.stdout and "capability" in p.stdout
    record("python_m_keel_help", ok,
           f"rc={p.returncode} stdout_lines={len(p.stdout.splitlines())} "
           f"stderr={p.stderr.strip()!r}")


def check_capabilities() -> None:
    p = run([sys.executable, "-m", "keel", "capability", "list"])
    ids = [line.split()[0] for line in p.stdout.splitlines() if line.strip()]
    expected = {"backend.modules", "backend.describe", "backend.invoke", "backend.verify"}
    missing = sorted(expected - set(ids))
    backend_ids = sorted(x for x in ids if x.startswith("backend."))
    ok = p.returncode == 0 and not missing
    record("capability_list_backend", ok,
           f"rc={p.returncode} total_capabilities={len(ids)} "
           f"backend_capabilities={backend_ids} missing={missing} "
           f"stderr={p.stderr.strip()!r}")


def check_db() -> None:
    from keel.fleet import db as fleet_db
    from keel.fleet.service import FleetStore

    db_path = STATE / "fleet.db"
    conn = fleet_db.connect(db_path)
    tables = sorted(
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    )
    versions = [r[0] for r in conn.execute(
        "SELECT version FROM schema_version ORDER BY version").fetchall()]
    conn.close()

    expected = {"bots", "rows", "fleet_tasks", "fleet_audit", "groups", "schema_version"}
    missing = sorted(expected - set(tables))
    store_path = STATE / "fleet-service.db"
    store = FleetStore(store_path)
    store_tables = sorted(
        r[0] for r in store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    )
    store.close()
    ok = (not missing and db_path.is_file() and store_path.is_file()
          and len(store_tables) >= len(expected))
    record("db_init_fresh_state_dir", ok,
           f"db={db_path} exists={db_path.is_file()} tables={len(tables)} "
           f"schema_versions={versions} missing={missing} "
           f"store_db={store_path} store_tables={len(store_tables)}")


def check_health_and_shutdown() -> None:
    # KEEL_TOKEN must be set before webapp is imported (module-level _TOKEN).
    os.environ["KEEL_TOKEN"] = TOKEN
    import keel.webapp as webapp

    srv = webapp.make_server(0)
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}/api/health"

    body = ""
    status = None
    unauth_status = None
    try:
        authorized = urllib.request.Request(url, headers={"X-Keel-Token": TOKEN})
        for _ in range(60):
            try:
                with urllib.request.urlopen(authorized, timeout=2) as r:
                    status = r.status
                    body = r.read().decode("utf-8")
                break
            except urllib.error.HTTPError as exc:
                status = exc.code
                body = exc.read().decode("utf-8", "replace")
                break
            except OSError:
                time.sleep(0.1)

        req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=2) as r:
                unauth_status = r.status
        except urllib.error.HTTPError as exc:
            unauth_status = exc.code
        except OSError as exc:
            unauth_status = f"OSError:{type(exc).__name__}"

        payload = json.loads(body) if body else {}
        healthy = status == 200 and payload.get("ok") is True
        gated = unauth_status == 403
        record("api_health_authorized", healthy,
               f"url={url} status={status} body={body!r}")
        record("api_health_token_gated", gated,
               f"status_without_token={unauth_status}")

        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)
        stopped = not thread.is_alive()
        refused = False
        after = "not_probed"
        if stopped:
            try:
                with urllib.request.urlopen(url, timeout=2) as r:
                    after = f"still_serving:{r.status}"
            except OSError as exc:
                refused = True
                after = f"connection_refused:{type(exc).__name__}"
        else:
            after = "thread_alive"
        record("graceful_shutdown", stopped and refused,
               f"thread_alive={thread.is_alive()} post_shutdown={after}")
    finally:
        if thread.is_alive():
            srv.shutdown()
            srv.server_close()
            thread.join(timeout=5)


def main() -> int:
    print(f"python={sys.executable}")
    print(f"version={sys.version.splitlines()[0]}")
    print(f"project={PROJECT}")
    print(f"state={STATE}")
    print(f"neutral_cwd={NEUTRAL_CWD}")
    for fn in (check_import, check_help, check_capabilities,
               check_db, check_health_and_shutdown):
        try:
            fn()
        except Exception as exc:  # honest failure, never fake success
            record(fn.__name__, False, f"{type(exc).__name__}: {exc}")
    passed = sum(1 for r in RESULTS if r["ok"])
    print(f"SUMMARY: {passed}/{len(RESULTS)} checks passed")
    out = os.environ.get("KEEL_SETUP_RESULTS_JSON")
    if out:
        Path(out).write_text(json.dumps(RESULTS, indent=2), encoding="utf-8")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
