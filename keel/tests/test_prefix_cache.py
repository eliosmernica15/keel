"""B1.4/B1.10 — prefix cache and speculative decoding toggle."""

from __future__ import annotations

from keel.prefix_cache import PrefixCache, speculative_enabled


def test_longest_prefix():
    cache = PrefixCache()
    cache.store("the quick brown fox jumps")
    cache.store("the quick red fox")
    hit = cache.longest_prefix("the quick brown cat")
    assert hit.text == "the quick brown "
    assert hit.length == len("the quick brown ")


def test_store_eviction_and_clear():
    cache = PrefixCache(max_entries=1)
    cache.store("first long prompt")
    cache.store("second prompt")
    assert cache.longest_prefix("first").length == 0
    cache.clear()
    assert cache.longest_prefix("second").length == 0


def test_speculative_opt_in(monkeypatch):
    monkeypatch.setenv("KEEL_SPECULATIVE_DECODING", "0")
    assert speculative_enabled() is False
    monkeypatch.setenv("KEEL_SPECULATIVE_DECODING", "1")
    assert speculative_enabled() is True
