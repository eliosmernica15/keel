"""Clean-setup verification harness for the stabilization install/rollback gate.

Run with the Python interpreter of a disposable clean venv that has the exact
checkout installed editable::

    KEEL_SETUP_PROJECT=<checkout>/keel KEEL_STATE_DIR=<fresh temp dir> \
      <venv>/Scripts/python.exe scripts/verify_stab_install.py

Required environment:
    KEEL_SETUP_PROJECT  path to the checkout's ``keel/`` directory
    KEEL_STATE_DIR      a fresh, empty temporary state directory

Optional environment:
    KEEL_SETUP_RESULTS_JSON  path to write machine-readable results

All state is created under KEEL_STATE_DIR. Subprocesses run from a neutral cwd
with PYTHONPATH cleared and PYTHONNOUSERSITE=1 so imports resolve only through
the venv's editable install. Nothing is installed into the user's Python and no
credentials, signing identity or paid service is used.
"""

from __future__ import annotations

import json
import os
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

TOKEN = "stab-install-clean-setup-token"
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
    proc = run([sys.executable, "-c", code])
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    ok = (proc.returncode == 0 and len(lines) >= 2
          and str(PROJECT / "src" / "keel") in lines[-1])
    record("clean_import", ok,
           f"rc={proc.returncode} version={lines[0] if lines else '?'} "
           f"module={lines[-1] if lines else '?'} stderr={proc.stderr.strip()!r}")


def check_cli_help() -> None:
    proc = run([sys.executable, "-m", "keel", "--help"])
    ok = (proc.returncode == 0 and "usage: keel" in proc.stdout
          and "capability" in proc.stdout)
    record("cli_help", ok,
           f"rc={proc.returncode} stdout_lines={len(proc.stdout.splitlines())} "
           f"stderr={proc.stderr.strip()!r}")


def check_cli_capability() -> None:
    proc = run([sys.executable, "-m", "keel", "capability", "list"])
    ids = [line.split()[0] for line in proc.stdout.splitlines() if line.strip()]
    expected = {"backend.modules", "backend.describe", "backend.invoke", "backend.verify"}
    missing = sorted(expected - set(ids))
    backend_ids = sorted(x for x in ids if x.startswith("backend."))
    ok = proc.returncode == 0 and not missing
    record("cli_capability_list_backend", ok,
           f"rc={proc.returncode} total_capabilities={len(ids)} "
           f"backend_capabilities={backend_ids} missing={missing} "
           f"stderr={proc.stderr.strip()!r}")


def check_db_init() -> None:
    from keel.fleet import db as fleet_db
    from keel.fleet.service import FleetStore

    db_path = STATE / "fleet.db"
    conn = fleet_db.connect(db_path)
    tables = sorted(
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    )
    versions = [row[0] for row in conn.execute(
        "SELECT version FROM schema_version ORDER BY version").fetchall()]
    conn.close()

    expected = {"bots", "rows", "fleet_tasks", "fleet_audit", "groups", "schema_version"}
    missing = sorted(expected - set(tables))
    store_path = STATE / "fleet-service.db"
    store = FleetStore(store_path)
    store_tables = sorted(
        row[0] for row in store._conn.execute(
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
                with urllib.request.urlopen(authorized, timeout=2) as resp:
                    status = resp.status
                    body = resp.read().decode("utf-8")
                break
            except urllib.error.HTTPError as exc:
                status = exc.code
                body = exc.read().decode("utf-8", "replace")
                break
            except OSError:
                time.sleep(0.1)

        request = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(request, timeout=2) as resp:
                unauth_status = resp.status
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
                with urllib.request.urlopen(url, timeout=2) as resp:
                    after = f"still_serving:{resp.status}"
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


def check_version_gate() -> None:
    from keel.release.common import load_versions, validate_version

    versions = load_versions()
    distinct = set(versions.values())
    version = validate_version()
    ok = len(distinct) == 1 and version == "0.1.1"
    record("version_consistency_gate", ok,
           f"version={version} sources={len(versions)} distinct={sorted(distinct)}")


def main() -> int:
    print(f"python={sys.executable}")
    print(f"version={sys.version.splitlines()[0]}")
    print(f"project={PROJECT}")
    print(f"state={STATE}")
    print(f"neutral_cwd={NEUTRAL_CWD}")
    for fn in (check_import, check_cli_help, check_cli_capability,
               check_db_init, check_health_and_shutdown, check_version_gate):
        try:
            fn()
        except Exception as exc:  # honest failure, never fake success
            record(fn.__name__, False, f"{type(exc).__name__}: {exc}")
    passed = sum(1 for result in RESULTS if result["ok"])
    print(f"SUMMARY: {passed}/{len(RESULTS)} checks passed")
    out = os.environ.get("KEEL_SETUP_RESULTS_JSON")
    if out:
        Path(out).write_text(json.dumps(RESULTS, indent=2), encoding="utf-8")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
