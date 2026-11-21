"""Plugin/skill supply-chain review with permission diffs (C8.5).

Summarises the capabilities a skill requests and compares them against a
baseline allowlist, producing a human-readable permission diff. Review is
advisory: nothing is granted silently and project-scope skills stay untrusted.
"""

from __future__ import annotations

import re
from typing import Any

_TOOL_RE = re.compile(r"\b(read_file|write_file|edit_file|delete_file|run_shell|"
                      r"run_python|web_fetch|web_search|git_commit|git_push|"
                      r"install_deps|send_to_bot|process_kill)\b")

CAPABILITY_LABELS = {
    "write_file": "write files", "edit_file": "edit files",
    "delete_file": "delete files", "run_shell": "run shell commands",
    "run_python": "run Python", "web_fetch": "network fetch",
    "web_search": "network search", "git_commit": "commit changes",
    "git_push": "push changes", "install_deps": "install dependencies",
    "send_to_bot": "delegate to agents", "process_kill": "kill processes",
}


def skill_capabilities(skill: Any) -> list[str]:
    """Extract declared and inferred capabilities from a skill."""
    declared = []
    fm = getattr(skill, "frontmatter", {}) or {}
    raw = fm.get("allowed-tools", fm.get("allowed_tools", []))
    if isinstance(raw, str):
        declared = [part.strip() for part in re.split(r"[,\s]+", raw)
                    if part.strip()]
    elif isinstance(raw, (list, tuple)):
        declared = [str(item).strip() for item in raw if str(item).strip()]
    text = getattr(skill, "body", "") or ""
    inferred = _TOOL_RE.findall(text)
    return sorted(set(declared) | set(inferred))


def permission_diff(skill: Any, baseline: set[str] | frozenset[str]) -> dict:
    requested = skill_capabilities(skill)
    baseline_set = set(baseline)
    gained = [cap for cap in requested if cap not in baseline_set]
    review = not getattr(skill, "trusted", False)
    return {
        "skill": getattr(skill, "name", ""),
        "scope": getattr(skill, "scope", ""),
        "trusted": not review,
        "requested": requested,
        "gained": gained,
        "gained_labels": [CAPABILITY_LABELS.get(cap, cap) for cap in gained],
        "requires_review": review or bool(gained),
        "summary": review_summary(gained, review),
    }


def review_summary(gained: list[str], untrusted: bool) -> str:
    parts = []
    if untrusted:
        parts.append("project-scope skill is untrusted by default")
    if gained:
        parts.append("requests new capabilities: " + ", ".join(
            CAPABILITY_LABELS.get(cap, cap) for cap in gained))
    if not parts:
        return "no new capabilities requested"
    return "; ".join(parts) + " — review before enabling"
