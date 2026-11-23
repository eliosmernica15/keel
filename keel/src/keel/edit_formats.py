"""Selectable edit formats (X1.4) and fuzzy patch application (X1.5).

Stdlib only. This module is deliberately self-contained: it operates on text,
never on the filesystem, so a router can choose a dialect for a model and an
applier can convert that dialect's output into new file content without any
side effects.

Design guarantees
-----------------
* ``detect_edit_format`` is a conservative heuristic; plain text is always
  treated as a whole-file replacement unless structured markers are present.
* ``apply_edit`` honours an explicit format over detection and raises a typed
  :class:`EditParseError` for malformed/structurally invalid patches.
* ``fuzzy_replace`` uses a strict search window (same number of lines), a
  similarity threshold, an indentation penalty and an ambiguity guard. It
  never guesses between equally good candidates and never mutates its inputs.
* All line-ending handling is lossless: replacements inherit the separators of
  the region they replace (CRLF, LF or CR), and no-op edits return the original
  string byte-for-byte.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Mapping, Sequence

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

FORMAT_WHOLE_FILE = "whole_file"
FORMAT_SEARCH_REPLACE = "search_replace"
FORMAT_UNIFIED_DIFF = "unified_diff"
FORMAT_LINE_RANGE = "line_range"

SUPPORTED_FORMATS: tuple[str, ...] = (
    FORMAT_WHOLE_FILE,
    FORMAT_SEARCH_REPLACE,
    FORMAT_UNIFIED_DIFF,
    FORMAT_LINE_RANGE,
)

DEFAULT_FORMAT = FORMAT_SEARCH_REPLACE
DEFAULT_THRESHOLD = 0.8

# Deterministic tie-break order used by the recommender (narrower edits first;
# whole-file rewrites last because they are the most expensive to emit).
_FORMAT_PREFERENCE: tuple[str, ...] = (
    FORMAT_SEARCH_REPLACE,
    FORMAT_UNIFIED_DIFF,
    FORMAT_LINE_RANGE,
    FORMAT_WHOLE_FILE,
)

_FORMAT_ALIASES: dict[str, str] = {
    "whole_file": FORMAT_WHOLE_FILE,
    "whole-file": FORMAT_WHOLE_FILE,
    "whole": FORMAT_WHOLE_FILE,
    "file": FORMAT_WHOLE_FILE,
    "write": FORMAT_WHOLE_FILE,
    "search_replace": FORMAT_SEARCH_REPLACE,
    "search-replace": FORMAT_SEARCH_REPLACE,
    "search/replace": FORMAT_SEARCH_REPLACE,
    "searchreplace": FORMAT_SEARCH_REPLACE,
    "sr": FORMAT_SEARCH_REPLACE,
    "edit": FORMAT_SEARCH_REPLACE,
    "aider": FORMAT_SEARCH_REPLACE,
    "patch": FORMAT_SEARCH_REPLACE,
    "begin_patch": FORMAT_SEARCH_REPLACE,
    "unified_diff": FORMAT_UNIFIED_DIFF,
    "unified-diff": FORMAT_UNIFIED_DIFF,
    "unified": FORMAT_UNIFIED_DIFF,
    "udiff": FORMAT_UNIFIED_DIFF,
    "diff": FORMAT_UNIFIED_DIFF,
    "line_range": FORMAT_LINE_RANGE,
    "line-range": FORMAT_LINE_RANGE,
    "lines": FORMAT_LINE_RANGE,
    "range": FORMAT_LINE_RANGE,
}

_EPS = 1e-9
_LEVELS: tuple[str, ...] = ("exact", "rstrip", "collapsed", "indentless", "compact")


# ---------------------------------------------------------------------------
# Typed errors and result records
# ---------------------------------------------------------------------------


class EditFormatError(ValueError):
    """Base class for every structured edit failure.

    ``code`` is machine-readable; ``line``/``snippet``/``similarity``/
    ``candidates`` carry the evidence a model needs to issue a corrected edit.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        line: int | None = None,
        snippet: str | None = None,
        similarity: float | None = None,
        candidates: Sequence[int] = (),
    ) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.line = line
        self.snippet = snippet
        self.similarity = similarity
        self.candidates = list(candidates)

    def to_model_message(self) -> str:
        """Render a precise, model-facing failure message."""
        parts = [f"Edit failed ({self.code}): {self.message}"]
        if self.line is not None:
            parts.append(f"Nearest location: line {self.line}.")
        if self.candidates:
            parts.append("Equally good candidates: " + ", ".join(str(c) for c in self.candidates))
        if self.similarity is not None:
            parts.append(f"Best similarity: {self.similarity:.3f}.")
        if self.snippet:
            parts.append("Nearest match:\n" + self.snippet)
        return "\n".join(parts)


class EditParseError(EditFormatError):
    """The edit text is malformed or structurally inconsistent."""


class FuzzyMatchError(EditFormatError):
    """No unique, sufficiently similar match could be located."""


@dataclass(frozen=True)
class MatchInfo:
    """Where and how a fuzzy replacement was applied."""

    start: int  # 0-based first replaced line
    end: int  # 0-based line after the last replaced line
    line: int  # 1-based first replaced line (human/model facing)
    similarity: float
    strategy: str  # one of exact/rstrip/collapsed/indentless/compact
    no_op: bool = False
    indent_delta: int = 0
    anchor: int | None = None


@dataclass(frozen=True)
class FormatDetection:
    format: str
    confidence: float
    reason: str
    markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class FormatRecommendation:
    format: str
    source: str  # "eval" when local stats decided, "default" otherwise
    scores: dict[str, float] = field(default_factory=dict)
    model_id: str = ""


@dataclass(frozen=True)
class _Block:
    old: str
    new: str
    anchor: int | None = None
    mode: str = "replace"  # "replace" | "whole"


# ---------------------------------------------------------------------------
# Line-ending-safe text primitives
# ---------------------------------------------------------------------------

_NEWLINE_RE = re.compile(r"(\r\n|\r|\n)")
_WS_RE = re.compile(r"\s+")


def _split_lines(text: str) -> list[tuple[str, str]]:
    """Split into ``(body, separator)`` pairs without losing line endings."""
    parts = _NEWLINE_RE.split(text)
    lines: list[tuple[str, str]] = []
    for i in range(0, len(parts), 2):
        body = parts[i]
        sep = parts[i + 1] if i + 1 < len(parts) else ""
        if body or sep:
            lines.append((body, sep))
    return lines


def _join(lines: Sequence[tuple[str, str]], default: str = "\n") -> str:
    out: list[str] = []
    last = len(lines) - 1
    for idx, (body, sep) in enumerate(lines):
        out.append(body)
        if idx < last:
            out.append(sep or default)
        elif sep:
            out.append(sep)
    return "".join(out)


def _bodies(lines: Sequence[tuple[str, str]]) -> list[str]:
    return [body for body, _ in lines]


def _line_texts(text: str) -> list[str]:
    return _bodies(_split_lines(text))


def _dominant_sep(lines: Sequence[tuple[str, str]]) -> str:
    counts = {"\r\n": 0, "\n": 0, "\r": 0}
    for _, sep in lines:
        if sep in counts:
            counts[sep] += 1
    if not any(counts.values()):
        return "\n"
    return max(("\r\n", "\n", "\r"), key=lambda s: counts[s])


def _indent_width(body: str) -> int:
    prefix = re.match(r"[ \t]*", body)
    return len(prefix.group(0).expandtabs(4)) if prefix else 0


def _first_nonempty_width(bodies: Sequence[str]) -> int | None:
    for body in bodies:
        if body.strip():
            return _indent_width(body)
    return None


def _indent_delta(old_bodies: Sequence[str], window_bodies: Sequence[str]) -> int:
    old = _first_nonempty_width(old_bodies)
    window = _first_nonempty_width(window_bodies)
    if old is None or window is None:
        return 0
    return window - old


def _adapt_indentation(
    new_bodies: Sequence[str], old_bodies: Sequence[str], window_bodies: Sequence[str]
) -> list[str]:
    """Carry an indentation shift from the matched region into new lines."""
    delta = _indent_delta(old_bodies, window_bodies)
    if delta == 0:
        return list(new_bodies)
    out: list[str] = []
    for line in new_bodies:
        if not line.strip():
            out.append(line)
        elif delta > 0:
            out.append(" " * delta + line)
        else:
            available = len(line) - len(line.lstrip(" \t"))
            out.append(line[min(-delta, available) :] if available else line)
    return out


def _snippet(
    all_bodies: Sequence[str], start: int, end: int, radius: int = 1
) -> str:
    lo = max(0, start - radius)
    hi = min(len(all_bodies), max(end, start + 1) + radius)
    rows: list[str] = []
    if lo > 0:
        rows.append("     ...")
    for idx in range(lo, hi):
        rows.append(f"{idx + 1:>5} | {all_bodies[idx]}")
    if hi < len(all_bodies):
        rows.append("     ...")
    return "\n".join(rows)


def _replace_span(
    lines: Sequence[tuple[str, str]],
    start: int,
    end: int,
    old_bodies: Sequence[str],
    new_bodies: Sequence[str],
) -> str:
    """Replace ``lines[start:end]`` while preserving local line-ending style."""
    original = _join(lines)
    window = _bodies(lines[start:end])
    if list(old_bodies) == list(new_bodies):
        return original  # exact no-op: preserve the original bytes

    adapted = _adapt_indentation(new_bodies, old_bodies, window)
    target_sep = _dominant_sep(lines)
    if start < len(lines) and lines[start][1]:
        target_sep = lines[start][1]
    if end > 0 and end <= len(lines):
        trailing_sep = lines[end - 1][1] or target_sep
    else:
        trailing_sep = target_sep

    replaced: list[tuple[str, str]] = [
        (body, target_sep if idx < len(adapted) - 1 else trailing_sep)
        for idx, body in enumerate(adapted)
    ]
    result = list(lines[:start]) + replaced + list(lines[end:])
    if not adapted and 0 < start < len(lines):
        prev_body = result[start - 1][0]
        result[start - 1] = (prev_body, trailing_sep)
    return _join(result)


# ---------------------------------------------------------------------------
# X1.4 — syntax recognizers
# ---------------------------------------------------------------------------

_BEGIN_RE = re.compile(r"^\*\*\* Begin Patch\s*$")
_END_PATCH_RE = re.compile(r"^\*\*\* End Patch\s*$")
_UPDATE_FILE_RE = re.compile(r"^\*\*\* Update File:\s*(.*)$")
_ADD_FILE_RE = re.compile(r"^\*\*\* Add File:\s*(.*)$")
_DELETE_FILE_RE = re.compile(r"^\*\*\* Delete File:\s*(.*)$")
_SECTION_RE = re.compile(r"^@@\s*(.*)$")
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")

_AIDER_START = re.compile(r"^<{7}\s*(?:SEARCH|FIND|OLD)\b.*$", re.I)
_AIDER_SEP = re.compile(r"^={7,}\s*$")
_AIDER_END = re.compile(r"^>{7}\s*(?:REPLACE|NEW)\b.*$", re.I)
_ANGLE_START = re.compile(r"^<<<\s*(?:SEARCH|FIND|OLD)\s*>>>$", re.I)
_ANGLE_SEP = re.compile(r"^(?:<<<\s*(?:DIVIDER|SPLIT|SEP)\s*>>>|={3,})$", re.I)
_ANGLE_END = re.compile(r"^<<<\s*(?:REPLACE|NEW)\s*>>>$", re.I)
_XML_START = re.compile(r"^<\s*(?:search|old)\s*>$", re.I)
_XML_MID = re.compile(r"^<\s*/\s*(?:search|old)\s*>$", re.I)
_XML_REPLACE = re.compile(r"^<\s*replace\s*>$", re.I)
_XML_END = re.compile(r"^<\s*/\s*replace\s*>$", re.I)

_LINE_RANGE_RE = re.compile(
    r"^\s*[\[\(]?\s*(?:lines?|L)\s*(\d+)\s*(?:-|–|—|to|through|\.\.)\s*"
    r"(?:lines?\s*)?(\d+)\s*[\]\)]?:?\s*$",
    re.I,
)
_SINGLE_LINE_RE = re.compile(
    r"^\s*[\[\(]?\s*(?:lines?|L)\s*(\d+)\s*[\]\)]?:?\s*$", re.I
)


def _has_begin_patch(text: str) -> bool:
    return any(_BEGIN_RE.match(line) for line in _line_texts(text))


def _has_search_markers(text: str) -> bool:
    lines = _line_texts(text)
    return any(
        marker.match(line)
        for line in lines
        for marker in (
            _AIDER_START,
            _ANGLE_START,
            _XML_START,
        )
    )


def _has_hunk(text: str) -> bool:
    return any(_HUNK_RE.match(line) for line in _line_texts(text))


def _has_line_range_header(text: str) -> bool:
    return any(
        _LINE_RANGE_RE.match(line) or _SINGLE_LINE_RE.match(line)
        for line in _line_texts(text)
    )


def detect_edit_format_details(text: str) -> FormatDetection:
    """Detect an edit dialect with the evidence used to make the decision."""
    if _has_begin_patch(text):
        return FormatDetection(
            FORMAT_SEARCH_REPLACE, 0.99, "*** Begin Patch block", ("begin_patch",)
        )
    if _has_search_markers(text):
        return FormatDetection(
            FORMAT_SEARCH_REPLACE,
            0.98,
            "explicit search/replace markers",
            ("search_replace_markers",),
        )
    hunks = sum(1 for line in _line_texts(text) if _HUNK_RE.match(line))
    if hunks:
        return FormatDetection(
            FORMAT_UNIFIED_DIFF,
            0.97,
            f"{hunks} unified-diff hunk header(s)",
            ("hunk_header",),
        )
    if _has_line_range_header(text):
        return FormatDetection(
            FORMAT_LINE_RANGE, 0.90, "explicit line-range header", ("line_range",)
        )
    return FormatDetection(
        FORMAT_WHOLE_FILE, 0.50, "no structured edit markers detected", ()
    )


def detect_edit_format(text: str) -> str:
    """Return the canonical format id for ``edit_text``."""
    return detect_edit_format_details(text).format


def _coerce_format(fmt: str | None) -> str | None:
    if fmt is None or (isinstance(fmt, str) and fmt.strip().lower() == "auto"):
        return None
    if isinstance(fmt, str):
        key = fmt.strip().lower().replace(" ", "_")
        if key in _FORMAT_ALIASES:
            return _FORMAT_ALIASES[key]
        if key in SUPPORTED_FORMATS:
            return key
    raise EditParseError(
        "unsupported_format",
        f"Unknown edit format {fmt!r}; supported: {', '.join(SUPPORTED_FORMATS)}",
    )


# ---------------------------------------------------------------------------
# X1.5 — fuzzy matching core
# ---------------------------------------------------------------------------


def _check_threshold(threshold: float) -> None:
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise FuzzyMatchError(
            "invalid_threshold", f"Threshold must be a number, got {threshold!r}"
        )
    if not 0.0 < float(threshold) <= 1.0:
        raise FuzzyMatchError(
            "invalid_threshold",
            f"Threshold must be in (0, 1], got {threshold!r}",
        )


def _normalize(body: str, level: str) -> str:
    if level == "exact":
        return body
    if level == "rstrip":
        return body.rstrip()
    if level == "collapsed":
        return _WS_RE.sub(" ", body).strip()
    if level == "indentless":
        return _WS_RE.sub(" ", body.lstrip(" \t")).strip()
    return _WS_RE.sub("", body)  # compact


def _similarity(old_norm: str, window_norm: str) -> float:
    if old_norm == window_norm:
        return 1.0
    matcher = SequenceMatcher(None, old_norm, window_norm, autojunk=False)
    if matcher.real_quick_ratio() < 0.25 or matcher.quick_ratio() < 0.25:
        return 0.0
    return matcher.ratio()


def _no_match_error(
    old_bodies: Sequence[str],
    all_bodies: Sequence[str],
    idx: int,
    width: int,
    score: float,
    threshold: float,
) -> FuzzyMatchError:
    line = min(idx + 1, len(all_bodies)) if all_bodies else 1
    snippet = _snippet(all_bodies, idx, idx + width)
    return FuzzyMatchError(
        "no_match",
        f"No sufficiently similar match for the {len(old_bodies)}-line search block "
        f"(best similarity {score:.3f}, threshold {threshold:.3f}).",
        line=line,
        snippet=snippet,
        similarity=score,
    )


def _fuzzy_replace_lines(
    lines: Sequence[tuple[str, str]],
    old_text: str,
    new_text: str,
    threshold: float,
    anchor: int | None = None,
) -> tuple[str, MatchInfo]:
    old_bodies = _bodies(_split_lines(old_text))
    new_bodies = _bodies(_split_lines(new_text))
    if not any(body.strip() for body in old_bodies):
        raise FuzzyMatchError(
            "empty_search",
            "The search text is empty or whitespace-only; refusing to guess a location.",
        )

    n = len(lines)
    width = len(old_bodies)
    all_bodies = _bodies(lines)
    if width > n or n == 0:
        raise _no_match_error(old_bodies, all_bodies, 0, max(1, min(width, n)), 0.0, threshold)

    windows: list[tuple[list[str], int, tuple[str, ...]]] = []
    for i in range(n - width + 1):
        window = all_bodies[i : i + width]
        penalty = min(0.20, 0.03 * abs(_indent_delta(old_bodies, window)))
        norms = tuple(
            "\n".join(_normalize(body, level) for body in window) for level in _LEVELS
        )
        windows.append((window, penalty, norms))

    old_norms = {
        level: "\n".join(_normalize(body, level) for body in old_bodies)
        for level in _LEVELS
    }
    best: dict[int, tuple[float, str]] = {}
    for level_index, level in enumerate(_LEVELS):
        old_norm = old_norms[level]
        for i, (_window, penalty, norms) in enumerate(windows):
            score = _similarity(old_norm, norms[level_index]) - penalty
            if i not in best or score > best[i][0] + _EPS:
                best[i] = (score, level)

    eligible = [
        (score, i, level)
        for i, (score, level) in best.items()
        if score >= threshold - _EPS
    ]
    if not eligible:
        nearest_i = max(
            best,
            key=lambda i: (
                best[i][0],
                -abs((i + 1) - anchor) if anchor is not None else 0,
                -i,
            ),
        )
        raise _no_match_error(
            old_bodies, all_bodies, nearest_i, width, best[nearest_i][0], threshold
        )

    best_score = max(score for score, _, _ in eligible)
    tied = [entry for entry in eligible if abs(entry[0] - best_score) <= _EPS]
    if anchor is not None and len(tied) > 1:
        min_distance = min(abs((i + 1) - anchor) for _, i, _ in tied)
        narrowed = [
            entry for entry in tied if abs((entry[1] + 1) - anchor) == min_distance
        ]
        if narrowed:
            tied = narrowed

    if len(tied) > 1:
        candidates = sorted(i + 1 for _, i, _ in tied)
        first = tied[0][1]
        raise FuzzyMatchError(
            "ambiguous_match",
            f"Refusing to apply an ambiguous edit: {len(candidates)} equally good "
            f"matches at lines {', '.join(str(c) for c in candidates)}.",
            line=candidates[0],
            snippet=_snippet(all_bodies, first, first + width),
            similarity=best_score,
            candidates=candidates,
        )

    score, idx, level = tied[0]
    window = windows[idx][0]
    result = _replace_span(lines, idx, idx + width, old_bodies, new_bodies)
    info = MatchInfo(
        start=idx,
        end=idx + width,
        line=idx + 1,
        similarity=score,
        strategy=level,
        no_op=list(old_bodies) == list(new_bodies),
        indent_delta=_indent_delta(old_bodies, window),
        anchor=anchor,
    )
    return result, info


def fuzzy_replace(
    original: str,
    old: str,
    new: str,
    threshold: float = DEFAULT_THRESHOLD,
    *,
    anchor: int | None = None,
) -> tuple[str, MatchInfo]:
    """Fuzzy-replace ``old`` with ``new`` inside ``original``.

    Returns ``(new_content, MatchInfo)``. Raises :class:`FuzzyMatchError` when
    the best candidate is below ``threshold``, when ``old`` is empty, or when
    two or more candidates are equally good (ambiguity guard). ``anchor`` is a
    optional 1-based hint used only to disambiguate otherwise equal candidates.
    """
    _check_threshold(threshold)
    lines = _split_lines(original)
    return _fuzzy_replace_lines(lines, old, new, threshold, anchor)


# ---------------------------------------------------------------------------
# X1.4 — patch parsers
# ---------------------------------------------------------------------------


def _parse_unified_diff(text: str) -> list[_Block]:
    lines = _line_texts(text)
    blocks: list[_Block] = []
    i = 0
    while i < len(lines):
        header = _HUNK_RE.match(lines[i])
        if not header:
            i += 1
            continue
        header_index = i
        old_start = int(header.group(1))
        old_count = int(header.group(2)) if header.group(2) is not None else 1
        new_count = int(header.group(4)) if header.group(4) is not None else 1
        i += 1
        body: list[str] = []
        while i < len(lines):
            line = lines[i]
            if _HUNK_RE.match(line) or line.startswith("diff --git") or line.startswith("*** "):
                break
            body.append(line)
            i += 1

        old_lines: list[str] = []
        new_lines: list[str] = []
        for line in body:
            if line.startswith("\\ No newline"):
                continue
            if line.startswith(" "):
                old_lines.append(line[1:])
                new_lines.append(line[1:])
            elif line.startswith("-"):
                old_lines.append(line[1:])
            elif line.startswith("+"):
                new_lines.append(line[1:])
            elif line == "":
                old_lines.append("")
                new_lines.append("")
            else:
                raise EditParseError(
                    "invalid_diff_line",
                    f"Unrecognised unified-diff line: {line!r}",
                    line=header_index + 1 + len(old_lines) + len(new_lines),
                    snippet="\n".join(body[:6]),
                )

        if len(old_lines) != old_count or len(new_lines) != new_count:
            snippet = "\n".join(lines[header_index : header_index + 7])
            raise EditParseError(
                "truncated_diff",
                f"Hunk at line {header_index + 1} expected {old_count} old / "
                f"{new_count} new lines but contains {len(old_lines)} / "
                f"{len(new_lines)}; the diff may be truncated.",
                line=header_index + 1,
                snippet=snippet,
            )
        blocks.append(_Block("\n".join(old_lines), "\n".join(new_lines), old_start))
    if not blocks:
        raise EditParseError("no_hunks", "No unified-diff hunk header (@@ ...) was found.")
    return blocks


def _find_anchor(all_bodies: Sequence[str], header: str) -> int | None:
    needle = header.strip()
    if not needle:
        return None
    for idx, body in enumerate(all_bodies):
        if body.rstrip() == needle:
            return idx + 1
    return None


def _parse_begin_patch(text: str) -> list[_Block]:
    lines = _line_texts(text)
    blocks: list[_Block] = []
    if not any(_BEGIN_RE.match(line) for line in lines):
        raise EditParseError("no_begin_patch", "Missing *** Begin Patch marker.")

    i = next(idx for idx, line in enumerate(lines) if _BEGIN_RE.match(line)) + 1
    file_header_res = (_UPDATE_FILE_RE, _ADD_FILE_RE, _DELETE_FILE_RE)
    while i < len(lines) and not _END_PATCH_RE.match(lines[i]):
        matched = None
        kind = "update"
        for pattern in file_header_res:
            m = pattern.match(lines[i])
            if m:
                matched = m
                kind = (
                    "update"
                    if pattern is _UPDATE_FILE_RE
                    else "add"
                    if pattern is _ADD_FILE_RE
                    else "delete"
                )
                break
        if not matched:
            i += 1
            continue
        i += 1
        sections: list[tuple[str, list[str]]] = []
        current_header = ""
        current_body: list[str] = []
        while i < len(lines) and not _END_PATCH_RE.match(lines[i]):
            if any(pattern.match(lines[i]) for pattern in file_header_res):
                break
            section = _SECTION_RE.match(lines[i])
            if section:
                if current_body or current_header:
                    sections.append((current_header, current_body))
                current_header = section.group(1).strip()
                current_body = []
                i += 1
                continue
            current_body.append(lines[i])
            i += 1
        if current_body or current_header:
            sections.append((current_header, current_body))

        for header, body in sections:
            old_lines: list[str] = []
            new_lines: list[str] = []
            for line in body:
                if line.startswith("\\ No newline"):
                    continue
                if line.startswith(" "):
                    old_lines.append(line[1:])
                    new_lines.append(line[1:])
                elif line.startswith("-"):
                    old_lines.append(line[1:])
                elif line.startswith("+"):
                    new_lines.append(line[1:])
                elif line == "":
                    old_lines.append("")
                    new_lines.append("")
                else:
                    old_lines.append(line)
                    new_lines.append(line)
            if kind == "add":
                blocks.append(_Block("", "\n".join(new_lines), mode="whole"))
            elif kind == "delete":
                blocks.append(_Block("\n".join(old_lines), "", mode="whole"))
            else:
                blocks.append(
                    _Block(
                        "\n".join(old_lines),
                        "\n".join(new_lines),
                        _find_anchor(_line_texts(text), header),
                    )
                )
    if not blocks:
        raise EditParseError(
            "no_patch_sections", "*** Begin Patch block contained no file changes."
        )
    return blocks


def _parse_search_replace(text: str) -> list[_Block]:
    lines = _line_texts(text)
    blocks: list[_Block] = []
    i = 0
    starts = (_AIDER_START, _ANGLE_START)
    while i < len(lines):
        line = lines[i]
        if any(pattern.match(line) for pattern in starts):
            sep = _AIDER_SEP if _AIDER_START.match(line) else _ANGLE_SEP
            end = _AIDER_END if _AIDER_START.match(line) else _ANGLE_END
            old_lines: list[str] = []
            j = i + 1
            while j < len(lines) and not sep.match(lines[j]):
                old_lines.append(lines[j])
                j += 1
            if j >= len(lines):
                raise EditParseError(
                    "unterminated_search_block",
                    "Search/replace block is missing its divider marker.",
                    line=i + 1,
                    snippet="\n".join(lines[i : i + 5]),
                )
            new_lines: list[str] = []
            j += 1
            while j < len(lines) and not end.match(lines[j]) and not any(
                pattern.match(lines[j]) for pattern in starts
            ):
                new_lines.append(lines[j])
                j += 1
            if j >= len(lines) or not end.match(lines[j]):
                raise EditParseError(
                    "unterminated_search_block",
                    "Search/replace block is missing its REPLACE marker.",
                    line=i + 1,
                    snippet="\n".join(lines[i : i + 6]),
                )
            blocks.append(_Block("\n".join(old_lines), "\n".join(new_lines)))
            i = j + 1
            continue
        if _XML_START.match(line):
            old_lines = []
            j = i + 1
            while j < len(lines) and not _XML_MID.match(lines[j]):
                old_lines.append(lines[j])
                j += 1
            if j >= len(lines):
                raise EditParseError(
                    "unterminated_search_block",
                    "Custom <search> block is missing </search>.",
                    line=i + 1,
                    snippet="\n".join(lines[i : i + 5]),
                )
            j += 1
            if j >= len(lines) or not _XML_REPLACE.match(lines[j]):
                raise EditParseError(
                    "unterminated_search_block",
                    "Custom search block is missing <replace>.",
                    line=i + 1,
                    snippet="\n".join(lines[i : i + 5]),
                )
            new_lines = []
            j += 1
            while j < len(lines) and not _XML_END.match(lines[j]):
                new_lines.append(lines[j])
                j += 1
            if j >= len(lines):
                raise EditParseError(
                    "unterminated_search_block",
                    "Custom <replace> block is missing </replace>.",
                    line=i + 1,
                    snippet="\n".join(lines[i : i + 5]),
                )
            blocks.append(_Block("\n".join(old_lines), "\n".join(new_lines)))
            i = j + 1
            continue
        i += 1
    if not blocks:
        raise EditParseError(
            "no_search_blocks", "No search/replace markers were found in the edit text."
        )
    return blocks


def _parse_line_range(text: str, original_lines: Sequence[tuple[str, str]]) -> tuple[int, int, str]:
    lines = _line_texts(text)
    idx = next((i for i, line in enumerate(lines) if line.strip()), None)
    if idx is None:
        raise EditParseError("invalid_line_range_header", "Line-range edit is empty.")
    header = lines[idx]
    single = _SINGLE_LINE_RE.match(header)
    span = _LINE_RANGE_RE.match(header)
    if not single and not span:
        raise EditParseError(
            "invalid_line_range_header",
            f"Expected a header such as '[lines 3-5]' or 'L7', got {header!r}.",
            line=idx + 1,
            snippet=header,
        )
    if single:
        start = end = int(single.group(1))
    else:
        start, end = int(span.group(1)), int(span.group(2))
    count = len(original_lines)
    if start < 1 or start > count + 1 or end < start:
        raise EditParseError(
            "out_of_range",
            f"Line range {start}-{end} is outside the file ({count} lines).",
            line=idx + 1,
            snippet=header,
        )
    start0 = min(start - 1, count)
    end0 = min(max(end, start), count)
    if end0 < start0:
        end0 = start0
    return start0, end0, "\n".join(lines[idx + 1 :])


# ---------------------------------------------------------------------------
# X1.4 — application
# ---------------------------------------------------------------------------


def _apply_blocks(original: str, blocks: Sequence[_Block], threshold: float) -> str:
    lines = _split_lines(original)
    for block in blocks:
        if block.mode == "whole":
            new_bodies = _bodies(_split_lines(block.new))
            text = _replace_span(lines, 0, len(lines), [], new_bodies)
        elif not any(body.strip() for body in _bodies(_split_lines(block.old))):
            # Pure insertion (e.g. an all-'+' diff hunk) has no search text.
            pos = min(max((block.anchor or len(lines) + 1) - 1, 0), len(lines))
            new_bodies = _bodies(_split_lines(block.new))
            text = _replace_span(lines, pos, pos, [], new_bodies)
        else:
            text, _info = _fuzzy_replace_lines(
                lines, block.old, block.new, threshold, block.anchor
            )
        lines = _split_lines(text)
    return _join(lines)


def apply_edit(
    original: str,
    edit_text: str,
    format: str | None = None,
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> str:
    """Apply ``edit_text`` in ``format`` to ``original`` and return new content.

    ``format=None`` (or ``"auto"``) uses :func:`detect_edit_format`. Malformed
    patches raise :class:`EditParseError`; unmatched fuzzy blocks raise
    :class:`FuzzyMatchError`. The original string is never modified in place.
    """
    _check_threshold(threshold)
    fmt = _coerce_format(format) or detect_edit_format(edit_text)
    if fmt == FORMAT_WHOLE_FILE:
        return edit_text
    if fmt == FORMAT_SEARCH_REPLACE:
        blocks = (
            _parse_begin_patch(edit_text)
            if _has_begin_patch(edit_text)
            else _parse_search_replace(edit_text)
        )
        return _apply_blocks(original, blocks, threshold)
    if fmt == FORMAT_UNIFIED_DIFF:
        return _apply_blocks(original, _parse_unified_diff(edit_text), threshold)
    if fmt == FORMAT_LINE_RANGE:
        start, end, replacement = _parse_line_range(edit_text, _split_lines(original))
        return _replace_span(
            _split_lines(original), start, end, [], _bodies(_split_lines(replacement))
        )
    raise EditParseError("unsupported_format", f"Unhandled edit format {fmt!r}")


# ---------------------------------------------------------------------------
# X1.4 — deterministic per-model format recommendation
# ---------------------------------------------------------------------------


def _stat_to_counts(value: Any) -> tuple[float, float] | None:
    """Normalise a local-eval statistic into ``(successes, attempts)``."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if 0.0 <= number <= 1.0:
            return number * 100.0, 100.0
        if number > 1.0:
            return number, number + 1.0
        return None
    if not isinstance(value, Mapping):
        return None

    successes = value.get("successes", value.get("success", value.get("passed")))
    attempts = value.get("attempts", value.get("trials", value.get("total")))
    rate = value.get("success_rate", value.get("rate"))
    failures = value.get("failures", value.get("failed"))
    if rate is not None and successes is None:
        try:
            successes, attempts = float(rate) * 100.0, 100.0
        except (TypeError, ValueError):
            return None
    if attempts is None and successes is not None:
        attempts = float(successes) + (float(failures) if failures is not None else 1.0)
    if successes is None and attempts is not None and failures is not None:
        successes = float(attempts) - float(failures)
    try:
        successes = float(successes)
        attempts = float(attempts)
    except (TypeError, ValueError):
        return None
    if attempts <= 0 or successes < 0:
        return None
    return successes, attempts


def recommend_format_details(
    model_id: str,
    eval_stats: Mapping[str, Any] | None,
    *,
    default: str = DEFAULT_FORMAT,
) -> FormatRecommendation:
    """Pick a format from local eval stats, deterministically.

    Accepted ``eval_stats`` shapes::

        {"models": {model_id: {"formats": {fmt: stat, ...}}}}
        {model_id: {"formats": {fmt: stat, ...}}}
        {fmt: stat, ...}

    A ``stat`` is a rate in [0, 1], a success count, or a mapping with
    ``successes``/``attempts`` (or ``success_rate``). Rates use Laplace
    smoothing ``(successes + 1) / (attempts + 2)``; ties break on the fixed
    preference order then format name. With no usable stats the ``default``
    is returned, so the result never depends on dict insertion order.
    """
    raw: Any = {}
    if isinstance(eval_stats, Mapping):
        models = eval_stats.get("models")
        if isinstance(models, Mapping):
            raw = models.get(model_id, {})
        elif "formats" in eval_stats and isinstance(eval_stats["formats"], Mapping):
            raw = eval_stats
        else:
            raw = eval_stats.get(model_id, eval_stats)
    if isinstance(raw, Mapping) and "formats" in raw and isinstance(raw["formats"], Mapping):
        raw = raw["formats"]

    scores: dict[str, float] = {}
    if isinstance(raw, Mapping):
        for fmt in SUPPORTED_FORMATS:
            if fmt not in raw:
                continue
            counts = _stat_to_counts(raw[fmt])
            if counts is None:
                continue
            successes, attempts = counts
            scores[fmt] = min(1.0, (successes + 1.0) / (attempts + 2.0))

    if not scores:
        return FormatRecommendation(_coerce_format(default) or DEFAULT_FORMAT, "default", {}, model_id)

    preference = {fmt: i for i, fmt in enumerate(_FORMAT_PREFERENCE)}
    chosen = sorted(
        scores.items(),
        key=lambda item: (-item[1], preference.get(item[0], len(preference)), item[0]),
    )[0][0]
    return FormatRecommendation(chosen, "eval", scores, model_id)


def recommend_format(
    model_id: str, eval_stats: Mapping[str, Any] | None, *, default: str = DEFAULT_FORMAT
) -> str:
    """Return the canonical format id the router should use for ``model_id``."""
    return recommend_format_details(model_id, eval_stats, default=default).format


__all__ = [
    "FORMAT_WHOLE_FILE",
    "FORMAT_SEARCH_REPLACE",
    "FORMAT_UNIFIED_DIFF",
    "FORMAT_LINE_RANGE",
    "SUPPORTED_FORMATS",
    "DEFAULT_FORMAT",
    "DEFAULT_THRESHOLD",
    "EditFormatError",
    "EditParseError",
    "FuzzyMatchError",
    "MatchInfo",
    "FormatDetection",
    "FormatRecommendation",
    "detect_edit_format",
    "detect_edit_format_details",
    "apply_edit",
    "fuzzy_replace",
    "recommend_format",
    "recommend_format_details",
]
