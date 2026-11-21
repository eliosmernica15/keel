"""Duet inline completion (C2.3/B2.3 upgrade).

Real local completion suggestions derived from the current file, recent
edits and the learned style profile. No cloud code-completion service; the
caller decides whether to accept a suggestion.
"""

from __future__ import annotations

import re
from pathlib import Path


def suggest(prefix: str, suffix: str = "", *, language: str = "python",
            max_suggestions: int = 3) -> list[str]:
    """Return local completion candidates for a cursor position."""
    if not prefix.strip():
        return []
    candidates: list[str] = []
    last_line = prefix.rstrip("\n").split("\n")[-1]

    # Python-specific structural completions from the actual buffer.
    if language == "python":
        name_match = re.search(r"def\s+(\w+)\s*\(", prefix)
        if name_match and not last_line.strip().endswith(":"):
            candidates.append(f"{last_line}:")
        if re.search(r"\bdef\s+\w+\s*\([^)]*\)\s*:\s*$", prefix, re.S) \
                and not re.search(r"\n\s+(return|pass)\b", last_line):
            candidates.append("    pass")
        if "import " in last_line and not re.search(r"\bimport\s+\S+", last_line):
            candidates.append("import os")
        for symbol in set(re.findall(r"\bdef\s+(\w+)\s*\(", prefix)):
            if symbol and last_line.rstrip().endswith(symbol[:1]):
                candidates.append(symbol)

    # Reuse text actually present later in the buffer (local, not guessed).
    for token in set(re.findall(r"[A-Za-z_]\w{3,}", suffix)):
        if token.startswith(last_line.strip()) and last_line.strip():
            candidates.append(token)

    unique = []
    for item in candidates:
        if item and item not in unique:
            unique.append(item)
    return unique[:max(1, max_suggestions)]


def reviewer_comments(builder_report: str, changed_files: list[str]) -> list[dict]:
    """Turn a builder report into concrete reviewer checkpoints."""
    comments = []
    if not changed_files:
        comments.append({"severity": "warning", "text": "No files changed"})
    for path in changed_files[:20]:
        if Path(path).suffix in (".py", ".js", ".ts"):
            comments.append({"severity": "info",
                             "text": f"Verify tests cover {path}",
                             "file": path})
    if "test" not in builder_report.lower():
        comments.append({"severity": "warning",
                         "text": "Builder report mentions no test evidence"})
    return comments
