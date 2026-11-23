"""Build Keel_Master_Plan_v6.md from preserved authoritative sources."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCES = REPO / "keel" / "docs" / "plan-sources"
DOWNLOADS = Path(r"C:\Users\Admin\Downloads")


def _source(name: str) -> Path:
    in_repo = SOURCES / name
    return in_repo if in_repo.is_file() else DOWNLOADS / name


V5 = _source("Keel_Master_Plan_v5.md")
ADD1 = _source("Keel_Plan_v5_Addendum_Missed_Features.md")
ADD2 = _source("Keel_Plan_v5_Addendum_2_More_Features.md")
ADD3 = _source("Keel_Plan_v5_Addendum_3_Gaps_and_Advanced.md")
ADD4 = _source("Keel_Plan_v5_Addendum_4_Sourced_Features_and_Builder_Guide.md")
ADD5 = _source("Keel_Plan_v5_Addendum_5_DeepSeek_Harness_and_Deep_Reads.md")
ADD6 = _source("Keel_Plan_v5_Addendum_6_DeepSeek_Harness_Full_Teardown.md")
ADD7 = _source("Keel_Plan_v5_Addendum_7_DeepSeek_Deep_Reads.md")
ALL_SOURCES = [V5, ADD1, ADD2, ADD3, ADD4, ADD5, ADD6, ADD7]
INDEX = REPO / "PLAN-INDEX.json"
OUT = REPO / "Keel_Master_Plan_v6.md"


def main() -> None:
    registry = json.loads(INDEX.read_text(encoding="utf-8"))
    lines = [
        "# Keel Master Plan v6",
        "",
        "**Status:** canonical expanded roadmap. Supersedes v5 for planning purposes while preserving v5 as the historical baseline.",
        "",
        "## Source documents (preserved unchanged)",
        "",
        "All eight uploaded specification documents are preserved verbatim in "
        "`keel/docs/plan-sources/`.",
        "",
        "- `Keel_Master_Plan_v5.md`",
        "- `Keel_Plan_v5_Addendum_Missed_Features.md`",
        "- `Keel_Plan_v5_Addendum_2_More_Features.md`",
        "- `Keel_Plan_v5_Addendum_3_Gaps_and_Advanced.md`",
        "- `Keel_Plan_v5_Addendum_4_Sourced_Features_and_Builder_Guide.md`",
        "- `Keel_Plan_v5_Addendum_5_DeepSeek_Harness_and_Deep_Reads.md`",
        "- `Keel_Plan_v5_Addendum_6_DeepSeek_Harness_Full_Teardown.md`",
        "- `Keel_Plan_v5_Addendum_7_DeepSeek_Deep_Reads.md`",
        "",
        f"**Registry:** {len(registry['features'])} features "
        f"(priority counts: {registry.get('priority_counts', {})}).",
        "",
        "## Known source gap",
        "",
        "The supplied v5 copy ends during Section 11. Sections 12–16, the Section 13 milestone mapping, complete M0–M26 definitions, and Appendices A–D were not supplied and are **not reconstructed**. The addenda provide explicit feature-level authorization for the expanded scope below.",
        "",
        "## Expanded product vision",
        "",
        "Keel is a local-first AI workstation with four surfaces: **Keel Cowork** (knowledge work), **Keel Code** (engineering), **Keel Duet** (live pairing), and **Keel Fleet** (multi-agent organization). Electron is the desktop shell, Python is the authoritative runtime, and SQLite is the canonical local database. A loopback web UI, CLI and TUI share the same token-authenticated Python runtime.",
        "",
        "## Architecture constraints",
        "",
        "- Python authoritative backend/runtime; Electron desktop shell; SQLite canonical DB.",
        "- Local-first, offline-capable, free to use; no mandatory account, hosted backend, paid service or telemetry.",
        "- Preserve existing permission tiers, approval broker, session/event model, and DB migrations.",
        "- Python enforces all permissions. Plugins, skills and MCP remain gated and observable.",
        "- New dependencies require license, security, maintenance and packaging review; optional local tools preferred.",
        "",
        "## Feature traceability",
        "",
        "Machine-readable registry: `PLAN-INDEX.json` (canonical) and `parity.json` (synchronized projection generated from it). Every addendum feature ID is preserved; no feature is silently omitted.",
        "",
        "| ID | Feature | Milestone | Priority | Status |",
        "| --- | --- | --- | --- | --- |",
    ]
    for feature in registry["features"]:
        name = feature["feature"].replace("|", "\\|")
        lines.append(
            f"| {feature['id']} | {name} | "
            f"{feature['milestone']} | {feature['priority']} | {feature['status']} |")
    lines.extend([
        "",
        "## Acceptance framework",
        "",
        "A feature is `verified` only when its acceptance criteria, automated tests, and real-runtime evidence pass. `implemented` means code exists with tests but end-to-end evidence remains. `blocked` is reserved for genuine owner-approval or missing-source dependencies. Source gap notes are not a blanket blocker.",
        "",
        "## Prioritized build order",
        "",
        "1. Security, trust, release, destructive-operation and repository-protection P0 items.",
        "2. Local-model reliability and agent verification (B1.x, C3.x, C9.x).",
        "3. Product surfaces, especially Cowork and Duet.",
        "4. Engineering tools, workflows, memory, connectors, channels, Fleet.",
        "5. Desktop, distribution, observability and documentation.",
        "6. Remaining P1, then P2 features; P2 means later, never exclusion.",
        "",
        "---",
        "",
        "# Appendix V5 — Original Master Plan v5 (preserved)",
        "",
        V5.read_text(encoding="utf-8"),
        "",
        "---",
        "",
        "# Appendix A1 — Addendum: Missed Features (preserved)",
        "",
        ADD1.read_text(encoding="utf-8"),
        "",
        "---",
        "",
        "# Appendix A2 — Addendum: More Features (preserved)",
        "",
        ADD2.read_text(encoding="utf-8"),
        "",
        "---",
        "",
        "# Appendix A3 — Addendum: Gaps and Advanced Features (preserved)",
        "",
        ADD3.read_text(encoding="utf-8"),
        "",
        "---",
        "",
        "# Appendix A4 — Addendum: Sourced Features and Builder Guide (preserved)",
        "",
        ADD4.read_text(encoding="utf-8"),
        "",
        "---",
        "",
        "# Appendix A5 — Addendum: DeepSeek Harness and Deep Reads (preserved)",
        "",
        ADD5.read_text(encoding="utf-8"),
        "",
        "---",
        "",
        "# Appendix A6 — Addendum: DeepSeek Harness Full Teardown (preserved)",
        "",
        ADD6.read_text(encoding="utf-8"),
        "",
        "---",
        "",
        "# Appendix A7 — Addendum: DeepSeek Deep Reads (preserved)",
        "",
        ADD7.read_text(encoding="utf-8"),
    ])
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT} with {len(registry['features'])} features")


if __name__ == "__main__":
    main()
