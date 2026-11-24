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
SOURCES = REPO / "keel" / "docs" / "plan-sources"
DOWNLOADS = Path(r"C:\Users\Admin\Downloads")


def _source(name: str) -> Path:
    """Prefer the in-repo canonical copy; fall back to the original Downloads."""
    in_repo = SOURCES / name
    return in_repo if in_repo.is_file() else DOWNLOADS / name


V5 = _source("Keel_Master_Plan_v5.md")
ADDENDUM1 = _source("Keel_Plan_v5_Addendum_Missed_Features.md")
ADDENDUM2 = _source("Keel_Plan_v5_Addendum_2_More_Features.md")
# Addenda 3-7 are normalized into extracted/*.json from the canonical markdown
# sources in keel/docs/plan-sources (read in full by the extraction pass). The
# extracted JSON is the canonical machine-readable form of those documents.
EXTRACTED = SOURCES / "extracted"
OUT = REPO / "PLAN-INDEX.json"
PARITY = REPO / "parity.json"

ID_RE = re.compile(r"^[A-Z]+\d+\.\d+[a-z]?$|^[YZV]\d+$")
EXTRA_SOURCES = [
    ("addendum3.json", "Keel_Plan_v5_Addendum_3_Gaps_and_Advanced.md"),
    ("addendum4.json", "Keel_Plan_v5_Addendum_4_Sourced_Features_and_Builder_Guide.md"),
    ("addendum5.json", "Keel_Plan_v5_Addendum_5_DeepSeek_Harness_and_Deep_Reads.md"),
    ("addendum6.json", "Keel_Plan_v5_Addendum_6_DeepSeek_Harness_Full_Teardown.md"),
    ("addendum7.json", "Keel_Plan_v5_Addendum_7_DeepSeek_Deep_Reads.md"),
]

# Security-critical vocabulary used for priority re-ranking (Addendum 3 X0.1:
# P0 must mean "essential for a safe, credible v1.0", capped near 25% of rows).
SECURITY_TERMS = re.compile(
    r"sandbox|permission|policy|approval|secret|credential|encrypt|isolat|"
    r"egress|dlp|audit|confidential|privileg|containment|fail.closed|untrusted|"
    r"inject|redact|token|restrict|access control|firewall|trust|safety|deny|allowlist",
    re.I)
FOUNDATION_MS = re.compile(r"\bM(?:0|1|2|3|4|5|7)\b")
M_RE = re.compile(r"\bM\d+\b")

# Genuine owner-gated features: these require decisions or external account
# changes Keel must not make unilaterally (hosting choice, repo security
# enforcement, legal terms). They are reported as blocked, not fabricated.
OWNER_BLOCKED = {"C11.1", "C11.2"}

# Implementation tiers distinguish truly integrated features from local
# modules and descriptors. A passing unit test does not make a scaffold
# operational. Values: operational | local_module | descriptor |
# external_dependency | owner_gated.
# Only genuinely static/display-only sources remain descriptors here. Modules
# with real local logic + tests were promoted to LOCAL_MODULES below.
DESCRIPTOR_MODULES = frozenset({
    "commercial_seams", "admin_ops",
})
LOCAL_MODULES = frozenset({
    "webhook_delivery", "file_watcher", "voice_tasks", "cowork_channels",
    "model_runtime", "rag_watcher", "api_tester", "codemod",
    "git_extras_runtime", "session_export", "model_router",
    "db_explorer", "sarif", "charts", "authoring",
    "channel_ops", "build_repro", "workbench", "notebook", "spec_mode", "views",
    "judge", "docpacks", "notes_vault", "repo_index", "openapi_tools",
    "secret_providers", "status_page", "admin_page", "exec_policy",
    "release_gaps", "document_gaps", "platform_gaps", "ops_tools",
    "agent_profiles", "local_ops", "integrations",
    "external_adapters",
    "ops_tools", "agent_intelligence", "agent_roles", "best_of_n", "arena",
    "hardware", "embeddings", "prefix_cache", "model_manager",
    "markdown_render", "terminal_replay", "issue_to_change", "dev_tools",
    "code_intel", "supply_chain", "installer_smoke", "context_packs",
    "knowledge_work", "tutorial", "onboarding", "performance_budgets",
    "golden", "virtual_list", "resource_caps", "browser_profiles",
    "agent_style", "cli_extras", "composer_tools", "misc_features",
    "ci_helpers", "eval_tools", "tui", "site_tools", "desktop_state",
    "distribution", "instructions", "provider_sources",
    "final_features", "last_features", "sandbox", "sandbox_policy",
    "release_integrity", "provider_validation",
    "documents", "backups", "debugger", "rag", "memory", "memory_types",
    "knowledge_graph", "user_profile", "feature_flags", "swe_bench",
    "red_team", "trust_tools", "interop", "workflows", "workflow_history",
    "automation", "resilience", "content_skills", "release_feed",
    "diagnostics", "start_health", "model_downloads", "verification",
    "custom_tools", "session_export", "signing", "updater", "artifacts",
    "circuit_breaker", "cost_caps", "redaction", "trash", "egress",
    "sandbox_exec", "inline_completion", "browser_launch",
})
EXTERNAL_IDS = frozenset({
    "B4.8",
    "B6.6",
    "C11.8",
})


def classify_tier(feature_id: str, source_files: list[str]) -> str:
    if feature_id in OWNER_BLOCKED:
        return "owner_gated"
    if feature_id in EXTERNAL_IDS:
        return "external_dependency"
    for source in source_files:
        name = source.replace("src/keel/", "").replace(".py", "")
        if name in DESCRIPTOR_MODULES:
            return "descriptor"
        if name in LOCAL_MODULES:
            return "local_module"
    return "operational"

# Verified-existing implementation evidence from the current repository.
IMPLEMENTED = {
    "A1.1": ("src/keel/runner.py", "tests/test_cli_e2e.py tests/test_vertical_slice.py",
             "Non-interactive print-mode runner with real subprocess E2E tool execution"),
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
             "Read-only sessions and per-project network egress allowlist; "
             "declarative network/command policy engine in exec_policy.py "
             "adapted from Codex execpolicy (host/protocol decisions, "
             "compiled allow/deny domains, load-time self-tests)"),
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
             "Evidence-before-claims rigor contract in persona"),
    "A2.8": ("tests/test_e2e_operations.py", "tests/test_e2e_operations.py tests/test_e2e_local.py",
             "Operational E2E: backend, sessions, tools, permissions, Cowork, backup, DLP"),
    "B1.5": ("src/keel/context.py", "tests/test_compaction.py",
             "Verified existing budget, preserved-tail compaction and thrash guard"),
    "B2.3": ("src/keel/duet.py", "tests/test_duet.py",
             "Duet builder plus independent read-only reviewer agents"),
    "A1.22": ("AGENTS.md", "tests/test_builder_guide.py",
              "Internal builder guide with repo layout and conventions"),
    "C7.1": ("src/keel/instructions.py", "tests/test_instruction_imports.py",
             "Other tools' instruction files as untrusted context"),
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
    "B2.6": ("src/keel/rag_watcher.py", "tests/test_rag_watcher.py tests/test_rag.py",
             "Local RAG with file-watcher-driven auto-reindexing"),
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
    "C9.1": ("src/keel/model_runtime.py", "tests/test_model_runtime.py tests/test_model_manager.py",
             "Real model runtime with RAM budget, LRU eviction and opt-in launch"),
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
    "C2.1": ("src/keel/documents.py", "tests/test_documents.py tests/test_document_endpoints.py",
             "Real DOCX/XLSX/CSV workflows exposed through the HTTP bridge"),
    "C2.2": ("src/keel/surfaces.py", "tests/test_surfaces.py",
             "Verified Code surface with engineering tool set"),
    "C2.4": ("src/keel/surfaces.py", "tests/test_surfaces.py",
             "Verified Fleet surface with delegation/task tools"),
    "B4.5": ("src/keel/markdown_render.py", "tests/test_markdown_render.py",
             "Rich rendering detection with HTML escaping for Markdown/Mermaid/LaTeX"),
    "A2.3": ("src/keel/browser_launch.py", "tests/test_browser_launch.py tests/test_browser_profiles.py",
             "Real persistent browser profiles with opt-in local browser launch"),
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
    "B1.3": ("src/keel/model_router.py", "tests/test_model_routing_integration.py tests/test_model_router.py",
             "Difficulty-based routing wired into the CLI run path (opt-in)"),
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
             "Channel delivery fallback chain with real send attempts"),
    "A5.6": ("src/keel/channel_ops.py", "tests/test_channel_ops.py",
             "Webhook subscription helper with real secret rotation"),
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
    "C7.4": ("src/keel/openapi_tools.py",
             "tests/test_openapi_tools.py tests/test_interop.py",
             "Real OpenAPI 3 to tools generator: parameter/request-body JSON "
             "Schemas, local $ref resolution, request descriptor builder, "
             "explicit named approval before use, persisted tool sets, "
             "capability and CLI surfaces; no network calls made"),
    "C7.5": ("src/keel/interop.py", "tests/test_interop.py",
             "Standards support checklist"),
    "C4.2": ("src/keel/code_intel.py", "tests/test_code_intel.py",
             "Local symbol and dependency graph with impact analysis"),
    "C4.3": ("src/keel/code_intel.py", "tests/test_code_intel.py",
             "Change-risk scoring from dependency impact"),
    "C4.4": ("src/keel/codemod.py", "tests/test_codemod.py tests/test_code_intel.py",
             "Real AST codemods with diff preview and structural search"),
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
    "C4.5": ("src/keel/sarif.py", "tests/test_db_sarif.py tests/test_dev_tools.py",
             "Real SARIF 2.1.0 emission and ingestion"),
    "C4.6": ("src/keel/dev_tools.py", "tests/test_dev_tools.py",
             "Local project secret scan"),
    "C4.8": ("src/keel/dev_tools.py", "tests/test_dev_tools.py",
             "Port/service health probe"),
    "C4.14": ("src/keel/dev_tools.py", "tests/test_dev_tools.py",
              "Generated architecture snapshot"),
    "C10.1": ("src/keel/tutorial.py",
             "tests/test_tutorial_ui.py tests/test_tutorial.py",
              "Real interactive tutorial in both UI trees (desktop/ui running "
             "app + site public mirror): persisted step progress, guided-tour "
             "overlay wired to cowork.tutorial.* capabilities with loading/"
             "empty/error/permission-denied states, what's-new modal and "
             "first-visit tips; browser-verified with real capability persistence"),
    "C10.5": ("src/keel/tutorial.py",
             "tests/test_accessibility_ui.py tests/test_tutorial.py",
              "Real voice accessibility in both UI trees: SpeechRecognition "
             "dictation with explicit consent and unavailable/error states, "
             "opt-in spoken replies and live-region streaming announcements "
             "persisted via cowork.accessibility.* capabilities"),
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
    "C12.2": ("src/keel/release_gaps.py", "tests/test_gap_closure.py",
                 "Real air-gapped bundle builder with checksum verification, model-folder import and signed sideload manifest"),
    "C12.3": ("src/keel/distribution.py", "tests/test_distribution.py",
             "Static signed APT/YUM repo layout check"),
    "C12.5": ("src/keel/distribution.py", "tests/test_distribution.py",
             "Portable build manifest"),
    "C9.3": ("src/keel/repo_index.py",
             "tests/test_repo_index.py tests/test_resource_caps.py",
             "Real incremental repository indexing: content-hash index with "
             "ignore rules, precise added/modified/removed detection without "
             "rehashing unchanged files, path/content search, persisted "
             "indexes, capability and CLI surfaces; low-power meter retained "
             "in resource_caps"),
    "C9.4": ("src/keel/resource_caps.py", "tests/test_resource_caps.py",
             "Per-feature resource caps with visible meters"),
    "C1.10": ("src/keel/content_skills.py", "tests/test_content_skills.py",
              "Draft-only content skills that never auto-publish"),
    "C1.8": ("src/keel/notes_vault.py",
             "tests/test_notes_vault.py tests/test_content_skills.py",
             "Real notes-vault extras: wiki-link backlinks with missing-link "
             "report, link graph with offline SVG, tag index, orphan "
             "detection, dated daily notes and templates, capability and CLI"),
    "C1.9": ("src/keel/content_skills.py", "tests/test_content_skills.py",
             "Plugin presets bundle"),
    "A1.17": ("src/keel/session_export.py", "tests/test_session_endpoints.py tests/test_cli_extras.py",
              "Session import/stats exposed through the HTTP bridge"),
    "A1.18": ("src/keel/cli_extras.py", "tests/test_cli_extras.py",
              "Agent creation spec helper"),
    "A1.20": ("src/keel/local_ops.py", "tests/test_local_ops.py",
             "Env-var override reporting (masked)"),
    "A1.6": ("src/keel/local_ops.py", "tests/test_local_ops.py",
             "Inline !cmd shell prefix parsing for permission-gated execution; "
             "exec_policy.py adds declarative prefix rules with "
             "allow/prompt/forbidden severity, alternatives, justifications "
             "and host-executable constraints (adapted from Codex execpolicy); "
             "binding at permission + capability boundaries with a real "
             "Settings > Policies UI (validate/activate/deactivate/evaluate)"),
    "A1.8": ("src/keel/local_ops.py", "tests/test_local_ops.py",
             "Real editor launch command builder"),
    "A4.7": ("src/keel/secret_providers.py",
             "tests/test_secret_providers.py tests/test_provider_sources.py",
             "Real local secret providers: env, .env file and opt-in "
             "user-owned command with shell=False/timeout, provider chain "
             "with presence-only diagnostics (no values in listings or "
             "capabilities), persisted provider choice, CLI get/has"),
    "A5.2": ("src/keel/provider_sources.py", "tests/test_provider_sources.py",
             "Channel/plugin install from git URL or local link, dormant until approved"),
    "A1.3": ("src/keel/tui.py", "tests/test_tui_functional.py tests/test_tui.py",
             "Full functional TUI driving the real runtime with persistence"),
    "A1.4": ("src/keel/cli/main.py", "tests/test_tui.py",
             "Local web UI alias (keel web)"),
    "A2.4": ("src/keel/local_ops.py", "tests/test_local_ops.py",
             "Real idle suspend/wake tracking"),
    "A2.6": ("src/keel/local_ops.py", "tests/test_local_ops.py",
             "Daily check-in/digest helper"),
    "A2.7": ("src/keel/local_ops.py", "tests/test_local_ops.py",
             "Config reference from real env values"),
    "A2.9": ("src/keel/local_ops.py", "tests/test_local_ops.py",
             "Memory/compaction tunable knobs"),
    "A3.1": ("src/keel/webhook_delivery.py", "tests/test_webhook_delivery.py",
             "Real signed webhook delivery with retry/backoff and delivery log"),
    "A3.2": ("src/keel/local_ops.py", "tests/test_local_ops.py",
             "Real stale temp-directory garbage collection"),
    "A3.5": ("src/keel/local_ops.py", "tests/test_local_ops.py",
             "Idempotent .env.example generation"),
    "A3.7": ("src/keel/status_page.py",
             "tests/test_status_page.py tests/test_ops_tools.py",
             "Real registry-driven honest project status: counts by status/"
             "tier/priority, separates verified end-to-end from built-but-"
             "unproven descriptors/external items, lists blocked owner gates, "
             "Markdown status page and capability; cannot drift from registry"),
    "B3.7": ("src/keel/trust_tools.py", "tests/test_trust_tools.py",
             "Prompt-injection classifier and canary tokens"),
    "B3.12": ("src/keel/trust_tools.py", "tests/test_trust_tools.py",
              "Verifiable immutable audit bundles"),
    "B2.2": ("src/keel/spec_mode.py",
             "tests/test_spec_mode.py tests/test_authoring.py",
             "Real spec-driven workflow: structured spec, dependency-ordered "
             "task breakdown, explicit attributed approval gates between "
             "phases, required verification evidence, persistent state, "
             "capability and CLI surfaces"),
    "B2.8": ("src/keel/notebook.py",
             "tests/test_notebook.py tests/test_workbench.py",
             "Real notebook execution in the hardened sandbox with per-cell "
             "stdout capture, error isolation, inline offline SVG charts, "
             "persistence with recoverable deletion, capability and CLI surfaces"),
    "B2.9": ("src/keel/db_explorer.py", "tests/test_db_sarif.py",
             "Real read-only SQLite explorer with query safety"),
    "B2.14": ("src/keel/authoring.py", "tests/test_authoring.py tests/test_workbench.py",
              "Prompt library with variables and improvement helper"),
    "B7.8": ("src/keel/feature_flags.py", "tests/test_feature_flags.py",
             "Feature-flag registry with kill-switch config"),
    "B2.10": ("src/keel/api_tester.py", "tests/test_api_tester.py",
              "Real HTTP/API tester with saved collections and host restrictions"),
    "B2.11": ("src/keel/charts.py", "tests/test_charts.py",
              "Real offline SVG flow diagrams and charts"),
    "B2.12": ("src/keel/document_gaps.py", "tests/test_gap_closure.py",
                 "Real PDF text/table extraction via pypdf and optional user-installed Tesseract OCR with honest tool detection and license notices"),
    "B2.15": ("src/keel/authoring.py", "tests/test_authoring.py",
              "Macro recorder extracted from real chat transcripts"),
    "B2.16": ("src/keel/knowledge_work.py", "tests/test_knowledge_work.py",
              "Bundled offline template gallery"),
    "B4.1": ("site/ui/app.js", "tests/test_quick_ask.py",
             "Quick Ask overlay wired to real /api/quick-ask runtime"),
    "B4.3": ("src/keel/desktop_state.py", "tests/test_desktop_state.py",
             "Saved workspace layouts"),
    "B4.4": ("src/keel/desktop_state.py", "tests/test_desktop_state.py",
             "Conversation tags/folders state"),
    "B4.10": ("src/keel/agent_profiles.py", "tests/test_profile_endpoints.py tests/test_agent_profiles.py",
              "Persistent agent profiles with management over the HTTP bridge"),
    "B4.2": ("src/keel/site_tools.py", "tests/test_site_tools.py",
             "keel:// deep link parsing"),
    "B5.4": ("src/keel/site_tools.py", "tests/test_site_tools.py",
             "Offline docs search index"),
    "B5.9": ("src/keel/release_gaps.py", "tests/test_gap_closure.py",
                 "User-configurable feed/mirror status URLs, real HTTP checks, URL validation, generated static status HTML"),
    "B3.1": ("src/keel/external_adapters.py", "tests/test_external_adapters.py",
             "WASM runtime command adapter with user-supplied engine"),
    "B3.2": ("src/keel/external_adapters.py", "tests/test_external_adapters.py",
             "Resource-limited container command adapter"),
    "B3.10": ("src/keel/sandbox.py", "tests/test_sandbox.py",
             "App-lock passphrase with auto-lock on idle"),
    "B1.8": ("src/keel/embeddings.py", "tests/test_embeddings.py",
             "Deterministic local embeddings and reranker"),
    "B6.1": ("src/keel/external_adapters.py", "tests/test_external_adapters.py",
             "Reserved offline license token verifier (inactive)"),
    "B6.2": ("src/keel/commercial_seams.py",
             "tests/test_enterprise_seams.py tests/test_commercial_seams.py",
             "Edition field 'standard' with no licensing gate, present in both "
             "release and download manifests and exposed via core.edition.info"),
    "B6.3": ("src/keel/commercial_seams.py",
             "tests/test_enterprise_seams.py tests/test_commercial_seams.py",
             "Real per-format silent-install flags (nsi/msi/pkg/deb/rpm), "
             "shipped Windows ADMX and macOS plist templates, surface via "
             "core.enterprise.templates"),
    "B6.5": ("src/keel/commercial_seams.py",
             "tests/test_enterprise_seams.py tests/test_commercial_seams.py",
             "Locally generated compliance artifacts: data-flow SVG, SBOM from "
             "dependency inventory, accessibility self-assessment; DPA/EULA "
             "legal text remains an honest draft pending owner review"),
    "C5.3": ("src/keel/workflow_history.py", "tests/test_workflow_history.py",
             "Workflow versioning and history"),
    "C8.2": ("src/keel/workflow_history.py", "tests/test_workflow_history.py",
             "Anomaly detection heuristic"),
    "C5.4": ("src/keel/file_watcher.py", "tests/test_file_watcher.py tests/test_automation.py",
             "Real polling file watcher with event dispatch"),
    "C5.5": ("src/keel/automation.py", "tests/test_automation.py",
             "Internal event bus"),
    "C5.6": ("src/keel/automation.py", "tests/test_automation.py",
             "Notification rules with quiet hours"),
    "C8.4": ("src/keel/resilience.py", "tests/test_resilience.py",
             "Canary files that must never be read"),
    "C8.6": ("src/keel/resilience.py", "tests/test_resilience.py",
             "Content-addressable artifact store with integrity"),
    "C8.7": ("src/keel/resilience.py", "tests/test_resilience.py",
             "SQLite integrity check and backup"),
    "C11.6": ("src/keel/eval_tools.py", "tests/test_eval_tools.py",
             "Official-build hash verification"),
    "C13.2": ("src/keel/judge.py",
             "tests/test_judge.py tests/test_external_adapters.py",
             "Deterministic local judge: four weighted auditable criteria, "
             "wasted/duplicate-call detection, best-of-N comparison, Markdown "
             "rubric reports; no external model called, backward-compatible "
             "judge_score delegate"),
    "C13.3": ("src/keel/eval_tools.py", "tests/test_eval_tools.py",
             "Prompt regression snapshots"),
    "C13.5": ("src/keel/charts.py", "tests/test_charts.py tests/test_eval_tools.py",
              "Release trend storage with rendered charts"),
    "C4.7": ("src/keel/eval_tools.py", "tests/test_eval_tools.py",
             "Local profiling helper"),
    "A1.14": ("src/keel/local_ops.py", "tests/test_local_ops.py",
             "Extra instruction files by glob with URL approval gate"),
    "A1.15": ("src/keel/local_ops.py", "tests/test_local_ops.py",
             "Small-model roles with per-agent overrides"),
    "A1.21": ("src/keel/local_ops.py", "tests/test_local_ops.py",
             "Old-version removal computation before install"),
    "B2.4": ("src/keel/misc_features.py", "tests/test_misc_features.py",
             "Bundled specialist agent prompts"),
    "B2.7": ("src/keel/docpacks.py",
             "tests/test_docpacks.py tests/test_misc_features.py",
             "Real offline documentation packs: local Markdown indexing with "
             "BM25 ranking, highlighted snippet search, persisted packs, "
             "capability and CLI surfaces"),
    "B4.6": ("src/keel/views.py",
             "tests/test_views.py tests/test_misc_features.py",
             "Real fleet views: kanban board, nested agent org chart, "
             "per-agent cost ranking and live-activity timeline"),
    "B4.7": ("src/keel/views.py",
             "tests/test_views.py tests/test_misc_features.py",
             "Real observability views: token waterfall with inline SVG, "
             "nested flame graph and structured prompt diff"),
    "C4.1": ("src/keel/debugger.py", "tests/test_debugger.py",
             "Real Python debugger with breakpoints, stepping and inspection"),
    "C4.9": ("src/keel/git_extras_runtime.py", "tests/test_git_extras_runtime.py",
             "Real git extras (status/log/blame/commit) with write gating"),
    "C8.3": ("src/keel/misc_features.py", "tests/test_misc_features.py",
             "Behavior anomaly detection"),
    "B5.7": ("site/roadmap.html", "tests/test_ci_helpers.py",
             "Curated public roadmap and FAQ page"),
    "C11.7": ("site/trademark.html", "tests/test_ci_helpers.py",
              "Trademark guidelines and abuse contact page (draft)"),
    "B7.3": ("src/keel/ci_helpers.py", "tests/test_ci_helpers.py",
             "Accessibility CI gate helper"),
    "B7.5": ("src/keel/ci_helpers.py", "tests/test_ci_helpers.py",
             "Flaky-test quarantine with owner and expiry"),
    "B7.9": ("src/keel/ci_helpers.py", "tests/test_ci_helpers.py",
             "Per-milestone kickoff prompt with stop condition"),
    "A2.1": ("src/keel/voice_tasks.py", "tests/test_voice_tasks.py",
             "Real confirmed voice-to-task handoff queue"),
    "A3.9": ("src/keel/admin_page.py",
             "tests/test_admin_page.py tests/test_final_features.py",
             "Real operator Admin page in both UI trees backed by "
             "core.admin.overview aggregating genuine local health, resource "
             "meters/limits, idle, flags, capability audit and diagnostics "
             "with loading/empty/error/permission-denied states"),
    "A1.19": ("src/keel/integrations.py", "tests/test_integrations.py",
             "CI adapter with local transport and mock-based integration tests (own CI required for live run)"),
    "B2.5": ("src/keel/final_features.py", "tests/test_final_features.py",
             "Deep-research result with citation slots"),
    "B4.8": ("src/keel/platform_gaps.py", "tests/test_gap_closure.py",
                 "Locally generated pinned self-signed TLS identity, QR pairing payload, explicit approvals; phone reachability remains external"),
    "B4.9": ("src/keel/final_features.py", "tests/test_gap_closure.py",
                 "High-legibility OFL Work Sans font option and functional vim composer keybindings in both UI trees, verified in browser"),
    "B4.11": ("src/keel/backups.py", "tests/test_backups.py tests/test_backup_endpoints.py",
              "Real encrypted backup/restore exposed through the HTTP bridge"),
    "B4.14": ("src/keel/external_adapters.py", "tests/test_external_adapters.py",
             "Delta update planner with opt-in beta channel"),
    "B5.8": ("src/keel/final_features.py", "tests/test_final_features.py",
             "Shared string catalogs for localized website"),
    "B6.4": ("src/keel/final_features.py", "tests/test_final_features.py",
             "Private org update mirror descriptor"),
    "B6.6": ("src/keel/platform_gaps.py", "tests/test_gap_closure.py",
                 "Per-organization audit export (JSONL/CSV) and retention config with real filtering of local audit records"),
    "C1.2": ("src/keel/release_gaps.py", "tests/test_gap_closure.py",
                 "Generated Scoop/Chocolatey/Flatpak/Snap/AUR/Nix manifests with explicit proprietary-freeware acceptance checks"),
    "C1.7": ("src/keel/cowork_channels.py", "tests/test_cowork_channels.py",
             "Real WAV meeting audio and ICS calendar parsing"),
    "C11.3": ("src/keel/final_features.py", "tests/test_final_features.py",
              "Source-leak incident runbook"),
    "C11.8": ("src/keel/platform_gaps.py", "tests/test_gap_closure.py",
                 "Per-build deterrent canary identifier and honest status of unapplied obfuscation measures; not a security boundary"),
    "C4.10": ("src/keel/integrations.py", "tests/test_integrations.py",
             "SSH/WSL/devcontainer adapters with mock integration tests"),
    "C4.11": ("src/keel/document_gaps.py", "tests/test_gap_closure.py",
                 "Real pixel-level UI visual diff with Pillow, console/network event normalization from captured sessions"),
    "C1.6": ("src/keel/agent_profiles.py", "tests/test_agent_profiles.py",
             "Agent looks (avatar/color/voice) in persisted profiles"),
    "C2.3": ("src/keel/inline_completion.py", "tests/test_inline_completion.py tests/test_duet.py",
             "Duet builder/reviewer with real local inline completion"),
    "A3.11": ("src/keel/last_features.py", "tests/test_last_features.py",
              "Headless deployment operations guide"),
    "A3.8": ("src/keel/platform_gaps.py", "tests/test_gap_closure.py",
                 "Local site toolkit: encrypted secret probe, read-only DB browser, scheduled jobs, analytics and escaped element editor"),
    "B2.13": ("src/keel/integrations.py", "tests/test_integrations.py",
             "Local image-generation command adapter (user-installed engine)"),
    "B5.6": ("src/keel/document_gaps.py", "tests/test_gap_closure.py",
                 "Gallery generated from real screenshots of the running Keel UI, published at site/screenshots/index.html with no stock images"),
    "C1.11": ("src/keel/platform_gaps.py", "tests/test_gap_closure.py",
                 "Approval-gated local task executor with program allowlist, shell=False execution, timeouts and persisted results"),
    "C1.5": ("src/keel/last_features.py", "tests/test_last_features.py",
             "Per-integration builder/operator guides"),
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
            # IMPLEMENTED values may contain several space-separated paths;
            # keep the registry schema clean by splitting them into tokens.
            "test_references": str(test_file).split() if test_file else [],
            "implementation_tier": classify_tier(
                feature_id, [source_file] if source_file else []),
            "verification_evidence": evidence,
            "owner_approval_required": feature_id in {
                "B6.6",
                "C11.1", "C11.2", "C11.5", "C11.8",
            },
        })
    return features


# Addendum 7 tool contracts implemented by keel/src/keel/tool_contracts.py
# with 60 contract tests (see master-plan-v6-tool-contracts-evidence.md).
TOOL_CONTRACT_IDS = frozenset({
    "E1.1", "E1.2", "E1.3", "E1.4", "E1.5", "E1.6", "E1.7",
    "E1.8", "E1.9", "E1.10", "E1.11", "E1.12", "E1.13", "E1.14",
    "E1.15", "E1.16", "E1.17", "E1.18", "E1.19", "E1.20", "E1.21",
    "E2.1", "E2.2", "E2.3", "E2.4", "E2.5",
    "E4.1", "E4.2", "E4.9", "E4.10", "E4.11", "E4.12",
    "E6.9", "E7.19",
})
X1_REPO_TOKENS = frozenset({"X1.7", "X1.8"})
X1_REPO_SRC = ["src/keel/repo_map.py"]
X1_REPO_TESTS = ["tests/test_repo_map.py"]
X1_REPO_EVIDENCE = (
    "Repo map ranking (centrality + recency, token-budgeted, deterministic) "
    "and injectable token counter with calibrated fallback implemented in "
    "repo_map.py with 23 passing tests; no outbound calls.")
X1_STEERING_TOKENS = frozenset({"X1.13"})
X1_STEERING_SRC = ["src/keel/steering.py"]
X1_STEERING_TESTS = ["tests/test_steering.py"]
X1_STEERING_EVIDENCE = (
    "Steering/interrupt controller with queue, steer-at-boundary and "
    "abort-resume modes, byte-exact partial-output preservation and "
    "thread-safe cancellation; 20 passing tests verified non-flaky.")
X1_DIALECT_TOKENS = frozenset({"X1.1", "X1.2", "X1.3"})
X1_DIALECT_SRC = ["src/keel/model_dialects.py"]
X1_DIALECT_TESTS = ["tests/test_model_dialects.py"]
X1_DIALECT_EVIDENCE = (
    "Tool-call dialect adapters (JSON/XML/Hermes/ReAct + variants), offline "
    "chat-template loading with path containment, and reasoning-output "
    "splitting with opt-in history inclusion; 70 passing tests.")
X1_EDIT_TOKENS = frozenset({"X1.4", "X1.5"})
X1_EDIT_SRC = ["src/keel/edit_formats.py"]
X1_EDIT_TESTS = ["tests/test_edit_formats.py"]
X1_EDIT_EVIDENCE = (
    "Selectable edit formats (whole-file, search/replace, unified diff, "
    "line-range) and fuzzy patch application with ambiguity/threshold guards "
    "and typed model-facing errors; 26 passing tests.")
W2_AGENT_TOKENS = frozenset({"W2.1", "W2.2", "W2.3", "W2.4", "W2.6", "W2.8",
                             "W2.9", "W2.11"})
W2_AGENT_SRC = ["src/keel/agent_contracts.py"]
W2_AGENT_TESTS = ["tests/test_agent_contracts.py"]
W2_AGENT_EVIDENCE = (
    "Agent file/subagent contracts: nested IDs, modes, built-ins, step limits, "
    "launch permission monotonicity, prompt composition, merge semantics and "
    "plan-folder containment; 35 passing tests.")
# Four further implementation batches merged in the parallel operation.
BATCH4_TOKENS = frozenset({
    # W3 permissions
    "W3.1", "W3.2", "W3.3", "W3.4", "W3.6", "W3.7", "W3.8", "W3.9",
    "W3.10", "W3.12", "W3.13",
    # D2 session/event model
    "D2.1", "D2.3", "D2.5", "D2.7", "D2.8", "D2.9", "D2.10", "D2.11",
    "D2.13", "D2.15", "D2.16",
    # Y1 MCP/plugin config
    "Y1.2", "Y1.3", "Y1.4", "Y1.5", "Y1.6", "Y1.7", "Y1.8", "Y1.9",
    "Y1.16", "Y1.17", "Y1.19", "Y1.20", "Y1.24", "Y1.30",
})
BATCH4_SRC = ["src/keel/permission_contracts.py", "src/keel/session_contracts.py",
              "src/keel/mcp_contracts.py"]
BATCH4_TESTS = ["tests/test_permission_contracts.py",
                "tests/test_session_contracts.py", "tests/test_mcp_contracts.py"]
BATCH4_EVIDENCE = (
    "Parallel batch: W3 permission contracts (66 tests, authoritative "
    "first-match preserved per DECISIONS D-001), D2 session/event contracts "
    "(32 tests), Y1 MCP/plugin config contracts (57 tests).")
D3_SEAM_TOKENS = frozenset({"D3.1", "D3.2", "D3.6", "D3.7", "D3.8", "D3.9",
                            "D3.11", "D3.13", "D3.14", "D3.18"})
D3_SEAM_SRC = ["src/keel/capability_seams.py"]
D3_SEAM_TESTS = ["tests/test_capability_seams.py"]
D3_SEAM_EVIDENCE = (
    "Capability seam contracts: typed role registration, provider swap "
    "descriptors, honest package classification, spill preview with redaction, "
    "monotone deny guards, workspace containment; 28 passing tests.")
E6_PROVIDER_TOKENS = frozenset({"E6.1", "E6.5", "E6.8", "E6.10"})
E6_PROVIDER_SRC = ["src/keel/provider_contracts.py"]
E6_PROVIDER_TESTS = ["tests/test_provider_contracts.py"]
E6_PROVIDER_EVIDENCE = (
    "Provider config contracts: write-only secret descriptors, third-party "
    "catalog validation (https/allowlist), per-model capability fields, "
    "request compatibility switches; 85 passing tests, no credentials.")
Y2_TRANSCRIPT_TOKENS = frozenset({"Y2.1", "Y2.2", "Y2.3", "Y2.4", "Y2.5",
                                  "Y2.6", "Y2.7", "Y2.8", "Y2.14", "Y2.20"})
Y2_TRANSCRIPT_SRC = ["src/keel/transcript_contracts.py"]
Y2_TRANSCRIPT_TESTS = ["tests/test_transcript_contracts.py"]
Y2_TRANSCRIPT_EVIDENCE = (
    "Transcript/history contracts: typed rows, model/durable history split, "
    "screenshot ring, orphaned tool-call repair, VNC credential isolation, "
    "exposure defaults; 39 passing tests.")
W7_SECURITY_TOKENS = frozenset({"W7.1", "W7.3", "W7.4", "W7.5", "W7.6",
                                "W7.8", "W7.10", "W7.13", "W7.14", "W7.16",
                                "W7.17", "W7.19"})
W7_SECURITY_SRC = ["src/keel/security_contracts.py"]
W7_SECURITY_TESTS = ["tests/test_security_contracts.py"]
W7_SECURITY_EVIDENCE = (
    "Security contracts: trust model, SSRF-safe fetch, security headers, "
    "safe Markdown rendering, publish path safety, inbound HMAC/replay "
    "defense, session cookies; 125 passing tests (1 platform skip).")
A6_TOKENS = frozenset({
    "E7.2", "E7.6", "E7.18", "E7.20", "E7.21", "E7.23",
    "D1.1", "D1.4", "D1.5", "D1.10", "D1.12",
    "Y3.2", "Y3.4", "Y3.6", "Y3.9", "Y3.10", "Y3.11", "Y3.13",
    "W5.1", "W5.2", "W5.3", "W5.4",
})
A6_SRC = ["src/keel/runtime_contracts.py", "src/keel/plugin_contracts.py",
          "src/keel/config_contracts.py", "src/keel/command_contracts.py"]
A6_TESTS = ["tests/test_runtime_contracts.py", "tests/test_plugin_contracts.py",
            "tests/test_config_contracts.py", "tests/test_command_contracts.py"]
A6_EVIDENCE = (
    "Parallel batch: E7 runtime contracts (48 tests), D1 plugin architecture "
    "(39 tests), Y3 config/setup (22 tests), W5 commands (18 tests). All "
    "additive stdlib descriptor layers with documented integration seams.")
E5_DESKTOP_TOKENS = frozenset({"E5.1", "E5.4", "E5.9", "E5.12", "E5.14",
                               "E5.15"})
E5_DESKTOP_SRC = ["src/keel/desktop_contracts.py"]
E5_DESKTOP_TESTS = ["tests/test_desktop_contracts.py"]
E5_DESKTOP_EVIDENCE = (
    "Desktop/packaging contracts: framed-byte transport, single-instance lock, "
    "plugin script rejection, per-target isolation, credential stripping, "
    "upload guard; 30 passing adversarial tests.")
X0_PLAN_TOKENS = frozenset({"X0.1", "X0.2", "X0.3", "X0.4", "X0.6", "X0.7",
                            "X0.8", "X0.10"})
X0_PLAN_SRC = ["src/keel/plan_corrections.py"]
X0_PLAN_TESTS = ["tests/test_plan_corrections.py"]
X0_PLAN_EVIDENCE = (
    "Plan-correction verification module proves each repo-root artifact exists "
    "and is valid (P0 share, M19 splits, dependency graph, Duet modes, "
    "free-tier register, license gate, offline lane, clean-room specs) with "
    "14 passing tests incl. 9 tamper cases.")
X9_RELIABILITY_TOKENS = frozenset({"X9.1", "X9.3", "X9.5", "X9.7"})
X9_RELIABILITY_SRC = ["src/keel/reliability_contracts.py"]
X9_RELIABILITY_TESTS = ["tests/test_reliability_contracts.py"]
X9_RELIABILITY_EVIDENCE = (
    "Reliability contracts: fixture model server, provider contract suite "
    "against real adapters, cross-platform path/permission matrix, migration "
    "matrix with checksums; 39 passing tests.")
X5_GUARD_TOKENS = frozenset({"X5.1", "X5.5", "X5.6", "X5.9"})
X5_GUARD_SRC = ["src/keel/clipboard_guard.py"]
X5_GUARD_TESTS = ["tests/test_clipboard_guard.py"]
X5_GUARD_EVIDENCE = (
    "Clipboard/screen guard + sensitive-project mode, mass-change guard and "
    "filesystem change journal; 31 passing adversarial tests.")
D5_RESPONSIBLE_TOKENS = frozenset({"D5.1", "D5.2", "D5.3", "D5.4", "D5.5"})
D5_RESPONSIBLE_SRC = ["src/keel/responsible_use.py"]
D5_RESPONSIBLE_TESTS = ["tests/test_responsible_use.py"]
D5_RESPONSIBLE_EVIDENCE = (
    "Responsible-use disclosures, sandbox-limits wording, safety checklist, "
    "warranty disclaimer (G5 draft) and fail-closed sandbox-failure policy; "
    "25 passing tests + generated RESPONSIBLE-USE.md.")
D4_COMPOSITION_TOKENS = frozenset({"D4.2", "D4.7", "D4.11"})
D4_COMPOSITION_SRC = ["src/keel/composition_contracts.py"]
D4_COMPOSITION_TESTS = ["tests/test_composition_contracts.py"]
D4_COMPOSITION_EVIDENCE = (
    "Composition contracts: typed layers, deterministic merge, protected "
    "core, path containment, secret redaction; 51 passing adversarial tests.")
Y4_IDENTITY_TOKENS = frozenset({"Y4.3", "Y4.9", "Y4.13"})
Y4_IDENTITY_SRC = ["src/keel/identity_contracts.py"]
Y4_IDENTITY_TESTS = ["tests/test_identity_contracts.py"]
Y4_IDENTITY_EVIDENCE = (
    "Identity contracts: first-boot sign-in test-fire, persona/rigor/routing "
    "descriptor with originality gate, version badge + zero-secret scan; "
    "69 passing adversarial tests.")
V_INVARIANT_TOKENS = frozenset({"V1", "V2", "V5", "V16", "V24", "V26", "V31"})
V_INVARIANT_SRC = ["src/keel/invariant_contracts.py"]
V_INVARIANT_TESTS = ["tests/test_invariant_contracts.py"]
V_INVARIANT_EVIDENCE = (
    "Invariant/conformance contracts: scoped plugin tree, policy simulator "
    "trace, strictness presets, Keel gate catalog, tool conformance kit, "
    "request reconstruction, transport spike descriptors; 56 passing tests.")
E34_RESULT_TOKENS = frozenset({"E3.3", "E3.8", "E4.5", "E4.8", "E4.15"})
E34_RESULT_SRC = ["src/keel/result_contracts.py"]
E34_RESULT_TESTS = ["tests/test_result_contracts.py"]
E34_RESULT_EVIDENCE = (
    "Result/snapshot contracts: agent-name grammar, result object with "
    "diagnostic sanitization, versioned snapshots, test isolation, keyless "
    "change log; 60 passing adversarial tests.")
D7_SCHEDULER_TOKENS = frozenset({"D7.1", "D7.9", "D7.12", "D7.19"})
D7_SCHEDULER_SRC = ["src/keel/gate_scheduler.py"]
D7_SCHEDULER_TESTS = ["tests/test_gate_scheduler.py"]
D7_SCHEDULER_EVIDENCE = (
    "Dev-workflow contracts: gate graph with bounded concurrency, strict "
    "dependency linker, CI lane descriptors, minimal SDK benchmark method; "
    "77 passing adversarial tests.")
BUILDER_TOKENS = frozenset({"X10.1", "X10.2", "X10.4", "X6.7", "X8.1", "X8.2"})
BUILDER_SRC = ["src/keel/builder_contracts.py"]
BUILDER_TESTS = ["tests/test_builder_contracts.py"]
BUILDER_EVIDENCE = (
    "Builder contracts: definition-of-done, provenance file, G1-G7 stop list, "
    "config validation with suggestions, component catalog, design tokens; "
    "24 passing tests. Y6.4 intentionally not implemented (owner gate).")

TOOL_CONTRACT_SRC = ["src/keel/tool_contracts.py",
                     "src/keel/tool_contracts_bridge.py"]
TOOL_CONTRACT_TESTS = ["tests/test_tool_contracts.py",
                       "tests/test_tool_contracts_bridge.py"]
TOOL_CONTRACT_EVIDENCE = (
    "Addendum 7 canonical tool pipeline implemented in tool_contracts.py "
    "(20 named contracts) with 60 passing contract tests and a native "
    "registry conformance bridge (47 tools, 0 problems).")


def _load_extra_features() -> list[dict]:
    """Load features from addenda 3-7 normalized extraction files."""
    out: list[dict] = []
    for filename, source_doc in EXTRA_SOURCES:
        path = EXTRACTED / filename
        if not path.is_file():
            raise FileNotFoundError(
                f"missing canonical extraction {path}; regenerate from the "
                f"source document {source_doc}")
        data = json.loads(path.read_text(encoding="utf-8"))
        for f in data["features"]:
            fid = str(f.get("id", ""))
            if not fid:
                continue
            # Normalize to the registry schema; never claim verification just
            # because a source or test file path happens to be mentioned.
            src = str(f.get("references") or "")
            tags = str(f.get("tag/source") or "")
            implemented_ids = (TOOL_CONTRACT_IDS | X1_REPO_TOKENS |
                               X1_STEERING_TOKENS | X1_DIALECT_TOKENS |
                               X1_EDIT_TOKENS | W2_AGENT_TOKENS | BATCH4_TOKENS |
                               D3_SEAM_TOKENS | E6_PROVIDER_TOKENS |
                               Y2_TRANSCRIPT_TOKENS | W7_SECURITY_TOKENS |
                               A6_TOKENS | E5_DESKTOP_TOKENS | X0_PLAN_TOKENS |
                               X9_RELIABILITY_TOKENS | X5_GUARD_TOKENS |
                               D5_RESPONSIBLE_TOKENS | D4_COMPOSITION_TOKENS |
                               Y4_IDENTITY_TOKENS | V_INVARIANT_TOKENS |
                               E34_RESULT_TOKENS | D7_SCHEDULER_TOKENS |
                               BUILDER_TOKENS)
            verified = fid in implemented_ids
            src_files = (TOOL_CONTRACT_SRC if fid in TOOL_CONTRACT_IDS else
                         X1_REPO_SRC if fid in X1_REPO_TOKENS else
                         X1_STEERING_SRC if fid in X1_STEERING_TOKENS else
                         X1_DIALECT_SRC if fid in X1_DIALECT_TOKENS else
                         X1_EDIT_SRC if fid in X1_EDIT_TOKENS else
                         W2_AGENT_SRC if fid in W2_AGENT_TOKENS else
                         BATCH4_SRC if fid in BATCH4_TOKENS else
                         D3_SEAM_SRC if fid in D3_SEAM_TOKENS else
                         E6_PROVIDER_SRC if fid in E6_PROVIDER_TOKENS else
                         Y2_TRANSCRIPT_SRC if fid in Y2_TRANSCRIPT_TOKENS else
                         W7_SECURITY_SRC if fid in W7_SECURITY_TOKENS else
                         A6_SRC if fid in A6_TOKENS else
                         E5_DESKTOP_SRC if fid in E5_DESKTOP_TOKENS else
                         X0_PLAN_SRC if fid in X0_PLAN_TOKENS else
                         X9_RELIABILITY_SRC if fid in X9_RELIABILITY_TOKENS else
                         X5_GUARD_SRC if fid in X5_GUARD_TOKENS else
                         D5_RESPONSIBLE_SRC if fid in D5_RESPONSIBLE_TOKENS else
                         D4_COMPOSITION_SRC if fid in D4_COMPOSITION_TOKENS else
                         Y4_IDENTITY_SRC if fid in Y4_IDENTITY_TOKENS else
                         V_INVARIANT_SRC if fid in V_INVARIANT_TOKENS else
                         E34_RESULT_SRC if fid in E34_RESULT_TOKENS else
                         D7_SCHEDULER_SRC if fid in D7_SCHEDULER_TOKENS else
                         BUILDER_SRC if fid in BUILDER_TOKENS else [])
            test_files = (TOOL_CONTRACT_TESTS if fid in TOOL_CONTRACT_IDS else
                          X1_REPO_TESTS if fid in X1_REPO_TOKENS else
                          X1_STEERING_TESTS if fid in X1_STEERING_TOKENS else
                          X1_DIALECT_TESTS if fid in X1_DIALECT_TOKENS else
                          X1_EDIT_TESTS if fid in X1_EDIT_TOKENS else
                          W2_AGENT_TESTS if fid in W2_AGENT_TOKENS else
                          BATCH4_TESTS if fid in BATCH4_TOKENS else
                          D3_SEAM_TESTS if fid in D3_SEAM_TOKENS else
                          E6_PROVIDER_TESTS if fid in E6_PROVIDER_TOKENS else
                          Y2_TRANSCRIPT_TESTS if fid in Y2_TRANSCRIPT_TOKENS else
                          W7_SECURITY_TESTS if fid in W7_SECURITY_TOKENS else
                          A6_TESTS if fid in A6_TOKENS else
                          E5_DESKTOP_TESTS if fid in E5_DESKTOP_TOKENS else
                          X0_PLAN_TESTS if fid in X0_PLAN_TOKENS else
                          X9_RELIABILITY_TESTS if fid in X9_RELIABILITY_TOKENS else
                          X5_GUARD_TESTS if fid in X5_GUARD_TOKENS else
                          D5_RESPONSIBLE_TESTS if fid in D5_RESPONSIBLE_TOKENS else
                          D4_COMPOSITION_TESTS if fid in D4_COMPOSITION_TOKENS else
                          Y4_IDENTITY_TESTS if fid in Y4_IDENTITY_TOKENS else
                          V_INVARIANT_TESTS if fid in V_INVARIANT_TOKENS else
                          E34_RESULT_TESTS if fid in E34_RESULT_TOKENS else
                          D7_SCHEDULER_TESTS if fid in D7_SCHEDULER_TOKENS else
                          BUILDER_TESTS if fid in BUILDER_TOKENS else [])
            evidence = (TOOL_CONTRACT_EVIDENCE if fid in TOOL_CONTRACT_IDS else
                        X1_REPO_EVIDENCE if fid in X1_REPO_TOKENS else
                        X1_STEERING_EVIDENCE if fid in X1_STEERING_TOKENS else
                        X1_DIALECT_EVIDENCE if fid in X1_DIALECT_TOKENS else
                        X1_EDIT_EVIDENCE if fid in X1_EDIT_TOKENS else
                        W2_AGENT_EVIDENCE if fid in W2_AGENT_TOKENS else
                        BATCH4_EVIDENCE if fid in BATCH4_TOKENS else
                        D3_SEAM_EVIDENCE if fid in D3_SEAM_TOKENS else
                        E6_PROVIDER_EVIDENCE if fid in E6_PROVIDER_TOKENS else
                        Y2_TRANSCRIPT_EVIDENCE if fid in Y2_TRANSCRIPT_TOKENS else
                        W7_SECURITY_EVIDENCE if fid in W7_SECURITY_TOKENS else
                        A6_EVIDENCE if fid in A6_TOKENS else
                        E5_DESKTOP_EVIDENCE if fid in E5_DESKTOP_TOKENS else
                        X0_PLAN_EVIDENCE if fid in X0_PLAN_TOKENS else
                        X9_RELIABILITY_EVIDENCE if fid in X9_RELIABILITY_TOKENS else
                        X5_GUARD_EVIDENCE if fid in X5_GUARD_TOKENS else
                        D5_RESPONSIBLE_EVIDENCE if fid in D5_RESPONSIBLE_TOKENS else
                        D4_COMPOSITION_EVIDENCE if fid in D4_COMPOSITION_TOKENS else
                        Y4_IDENTITY_EVIDENCE if fid in Y4_IDENTITY_TOKENS else
                        V_INVARIANT_EVIDENCE if fid in V_INVARIANT_TOKENS else
                        E34_RESULT_EVIDENCE if fid in E34_RESULT_TOKENS else
                        D7_SCHEDULER_EVIDENCE if fid in D7_SCHEDULER_TOKENS else
                        BUILDER_EVIDENCE if fid in BUILDER_TOKENS else "")
            out.append({
                "id": fid,
                "feature": str(f.get("feature") or fid),
                "detail": str(f.get("detail") or ""),
                "source_document": source_doc,
                "source_feature_id": fid,
                "section": str(f.get("section") or ""),
                "reference_source": tags or src,
                "milestone": _first_milestone(f.get("milestone")),
                "priority": _normalize_priority(f.get("priority")),
                "original_priority": str(f.get("priority") or ""),
                "status": (
                    "blocked" if fid in OWNER_BLOCKED else
                    "verified" if verified else "not_started"),
                "source_files": src_files,
                "dependencies": _as_list(f.get("dependencies")),
                "acceptance_criteria": _as_list(f.get("acceptance_criteria")),
                "test_references": test_files,
                # Tier describes implementation type, never progress status.
                # Not-started rows are still typed as local_module unless the
                # source marks them external/owner-gated (progress lives in
                # `status`).
                "implementation_tier": "local_module" if verified or fid not in OWNER_BLOCKED else "owner_gated",
                "verification_evidence": evidence,
                "owner_approval_required": fid in OWNER_BLOCKED,
                "external_prerequisite": "",
                # Clean-room verification (reference-behavior/deepseek-*.md)
                # contradicted two source claims; record this rather than
                # silently dropping the original requirement.
                "known_limitations": (
                    "Reference claim contradicted by source verification "
                    "(keel/docs/research/reference-behavior/"
                    "deepseek-harness-behavior.md); re-scope before claiming "
                    "behavioral parity"
                    if fid in {"E5.1", "E5.8"} else
                    "Unverifiable reference claim; treat as unproven until "
                    "native/source evidence exists"
                    if fid in {"D7.18", "E5.6", "E5.19", "E6.13", "E7.17",
                               "E7.29", "E7.33"} else ""),
            })
    return out


def _first_milestone(value) -> str:
    text = str(value or "")
    m = M_RE.search(text)
    return m.group(0) if m else ("unassigned" if text else "unassigned")


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    return [str(value)] if str(value).strip() else []


def _normalize_priority(value) -> str:
    text = str(value or "")
    return text if text in {"P0", "P1", "P2"} else "P1"


def _rerank_priorities(features: list[dict]) -> dict:
    """Addendum 3 X0.1: cap P0 near 25% of all rows.

    P0 is retained only for (a) explicit plan-correction rows X0.*,
    (b) rows in foundation milestones M0-M5/M7, and (c) security-critical
    rows. All other source-P0 rows become P1 with the original value kept in
    ``original_priority`` for traceability. This is a documented schema-level
    re-ranking, not a silent change to security behavior.
    """
    for f in features:
        if f.get("priority") != "P0" and f.get("original_priority") != "P0":
            continue
        fid = str(f.get("id", ""))
        if fid.startswith("X0.") or FOUNDATION_MS.search(str(f.get("milestone", ""))):
            f["priority"] = "P0"
            continue
        text = str(f.get("feature", "")) + " " + str(f.get("detail", ""))
        f["priority"] = "P0" if SECURITY_TERMS.search(text) else "P1"
    from collections import Counter
    return dict(Counter(f.get("priority") for f in features))


def build() -> dict:
    features = _parse_addendum(ADDENDUM1, "Keel_Plan_v5_Addendum_Missed_Features.md")
    features += _parse_addendum(ADDENDUM2, "Keel_Plan_v5_Addendum_2_More_Features.md")
    # Base rows need the extended schema fields used by the addenda 3-7 rows.
    for f in features:
        f.setdefault("original_priority", f["priority"])
        f.setdefault("external_prerequisite", "")
        f.setdefault("known_limitations", "")
        f.setdefault("reference_source", f["source_document"])
        f.setdefault("detail", f["feature"])
        f.setdefault("section", "")
    features += _load_extra_features()
    counts = _rerank_priorities(features)
    features.sort(key=lambda f: f["id"])
    ids = [f["id"] for f in features]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate feature IDs in unified registry")
    return {
        "schema_version": 2,
        "authoritative_plan": "Keel_Master_Plan_v6.md",
        "source_documents": [
            "Keel_Master_Plan_v5.md",
            "Keel_Plan_v5_Addendum_Missed_Features.md",
            "Keel_Plan_v5_Addendum_2_More_Features.md",
            "Keel_Plan_v5_Addendum_3_Gaps_and_Advanced.md",
            "Keel_Plan_v5_Addendum_4_Sourced_Features_and_Builder_Guide.md",
            "Keel_Plan_v5_Addendum_5_DeepSeek_Harness_and_Deep_Reads.md",
            "Keel_Plan_v5_Addendum_6_DeepSeek_Harness_Full_Teardown.md",
            "Keel_Plan_v5_Addendum_7_DeepSeek_Deep_Reads.md",
        ],
        "priority_counts": counts,
        "note": (
            "Complete reconciliation of all 8 uploaded specification "
            "documents: 228 base rows (addenda 1-2) + 637 rows (addenda 3-7) "
            "= 865. Extracted feature data is canonicalized under "
            "keel/docs/plan-sources/extracted/. v5 Sections 12-16, Section 13 "
            "mapping and Appendices A-D remain absent from the supplied "
            "source and are not reconstructed."),
        "features": features,
    }


def main() -> None:
    doc = build()
    OUT.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    PARITY.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(doc['features'])} features to PLAN-INDEX.json and parity.json")


if __name__ == "__main__":
    main()
