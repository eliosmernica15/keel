"""A5.4/A5.6/A5.7 — fallback, subscriptions and troubleshooting."""

from __future__ import annotations

from keel.channel_ops import (SubscriptionStore, checklist,
                              deliver_with_fallback)


def test_fallback_stops_on_success():
    called = []

    def send(channel):
        called.append(channel)
        return (True, "ok") if channel == "second" else (False, "down")

    attempts = deliver_with_fallback(["first", "second", "third"], send)
    assert called == ["first", "second"]
    assert [a.ok for a in attempts] == [False, True]


def test_subscription_register_rotate_remove(tmp_path):
    store = SubscriptionStore(tmp_path)
    entry = store.register("builds", "https://x.test/hook", ["build"])
    assert entry["secret"]
    assert len(store.list()) == 1
    new_secret = store.rotate("builds")
    assert new_secret != entry["secret"]
    assert store.remove("builds") is True
    assert store.rotate("builds") is None


def test_troubleshooting_checklist():
    assert len(checklist("email")) >= 2
    assert "HTTPS" in " ".join(checklist("webhook"))
    assert checklist("unknown")
