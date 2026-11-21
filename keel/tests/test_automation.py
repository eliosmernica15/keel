"""C5.4/C5.5/C5.6 — event bus, triggers, notifications."""

from __future__ import annotations

from keel.automation import EventBus, NotificationRules, Trigger, match_trigger


def test_event_bus():
    bus = EventBus()
    seen = []
    bus.subscribe("file.saved", seen.append)
    assert bus.publish("file.saved", {"path": "a.py"}) == 1
    assert seen[0]["topic"] == "file.saved"
    assert len(bus.history) == 1


def test_trigger_match():
    trigger = Trigger("file", ".py", "lint")
    assert match_trigger(trigger, {"trigger": "file", "path": "a.py"})
    assert not match_trigger(trigger, {"trigger": "git", "path": "a.py"})


def test_notification_rules():
    rules = NotificationRules(quiet_from=22, quiet_to=8)
    assert rules.is_quiet(23) is True
    assert rules.is_quiet(12) is False
    assert rules.route("email", "critical") == "all"
