"""Fleet event-bus persistence and event-aware anomaly regressions (Agent 24).

The defects pinned here: ``_bus`` built a fresh in-memory ``EventBus()`` on
every invoke, nothing was written under ``state_root``, and ``fleet.anomaly``
never read the events that were published. The tests exercise the persistence
contract that ``EventBus(ctx.state_root)`` now provides, plus the anomaly logic
that consumes those real events.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from keel.automation import (
    DEFAULT_EVENT_LOG,
    MASS_READ_THRESHOLD,
    EventBus,
    anomaly_score,
)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _publish(state_root, topic: str, payload: dict) -> EventBus:
    """Simulate one ``_bus`` invoke: a new bus per publish, shared state root."""
    bus = EventBus(state_root)
    bus.publish(topic, payload)
    return bus


# ------------------------------------------------------------------ persistence
def test_three_publishes_with_shared_state_root_accumulate_history(tmp_path):
    state_root = tmp_path / "state"

    first = _publish(state_root, "task.done", {"id": "t1"})
    assert len(first.history) == 1

    second = _publish(state_root, "task.done", {"id": "t2"})
    assert len(second.history) == 2

    third = _publish(state_root, "task.done", {"id": "t3"})
    assert len(third.history) == 3
    assert [event["payload"]["id"] for event in third.history] == ["t1", "t2", "t3"]


def test_jsonl_state_file_is_created_and_subscribers_still_fire(tmp_path):
    state_root = tmp_path / "state"
    _publish(state_root, "task.done", {"id": "t1"})
    _publish(state_root, "task.done", {"id": "t2"})

    path = state_root / DEFAULT_EVENT_LOG
    assert path.is_file()
    lines = [line for line in path.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    assert len(lines) == 2
    assert [json.loads(line)["payload"]["id"] for line in lines] == ["t1", "t2"]

    bus = EventBus(state_root)
    seen = []
    bus.subscribe("task.done", seen.append)
    assert bus.publish("task.done", {"id": "t3"}) == 1
    assert seen[0]["topic"] == "task.done"
    assert len(EventBus(state_root).history) == 3


def test_without_state_root_bus_stays_in_memory_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bus = EventBus()
    assert bus.path is None
    bus.publish("task.done", {"id": "t1"})
    assert len(bus.history) == 1
    assert EventBus().history == []
    assert list(tmp_path.rglob("*.jsonl")) == []


def test_corrupt_jsonl_lines_are_skipped(tmp_path):
    state_root = tmp_path / "state"
    _publish(state_root, "task.done", {"id": "t1"})
    path = state_root / DEFAULT_EVENT_LOG
    with path.open("a", encoding="utf-8") as fh:
        fh.write("not-json\n")
    _publish(state_root, "task.done", {"id": "t2"})
    assert [event["payload"]["id"] for event in EventBus(state_root).history] == [
        "t1", "t2"]


def test_history_survives_a_fresh_interpreter(tmp_path):
    state_root = tmp_path / "state"
    write_code = (
        "import sys\n"
        f"sys.path.insert(0, {str(SRC)!r})\n"
        "from keel.automation import EventBus\n"
        "bus = EventBus(sys.argv[1])\n"
        "for i in range(3):\n"
        "    bus.publish('task.done', {'id': 'p%d' % i})\n"
    )
    read_code = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(SRC)!r})\n"
        "from keel.automation import EventBus, anomaly_score\n"
        "bus = EventBus(sys.argv[1])\n"
        "out = {'ids': [e['payload']['id'] for e in bus.history],\n"
        "       'score': anomaly_score(state_root=sys.argv[1])}\n"
        "print(json.dumps(out))\n"
    )
    for code in (write_code, read_code):
        proc = subprocess.run(
            [sys.executable, "-c", code, str(state_root)],
            capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr

    out = json.loads(proc.stdout)
    assert out["ids"] == ["p0", "p1", "p2"]
    assert out["score"] == 0.0


# ------------------------------------------------------------------- anomaly logic
def test_anomaly_reacts_to_real_persisted_event_patterns(tmp_path):
    denied = tmp_path / "denied"
    for i in range(4):
        _publish(denied, "tool.denied", {"kind": "denied", "id": i})
    assert anomaly_score(state_root=denied) == 1.0
    assert EventBus(denied).anomaly_score() == 1.0

    calm = tmp_path / "calm"
    for i in range(4):
        _publish(calm, "task.done", {"kind": "ok", "id": i})
    assert anomaly_score(state_root=calm) == 0.0


def test_anomaly_detects_mass_file_reads_from_event_payloads(tmp_path):
    state_root = tmp_path / "state"
    for i in range(MASS_READ_THRESHOLD + 5):
        _publish(state_root, "tool.read", {"tool": "read_file",
                                           "path": f"file{i}.py"})
    assert anomaly_score(state_root=state_root) >= 0.8


def test_explicit_events_and_legacy_fallback_still_work(tmp_path):
    # Caller-supplied events keep their previous behaviour.
    assert anomaly_score([{"tool": "delete_file"}] * 5) == 1.0
    assert anomaly_score([{"kind": "ok"}] * 5) == 0.0
    # No events and no state root: documented static-rule fallback.
    assert anomaly_score() == 0.0
