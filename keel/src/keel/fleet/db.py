"""keel.fleet.db — fleet.db schema + connection helpers.

Schema is versioned via schema_version (INTEGER PRIMARY KEY). Migrations are
idempotent: each runs at most once per DB and is recorded.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 9

_DDL = """
CREATE TABLE IF NOT EXISTS bots (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT '',
    engine          TEXT NOT NULL DEFAULT 'echo',   -- 'echo' (scripted) | 'provider'
    provider        TEXT NOT NULL DEFAULT 'auto',
    model           TEXT NOT NULL DEFAULT '',
    notes           TEXT NOT NULL DEFAULT '',
    avatar_hue      INTEGER NOT NULL DEFAULT 200,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    last_active_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rows (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id     TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,   -- message | step | turn_end | notice | approval
    body       TEXT NOT NULL,   -- JSON
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rows_bot_seq ON rows(bot_id, seq);
"""

_DDL_V5 = """
-- F4 routines & scheduling
CREATE TABLE IF NOT EXISTS fleet_routines (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    bot_id         TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    prompt         TEXT NOT NULL,
    cron_expr      TEXT NOT NULL,
    timezone       TEXT NOT NULL DEFAULT 'UTC',
    enabled        INTEGER NOT NULL DEFAULT 1,
    paused         INTEGER NOT NULL DEFAULT 0,
    running        INTEGER NOT NULL DEFAULT 0,
    pause_reason   TEXT NOT NULL DEFAULT '',
    next_run_at    TEXT,
    last_run_at    TEXT,
    last_status    TEXT,
    last_summary   TEXT NOT NULL DEFAULT '',
    created_by     TEXT NOT NULL DEFAULT 'user',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fleet_routines_next_run
    ON fleet_routines(enabled, paused, next_run_at);
CREATE INDEX IF NOT EXISTS idx_fleet_routines_bot
    ON fleet_routines(bot_id);

CREATE TABLE IF NOT EXISTS fleet_routine_runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    routine_id     TEXT NOT NULL REFERENCES fleet_routines(id) ON DELETE CASCADE,
    task_id        TEXT REFERENCES fleet_tasks(id) ON DELETE SET NULL,
    scheduled_at   TEXT NOT NULL,
    started_at     TEXT,
    finished_at    TEXT,
    status         TEXT NOT NULL,   -- running | completed | failed | timeout
                                    -- | awaiting_approval | skipped_missed
    summary        TEXT NOT NULL DEFAULT '',
    error          TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fleet_routine_runs_routine
    ON fleet_routine_runs(routine_id, id);
"""

_DDL_V4 = """
-- F2 tasks & library
CREATE TABLE IF NOT EXISTS fleet_tasks (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    priority        TEXT NOT NULL DEFAULT 'normal'
                    CHECK (priority IN ('low','normal','high')),
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','in_progress','completed',
                                      'failed','cancelled')),
    progress        INTEGER NOT NULL DEFAULT 0
                    CHECK (progress BETWEEN 0 AND 100),
    assigned_bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
    created_by      TEXT NOT NULL,   -- 'user' or a bot_id
    source          TEXT NOT NULL DEFAULT 'user',
                    -- 'user' | 'agent' | 'delegation'
    source_task_id  TEXT REFERENCES fleet_tasks(id) ON DELETE SET NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    completed_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_fleet_tasks_assigned
    ON fleet_tasks(assigned_bot_id, status);

CREATE TABLE IF NOT EXISTS fleet_task_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT NOT NULL REFERENCES fleet_tasks(id) ON DELETE CASCADE,
    actor       TEXT NOT NULL,    -- 'user' or a bot_id
    event       TEXT NOT NULL,    -- created | reassigned | status | progress
                                  -- | note | edited | delegated
    from_status TEXT,
    to_status   TEXT,
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fleet_task_events_task
    ON fleet_task_events(task_id, id);

CREATE TABLE IF NOT EXISTS fleet_library (
    id          TEXT PRIMARY KEY,
    bot_id      TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    task_id     TEXT REFERENCES fleet_tasks(id) ON DELETE SET NULL,
    name        TEXT NOT NULL,
    mime        TEXT NOT NULL DEFAULT 'application/octet-stream',
    size        INTEGER NOT NULL CHECK (size >= 0),
    sha256      TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'agent',  -- 'agent' | 'user'
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fleet_library_bot
    ON fleet_library(bot_id, created_at);
"""

_DDL_V3 = """
-- bounded group conversations (F3): 2-3 agents, shared ledger
CREATE TABLE IF NOT EXISTS groups (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS group_members (
    group_id    TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    bot_id      TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    ord         INTEGER NOT NULL,
    PRIMARY KEY (group_id, bot_id)
);
CREATE TABLE IF NOT EXISTS group_rows (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id   TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    author     TEXT NOT NULL,   -- 'user' or bot_id
    kind       TEXT NOT NULL,   -- message | member_status | notice
    body       TEXT NOT NULL,   -- JSON
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_group_rows_seq ON group_rows(group_id, seq);
"""

_DDL_V2 = """
-- standing per-agent, per-tool policies (always | never)
CREATE TABLE IF NOT EXISTS fleet_policies (
    bot_id     TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    tool_name  TEXT NOT NULL,
    decision   TEXT NOT NULL CHECK (decision IN ('always', 'never')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (bot_id, tool_name)
);

-- one row per pending/resolved approval request (single invocation)
CREATE TABLE IF NOT EXISTS fleet_approvals (
    approval_id  TEXT PRIMARY KEY,
    bot_id       TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    tool_name    TEXT NOT NULL,
    fingerprint  TEXT NOT NULL,   -- sha256 of canonical tool_input, 16 hex chars
    args_summary TEXT NOT NULL,   -- truncated, human-facing; never in audit
    status       TEXT NOT NULL CHECK (status IN
                   ('pending', 'approved', 'denied', 'expired')),
    decision     TEXT,            -- once | always | never (as chosen)
    created_at   TEXT NOT NULL,
    decided_at   TEXT,
    decided_by   TEXT,            -- operator | timeout | restart
    expires_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fleet_approvals_pending
    ON fleet_approvals(bot_id, status);

-- Fleet-only audit trail; NO raw tool arguments, fingerprints only
CREATE TABLE IF NOT EXISTS fleet_audit (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id      TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    tool_name   TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    event       TEXT NOT NULL,    -- requested | decided | outcome | policy_revoked
    decision    TEXT,             -- once | always | never | timeout | restart | null
    outcome     TEXT,             -- granted | refused | executed | error | null
    approval_id TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fleet_audit_bot ON fleet_audit(bot_id, id);
"""

_connection_lock = threading.Lock()


def default_db_path() -> Path:
    return Path.home() / ".keel" / "fleet.db"


def _now() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = Path(path) if path else default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connection_lock:
        conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version("
        "  version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    applied = row[0] if row and row[0] else 0
    if applied < 1:
        conn.executescript(_DDL)
        conn.execute(
            "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES (1, ?)",
            (_now(),))
    if applied < 2:
        conn.executescript(_DDL_V2)
        conn.execute(
            "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES (2, ?)",
            (_now(),))
    if applied < 3:
        conn.executescript(_DDL_V3)
        conn.execute(
            "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES (3, ?)",
            (_now(),))
    if applied < 4:
        conn.executescript(_DDL_V4)
        conn.execute(
            "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES (4, ?)",
            (_now(),))
    if applied < 5:
        conn.executescript(_DDL_V5)
        # link library files to the routine that produced them
        cols = {r[1] for r in conn.execute("PRAGMA table_info(fleet_library)")}
        if "routine_id" not in cols:
            conn.execute(
                "ALTER TABLE fleet_library ADD COLUMN routine_id TEXT\n"
                " REFERENCES fleet_routines(id) ON DELETE SET NULL")
        conn.execute(
            "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES (5, ?)",
            (_now(),))
    if applied < 6:
        # v6: task work-order position, single-level undo snapshot, soft
        # delete; per-agent reasoning effort for capable providers
        task_cols = {r[1] for r in conn.execute("PRAGMA table_info(fleet_tasks)")}
        for col, ddl in (("position", "ALTER TABLE fleet_tasks ADD COLUMN position INTEGER"),
                         ("prev_state", "ALTER TABLE fleet_tasks ADD COLUMN prev_state TEXT"),
                         ("deleted_at", "ALTER TABLE fleet_tasks ADD COLUMN deleted_at TEXT")):
            if col not in task_cols:
                conn.execute(ddl)
        bot_cols = {r[1] for r in conn.execute("PRAGMA table_info(bots)")}
        if "reasoning_effort" not in bot_cols:
            conn.execute("ALTER TABLE bots ADD COLUMN reasoning_effort TEXT")
        # deterministic work order for pre-v6 rows
        rows = conn.execute(
            "SELECT id FROM fleet_tasks ORDER BY created_at ASC, id ASC").fetchall()
        for i, r in enumerate(rows):
            conn.execute("UPDATE fleet_tasks SET position = ? WHERE id = ?",
                         (i, r[0]))
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fleet_tasks_position "
            "ON fleet_tasks(position)")
        conn.execute(
            "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES (6, ?)",
            (_now(),))
    if applied < 7:
        # v7: project registry — local folders a human picked to work in
        conn.executescript("""
CREATE TABLE IF NOT EXISTS fleet_projects (
  id              TEXT PRIMARY KEY,
  path            TEXT NOT NULL,
  name            TEXT NOT NULL,
  model           TEXT,
  created_at      TEXT NOT NULL,
  last_opened_at  TEXT NOT NULL
);
""")
        conn.execute(
            "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES (7, ?)",
            (_now(),))
    if applied < 8:
        # v8: trust flag for project workspaces (the "Trust this folder?" gate)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(fleet_projects)")}
        if "trusted" not in cols:
            conn.execute(
                "ALTER TABLE fleet_projects ADD COLUMN trusted INTEGER NOT NULL DEFAULT 0")
        conn.execute(
            "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES (8, ?)",
            (_now(),))
    if applied < 9:
        # v9: link each chat (bot) to the project folder it belongs to,
        # so opening a project opens ITS chat instead of a stale global one
        cols = {r[1] for r in conn.execute("PRAGMA table_info(bots)")}
        if "project_id" not in cols:
            conn.execute(
                "ALTER TABLE bots ADD COLUMN project_id TEXT REFERENCES fleet_projects(id) ON DELETE SET NULL")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bots_project ON bots(project_id)")
        conn.execute(
            "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES (9, ?)",
            (_now(),))
    conn.commit()
