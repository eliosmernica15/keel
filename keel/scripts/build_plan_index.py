"""Generate PLAN-INDEX.json and parity.json from the authoritative plan sources.

The addenda are the source of feature IDs. This script never edits them.
parity.json is a synchronized projection of PLAN-INDEX.json, not an independent
registry.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOWNLOADS = Path(r"C:\Users\Admin\Downloads")
V5 = DOWNLOADS / "Keel_Master_Plan_v5.md"
ADDENDUM1 = DOWNLOADS / "Keel_Plan_v5_Addendum_Missed_Features.md"
ADDENDUM2 = DOWNLOADS / "Keel_Plan_v5_Addendum_2_More_Features.md"
OUT = REPO / "PLAN-INDEX.json"
PARITY = REPO / "parity.json"

ID_RE = re.compile(r"^[ABC]\d+\.\d+$")
M_RE = re.compile(r"\bM\d+\b")

# Verified-existing implementation evidence from the current repository.
IMPLEMENTED = {
    "A1.1": ("src/keel/runner.py", "tests/test_vertical_slice.py",
             "Non-interactive print-mode runner with stream-json and exit codes"),
    "A1.11": ("src/keel/runner.py", "tests/test_safety.py",
              "SSRF-safe web_fetch and web_search tools"),
    "A3.3": ("src/keel/fakes.py", "tests/test_compat_runtime.py",
             "Deterministic fake/scripted provider for tests"),
    "A3.4": ("src/keel/fleet/tools.py", "tests/test_fleet_ask_user.py",
             "ask_user question flow with timeout and answer API"),
    "A4.6": ("src/keel/fleet/routes.py", "tests/test_fleet_credentials.py",
             "Provider credential test-fire endpoint"),
    "B7.6": ("PLAN-INDEX.json", "tests/test_plan_index.py",
             "Machine-readable feature registry"),
    "B7.7": (".pre-commit-config.yaml", "tests/test_release_controls.py",
             "Pinned gitleaks pre-commit hook and repo hygiene config"),
    "C7.3": ("src/keel/skills.py", "tests/test_skills.py",
             "SKILL.md-compatible skill format and markdown commands"),
    "C11.4": ("keel/docs/proprietary/THIRD_PARTY_NOTICES.draft.md",
              "tests/test_release_controls.py",
              "Proprietary notices draft and dependency license inventory"),
    "C12.1": ("src/keel/release/common.py", "tests/test_release_hardening.py",
              "Manifest min_version, blocked_versions and rollout policy fields"),
    "C12.4": ("src/keel/release/updater.py", "tests/test_release_hardening.py",
              "Mirror failover with signature verification on every mirror"),
    "C12.6": ("src/keel/release/cli.py", "tests/test_release_hardening.py",
              "Release dry-run command with local checks and no publish"),
    "C8.1": ("src/keel/trash.py", "tests/test_trash.py",
             "Recoverable trash for agent file deletions with restore"),
    "C3.2": ("src/keel/session.py", "tests/test_resilience.py",
             "Doom-loop hint and abort on repeated identical tool calls"),
    "C1.4": ("site/ui/app.js", "tests/test_screen_safe_mode.py",
             "Screen-share/recording safe mode masking sensitive UI fields"),
    "B3.6": ("src/keel/redaction.py", "tests/test_redaction.py",
             "Credential/PII redaction of outbound provider messages"),
    "B3.8": ("src/keel/runner.py", "tests/test_redaction.py",
             "Output DLP refusing secrets in written files"),
    "B3.5": ("src/keel/redaction.py", "tests/test_redaction.py",
             "Local egress log of data sent to remote providers"),
    "B3.3": ("src/keel/session.py", "tests/test_dry_run.py",
             "Dry-run mode: plan every tool side effect, execute none"),
    "B3.4": ("src/keel/egress.py", "tests/test_read_only.py",
             "Read-only sessions and per-project network egress allowlist"),
    "B2.1": ("src/keel/verification.py", "tests/test_verification.py",
             "Auto-detected verification commands run after file edits"),
    "A1.10": ("src/keel/todos.py", "tests/test_todo.py",
              "Visible persistent task checklist via the todo tool"),
    "A1.5": ("src/keel/init_project.py", "tests/test_init_project.py",
             "keel init scans a repo and generates AGENTS.md"),
    "A1.7": ("src/keel/commands.py", "tests/test_slash_commands.py",
             "Slash commands: undo/redo, compact, export, models, themes, details"),
    "A1.9": ("site/ui/app.js", "tests/test_attachments_ui.py",
             "Image paste/drag into composer and fuzzy @file search"),
    "C2.5": ("src/keel/surfaces.py", "tests/test_surfaces.py",
             "Unified surface switcher with per-surface agents and permissions"),
    "B3.9": ("src/keel/fleet/turn_core.py", "tests/test_kill_switch.py",
             "Global kill switch cancelling all in-flight agent turns"),
    "A3.6": ("src/keel/webapp.py", "tests/test_kill_switch.py",
             "Revoke all client tokens by rotating the bridge token"),
    "B3.11": ("src/keel/circuit_breaker.py", "tests/test_circuit_breaker.py",
              "Provider circuit breaker with health score and fail-fast"),
    "A4.8": ("src/keel/release/artifacts.py", "tests/test_release_no_secrets.py",
             "Release scan proving zero clear-text secrets in artifacts"),
    "C6.5": ("src/keel/memory.py", "tests/test_memory.py",
             "Memory provenance and tainted-source tracking"),
    "A2.2": ("site/ui/app.js", "tests/test_voice.py",
             "Push-to-talk dictation and voice-to-task handoff"),
    "A2.5": ("src/keel/fleet/mention_guard.py", "tests/test_mention_guard.py",
             "Group-chat loop guards for repeated agent @mentions"),
    "A1.13": ("src/keel/custom_tools.py", "tests/test_custom_tools.py",
              "Custom Python tools from .keel/tools with approval gating"),
    "A1.12": ("src/keel/fleet/service.py", "tests/test_fleet_approvals.py",
              "Verified existing per-agent tool policies and permission overrides"),
    "A1.2": ("src/keel/attach.py", "tests/test_attach.py",
             "Attach a CLI client to a running Keel daemon"),
    "A3.10": ("src/keel/cost_caps.py", "tests/test_cost_caps.py",
              "Per-vendor daily/monthly cost caps with local usage ledger"),
}


def _parse_addendum(path: Path, source: str) -> list[dict]:
    features = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells or not ID_RE.match(cells[0]):
            continue
        feature_id = cells[0]
        name = cells[1]
        milestones = sorted({m for cell in cells for m in M_RE.findall(cell)})
        priority = next((c for c in cells if c in {"P0", "P1", "P2"}), "P2")
        source_file, test_file, evidence = IMPLEMENTED.get(
            feature_id, ("", "", ""))
        status = "verified" if evidence else "not_started"
        features.append({
            "id": feature_id,
            "feature": name,
            "source_document": source,
            "source_feature_id": feature_id,
            "milestone": milestones[0] if milestones else "unassigned",
            "priority": priority,
            "status": status,
            "source_files": [source_file] if source_file else [],
            "dependencies": [],
            "acceptance_criteria": [
                f"Implement {name} according to {source} feature {feature_id}",
                "Automated test coverage exists and passes",
                "Behavior is verified in the real application/runtime where applicable",
            ],
            "test_references": [test_file] if test_file else [],
            "verification_evidence": evidence,
            "owner_approval_required": feature_id in {
                "B6.1", "B6.2", "B6.3", "B6.4", "B6.5", "B6.6",
                "C11.1", "C11.2", "C11.3", "C11.5", "C11.7", "C11.8",
            },
        })
    return features


def build() -> dict:
    features = _parse_addendum(ADDENDUM1, "Keel_Plan_v5_Addendum_Missed_Features.md")
    features += _parse_addendum(ADDENDUM2, "Keel_Plan_v5_Addendum_2_More_Features.md")
    features.sort(key=lambda f: f["id"])
    return {
        "schema_version": 1,
        "authoritative_plan": "Keel_Master_Plan_v6.md",
        "source_documents": [
            "Keel_Master_Plan_v5.md",
            "Keel_Plan_v5_Addendum_Missed_Features.md",
            "Keel_Plan_v5_Addendum_2_More_Features.md",
        ],
        "note": "v5 Sections 12-16, Section 13 mapping and Appendices A-D remain missing from the supplied source and are not reconstructed here.",
        "features": features,
    }


def main() -> None:
    doc = build()
    OUT.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    PARITY.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(doc['features'])} features to PLAN-INDEX.json and parity.json")


if __name__ == "__main__":
    main()
