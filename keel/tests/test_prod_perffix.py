"""Regressions for the three confirmed production performance defects.

1. Same-name bot creation / project chat creation raced into IntegrityError.
2. Pending ask_user rows were never expired on restart (wrong SQLite predicate).
3. Import of keel.capabilities eagerly imported all 20 backend modules.

The HTTP listen backlog is also checked: the stdlib default of 5 caused
connection refusals under a 100-client burst.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"

_BACKENDS = [
    "d3_backend", "d6_reliability_backend", "d7_workflow_backend",
    "e3_backend", "e5_backend", "e6_x5_x6_backend", "e7_runtime_backend",
    "small_groups_backend", "v_series_backend", "w1_security_backend",
    "w4_backend", "w7_x1_y5_d1_backend", "x2_orchestration_backend",
    "x3_memory_backend", "x8_backend", "y1_config_backend", "y2_backend",
    "y3_backend", "y4_d4_x7_backend", "z_backend",
]

_NOW = "2026-01-01T00:00:00.000Z"


def _clean_env(tmp_path: Path) -> dict:
    """Subprocess env with an empty HOME (no user config can skew imports)."""
    home = tmp_path / "cleanhome"
    home.mkdir(exist_ok=True)
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env.pop("PYTHONPATH", None)
    return env


def _seed_project(db_path: Path, project_id: str) -> None:
    from keel.fleet import db as fdb

    conn = fdb.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO fleet_projects(id, path, name, model, created_at, last_opened_at)"
            " VALUES(?,?,?,?,?,?)",
            (project_id, "/tmp/project", "Project", "", _NOW, _NOW))
        conn.commit()
    finally:
        conn.close()


# --- Defect 1: duplicate-agent creation race --------------------------------

def test_concurrent_same_name_create_bot_is_atomic(tmp_path):
    from keel.fleet.service import FleetStore

    store = FleetStore(tmp_path / "race.db")
    try:
        barrier = threading.Barrier(16)
        created: list[dict] = []
        errors: list[Exception] = []

        def worker() -> None:
            try:
                barrier.wait()
                created.append(store.create_bot(name="same"))
            except Exception as exc:  # collect instead of failing in a thread
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(16)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert errors == [], f"concurrent create_bot failed: {errors[:3]}"
        assert len(created) == 16
        # Every caller gets its own unique bot, no UNIQUE-constraint failures.
        assert len({bot["id"] for bot in created}) == 16
        bots = [b for b in store.list_bots(kind=None) if b["name"] == "same"]
        assert len(bots) == 16
    finally:
        store._conn.close()


@pytest.mark.parametrize("threads", [2, 8])
def test_concurrent_chat_for_project_creates_exactly_one_bot(tmp_path, threads):
    from keel.fleet.service import FleetStore

    db_path = tmp_path / f"project-{threads}.db"
    project_id = "a1b2c3d4"
    _seed_project(db_path, project_id)
    store = FleetStore(db_path)
    try:
        barrier = threading.Barrier(threads)
        chats: list[dict] = []
        errors: list[Exception] = []

        def worker() -> None:
            try:
                barrier.wait()
                chat = store.chat_for_project(project_id)
                assert chat is not None
                chats.append(chat)
            except Exception as exc:
                errors.append(exc)

        workers = [threading.Thread(target=worker) for _ in range(threads)]
        for thread in workers:
            thread.start()
        for thread in workers:
            thread.join(timeout=30)

        assert errors == [], f"concurrent chat_for_project failed: {errors[:3]}"
        assert len(chats) == threads
        assert len({chat["id"] for chat in chats}) == 1
        rows = store._conn.execute(
            "SELECT id FROM bots WHERE project_id = ?", (project_id,)).fetchall()
        assert len(rows) == 1
    finally:
        store._conn.close()


# --- Defect 2: pending asks never expired on restart -------------------------

def test_pending_asks_expire_on_restart(tmp_path):
    from keel.fleet import db as fdb
    from keel.fleet.service import FleetStore

    db_path = tmp_path / "asks.db"
    conn = fdb.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO bots(id,name,role,engine,provider,model,notes,avatar_hue,"
            "created_at,updated_at,last_active_at,project_id,kind)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("askbot", "Ask Bot", "", "provider", "auto", "", "", 0,
             _NOW, _NOW, _NOW, None, "agent"))
        conn.executemany(
            "INSERT INTO rows(bot_id, kind, body, created_at) VALUES(?,?,?,?)",
            [("askbot", "ask",
              json.dumps({"status": "pending", "question": f"q{i}"}), _NOW)
             for i in range(6)] +
            [("askbot", "ask",
              json.dumps({"status": "completed", "question": f"done{i}"}), _NOW)
             for i in range(4)])
        conn.commit()
    finally:
        conn.close()

    # A fresh store object on the same DB is exactly what a server restart does.
    restarted = FleetStore(db_path)
    try:
        statuses = [
            json.loads(row["body"])["status"]
            for row in restarted._conn.execute(
                "SELECT body FROM rows WHERE kind = 'ask'").fetchall()]
        assert statuses.count("interrupted") == 6
        assert statuses.count("completed") == 4  # resolved asks untouched
        assert "pending" not in statuses
        notices = restarted._conn.execute(
            "SELECT body FROM rows WHERE kind = 'notice'").fetchall()
        assert len(notices) == 6
        assert all(
            "interrupted by" in json.loads(row["body"])["text"] for row in notices)
    finally:
        restarted._conn.close()


# --- Defect 3: eager backend imports at startup ------------------------------

def test_import_capabilities_does_not_import_all_backends(tmp_path):
    code = f"""
import json, sys, time
sys.path.insert(0, r"{_SRC}")
t0 = time.perf_counter()
import keel.capabilities
ms = (time.perf_counter() - t0) * 1000
loaded = [m for m in {_BACKENDS!r} if "keel." + m in sys.modules]
print(json.dumps({{"ms": round(ms, 1), "loaded": len(loaded)}}))
"""
    out = subprocess.run(
        [sys.executable, "-P", "-c", code], cwd=str(tmp_path),
        env=_clean_env(tmp_path), capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["loaded"] == 0, (
        f"importing keel.capabilities imported {result['loaded']}/20 backends"
        f" in {result['ms']} ms")


def test_first_invoke_validates_dispatch_before_running_a_function(tmp_path):
    code = f"""
import json, sys
sys.path.insert(0, r"{_SRC}")
from keel import backend_hub as hub
import keel.e5_backend as e5
called = []
original = e5.validate_app_id
def spy(*args, **kwargs):
    called.append(1)
    return original(*args, **kwargs)
e5.validate_app_id = spy
hub.DISPATCH["e5_backend"] = tuple(hub.DISPATCH["e5_backend"]) + ("_not_a_real_function",)
out = {{"validated": False, "called": len(called)}}
try:
    hub.invoke("e5_backend", "validate_app_id", {{"app_id": "x"}})
except AssertionError as exc:
    out = {{"validated": "_not_a_real_function" in str(exc), "called": len(called)}}
print(json.dumps(out))
"""
    out = subprocess.run(
        [sys.executable, "-P", "-c", code], cwd=str(tmp_path),
        env=_clean_env(tmp_path), capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["validated"] is True
    assert result["called"] == 0, "invoke executed a function before validating"


# --- Additive HTTP backlog hardening ----------------------------------------

def test_webapp_listen_backlog_is_raised():
    from keel.webapp import make_server

    server = make_server(0)
    try:
        assert server.request_queue_size > 5
        assert server.request_queue_size >= 128
        assert server.daemon_threads is True
    finally:
        server.server_close()
