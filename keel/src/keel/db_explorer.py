"""Read-only local database explorer (B2.9).

Lists tables, columns and rows from a local SQLite database with a strict
read-only connection and bounded result sizes. No network databases are
contacted; the caller supplies the file.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|replace|vacuum|pragma)\b",
    re.I)


class DBError(RuntimeError):
    pass


class DBExplorer:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.is_file():
            raise DBError(f"not a file: {self.path}")

    def _connect(self):
        return sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)

    def tables(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "ORDER BY name").fetchall()
        return [row[0] for row in rows]

    def columns(self, table: str) -> list[dict]:
        if table not in self.tables():
            raise DBError(f"unknown table: {table}")
        with self._connect() as conn:
            rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        return [{"name": row[1], "type": row[2],
                 "not_null": bool(row[3])} for row in rows]

    def query(self, sql: str, *, limit: int = 100) -> list[dict]:
        """Run a read-only SELECT with a hard row cap."""
        if not sql.strip().lower().startswith("select"):
            raise DBError("only SELECT queries are allowed")
        if FORBIDDEN.search(sql):
            raise DBError("query contains a forbidden keyword")
        with self._connect() as conn:
            cursor = conn.execute(sql)
            rows = cursor.fetchmany(max(1, min(1000, limit)))
            names = [description[0] for description in cursor.description]
        return [dict(zip(names, row)) for row in rows]
