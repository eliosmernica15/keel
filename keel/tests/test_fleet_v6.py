"""v6 migration: task position / undo snapshot / soft delete / bot effort."""

import sqlite3
import threading

from keel.fleet import routes as fleet_routes
import keel.webapp as webapp


def test_v6_fresh_schema(tmp_path):
    path = tmp_path / "fresh.db"
    store = fleet_routes.reset_store_for_tests(path)
    cols = {}
    for table in ("fleet_tasks", "bots"):
        cols[table] = {r[1] for r in store._conn.execute(
            f"PRAGMA table_info({table})")}
    assert {"position", "prev_state", "deleted_at"} <= cols["fleet_tasks"]
    assert "reasoning_effort" in cols["bots"]
    version = store._conn.execute(
        "SELECT MAX(version) FROM schema_version").fetchone()[0]
    assert version == 8
    store.close()


def test_v6_reopen_idempotent(tmp_path):
    path = tmp_path / "reopen.db"
    store = fleet_routes.reset_store_for_tests(path)
    bot = store.create_bot(name="Legacy", engine="echo")
    task = store.create_task(title="one", assigned_bot_id=None,
                             created_by="user")
    assert task["position"] == 0
    task2 = store.create_task(title="two", assigned_bot_id=None,
                              created_by="user")
    assert task2["position"] == 1
    store.close()
    # second open must not fail, dup columns must not appear, positions hold
    store = fleet_routes.reset_store_for_tests(path)
    rows = store.list_tasks()
    assert [r["title"] for r in rows] == ["one", "two"]
    assert [r["position"] for r in rows] == [0, 1]
    store.close()


def test_v6_create_bot_honours_avatar_hue(tmp_path):
    store = fleet_routes.reset_store_for_tests(tmp_path / "hue.db")
    bot = store.create_bot(name="Huey", engine="echo", avatar_hue=42)
    assert bot["avatar_hue"] == 42
    default_bot = store.create_bot(name="DefaultBot", engine="echo")
    assert default_bot["avatar_hue"] is not None
    store.close()


def test_v6_reorder_undo_and_soft_delete(tmp_path):
    store = fleet_routes.reset_store_for_tests(tmp_path / "flows.db")
    a = store.create_task(title="a", created_by="user")
    b = store.create_task(title="b", created_by="user")
    c = store.create_task(title="c", created_by="user")
    # operator drags c to the top: c, a, b
    ordered = store.reorder_tasks([c["id"], a["id"], b["id"]], actor="user")
    assert [t["title"] for t in ordered] == ["c", "a", "b"]
    # undo reverts b's position back to the pre-reorder value
    undo = store.undo_task(b["id"], actor="user")
    assert undo["position"] == 1  # b was 2nd before the reorder
    # soft delete: invisible in lists, still restorable
    store.delete_task(b["id"])
    titles = [t["title"] for t in store.list_tasks()]
    assert "b" not in titles
    restored = store.undo_task(b["id"], actor="user")
    assert restored is not None
    assert restored["deleted_at"] is None
    titles = [t["title"] for t in store.list_tasks()]
    assert "b" in titles
    store.close()
