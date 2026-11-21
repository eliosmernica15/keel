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

# Genuine owner-gated features: these require decisions or external account
# changes Keel must not make unilaterally (hosting choice, repo security
# enforcement, legal terms). They are reported as blocked, not fabricated.
OWNER_BLOCKED = {"C11.1", "C11.2"}

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
    "B1.1": ("src/keel/tool_json.py", "tests/test_tool_json.py",
             "Tightened tool schemas with additionalProperties=false"),
    "B1.2": ("src/keel/tool_json.py", "tests/test_tool_json.py",
             "Tolerant tool-call JSON repair, validation and coercion"),
    "B1.6": ("src/keel/model_downloads.py", "tests/test_model_downloads.py",
             "Resumable model downloads with SHA-256 integrity verification"),
    "A4.4": ("src/keel/instructions.py", "tests/test_rigor.py",
             "Evidence-before-claims rigor contract in agent persona"),
    "A2.8": ("tests/test_e2e_local.py", "tests/test_e2e_local.py",
             "Local E2E harness exercising real bridge chat/settings/viewer flows"),
    "B1.5": ("src/keel/context.py", "tests/test_compaction.py",
             "Verified existing budget, preserved-tail compaction and thrash guard"),
    "B2.3": ("src/keel/duet.py", "tests/test_duet.py",
             "Duet builder plus independent read-only reviewer agents"),
    "A1.22": ("AGENTS.md", "tests/test_builder_guide.py",
              "Internal builder guide with repo layout and conventions"),
    "C7.1": ("src/keel/instructions.py", "tests/test_instruction_imports.py",
             "Import other tools' instruction files as untrusted context"),
    "C1.1": ("scripts/check_repo_hygiene.py", "tests/test_repo_hygiene.py",
             "Editorconfig, changelog, patch policy and lint/type config"),
    "A5.1": ("src/keel/gateway.py", "tests/test_gateway.py",
             "Gateway process with status/start/stop lifecycle"),
    "A4.1": ("src/keel/webhooks.py", "tests/test_webhooks.py",
             "Signed outgoing webhooks with replay protection"),
    "A5.3": ("src/keel/settings.py", "tests/test_settings.py",
             "Verified layered account/user config inheritance"),
    "A5.5": ("src/keel/message_state.py", "tests/test_message_state.py",
             "Outbound message state machine with queued/sent/delivered/read/failed"),
    "B2.6": ("src/keel/rag.py", "tests/test_rag.py",
             "Local RAG knowledge bases with deterministic lexical embeddings"),
    "A1.16": ("src/keel/session_export.py", "tests/test_session_export.py",
              "Session import/export bundles and statistics"),
    "A1.11": ("src/keel/resource_limits.py", "tests/test_resource_limits.py",
              "Browser tab and workspace resource budgets"),
    "A4.3": ("src/keel/fleet/connector_ops.py", "tests/test_mcp_presets.py",
             "MCP presets catalog of free/self-hosted servers"),
    "B4.12": ("src/keel/diagnostics.py", "tests/test_diagnostics.py",
              "Redacted diagnostics bundle via keel doctor --bundle"),
    "B4.13": ("src/keel/start_health.py", "tests/test_start_health.py",
              "Auto-rollback after repeated failed starts"),
    "B5.2": ("src/keel/release_feed.py", "tests/test_release_feed.py",
             "latest.json, version history and RSS release feed"),
    "B5.5": ("site/privacy.html", "tests/test_legal_pages.py",
             "Privacy, EULA and third-party notices site pages (drafts)"),
    "B5.1": ("site/ui/landing-download.js", "tests/test_download_detect.py",
             "Download page OS/CPU auto-detection and recommendation"),
    "C1.12": ("src/keel/pairing.py", "tests/test_pairing.py",
              "Explicit LAN/headless client pairing allowlist with revocation"),
    "C8.5": ("src/keel/supply_chain.py", "tests/test_supply_chain.py",
             "Plugin/skill capability review with permission diffs"),
    "C9.1": ("src/keel/model_manager.py", "tests/test_model_manager.py",
             "Local model manager with RAM budget and idle unload"),
    "B5.3": ("site/requirements.html", "tests/test_requirements_page.py",
             "System requirements, model-size guide and first-run guide"),
    "B7.1": ("tests/test_property_safety.py", "tests/test_property_safety.py",
             "Seeded fuzz tests for path containment and command safety"),
    "C5.1": ("src/keel/workflows.py", "tests/test_workflow_nodes.py",
             "Deterministic map/loop workflow nodes with typed inputs"),
    "C5.2": ("src/keel/workflows.py", "tests/test_workflow_nodes.py",
             "Human-task workflow node with timeout and default"),
    "C3.1": ("src/keel/best_of_n.py", "tests/test_best_of_n.py",
             "Best-of-N candidate generation with test-based selection"),
    "C8.8": ("src/keel/red_team.py", "tests/test_red_team.py",
             "Local deterministic red-team evaluation suite"),
    "C2.1": ("src/keel/surfaces.py", "tests/test_surfaces.py",
             "Verified Cowork surface with knowledge-work tool set"),
    "C2.2": ("src/keel/surfaces.py", "tests/test_surfaces.py",
             "Verified Code surface with engineering tool set"),
    "C2.4": ("src/keel/surfaces.py", "tests/test_surfaces.py",
             "Verified Fleet surface with delegation/task tools"),
    "B4.5": ("src/keel/markdown_render.py", "tests/test_markdown_render.py",
             "Rich rendering detection with HTML escaping for Markdown/Mermaid/LaTeX"),
    "A2.3": ("src/keel/browser_profiles.py", "tests/test_browser_profiles.py",
             "Persistent per-agent browser profiles and workspace folders"),
    "B7.4": ("src/keel/performance_budgets.py", "tests/test_performance_budgets.py",
             "Performance budgets with measured-value checker"),
    "B7.2": ("src/keel/golden.py", "tests/test_golden_chaos.py",
             "Golden-file snapshots and deterministic chaos fault injection"),
    "C11.5": ("src/keel/eula.py", "tests/test_eula.py",
              "Local EULA acceptance state with version re-prompt"),
    "C9.2": ("src/keel/virtual_list.py", "tests/test_virtual_list.py",
             "Virtualized list windowing and streaming backpressure"),
    "C1.3": ("src/keel/agent_style.py", "tests/test_agent_style.py",
             "Deterministic agent avatars, colors and voice previews"),
    "B1.3": ("src/keel/model_router.py", "tests/test_model_router.py",
             "Difficulty-based model routing with local heuristics"),
    "B1.7": ("src/keel/hardware.py", "tests/test_hardware.py",
             "Hardware detection and quantization advice"),
    "B1.9": ("src/keel/arena.py", "tests/test_arena.py",
             "Compare mode (arena) for local candidate comparison"),
    "C13.1": ("src/keel/swe_bench.py", "tests/test_swe_bench.py",
              "Local SWE-task benchmark suite with per-model leaderboard"),
    "C13.4": ("src/keel/installer_smoke.py", "tests/test_installer_smoke.py",
              "Installer smoke-test harness with manifest checksum checks"),
    "B1.4": ("src/keel/prefix_cache.py", "tests/test_prefix_cache.py",
             "Prefix/KV-cache reuse helper"),
    "B1.10": ("src/keel/prefix_cache.py", "tests/test_prefix_cache.py",
              "Opt-in speculative decoding toggle"),
    "A5.4": ("src/keel/channel_ops.py", "tests/test_channel_ops.py",
             "Channel delivery fallback chain"),
    "A5.6": ("src/keel/channel_ops.py", "tests/test_channel_ops.py",
             "Webhook subscription helper with secret rotation"),
    "A5.7": ("src/keel/channel_ops.py", "tests/test_channel_ops.py",
             "Per-channel troubleshooting checklists"),
    "A4.2": ("src/keel/build_repro.py", "tests/test_build_repro.py",
             "Reproducible build manifest with stable digest"),
    "A4.5": ("src/keel/build_repro.py", "tests/test_build_repro.py",
             "Coding-agent routing rules by task type"),
    "C6.1": ("src/keel/memory_types.py", "tests/test_memory_types.py",
             "Episodic, semantic and procedural memory types"),
    "C6.2": ("src/keel/knowledge_graph.py", "tests/test_knowledge_graph.py",
             "Local entity/relation knowledge graph"),
    "C6.4": ("src/keel/user_profile.py", "tests/test_user_profile.py",
             "Editable local user profile with opt-in context"),
    "C6.3": ("src/keel/memory_types.py", "tests/test_memory_types.py",
             "Importance scoring, decay and dreaming consolidation"),
    "C7.2": ("src/keel/interop.py", "tests/test_interop.py",
             "MCP config import/export and settings interchange"),
    "C7.4": ("src/keel/interop.py", "tests/test_interop.py",
             "OpenAPI-to-tools generator with dormant approval gate"),
    "C7.5": ("src/keel/interop.py", "tests/test_interop.py",
             "Standards support checklist"),
    "C4.2": ("src/keel/code_intel.py", "tests/test_code_intel.py",
             "Local symbol and dependency graph with impact analysis"),
    "C4.3": ("src/keel/code_intel.py", "tests/test_code_intel.py",
             "Change-risk scoring from dependency impact"),
    "C4.4": ("src/keel/code_intel.py", "tests/test_code_intel.py",
             "Structural search across source"),
    "C10.2": ("src/keel/onboarding.py", "tests/test_onboarding.py",
              "Stable offline error catalog"),
    "C10.3": ("src/keel/onboarding.py", "tests/test_onboarding.py",
              "Contextual help linked to offline docs"),
    "C10.4": ("src/keel/onboarding.py", "tests/test_onboarding.py",
              "Local feedback with redacted export"),
    "C4.12": ("src/keel/terminal_replay.py", "tests/test_terminal_and_issues.py",
              "Terminal session recording and replay"),
    "C4.13": ("src/keel/issue_to_change.py", "tests/test_terminal_and_issues.py",
              "Issue-to-change draft planning"),
    "C4.5": ("src/keel/dev_tools.py", "tests/test_dev_tools.py",
             "SARIF result summarisation"),
    "C4.6": ("src/keel/dev_tools.py", "tests/test_dev_tools.py",
             "Local project secret scan"),
    "C4.8": ("src/keel/dev_tools.py", "tests/test_dev_tools.py",
             "Port/service health probe"),
    "C4.14": ("src/keel/dev_tools.py", "tests/test_dev_tools.py",
              "Generated architecture snapshot"),
    "C10.1": ("src/keel/tutorial.py", "tests/test_tutorial.py",
              "Interactive tutorial scaffold"),
    "C10.5": ("src/keel/tutorial.py", "tests/test_tutorial.py",
              "Voice accessibility descriptors with opt-in responses"),
    "C3.4": ("src/keel/agent_intelligence.py", "tests/test_agent_intelligence.py",
             "Think-harder effort controls"),
    "C3.8": ("src/keel/agent_intelligence.py", "tests/test_agent_intelligence.py",
             "Failure postmortems stored per project"),
    "C3.9": ("src/keel/agent_intelligence.py", "tests/test_agent_intelligence.py",
             "Pre-run cost/time estimates with confidence"),
    "C3.10": ("src/keel/agent_intelligence.py", "tests/test_agent_intelligence.py",
              "Uncertainty policy"),
    "C3.11": ("src/keel/agent_intelligence.py", "tests/test_agent_intelligence.py",
              "Project style learning"),
    "C3.3": ("src/keel/agent_roles.py", "tests/test_agent_roles.py",
             "Goal and overnight mode with approval checkpoints"),
    "C3.5": ("src/keel/agent_roles.py", "tests/test_agent_roles.py",
             "Planner/critic/executor role prompts"),
    "C3.6": ("src/keel/agent_roles.py", "tests/test_agent_roles.py",
             "Map-reduce chunking for refactors"),
    "C3.7": ("src/keel/agent_roles.py", "tests/test_agent_roles.py",
             "Reflection with approval gate"),
    "C3.12": ("src/keel/context_packs.py", "tests/test_context_packs.py",
              "Context packs with budget tracking"),
    "C12.2": ("src/keel/distribution.py", "tests/test_distribution.py",
              "Air-gapped offline bundle descriptor"),
    "C12.3": ("src/keel/distribution.py", "tests/test_distribution.py",
              "Static signed APT/YUM repo layout check"),
    "C12.5": ("src/keel/distribution.py", "tests/test_distribution.py",
              "Portable build manifest"),
    "C9.3": ("src/keel/resource_caps.py", "tests/test_resource_caps.py",
             "Low-power mode and resource meter descriptors"),
    "C9.4": ("src/keel/resource_caps.py", "tests/test_resource_caps.py",
             "Per-feature resource caps with visible meters"),
    "C1.10": ("src/keel/content_skills.py", "tests/test_content_skills.py",
              "Draft-only content skills that never auto-publish"),
    "C1.8": ("src/keel/content_skills.py", "tests/test_content_skills.py",
             "Notes vault backlinks"),
    "C1.9": ("src/keel/content_skills.py", "tests/test_content_skills.py",
             "Plugin presets bundle"),
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
        status = ("verified" if evidence else
                  "blocked" if feature_id in OWNER_BLOCKED else "not_started")
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
