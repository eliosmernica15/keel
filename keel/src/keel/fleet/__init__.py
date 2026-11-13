"""keel.fleet — Keel Fleet: persistent multi-agent roster + chat rows.

Persistence lives in ~/.keel/fleet.db (SQLite, WAL). One monotonically
increasing `seq` per row, used for cursor-based SSE replay.
"""

__all__ = ["db", "service", "echo", "routes"]
