import multiprocessing as mp
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "int" / "keel" / "src"))
from keel.backend_events import (EventBus, SessionStarted, CorruptRecordError)


def worker(root, i, q):
    try:
        bus = EventBus(root)
        bus.publish(SessionStarted(event_id=f"evt-{i}", session_id=f"session-{i}"))
        q.put((i, "ok"))
    except Exception as exc:
        q.put((i, type(exc).__name__, str(exc)[:120]))


if __name__ == "__main__":
    for trial in range(3):
        root = Path(tempfile.mkdtemp(prefix="probe-events-race-"))
        q = mp.Queue()
        procs = [mp.Process(target=worker, args=(root, i, q)) for i in range(8)]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=60)
        outcomes = [q.get() for _ in procs]
        log = root / "backend-events.jsonl"
        lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        try:
            bus = EventBus(root)
            count = len(bus.events)
            status = f"read ok ({count} events)"
        except Exception as exc:
            status = f"READ FAILED: {type(exc).__name__}: {str(exc)[:120]}"
        print(f"trial {trial}: lines={len(lines)} statuses={status}")
        print("  seqs:", [__import__('json').loads(x)['seq'] for x in lines])
        print("  outcomes:", outcomes)
