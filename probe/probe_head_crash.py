import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "int" / "keel" / "src"))
from keel.backend_events import EventBus, SessionStarted

root = Path(tempfile.mkdtemp(prefix="probe-head-"))
bus = EventBus(root)
bus.publish(SessionStarted(event_id="e1", session_id="s1"))
head = Path(str(root / "backend-events.jsonl") + ".head")
print("head before:", head.read_text())
# Simulate a crash after the JSONL line was fsynced but before the head was
# committed: restore the old head (count=0, genesis digest).
head.write_text(json.dumps({"count": 0, "digest": "0" * 64}) + "\n")
try:
    bus2 = EventBus(root)
    print("reopen: ok", len(bus2.events))
except Exception as exc:
    print("reopen:", type(exc).__name__, str(exc)[:160])
try:
    bus.publish(SessionStarted(event_id="e2", session_id="s2"))
    print("append after corruption: ok")
except Exception as exc:
    print("append after corruption:", type(exc).__name__, str(exc)[:120])
