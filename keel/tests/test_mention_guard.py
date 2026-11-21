"""A2.5 — group-chat loop prevention via bounded @mentions."""

from __future__ import annotations

from keel.fleet.groups import group_attachment
from keel.fleet.mention_guard import MentionGuard, extract_mentions


def test_extract_mentions():
    assert extract_mentions("hey @sage and @Sage, cc @fleet-1") == [
        "sage", "sage", "fleet-1"]


def test_per_pair_cap():
    guard = MentionGuard(max_per_pair=2, max_per_round=20)
    assert guard.check("alice", "@bob please") == []
    assert guard.check("alice", "@bob again") == []
    assert guard.check("alice", "@bob third") == ["bob"]
    assert guard.check("alice", "@carol first") == []


def test_per_round_cap():
    guard = MentionGuard(max_per_pair=10, max_per_round=2)
    assert guard.check("alice", "@bob") == []
    assert guard.check("carol", "@bob") == []
    assert guard.check("dave", "@bob") == ["bob"]


def test_self_mentions_are_ignored():
    guard = MentionGuard(max_per_pair=1, max_per_round=1)
    assert guard.check("alice", "@alice thinking out loud") == []


def test_group_brief_warns_about_loops():
    brief = group_attachment(
        {"members": [{"id": "a", "name": "Alice"},
                     {"id": "b", "name": "Bob"}]}, "hi")
    assert "@mention" in brief and "suppressed" in brief
