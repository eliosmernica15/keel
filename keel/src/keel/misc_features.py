"""Assorted local feature descriptors from both addenda.

Each helper produces deterministic local data; no hosted service, external
account or CI runner is required. Optional integrations are described and
gated, never silently enabled.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path


def extra_instruction_files(cwd: str | Path, globs: list[str]) -> list[str]:
    """A1.14: resolve extra instruction files by glob (no URL fetching here)."""
    root = Path(cwd)
    found = []
    for pattern in globs:
        if pattern.startswith(("http://", "https://")):
            found.append({"url": pattern, "note": "fetch only with approval"})
            continue
        found.extend(str(path) for path in sorted(root.glob(pattern)))
    return found[:100]


def small_model_role() -> dict:
    """A1.15: per-agent small-model role for titles/summaries."""
    return {"role": "small_model", "purpose": "titles and summaries",
            "default": "keel-fake-1", "per_agent_override": True}


def prune_old_versions(versions: list[str], keep: int = 3) -> list[str]:
    """A1.21: versions eligible for removal notice before install."""
    return versions[keep:]


def specialist_agents() -> dict[str, str]:
    """B2.4: bundled specialist agent prompts (markdown-ready)."""
    return {
        "code-reviewer": "Review changes for correctness; cite file:line.",
        "security-reviewer": "Look for injection, secrets and privilege issues.",
        "docs-writer": "Write concise, accurate documentation with examples.",
    }


def offline_doc_pack(root: str | Path, name: str) -> dict:
    """B2.7: describe a local documentation pack."""
    path = Path(root)
    files = [str(p) for p in sorted(path.rglob("*.md"))][:200] if path.is_dir() else []
    return {"name": name, "files": files, "searchable": bool(files)}


def fleet_views() -> dict:
    """B4.6: Fleet view descriptors."""
    return {"kanban": ["todo", "in_progress", "done"],
            "org_chart": True, "cost_per_agent": True, "live_activity": True}


def observability_views() -> dict:
    """B4.7: observability view descriptors."""
    return {"token_waterfall": True, "flame_graph": True,
            "prompt_diff": True}


def dap_breakpoint(file: str, line: int) -> dict:
    """C4.1: DAP breakpoint descriptor."""
    return {"file": file, "line": max(1, int(line)),
            "verified": False, "note": "Requires user's DAP adapter."}


def git_extras() -> list[str]:
    """C4.9: supported git extra operations."""
    return ["stacked_commits", "hunk_staging", "conflict_resolver",
            "blame_aware_commit"]


def behavior_anomaly(events: list[dict]) -> dict:
    """C8.3: detect mass file reads / unusual network / rapid retries."""
    reads = sum(1 for e in events if e.get("tool") == "read_file")
    net = sum(1 for e in events if e.get("tool") in ("web_fetch", "web_search"))
    retries = sum(1 for e in events if e.get("retry"))
    flags = []
    if reads > 20:
        flags.append("mass_file_reads")
    if net > 20:
        flags.append("unusual_network")
    if retries > 5:
        flags.append("rapid_retries")
    return {"flags": flags, "suspicious": bool(flags)}
