"""Recovery hardening regressions: crash-safe state, retention, breaker recovery.

Each test exercises real functions against temp directories and simulates the
kind of interrupted write / stale state that follows a crash or task abort.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest


# --------------------------------------------------------------------------
# resilience.CanaryFiles / ContentStore — crashes during local state writes
# --------------------------------------------------------------------------

def test_canary_add_survives_crash_mid_write(tmp_path, monkeypatch):
    """A crash while rewriting canaries must not erase existing registrations."""
    from keel.resilience import CanaryFiles

    canaries = CanaryFiles(tmp_path)
    canaries.add("secrets/canary.txt")
    assert canaries.touches("secrets/canary.txt") is True

    real_write_text = Path.write_text

    def crashy_write_text(self, data, *args, **kwargs):
        if self.name == "canary-files.json":
            # Simulate a torn write to the live file, then power loss.
            real_write_text(self, '["secrets/canary.txt", "secrets/h',
                            *args, **kwargs)
            raise OSError("simulated power loss")
        return real_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", crashy_write_text)
    try:
        canaries.add("secrets/other.txt")
    except OSError:
        pass  # the process may die; what matters is durable state afterwards

    assert canaries.touches("secrets/canary.txt") is True
    assert canaries.touches("secrets/other.txt") is True


def test_canary_loader_tolerates_torn_json(tmp_path):
    """A leftover partial JSON file must be treated as empty, never raise."""
    from keel.resilience import CanaryFiles

    canaries = CanaryFiles(tmp_path)
    canaries.path.write_text('["secrets/partial', encoding="utf-8")
    assert canaries.touches("secrets/partial") is False


def test_content_store_repairs_blob_left_by_crash(tmp_path, monkeypatch):
    """A partial blob must be healable by a later put (restart/retry)."""
    from keel.resilience import ContentStore

    store = ContentStore(tmp_path)
    payload = b"x" * 4096
    digest = hashlib.sha256(payload).hexdigest()

    real_write_bytes = Path.write_bytes

    def crashy_write_bytes(self, data, *args, **kwargs):
        if self.name == digest:
            real_write_bytes(self, data[:10], *args, **kwargs)
            raise OSError("simulated power loss")
        return real_write_bytes(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_bytes", crashy_write_bytes)
    try:
        store.put(payload)
    except OSError:
        pass
    monkeypatch.undo()

    # Process restarts and retries the same content-addressed write.
    store.put(payload)
    assert store.get(digest) == payload


def test_content_store_detects_and_repairs_corrupt_existing_blob(tmp_path):
    """An already-present blob with the wrong hash must be rewritten, not trusted."""
    from keel.resilience import ContentStore

    store = ContentStore(tmp_path)
    payload = b"important payload"
    digest = hashlib.sha256(payload).hexdigest()
    target = tmp_path / digest[:2] / digest
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"corrupted")

    store.put(payload)
    assert store.get(digest) == payload


# --------------------------------------------------------------------------
# message_state — torn append / corrupt records during interrupted writes
# --------------------------------------------------------------------------

def test_torn_last_line_does_not_swallow_next_append(tmp_path):
    """An append after a truncated line must remain a parseable standalone record."""
    from keel.message_state import MessageStates

    states = MessageStates(str(tmp_path))
    record = states.queue(channel="webhook")

    # Simulate a crash that left a half-written final line with no newline.
    with open(states.path, "a", encoding="utf-8") as handle:
        handle.write('{"id":"crashed","state":"queued"')

    states.advance(record["id"], "sent")
    assert states.state(record["id"]) == "sent"
    assert [r["state"] for r in states.history(record["id"])] == [
        "queued", "sent"]


def test_message_state_ignores_non_object_records(tmp_path):
    """Corrupt JSONL lines that decode to scalars must not break the loader."""
    from keel.message_state import MessageStates

    states = MessageStates(str(tmp_path))
    record = states.queue(channel="webhook")
    with open(states.path, "a", encoding="utf-8") as handle:
        handle.write("42\n")
        handle.write('"not a record"\n')

    assert states.state(record["id"]) == "queued"
    assert len(states.history(record["id"])) == 1


def test_message_state_transition_graph_has_no_state_skips():
    """Direct transitions that skip a delivery stage are illegal."""
    from keel.message_state import MessageStateError, transition

    for current, target in (("queued", "delivered"), ("queued", "read"),
                            ("sent", "read"), ("cancelled", "queued"),
                            ("read", "delivered")):
        with pytest.raises(MessageStateError, match="illegal transition"):
            transition(current, target)
    # Legal single-step progression and explicit retry remain intact.
    assert transition("queued", "sent") == "sent"
    assert transition("failed", "queued") == "queued"


# --------------------------------------------------------------------------
# circuit_breaker — interruption during a half-open probe must not wedge it
# --------------------------------------------------------------------------

def test_interrupted_half_open_probe_does_not_wedge_breaker():
    """A probe whose outcome is never recorded (abort) must be released."""
    from keel.circuit_breaker import CircuitBreaker

    breaker = CircuitBreaker("aborted", failure_threshold=1,
                             recovery_timeout=0.01)
    breaker.record_failure()
    assert breaker.state == "open"
    breaker._opened_at = time.monotonic() - 1.0
    assert breaker.allow() is True  # one probe goes out
    # Simulated crash: no record_success()/record_failure() ever arrives.
    time.sleep(0.03)
    assert breaker.allow() is True  # a new probe must be permitted
    breaker.record_success()
    assert breaker.state == "closed"


def test_single_failure_during_parallel_probes_keeps_breaker_open():
    """One failing probe must not be silently overwritten by a late success."""
    from keel.circuit_breaker import CircuitBreaker

    breaker = CircuitBreaker("mixed", failure_threshold=1,
                             recovery_timeout=0.01, half_open_max=2)
    breaker.record_failure()
    breaker._opened_at = time.monotonic() - 1.0
    assert breaker.allow() is True
    assert breaker.allow() is True

    breaker.record_failure()  # probe A fails: recovery window restarts
    assert breaker.state == "open"
    breaker.record_success()  # probe B reports success late
    assert breaker.state == "open"


# --------------------------------------------------------------------------
# trash — retention and restore of ordinary files
# --------------------------------------------------------------------------

def test_restore_json_named_file(tmp_path, monkeypatch):
    """A trashed .json data blob must not be mistaken for a metadata file."""
    from keel import trash

    monkeypatch.setenv("KEEL_TRASH_DIR", str(tmp_path / "trash"))
    target = tmp_path / "config.json"
    target.write_text('{"a": 1}', encoding="utf-8")
    meta = trash.move_to_trash(target)
    assert not target.exists()
    assert [i["id"] for i in trash.list_items()] == [meta["id"]]

    restored = trash.restore(meta["id"])
    assert restored == target
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}


def test_trash_retention_purges_expired_items(tmp_path, monkeypatch):
    """Items past the retention window are removed from listing and disk."""
    from keel import trash

    monkeypatch.setenv("KEEL_TRASH_DIR", str(tmp_path / "trash"))
    monkeypatch.setenv("KEEL_TRASH_RETENTION_DAYS", "7")
    target = tmp_path / "old.txt"
    target.write_text("old", encoding="utf-8")
    meta = trash.move_to_trash(target)
    root = trash.trash_root()

    meta_path = root / f"{meta['id']}.json"
    doc = json.loads(meta_path.read_text(encoding="utf-8"))
    doc["trashed_at"] = "2000-01-01T00:00:00Z"
    meta_path.write_text(json.dumps(doc), encoding="utf-8")

    assert trash.list_items() == []
    assert not meta_path.exists()
    assert not any(meta["id"] in p.name for p in root.iterdir())


def test_trash_retention_enforces_max_items(tmp_path, monkeypatch):
    """The configured item cap bounds trash growth."""
    from keel import trash

    monkeypatch.setenv("KEEL_TRASH_DIR", str(tmp_path / "trash"))
    monkeypatch.setenv("KEEL_TRASH_MAX_ITEMS", "2")
    ids = []
    for i in range(5):
        target = tmp_path / f"f{i}.txt"
        target.write_text(str(i), encoding="utf-8")
        ids.append(trash.move_to_trash(target)["id"])

    items = trash.list_items()
    assert len(items) == 2
    assert {i["id"] for i in items}.issubset(set(ids))


def test_trash_list_ignores_torn_metadata(tmp_path, monkeypatch):
    """A partial metadata file left by a crash must not break listing."""
    from keel import trash

    monkeypatch.setenv("KEEL_TRASH_DIR", str(tmp_path / "trash"))
    root = trash.trash_root()
    (root / "torn.json").write_text('{"id": "tor', encoding="utf-8")
    target = tmp_path / "good.txt"
    target.write_text("good", encoding="utf-8")
    meta = trash.move_to_trash(target)

    assert [i["id"] for i in trash.list_items()] == [meta["id"]]
