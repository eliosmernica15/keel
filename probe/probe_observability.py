import json
import multiprocessing as mp
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "int" / "keel" / "src"))
from keel import backend_observability as bo


def worker(root, i, q):
    try:
        bo.record_event("probe", session_id=f"s{i}", data={"i": i}, state_root=root)
        q.put((i, "ok"))
    except Exception as exc:
        q.put((i, type(exc).__name__, str(exc)[:140]))


if __name__ == "__main__":
    root = Path(tempfile.mkdtemp(prefix="probe-obs-"))
    q = mp.Queue()
    procs = [mp.Process(target=worker, args=(root, i, q)) for i in range(12)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=60)
    print("outcomes:", sorted([q.get() for _ in procs]))
    result = bo.verify_chain(root)
    print("chain:", result.as_dict(), "events:", len(bo.read_events(root)))

    redacted = bo.redact({
        "password": "hunter2",
        "nested": {"Authorization": "Bearer abc123def456", "note": "sk-abcdefghij1234567890"},
        "list": [{"api_key": "super-secret"}],
    })
    print("redacted:", json.dumps(redacted, sort_keys=True))
    raw = Path(root / "observability.jsonl").read_text(encoding="utf-8")
    print("plaintext secrets in log:",
          [s for s in ("hunter2", "abc123def456", "super-secret") if s in raw])
