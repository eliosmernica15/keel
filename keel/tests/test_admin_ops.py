"""A2.4/A2.6/A2.7/A2.9 — admin operations."""

from __future__ import annotations

from keel.admin_ops import (CONFIG_REFERENCE, DEFAULT_TUNABLES, IdleSuspend,
                            daily_digest)


def test_config_reference_covers_settings():
    assert "KEEL_EGRESS_ALLOWLIST" in CONFIG_REFERENCE
    assert all(isinstance(v, tuple) and len(v) == 2
               for v in CONFIG_REFERENCE.values())


def test_idle_suspend():
    idle = IdleSuspend(timeout_s=10)
    idle.touch(now=0)
    assert idle.maybe_suspend(now=5) is False
    assert idle.maybe_suspend(now=11) is True
    idle.touch(now=12)
    assert idle.suspended is False


def test_digest():
    digest = daily_digest([{"kind": "user"}, {"kind": "user"},
                           {"subtype": "success"}])
    assert digest["counts"]["user"] == 2
    assert len(digest["date"]) == 10
    assert DEFAULT_TUNABLES["memory_half_life_days"] == 30
