"""A2.1/A2.2 — real voice-to-task handoff queue."""

from __future__ import annotations

from keel.voice_tasks import VoiceTaskQueue


def test_full_handoff_lifecycle(tmp_path):
    queue = VoiceTaskQueue(tmp_path)
    task = queue.enqueue("Summarize the report", session_id="s1")
    assert task["status"] == "pending_confirmation"
    assert queue.pending()[0]["id"] == task["id"]
    queue.confirm(task["id"])
    ready = queue.take_ready("s1")
    assert ready["transcript"] == "Summarize the report"
    assert queue.take_ready("other") is None
    assert queue.complete(task["id"], result="done") is True
    assert queue.pending() == []


def test_persistence(tmp_path):
    task = VoiceTaskQueue(tmp_path).enqueue("hello", session_id="s2")
    assert VoiceTaskQueue(tmp_path).pending()[0]["id"] == task["id"]
