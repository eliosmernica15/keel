"""X1.4 / X1.5 — selectable edit formats and fuzzy patch application.

Covers format detection, each supported edit format, fuzzy matching
(including whitespace/indentation tolerance, ambiguity and failure reporting),
line-ending preservation, unicode, large inputs, no-op edits and the
deterministic per-model format recommender.
"""

from __future__ import annotations

import pytest

from keel.edit_formats import (
    FORMAT_LINE_RANGE,
    FORMAT_SEARCH_REPLACE,
    FORMAT_UNIFIED_DIFF,
    FORMAT_WHOLE_FILE,
    EditParseError,
    FuzzyMatchError,
    apply_edit,
    detect_edit_format,
    fuzzy_replace,
    recommend_format,
    recommend_format_details,
)


# ---------------------------------------------------------------------------
# X1.4 — format detection and application
# ---------------------------------------------------------------------------


def test_detect_whole_file_is_default():
    assert detect_edit_format("just some text\nwith lines\n") == FORMAT_WHOLE_FILE
    assert detect_edit_format("") == FORMAT_WHOLE_FILE


def test_detect_search_replace_styles():
    aider = "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n"
    begin_patch = (
        "*** Begin Patch\n*** Update File: f.py\n@@ def f():\n"
        "-old\n+new\n*** End Patch\n"
    )
    custom = "<search>\nold\n</search>\n<replace>\nnew\n</replace>\n"
    angle = "<<< SEARCH >>>\nold\n<<< DIVIDER >>>\nnew\n<<< REPLACE >>>\n"
    for text in (aider, begin_patch, custom, angle):
        assert detect_edit_format(text) == FORMAT_SEARCH_REPLACE


def test_detect_unified_diff_and_line_range():
    diff = "--- a/f.py\n+++ b/f.py\n@@ -1,2 +1,2 @@\n-a\n+A\n b\n"
    assert detect_edit_format(diff) == FORMAT_UNIFIED_DIFF
    assert detect_edit_format("[lines 2-4]\nnew\n") == FORMAT_LINE_RANGE
    assert detect_edit_format("L7\nnew\n") == FORMAT_LINE_RANGE


def test_apply_whole_file_and_noop():
    original = "a\nb\n"
    assert apply_edit(original, "x\ny\n", FORMAT_WHOLE_FILE) == "x\ny\n"
    assert apply_edit(original, original, FORMAT_WHOLE_FILE) == original


def test_apply_aider_search_replace_single_and_multiple_blocks():
    original = "alpha\nbeta\ngamma\n"
    one = "<<<<<<< SEARCH\nbeta\n=======\nBETA\n>>>>>>> REPLACE\n"
    assert apply_edit(original, one) == "alpha\nBETA\ngamma\n"

    two = (
        "<<<<<<< SEARCH\nalpha\n=======\nA\n>>>>>>> REPLACE\n"
        "<<<<<<< SEARCH\ngamma\n=======\nG\n>>>>>>> REPLACE\n"
    )
    assert apply_edit(original, two) == "A\nbeta\nG\n"


def test_apply_begin_patch_with_context_and_section_header():
    original = "def f():\n    return 1\n"
    edit = (
        "*** Begin Patch\n*** Update File: f.py\n@@ def f():\n"
        " def f():\n-    return 1\n+    return 2\n*** End Patch\n"
    )
    assert apply_edit(original, edit) == "def f():\n    return 2\n"


def test_apply_custom_marker_search_replace():
    original = "alpha\nbeta\ngamma\n"
    xml = "<search>\nbeta\n</search>\n<replace>\nB\n</replace>\n"
    assert apply_edit(original, xml) == "alpha\nB\ngamma\n"

    angle = "<<< SEARCH >>>\ngamma\n<<< DIVIDER >>>\nG\n<<< REPLACE >>>\n"
    assert apply_edit(original, angle) == "alpha\nbeta\nG\n"


def test_apply_unified_diff_single_and_multiple_hunks():
    original = "a\nb\nc\n"
    diff = "--- a/f\n+++ b/f\n@@ -1,3 +1,3 @@\n a\n-b\n+B\n c\n"
    assert apply_edit(original, diff) == "a\nB\nc\n"

    original2 = "a\nb\nc\nd\n"
    diff2 = (
        "--- a/f\n+++ b/f\n"
        "@@ -1,2 +1,2 @@\n-a\n+A\n b\n"
        "@@ -4 +4 @@\n-d\n+D\n"
    )
    assert apply_edit(original2, diff2) == "A\nb\nc\nD\n"


def test_truncated_unified_diff_raises_typed_error():
    diff = "--- a/f\n+++ b/f\n@@ -1,5 +1,5 @@\n-a\n+A\n"
    with pytest.raises(EditParseError) as excinfo:
        apply_edit("a\nb\nc\n", diff)
    assert excinfo.value.code == "truncated_diff"
    assert excinfo.value.line == 3
    assert "expected" in excinfo.value.message
    assert excinfo.value.snippet


def test_apply_line_range_replace_single_line_and_out_of_range():
    original = "a\nb\nc\nd\n"
    assert apply_edit(original, "[lines 2-3]\nB\nC\n", FORMAT_LINE_RANGE) == "a\nB\nC\nd\n"
    assert apply_edit(original, "L4\nD\n", FORMAT_LINE_RANGE) == "a\nb\nc\nD\n"
    with pytest.raises(EditParseError) as excinfo:
        apply_edit(original, "[lines 9-10]\nnope\n", FORMAT_LINE_RANGE)
    assert excinfo.value.code == "out_of_range"


def test_invalid_format_is_rejected():
    with pytest.raises(EditParseError) as excinfo:
        apply_edit("a\n", "b\n", "not_a_format")
    assert excinfo.value.code == "unsupported_format"


# ---------------------------------------------------------------------------
# X1.5 — fuzzy matching
# ---------------------------------------------------------------------------


def test_fuzzy_replace_tolerates_trailing_whitespace():
    original = "a = 1   \nb = 2\n"
    result, info = fuzzy_replace(original, "a = 1", "a = 9")
    assert result == "a = 9\nb = 2\n"
    assert info.line == 1 and info.no_op is False
    assert info.strategy in {"rstrip", "collapsed", "indentless", "compact"}


def test_fuzzy_replace_tolerates_collapsed_whitespace():
    original = "call( a , b )\n"
    result, info = fuzzy_replace(original, "call(a, b)", "call(c, d)")
    assert result == "call(c, d)\n"
    assert info.similarity >= 0.8


def test_fuzzy_replace_handles_indentation_shift_and_reindents_new_lines():
    original = "def outer():\n    def inner():\n        return 1\n"
    old = "def inner():\n    return 1\n"
    new = "def inner():\n    return 2\n"
    result, info = fuzzy_replace(original, old, new)
    assert result == "def outer():\n    def inner():\n        return 2\n"
    assert info.line == 2
    assert info.similarity < 1.0  # indentation mismatch is penalised, not ignored


def test_fuzzy_replace_is_indentation_aware_when_disambiguating():
    original = "def top():\n    return 1\n\nclass C:\n        return 1\n"
    result, info = fuzzy_replace(original, "return 1", "return 9")
    assert info.line == 2
    assert result == "def top():\n    return 9\n\nclass C:\n        return 1\n"


def test_fuzzy_replace_refuses_ambiguous_matches():
    original = "x = 1\ny = 2\nx = 1\n"
    with pytest.raises(FuzzyMatchError) as excinfo:
        fuzzy_replace(original, "x = 1", "x = 9")
    err = excinfo.value
    assert err.code == "ambiguous_match"
    assert err.candidates == [1, 3]
    assert "x = 1" in err.snippet
    assert "Refusing" in err.to_model_message()
    assert original == "x = 1\ny = 2\nx = 1\n"  # never mutates the caller's input


def test_fuzzy_replace_no_match_reports_nearest_snippet_and_line():
    original = "alpha\nbeta\ngamma\n"
    with pytest.raises(FuzzyMatchError) as excinfo:
        fuzzy_replace(original, "completely different text", "x")
    err = excinfo.value
    assert err.code == "no_match"
    assert err.line is not None and err.line >= 1
    assert err.similarity < 0.8
    assert "beta" in err.snippet
    msg = err.to_model_message()
    assert f"line {err.line}" in msg
    assert "threshold" in msg


def test_fuzzy_replace_rejects_below_threshold_and_bad_threshold():
    with pytest.raises(FuzzyMatchError) as excinfo:
        fuzzy_replace("alpha\n", "alphabet", "x", threshold=0.99)
    assert excinfo.value.code == "no_match"

    with pytest.raises(FuzzyMatchError) as excinfo:
        fuzzy_replace("alpha\n", "alpha", "x", threshold=1.5)
    assert excinfo.value.code == "invalid_threshold"

    with pytest.raises(FuzzyMatchError) as excinfo:
        fuzzy_replace("alpha\n", "   \n", "x")
    assert excinfo.value.code == "empty_search"


def test_fuzzy_replace_preserves_crlf_and_lf():
    original = "a\r\nb\r\nc\r\n"
    assert fuzzy_replace(original, "b", "B")[0] == "a\r\nB\r\nc\r\n"
    assert fuzzy_replace(original, "b\r\n", "B")[0] == "a\r\nB\r\nc\r\n"
    lf = "a\nb\nc\n"
    assert fuzzy_replace(lf, "b", "B")[0] == "a\nB\nc\n"


def test_fuzzy_replace_unicode():
    original = "café ☕ naïve\nsecond 日本\n"
    result, info = fuzzy_replace(original, "café ☕ naïve", "café ☕ naïve!")
    assert result == "café ☕ naïve!\nsecond 日本\n"
    assert info.line == 1
    result2, _ = fuzzy_replace("naïve  ＝  café\n", "naïve = café", "NAIVE")
    assert result2 == "NAIVE\n"


def test_fuzzy_replace_large_file():
    size = 20000
    original = "".join(f"line_{i}\n" for i in range(size))
    result, info = fuzzy_replace(original, "line_19999", "LINE")
    assert result.endswith("LINE\n")
    assert info.line == size


def test_fuzzy_replace_no_op_is_exact_and_preserves_bytes():
    original = "a\r\nb\r\n"
    result, info = fuzzy_replace(original, "b", "b")
    assert result == original
    assert info.no_op is True
    assert info.similarity == 1.0


def test_fuzzy_replace_preserves_absent_final_newline():
    """M3: a last-line edit must not invent a trailing separator."""
    original = "a\nb\nc"
    assert fuzzy_replace(original, "c", "C")[0] == "a\nb\nC"
    crlf = "a\r\nb\r\nc"
    assert fuzzy_replace(crlf, "c", "C")[0] == "a\r\nb\r\nC"
    assert fuzzy_replace("abc", "abc", "ABC")[0] == "ABC"


def test_fuzzy_compact_never_substitutes_semantically_different_lines():
    """H3 regression: whitespace removed inside literals/numbers is not a match."""
    cases = [
        ('x = "ab"\n', 'x = "a b"', 'x = "cd"'),
        ('url = "https://example.com"\n', 'url = "https://example. com"', 'url = "SAFE"'),
        ('msg = "hello world"\n', 'msg = "helloworld"', 'msg = "X"'),
        ('return 12\n', 'return 1 2', 'return 99'),
    ]
    for original, old, new in cases:
        pristine = (original, old, new)
        with pytest.raises(FuzzyMatchError) as excinfo:
            fuzzy_replace(original, old, new)
        assert excinfo.value.code == "no_match", (original, old)
        assert (original, old, new) == pristine  # inputs are never mutated


def test_fuzzy_threshold_one_cannot_be_defeated_by_compact():
    """H3 regression: threshold=1.0 is strict; compact is disabled there."""
    for original, old, new in (
        ('x = "ab"\n', 'x = "a b"', 'x = "cd"'),
        ('return 12\n', 'return 1 2', 'return 99'),
        ('call( a , b )\n', 'call(a, b)', 'call(c, d)'),
    ):
        with pytest.raises(FuzzyMatchError) as excinfo:
            fuzzy_replace(original, old, new, threshold=1.0)
        assert excinfo.value.code == "no_match", (original, old)

    # Exact equality still works at threshold=1.0.
    result, info = fuzzy_replace("x = 1\n", "x = 1", "x = 2", threshold=1.0)
    assert result == "x = 2\n"
    assert info.strategy == "exact" and info.similarity == 1.0


def test_apply_edit_chained_blocks_adjust_anchors():
    original = "a\nb\na\nb\n"
    edit = (
        "--- a/f\n+++ b/f\n"
        "@@ -1,1 +1,2 @@\n-a\n+A\n+EXTRA\n"
        "@@ -3,1 +4,1 @@\n-a\n+Z\n"
    )
    assert apply_edit(original, edit) == "A\nEXTRA\nb\nZ\nb\n"


# ---------------------------------------------------------------------------
# Deterministic per-model format recommendation
# ---------------------------------------------------------------------------


def test_recommend_format_uses_local_eval_stats():
    stats = {
        "models": {
            "model-a": {
                "formats": {
                    "search_replace": {"successes": 4, "attempts": 5},
                    "unified_diff": {"successes": 9, "attempts": 10},
                    "whole_file": 0.5,
                }
            }
        }
    }
    assert recommend_format("model-a", stats) == FORMAT_UNIFIED_DIFF
    assert recommend_format("unknown-model", stats) == FORMAT_SEARCH_REPLACE


def test_recommend_format_is_deterministic_and_tie_breaks_by_preference():
    stats = {"m": {"whole_file": 0.9, "search_replace": 0.9, "unified_diff": 0.9}}
    for _ in range(5):
        assert recommend_format("m", stats) == FORMAT_SEARCH_REPLACE
    details = recommend_format_details("m", stats)
    assert details.format == FORMAT_SEARCH_REPLACE
    assert details.source == "eval"
    assert set(details.scores) >= {
        FORMAT_WHOLE_FILE,
        FORMAT_SEARCH_REPLACE,
        FORMAT_UNIFIED_DIFF,
    }


def test_recommend_format_handles_missing_and_malformed_stats():
    assert recommend_format("m", None) == FORMAT_SEARCH_REPLACE
    assert recommend_format("m", {}) == FORMAT_SEARCH_REPLACE
    assert recommend_format("m", {"m": {"not_a_format": 0.99}}) == FORMAT_SEARCH_REPLACE
    stats = {"m": {"line_range": {"success_rate": 0.2}, "unified_diff": 0.7}}
    assert recommend_format("m", stats) == FORMAT_UNIFIED_DIFF
