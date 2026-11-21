"""Outbound redaction, output DLP and egress logging (B3.5 / B3.6 / B3.8).

All three features share one narrow secret-detection vocabulary. Patterns are
deliberately specific to real credential formats so ordinary prompts, source
code and test fixtures are never altered. Nothing in this module requires a
network connection or a hosted service; egress records are local JSONL files.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

# (kind, pattern) — ordered; ``redact_text`` applies each in turn.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("private_key", re.compile(
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
        re.S)),
    ("openrouter_key", re.compile(r"\bsk-or-v1-[A-Za-z0-9]{20,}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("google_key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(
        r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b"
        r"|\bgithub_pat_[A-Za-z0-9_]{30,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("jwt", re.compile(
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
]


def _merge(counts: dict, extra: dict) -> None:
    for kind, n in extra.items():
        counts[kind] = counts.get(kind, 0) + n


def redact_text(text: str, *, placeholder: str = "[REDACTED]") -> tuple[str, dict]:
    """Return ``(redacted_text, counts_by_kind)`` for a single string."""
    if not isinstance(text, str):
        return text, {}
    out = text
    counts: dict[str, int] = {}
    for kind, pattern in _PATTERNS:
        found = len(pattern.findall(out))
        if found:
            counts[kind] = counts.get(kind, 0) + found
            out = pattern.sub(placeholder, out)
    return out, counts


def redact_messages(messages, *, placeholder: str = "[REDACTED]"):
    """Redact text fields of an Anthropic-style message list.

    Returns ``(new_messages, counts_by_kind)``. The input list and its
    dictionaries are never mutated, so the caller can keep the original
    transcript intact while sending only the redacted copy to a provider.
    """
    counts: dict[str, int] = {}
    result = []
    for message in messages:
        if not isinstance(message, dict):
            result.append(message)
            continue
        copy = dict(message)
        content = copy.get("content")
        if isinstance(content, str):
            copy["content"], found = redact_text(content, placeholder=placeholder)
            _merge(counts, found)
        elif isinstance(content, list):
            blocks = []
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    new_block = dict(block)
                    new_block["text"], found = redact_text(
                        new_block["text"], placeholder=placeholder)
                    _merge(counts, found)
                    blocks.append(new_block)
                else:
                    blocks.append(block)
            copy["content"] = blocks
        result.append(copy)
    return result, counts


def check_output_dlp(text: str) -> list[str]:
    """Return the secret kinds found in *text* (empty means safe to persist)."""
    if not isinstance(text, str):
        return []
    return list(redact_text(text)[1])


def output_dlp_enabled() -> bool:
    return os.environ.get("KEEL_OUTPUT_DLP", "1").strip() not in {"0", "off", "false", "no"}


def egress_log_path(state_root: str) -> Path:
    raw = os.environ.get("KEEL_EGRESS_LOG")
    return Path(raw) if raw else Path(state_root) / "egress.jsonl"


def log_egress(state_root: str, *, provider: str, model: str,
               message_count: int, redactions: dict,
               outbound_bytes: int) -> Path:
    path = egress_log_path(state_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provider": provider,
        "model": model,
        "message_count": message_count,
        "outbound_bytes": outbound_bytes,
        "redactions": redactions,
    }
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return path


def read_egress(state_root: str) -> list[dict]:
    path = egress_log_path(state_root)
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records
