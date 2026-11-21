"""Restore the three authoritative plan sources from v6's preserved appendices.

The Downloads copies were external and volatile. v6 stores each source
verbatim in an appendix, so we can reconstruct canonical in-repo copies and
make the registry builder independent of the Downloads folder.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V6 = REPO / "Keel_Master_Plan_v6.md"
OUT = REPO / "keel" / "docs" / "plan-sources"

MARKERS = [
    ("# Appendix V5 — Original Master Plan v5 (preserved)", "Keel_Master_Plan_v5.md"),
    ("# Appendix A1 — Addendum: Missed Features (preserved)",
     "Keel_Plan_v5_Addendum_Missed_Features.md"),
    ("# Appendix A2 — Addendum: More Features (preserved)",
     "Keel_Plan_v5_Addendum_2_More_Features.md"),
]


def main() -> None:
    text = V6.read_text(encoding="utf-8")
    positions = []
    for marker, name in MARKERS:
        index = text.find(marker)
        if index < 0:
            raise SystemExit(f"missing appendix marker: {marker}")
        positions.append((index + len(marker), name))
    positions.sort()
    OUT.mkdir(parents=True, exist_ok=True)
    for i, (start, name) in enumerate(positions):
        end = positions[i + 1][0] - len(MARKERS[i + 1][0]) if i + 1 < len(positions) else len(text)
        # Trim the trailing separator inserted between appendices.
        body = text[start:end]
        body = re.sub(r"\n---\n\s*$", "", body).strip() + "\n"
        target = OUT / name
        # Originals used LF endings; write exact bytes so hashes match.
        target.write_bytes(body.encode("utf-8"))
        print(f"restored {target.relative_to(REPO)} ({len(body)} chars)")


if __name__ == "__main__":
    main()
