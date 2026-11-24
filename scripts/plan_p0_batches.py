#!/usr/bin/env python3
"""Group the not-started P0 features into coherent implementation batches.

Read-only planning helper. Emits P0-BATCHES.md with one batch per source
section prefix, sorted by count. Each batch is a candidate for one specialist
agent workstream with exclusive module ownership.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "PLAN-INDEX.json"
OUT = ROOT / "P0-BATCHES.md"


def main() -> None:
    registry = json.loads(INDEX.read_text(encoding="utf-8"))
    p0 = [f for f in registry["features"]
          if f.get("status") == "not_started" and f.get("priority") == "P0"]
    groups: dict[str, list[dict]] = defaultdict(list)
    for f in p0:
        fid = f["id"]
        prefix = fid.split(".")[0] if "." in fid else fid.rstrip("0123456789")
        groups[prefix].append(f)

    lines = [
        "# Remaining P0 implementation batches",
        "",
        f"Generated from PLAN-INDEX.json: **{len(p0)} not-started P0 features** "
        f"in {len(groups)} source groups.",
        "",
        "These are candidate workstreams for specialist agents. Do not mark any "
        "feature verified until real code, tests and runtime evidence exist.",
        "",
    ]
    for prefix in sorted(groups, key=lambda p: (-len(groups[p]), p)):
        fs = groups[prefix]
        lines += [f"## {prefix} — {len(fs)} features", ""]
        for f in fs:
            title = str(f.get("feature", "")).replace("|", "\\|")
            lines.append(
                f"- `{f['id']}` ({f.get('milestone','?')}) {title[:160]}")
        lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}: {len(p0)} P0 features in {len(groups)} batches")


if __name__ == "__main__":
    main()
