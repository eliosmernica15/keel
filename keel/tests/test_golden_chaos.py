"""B7.2 — golden-file and chaos test helpers."""

from __future__ import annotations

import pytest

from keel.golden import (ChaosFault, check_golden, digest, golden_diff,
                         maybe_inject, normalise)


def test_normalise_and_digest():
    assert normalise("  a  \n b \n") == "a\n b"
    assert digest("a\n b") == digest("  a  \n b \n")


def test_golden_update_and_check(tmp_path):
    path = tmp_path / "prompt.golden"
    assert check_golden("hello\nworld", path) is False
    assert check_golden("hello\nworld", path, update=True) is True
    assert check_golden("hello\nworld", path) is True
    assert check_golden("hello\nthere", path) is False
    assert "hello" in golden_diff("hello\nthere", path)


def test_chaos_injection():
    maybe_inject(0, 3)  # disabled
    maybe_inject(2, 1)  # not yet
    with pytest.raises(ChaosFault):
        maybe_inject(2, 2)
