"""Session import/export and statistics (A1.16).

Sessions are Fleet bots with message rows. Bundles are local JSON files; no
cloud service is involved. Import creates a new session and never overwrites
an existing one.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path


class SessionExportError(RuntimeError):
    pass


def export_bundle(store, session_id: str) -> dict:
    bot = store.get_bot(session_id)
    if bot is None:
        raise SessionExportError(f"unknown session: {session_id}")
    rows = store.list_rows(session_id, after_seq=0, limit=100000)
    return {
        "format": "keel-session-v1",
        "session": {"name": bot.get("name", ""),
                    "notes": bot.get("notes", "")},
        "rows": [{"kind": row.get("kind"), "body": row.get("body")}
                 for row in rows],
    }


def write_bundle(bundle: dict, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    return target


def read_bundle(path: str | Path) -> dict:
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SessionExportError(f"cannot read bundle: {exc}") from None
    if not isinstance(doc, dict) or doc.get("format") != "keel-session-v1":
        raise SessionExportError("not a Keel session bundle")
    return doc


def import_bundle(store, bundle: dict) -> dict:
    session = bundle.get("session", {}) or {}
    if not isinstance(session, dict):
        raise SessionExportError("invalid session metadata")
    name = str(session.get("name") or "Imported session")[:64]
    if not name.lower().startswith("imported"):
        name = "Imported " + name
    bot = store.create_bot(name=name, engine="provider",
                           notes=str(session.get("notes") or ""),
                           bot_id=secrets.token_urlsafe(9), kind="session")
    for row in bundle.get("rows", [])[:100000]:
        if isinstance(row, dict) and row.get("kind"):
            store.append_row(bot["id"], row["kind"], row.get("body") or {})
    return bot


def statistics(store, session_id: str) -> dict:
    bot = store.get_bot(session_id)
    if bot is None:
        raise SessionExportError(f"unknown session: {session_id}")
    rows = store.list_rows(session_id, after_seq=0, limit=100000)
    kinds: dict[str, int] = {}
    tokens = 0
    for row in rows:
        kind = row.get("kind") or "unknown"
        kinds[kind] = kinds.get(kind, 0) + 1
        body = row.get("body") or {}
        if isinstance(body, dict):
            usage = body.get("usage") or {}
            if isinstance(usage, dict):
                tokens += int(usage.get("input_tokens", 0)) + int(
                    usage.get("output_tokens", 0))
    return {"session_id": session_id, "rows": len(rows),
            "by_kind": kinds, "tokens": tokens}
