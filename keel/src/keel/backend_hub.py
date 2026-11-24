"""Unified backend service hub for the v6 backend modules.

The modules implemented for the 865-row Master Plan v6 are real, tested
contract/service libraries. This hub is their single integration point with
the live Keel runtime: it registers every implemented feature ID, exposes a
strictly allowlisted dispatcher for deterministic module functions, and is
consumed by keel.capabilities - the authenticated, permission-aware surface
used by the web bridge, CLI, TUI and desktop shell.

No capability here is a placeholder: invoke() calls real module functions and
returns their real results or an explicit typed error.

"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any


MODULE_FEATURES: dict[str, tuple[str, ...]] = {

    "d3_backend": (

        "D3.1", "D3.10", "D3.11", "D3.12", "D3.13", "D3.14",

        "D3.15", "D3.16", "D3.17", "D3.18", "D3.19", "D3.2",

        "D3.20", "D3.21", "D3.22", "D3.23", "D3.3", "D3.4",

        "D3.5", "D3.6", "D3.7", "D3.8", "D3.9", "V8",

        "X6.10",

    ),

    "d6_reliability_backend": (

        "D6.1", "D6.10", "D6.11", "D6.12", "D6.13", "D6.15",

        "D6.16", "D6.19", "D6.22", "D6.24", "D6.25", "D6.3",

        "D6.4", "D6.5", "D6.6", "D6.7", "D6.8", "D6.9",

    ),

    "d7_workflow_backend": (

        "D7.1", "D7.10", "D7.11", "D7.12", "D7.13", "D7.14",

        "D7.15", "D7.16", "D7.17", "D7.18", "D7.19", "D7.2",

        "D7.20", "D7.3", "D7.4", "D7.5", "D7.6", "D7.7",

        "D7.8", "D7.9",

    ),

    "e3_backend": (

        "E3.1", "E3.10", "E3.11", "E3.12", "E3.13", "E3.14",

        "E3.15", "E3.2", "E3.3", "E3.4", "E3.5", "E3.6",

        "E3.7", "E3.8", "E3.9",

    ),

    "e5_backend": (

        "E5.10", "E5.11", "E5.13", "E5.16", "E5.17", "E5.18",

        "E5.19", "E5.2", "E5.3", "E5.5", "E5.6", "E5.7",

        "E5.8",

    ),

    "e6_x5_x6_backend": (

        "E6.11", "E6.12", "E6.13", "E6.14", "E6.2", "E6.3",

        "E6.4", "E6.6", "E6.7", "X5.10", "X5.11", "X5.12",

        "X5.13", "X5.2", "X5.3", "X5.4", "X5.7", "X5.8",

        "X6.1", "X6.10", "X6.2", "X6.3", "X6.4", "X6.5",

        "X6.6", "X6.8", "X6.9",

    ),

    "e7_runtime_backend": (

        "D3.8", "E7.1", "E7.10", "E7.11", "E7.12", "E7.13",

        "E7.14", "E7.15", "E7.16", "E7.17", "E7.22", "E7.24",

        "E7.25", "E7.26", "E7.27", "E7.28", "E7.29", "E7.3",

        "E7.30", "E7.31", "E7.32", "E7.33", "E7.34", "E7.35",

        "E7.36", "E7.37", "E7.38", "E7.39", "E7.4", "E7.40",

        "E7.41", "E7.42", "E7.43", "E7.5", "E7.7", "E7.8",

        "E7.9", "V23", "W3.11",

    ),

    "small_groups_backend": (

        "D2.12", "D2.14", "D2.17", "D2.2", "D2.4", "D2.6",

        "E4.13", "E4.14", "E4.3", "E4.4", "E4.6", "E4.7",

        "W2.10", "W2.5", "W2.7", "W3.11", "W3.5", "W5.5",

        "W5.6", "W5.7", "W6.2", "W6.4", "W6.5", "W6.6",

        "W8.1", "W8.2", "W8.3", "W8.4", "W9.1", "W9.2",

        "W9.3", "W9.4", "W9.5", "W9.6", "X0.2b", "X0.5",

        "X0.9", "X10.3", "X10.5", "X10.6", "X4.1", "X4.2",

        "X4.3", "X4.4", "X4.5", "X4.6", "X4.7", "X9.10",

        "X9.2", "X9.4", "X9.6", "X9.8", "X9.9", "Y6.3",

    ),

    "v_series_backend": (

        "V1", "V10", "V11", "V12", "V13", "V14",

        "V15", "V16", "V17", "V18", "V19", "V2",

        "V20", "V21", "V22", "V23", "V24", "V25",

        "V26", "V27", "V28", "V29", "V3", "V30",

        "V31", "V4", "V5", "V6", "V7", "V8",

        "V9",

    ),

    "w1_security_backend": (

        "C11.7", "C13.5", "W1.1", "W1.11", "W1.12", "W1.13",

        "W1.14", "W1.15", "W1.16", "W1.17", "W1.2", "W1.3",

        "W1.4", "W1.5", "W1.6", "W1.7", "W1.8", "W1.9",

        "X6.10", "X6.3",

    ),

    "w4_backend": (

        "W4.1", "W4.10", "W4.11", "W4.12", "W4.13", "W4.14",

        "W4.2", "W4.3", "W4.4", "W4.5", "W4.6", "W4.7",

        "W4.8", "W4.9",

    ),

    "w7_x1_y5_d1_backend": (

        "A3.10", "D1.11", "D1.2", "D1.3", "D1.6", "D1.7",

        "D1.8", "D1.9", "W7.11", "W7.12", "W7.15", "W7.18",

        "W7.2", "W7.20", "W7.7", "W7.9", "X1.10", "X1.11",

        "X1.12", "X1.14", "X1.15", "X1.16", "X1.6", "X1.9",

        "Y3.8", "Y5.1", "Y5.2", "Y5.3", "Y5.5", "Y5.6",

        "Y5.7", "Y5.8", "Y5.9", "Z3",

    ),

    "x2_orchestration_backend": (

        "X2.1", "X2.10", "X2.11", "X2.12", "X2.13", "X2.14",

        "X2.15", "X2.16", "X2.2", "X2.3", "X2.4", "X2.5",

        "X2.6", "X2.7", "X2.8", "X2.9",

    ),

    "x3_memory_backend": (

        "X3.1", "X3.10", "X3.11", "X3.12", "X3.13", "X3.14",

        "X3.15", "X3.16", "X3.2", "X3.3", "X3.4", "X3.5",

        "X3.6", "X3.7", "X3.8", "X3.9",

    ),

    "x8_backend": (

        "X8.1", "X8.10", "X8.11", "X8.12", "X8.13", "X8.14",

        "X8.15", "X8.16", "X8.17", "X8.2", "X8.3", "X8.4",

        "X8.5", "X8.6", "X8.7", "X8.8", "X8.9",

    ),

    "y1_config_backend": (

        "V1", "Y1.1", "Y1.10", "Y1.11", "Y1.12", "Y1.13",

        "Y1.14", "Y1.15", "Y1.18", "Y1.21", "Y1.22", "Y1.23",

        "Y1.25", "Y1.26", "Y1.27", "Y1.28", "Y1.29", "Y1.31",

        "Y1.32", "Y1.33", "Y1.34", "Y1.35", "Y1.36", "Y1.37",

        "Y1.38", "Y1.39",

    ),

    "y2_backend": (

        "A3.7", "C1.11", "Y2.1", "Y2.10", "Y2.11", "Y2.12",

        "Y2.13", "Y2.14", "Y2.15", "Y2.16", "Y2.17", "Y2.18",

        "Y2.19", "Y2.20", "Y2.21", "Y2.22", "Y2.23", "Y2.24",

        "Y2.25", "Y2.8", "Y2.9",

    ),

    "y3_backend": (

        "A3.1", "A3.9", "Y3.1", "Y3.10", "Y3.11", "Y3.12",

        "Y3.13", "Y3.14", "Y3.15", "Y3.16", "Y3.17", "Y3.18",

        "Y3.19", "Y3.2", "Y3.20", "Y3.21", "Y3.3", "Y3.4",

        "Y3.5", "Y3.6", "Y3.7", "Y3.8", "Y3.9",

    ),

    "y4_d4_x7_backend": (

        "C1.9", "D4.1", "D4.10", "D4.11", "D4.12", "D4.13",

        "D4.2", "D4.3", "D4.4", "D4.5", "D4.6", "D4.7",

        "D4.8", "D4.9", "X7.1", "X7.10", "X7.2", "X7.3",

        "X7.4", "X7.5", "X7.6", "X7.7", "X7.8", "X7.9",

        "Y4.1", "Y4.10", "Y4.11", "Y4.12", "Y4.13", "Y4.14",

        "Y4.2", "Y4.3", "Y4.4", "Y4.5", "Y4.6", "Y4.7",

        "Y4.8", "Y4.9",

    ),

    "z_backend": (

        "X9.1", "Y1.29", "Y4.1", "Z1", "Z10", "Z11",

        "Z12", "Z13", "Z14", "Z15", "Z16", "Z2",

        "Z3", "Z4", "Z5", "Z6", "Z7", "Z8",

        "Z9",

    ),

}


DISPATCH: dict[str, tuple[str, ...]] = {

    "d3_backend": ('canonical_digest', 'check_metadata', 'check_offline_build'),

    "d6_reliability_backend": ('canonical_bytes', 'check_upgrade_guide', 'classify_path', 'fingerprint', 'render_mode', 'render_vendor_manifest', 'validate_plugin_config', 'validate_projection'),

    "d7_workflow_backend": ('build_breaking_notice', 'build_build_plan', 'build_face_programs', 'build_hook_set', 'check_builder_environment', 'check_contract_drift', 'check_dead_links', 'check_type_equivalence', 'extract_code_fences', 'make_build_identity'),

    "e3_backend": ('check_route', 'compute_fork_prefix', 'parse_model_route', 'resolve_child_cwd', 'validate_start_options'),

    "e5_backend": ('validate_app_id', 'validate_release_prerequisites'),

    "e6_x5_x6_backend": ('build_candidate', 'build_config_catalog', 'build_data_handling_cards', 'canonical_bytes', 'check_model_compatibility', 'digest', 'parse_models_response', 'parse_semver', 'parse_version', 'render_troubleshooting_page'),

    "e7_runtime_backend": ('make_snapshot', 'parse_at_paths', 'parse_market_index', 'parse_preset_yaml', 'resolve_session_reference', 'validate_env_fact', 'validate_index_source'),

    "small_groups_backend": ('build_palette_entries', 'normalize_agent_config', 'normalize_question', 'resolve_default_agent', 'resolve_model_precedence'),

    "v_series_backend": ('build_mcp_meta', 'canonical_bytes', 'check_fix_commit', 'check_fuzz_invariants', 'compute_surface', 'make_artifact', 'make_budget_override', 'make_case', 'make_config_rule', 'make_confirmation_rule'),

    "w1_security_backend": ('build_feedback_bundle', 'make_help', 'parse_simple_yaml', 'validate_payload', 'validate_suite_matrix'),

    "w4_backend": ('build_system_prompt', 'canonical_tool_resource', 'extract_callback_url', 'normalize_config_document', 'normalize_server_config', 'normalize_tool_name', 'normalize_tool_names', 'parse_pasted_callback', 'parse_slash_arguments', 'render_elicitation'),

    "w7_x1_y5_d1_backend": ('check_csrf_origin', 'classify_entrypoint', 'parse_install_source', 'render_history', 'render_share_html', 'resolve_profile', 'validate_plugin_manifest', 'validate_profile', 'validate_profile_name', 'validate_sdk_args'),

    "x2_orchestration_backend": ('normalize_diagnostic', 'normalize_outcome', 'parse_unified_diff'),

    "x3_memory_backend": ('_money', '_word_tokens', '_slug', '_embedding', '_cosine'),

    "x8_backend": ('build_thread_index', 'build_tray_snapshot', 'build_undo_action', 'canonical_bytes', 'check_contrast', 'normalize_zoom', 'render_unified', 'resolve_citation', 'resolve_preferences', 'validate_copy_deck'),

    "y1_config_backend": ('build_docs_pages', 'parse_instruction_sources', 'parse_plugin_manifest', 'parse_plugin_source', 'parse_references', 'parse_skill_sources', 'resolve_media_limits', 'resolve_tool_output_limits', 'resolve_update_mode', 'validate_base64_size'),

    "y2_backend": ('build_project_status', 'build_provider_identity', 'canonical_bytes', 'parse_cron', 'parse_mentions', 'parse_scheduler_flag', 'plan_compaction', 'stt_dictation_proxy', 'tts_preview'),

    "y3_backend": ('build_route', 'canonical_bytes', 'resolve_data_dir', 'validate_docs_set', 'validate_route', 'validate_settings_tree'),

    "y4_d4_x7_backend": ('build_onboarding_payload', 'check_artifact_budget', 'check_icon', 'parse_checksum_line', 'resolve_picker_mode', 'resolve_runbook', 'validate_desktop_tools', 'validate_preset', 'validate_skill_library'),

    "z_backend": ('build_lock', 'build_preflight_report', 'check_output_shape', 'check_refusal', 'check_tool_allowlist', 'parse_client_capabilities', 'render_replay', 'render_report_md', 'validate_rule'),

}


FEATURE_TO_MODULE: dict[str, str] = {

    "D3.1": "d3_backend",

    "D3.10": "d3_backend",

    "D3.11": "d3_backend",

    "D3.12": "d3_backend",

    "D3.13": "d3_backend",

    "D3.14": "d3_backend",

    "D3.15": "d3_backend",

    "D3.16": "d3_backend",

    "D3.17": "d3_backend",

    "D3.18": "d3_backend",

    "D3.19": "d3_backend",

    "D3.2": "d3_backend",

    "D3.20": "d3_backend",

    "D3.21": "d3_backend",

    "D3.22": "d3_backend",

    "D3.23": "d3_backend",

    "D3.3": "d3_backend",

    "D3.4": "d3_backend",

    "D3.5": "d3_backend",

    "D3.6": "d3_backend",

    "D3.7": "d3_backend",

    "D3.8": "d3_backend",

    "D3.9": "d3_backend",

    "V8": "d3_backend",

    "X6.10": "d3_backend",

    "D6.1": "d6_reliability_backend",

    "D6.10": "d6_reliability_backend",

    "D6.11": "d6_reliability_backend",

    "D6.12": "d6_reliability_backend",

    "D6.13": "d6_reliability_backend",

    "D6.15": "d6_reliability_backend",

    "D6.16": "d6_reliability_backend",

    "D6.19": "d6_reliability_backend",

    "D6.22": "d6_reliability_backend",

    "D6.24": "d6_reliability_backend",

    "D6.25": "d6_reliability_backend",

    "D6.3": "d6_reliability_backend",

    "D6.4": "d6_reliability_backend",

    "D6.5": "d6_reliability_backend",

    "D6.6": "d6_reliability_backend",

    "D6.7": "d6_reliability_backend",

    "D6.8": "d6_reliability_backend",

    "D6.9": "d6_reliability_backend",

    "D7.1": "d7_workflow_backend",

    "D7.10": "d7_workflow_backend",

    "D7.11": "d7_workflow_backend",

    "D7.12": "d7_workflow_backend",

    "D7.13": "d7_workflow_backend",

    "D7.14": "d7_workflow_backend",

    "D7.15": "d7_workflow_backend",

    "D7.16": "d7_workflow_backend",

    "D7.17": "d7_workflow_backend",

    "D7.18": "d7_workflow_backend",

    "D7.19": "d7_workflow_backend",

    "D7.2": "d7_workflow_backend",

    "D7.20": "d7_workflow_backend",

    "D7.3": "d7_workflow_backend",

    "D7.4": "d7_workflow_backend",

    "D7.5": "d7_workflow_backend",

    "D7.6": "d7_workflow_backend",

    "D7.7": "d7_workflow_backend",

    "D7.8": "d7_workflow_backend",

    "D7.9": "d7_workflow_backend",

    "E3.1": "e3_backend",

    "E3.10": "e3_backend",

    "E3.11": "e3_backend",

    "E3.12": "e3_backend",

    "E3.13": "e3_backend",

    "E3.14": "e3_backend",

    "E3.15": "e3_backend",

    "E3.2": "e3_backend",

    "E3.3": "e3_backend",

    "E3.4": "e3_backend",

    "E3.5": "e3_backend",

    "E3.6": "e3_backend",

    "E3.7": "e3_backend",

    "E3.8": "e3_backend",

    "E3.9": "e3_backend",

    "E5.10": "e5_backend",

    "E5.11": "e5_backend",

    "E5.13": "e5_backend",

    "E5.16": "e5_backend",

    "E5.17": "e5_backend",

    "E5.18": "e5_backend",

    "E5.19": "e5_backend",

    "E5.2": "e5_backend",

    "E5.3": "e5_backend",

    "E5.5": "e5_backend",

    "E5.6": "e5_backend",

    "E5.7": "e5_backend",

    "E5.8": "e5_backend",

    "E6.11": "e6_x5_x6_backend",

    "E6.12": "e6_x5_x6_backend",

    "E6.13": "e6_x5_x6_backend",

    "E6.14": "e6_x5_x6_backend",

    "E6.2": "e6_x5_x6_backend",

    "E6.3": "e6_x5_x6_backend",

    "E6.4": "e6_x5_x6_backend",

    "E6.6": "e6_x5_x6_backend",

    "E6.7": "e6_x5_x6_backend",

    "X5.10": "e6_x5_x6_backend",

    "X5.11": "e6_x5_x6_backend",

    "X5.12": "e6_x5_x6_backend",

    "X5.13": "e6_x5_x6_backend",

    "X5.2": "e6_x5_x6_backend",

    "X5.3": "e6_x5_x6_backend",

    "X5.4": "e6_x5_x6_backend",

    "X5.7": "e6_x5_x6_backend",

    "X5.8": "e6_x5_x6_backend",

    "X6.1": "e6_x5_x6_backend",

    "X6.10": "e6_x5_x6_backend",

    "X6.2": "e6_x5_x6_backend",

    "X6.3": "e6_x5_x6_backend",

    "X6.4": "e6_x5_x6_backend",

    "X6.5": "e6_x5_x6_backend",

    "X6.6": "e6_x5_x6_backend",

    "X6.8": "e6_x5_x6_backend",

    "X6.9": "e6_x5_x6_backend",

    "D3.8": "e7_runtime_backend",

    "E7.1": "e7_runtime_backend",

    "E7.10": "e7_runtime_backend",

    "E7.11": "e7_runtime_backend",

    "E7.12": "e7_runtime_backend",

    "E7.13": "e7_runtime_backend",

    "E7.14": "e7_runtime_backend",

    "E7.15": "e7_runtime_backend",

    "E7.16": "e7_runtime_backend",

    "E7.17": "e7_runtime_backend",

    "E7.22": "e7_runtime_backend",

    "E7.24": "e7_runtime_backend",

    "E7.25": "e7_runtime_backend",

    "E7.26": "e7_runtime_backend",

    "E7.27": "e7_runtime_backend",

    "E7.28": "e7_runtime_backend",

    "E7.29": "e7_runtime_backend",

    "E7.3": "e7_runtime_backend",

    "E7.30": "e7_runtime_backend",

    "E7.31": "e7_runtime_backend",

    "E7.32": "e7_runtime_backend",

    "E7.33": "e7_runtime_backend",

    "E7.34": "e7_runtime_backend",

    "E7.35": "e7_runtime_backend",

    "E7.36": "e7_runtime_backend",

    "E7.37": "e7_runtime_backend",

    "E7.38": "e7_runtime_backend",

    "E7.39": "e7_runtime_backend",

    "E7.4": "e7_runtime_backend",

    "E7.40": "e7_runtime_backend",

    "E7.41": "e7_runtime_backend",

    "E7.42": "e7_runtime_backend",

    "E7.43": "e7_runtime_backend",

    "E7.5": "e7_runtime_backend",

    "E7.7": "e7_runtime_backend",

    "E7.8": "e7_runtime_backend",

    "E7.9": "e7_runtime_backend",

    "V23": "e7_runtime_backend",

    "W3.11": "e7_runtime_backend",

    "D2.12": "small_groups_backend",

    "D2.14": "small_groups_backend",

    "D2.17": "small_groups_backend",

    "D2.2": "small_groups_backend",

    "D2.4": "small_groups_backend",

    "D2.6": "small_groups_backend",

    "E4.13": "small_groups_backend",

    "E4.14": "small_groups_backend",

    "E4.3": "small_groups_backend",

    "E4.4": "small_groups_backend",

    "E4.6": "small_groups_backend",

    "E4.7": "small_groups_backend",

    "W2.10": "small_groups_backend",

    "W2.5": "small_groups_backend",

    "W2.7": "small_groups_backend",

    "W3.11": "small_groups_backend",

    "W3.5": "small_groups_backend",

    "W5.5": "small_groups_backend",

    "W5.6": "small_groups_backend",

    "W5.7": "small_groups_backend",

    "W6.2": "small_groups_backend",

    "W6.4": "small_groups_backend",

    "W6.5": "small_groups_backend",

    "W6.6": "small_groups_backend",

    "W8.1": "small_groups_backend",

    "W8.2": "small_groups_backend",

    "W8.3": "small_groups_backend",

    "W8.4": "small_groups_backend",

    "W9.1": "small_groups_backend",

    "W9.2": "small_groups_backend",

    "W9.3": "small_groups_backend",

    "W9.4": "small_groups_backend",

    "W9.5": "small_groups_backend",

    "W9.6": "small_groups_backend",

    "X0.2b": "small_groups_backend",

    "X0.5": "small_groups_backend",

    "X0.9": "small_groups_backend",

    "X10.3": "small_groups_backend",

    "X10.5": "small_groups_backend",

    "X10.6": "small_groups_backend",

    "X4.1": "small_groups_backend",

    "X4.2": "small_groups_backend",

    "X4.3": "small_groups_backend",

    "X4.4": "small_groups_backend",

    "X4.5": "small_groups_backend",

    "X4.6": "small_groups_backend",

    "X4.7": "small_groups_backend",

    "X9.10": "small_groups_backend",

    "X9.2": "small_groups_backend",

    "X9.4": "small_groups_backend",

    "X9.6": "small_groups_backend",

    "X9.8": "small_groups_backend",

    "X9.9": "small_groups_backend",

    "Y6.3": "small_groups_backend",

    "V1": "v_series_backend",

    "V10": "v_series_backend",

    "V11": "v_series_backend",

    "V12": "v_series_backend",

    "V13": "v_series_backend",

    "V14": "v_series_backend",

    "V15": "v_series_backend",

    "V16": "v_series_backend",

    "V17": "v_series_backend",

    "V18": "v_series_backend",

    "V19": "v_series_backend",

    "V2": "v_series_backend",

    "V20": "v_series_backend",

    "V21": "v_series_backend",

    "V22": "v_series_backend",

    "V23": "v_series_backend",

    "V24": "v_series_backend",

    "V25": "v_series_backend",

    "V26": "v_series_backend",

    "V27": "v_series_backend",

    "V28": "v_series_backend",

    "V29": "v_series_backend",

    "V3": "v_series_backend",

    "V30": "v_series_backend",

    "V31": "v_series_backend",

    "V4": "v_series_backend",

    "V5": "v_series_backend",

    "V6": "v_series_backend",

    "V7": "v_series_backend",

    "V8": "v_series_backend",

    "V9": "v_series_backend",

    "C11.7": "w1_security_backend",

    "C13.5": "w1_security_backend",

    "W1.1": "w1_security_backend",

    "W1.11": "w1_security_backend",

    "W1.12": "w1_security_backend",

    "W1.13": "w1_security_backend",

    "W1.14": "w1_security_backend",

    "W1.15": "w1_security_backend",

    "W1.16": "w1_security_backend",

    "W1.17": "w1_security_backend",

    "W1.2": "w1_security_backend",

    "W1.3": "w1_security_backend",

    "W1.4": "w1_security_backend",

    "W1.5": "w1_security_backend",

    "W1.6": "w1_security_backend",

    "W1.7": "w1_security_backend",

    "W1.8": "w1_security_backend",

    "W1.9": "w1_security_backend",

    "X6.10": "w1_security_backend",

    "X6.3": "w1_security_backend",

    "W4.1": "w4_backend",

    "W4.10": "w4_backend",

    "W4.11": "w4_backend",

    "W4.12": "w4_backend",

    "W4.13": "w4_backend",

    "W4.14": "w4_backend",

    "W4.2": "w4_backend",

    "W4.3": "w4_backend",

    "W4.4": "w4_backend",

    "W4.5": "w4_backend",

    "W4.6": "w4_backend",

    "W4.7": "w4_backend",

    "W4.8": "w4_backend",

    "W4.9": "w4_backend",

    "A3.10": "w7_x1_y5_d1_backend",

    "D1.11": "w7_x1_y5_d1_backend",

    "D1.2": "w7_x1_y5_d1_backend",

    "D1.3": "w7_x1_y5_d1_backend",

    "D1.6": "w7_x1_y5_d1_backend",

    "D1.7": "w7_x1_y5_d1_backend",

    "D1.8": "w7_x1_y5_d1_backend",

    "D1.9": "w7_x1_y5_d1_backend",

    "W7.11": "w7_x1_y5_d1_backend",

    "W7.12": "w7_x1_y5_d1_backend",

    "W7.15": "w7_x1_y5_d1_backend",

    "W7.18": "w7_x1_y5_d1_backend",

    "W7.2": "w7_x1_y5_d1_backend",

    "W7.20": "w7_x1_y5_d1_backend",

    "W7.7": "w7_x1_y5_d1_backend",

    "W7.9": "w7_x1_y5_d1_backend",

    "X1.10": "w7_x1_y5_d1_backend",

    "X1.11": "w7_x1_y5_d1_backend",

    "X1.12": "w7_x1_y5_d1_backend",

    "X1.14": "w7_x1_y5_d1_backend",

    "X1.15": "w7_x1_y5_d1_backend",

    "X1.16": "w7_x1_y5_d1_backend",

    "X1.6": "w7_x1_y5_d1_backend",

    "X1.9": "w7_x1_y5_d1_backend",

    "Y3.8": "w7_x1_y5_d1_backend",

    "Y5.1": "w7_x1_y5_d1_backend",

    "Y5.2": "w7_x1_y5_d1_backend",

    "Y5.3": "w7_x1_y5_d1_backend",

    "Y5.5": "w7_x1_y5_d1_backend",

    "Y5.6": "w7_x1_y5_d1_backend",

    "Y5.7": "w7_x1_y5_d1_backend",

    "Y5.8": "w7_x1_y5_d1_backend",

    "Y5.9": "w7_x1_y5_d1_backend",

    "Z3": "w7_x1_y5_d1_backend",

    "X2.1": "x2_orchestration_backend",

    "X2.10": "x2_orchestration_backend",

    "X2.11": "x2_orchestration_backend",

    "X2.12": "x2_orchestration_backend",

    "X2.13": "x2_orchestration_backend",

    "X2.14": "x2_orchestration_backend",

    "X2.15": "x2_orchestration_backend",

    "X2.16": "x2_orchestration_backend",

    "X2.2": "x2_orchestration_backend",

    "X2.3": "x2_orchestration_backend",

    "X2.4": "x2_orchestration_backend",

    "X2.5": "x2_orchestration_backend",

    "X2.6": "x2_orchestration_backend",

    "X2.7": "x2_orchestration_backend",

    "X2.8": "x2_orchestration_backend",

    "X2.9": "x2_orchestration_backend",

    "X3.1": "x3_memory_backend",

    "X3.10": "x3_memory_backend",

    "X3.11": "x3_memory_backend",

    "X3.12": "x3_memory_backend",

    "X3.13": "x3_memory_backend",

    "X3.14": "x3_memory_backend",

    "X3.15": "x3_memory_backend",

    "X3.16": "x3_memory_backend",

    "X3.2": "x3_memory_backend",

    "X3.3": "x3_memory_backend",

    "X3.4": "x3_memory_backend",

    "X3.5": "x3_memory_backend",

    "X3.6": "x3_memory_backend",

    "X3.7": "x3_memory_backend",

    "X3.8": "x3_memory_backend",

    "X3.9": "x3_memory_backend",

    "X8.1": "x8_backend",

    "X8.10": "x8_backend",

    "X8.11": "x8_backend",

    "X8.12": "x8_backend",

    "X8.13": "x8_backend",

    "X8.14": "x8_backend",

    "X8.15": "x8_backend",

    "X8.16": "x8_backend",

    "X8.17": "x8_backend",

    "X8.2": "x8_backend",

    "X8.3": "x8_backend",

    "X8.4": "x8_backend",

    "X8.5": "x8_backend",

    "X8.6": "x8_backend",

    "X8.7": "x8_backend",

    "X8.8": "x8_backend",

    "X8.9": "x8_backend",

    "V1": "y1_config_backend",

    "Y1.1": "y1_config_backend",

    "Y1.10": "y1_config_backend",

    "Y1.11": "y1_config_backend",

    "Y1.12": "y1_config_backend",

    "Y1.13": "y1_config_backend",

    "Y1.14": "y1_config_backend",

    "Y1.15": "y1_config_backend",

    "Y1.18": "y1_config_backend",

    "Y1.21": "y1_config_backend",

    "Y1.22": "y1_config_backend",

    "Y1.23": "y1_config_backend",

    "Y1.25": "y1_config_backend",

    "Y1.26": "y1_config_backend",

    "Y1.27": "y1_config_backend",

    "Y1.28": "y1_config_backend",

    "Y1.29": "y1_config_backend",

    "Y1.31": "y1_config_backend",

    "Y1.32": "y1_config_backend",

    "Y1.33": "y1_config_backend",

    "Y1.34": "y1_config_backend",

    "Y1.35": "y1_config_backend",

    "Y1.36": "y1_config_backend",

    "Y1.37": "y1_config_backend",

    "Y1.38": "y1_config_backend",

    "Y1.39": "y1_config_backend",

    "A3.7": "y2_backend",

    "C1.11": "y2_backend",

    "Y2.1": "y2_backend",

    "Y2.10": "y2_backend",

    "Y2.11": "y2_backend",

    "Y2.12": "y2_backend",

    "Y2.13": "y2_backend",

    "Y2.14": "y2_backend",

    "Y2.15": "y2_backend",

    "Y2.16": "y2_backend",

    "Y2.17": "y2_backend",

    "Y2.18": "y2_backend",

    "Y2.19": "y2_backend",

    "Y2.20": "y2_backend",

    "Y2.21": "y2_backend",

    "Y2.22": "y2_backend",

    "Y2.23": "y2_backend",

    "Y2.24": "y2_backend",

    "Y2.25": "y2_backend",

    "Y2.8": "y2_backend",

    "Y2.9": "y2_backend",

    "A3.1": "y3_backend",

    "A3.9": "y3_backend",

    "Y3.1": "y3_backend",

    "Y3.10": "y3_backend",

    "Y3.11": "y3_backend",

    "Y3.12": "y3_backend",

    "Y3.13": "y3_backend",

    "Y3.14": "y3_backend",

    "Y3.15": "y3_backend",

    "Y3.16": "y3_backend",

    "Y3.17": "y3_backend",

    "Y3.18": "y3_backend",

    "Y3.19": "y3_backend",

    "Y3.2": "y3_backend",

    "Y3.20": "y3_backend",

    "Y3.21": "y3_backend",

    "Y3.3": "y3_backend",

    "Y3.4": "y3_backend",

    "Y3.5": "y3_backend",

    "Y3.6": "y3_backend",

    "Y3.7": "y3_backend",

    "Y3.8": "y3_backend",

    "Y3.9": "y3_backend",

    "C1.9": "y4_d4_x7_backend",

    "D4.1": "y4_d4_x7_backend",

    "D4.10": "y4_d4_x7_backend",

    "D4.11": "y4_d4_x7_backend",

    "D4.12": "y4_d4_x7_backend",

    "D4.13": "y4_d4_x7_backend",

    "D4.2": "y4_d4_x7_backend",

    "D4.3": "y4_d4_x7_backend",

    "D4.4": "y4_d4_x7_backend",

    "D4.5": "y4_d4_x7_backend",

    "D4.6": "y4_d4_x7_backend",

    "D4.7": "y4_d4_x7_backend",

    "D4.8": "y4_d4_x7_backend",

    "D4.9": "y4_d4_x7_backend",

    "X7.1": "y4_d4_x7_backend",

    "X7.10": "y4_d4_x7_backend",

    "X7.2": "y4_d4_x7_backend",

    "X7.3": "y4_d4_x7_backend",

    "X7.4": "y4_d4_x7_backend",

    "X7.5": "y4_d4_x7_backend",

    "X7.6": "y4_d4_x7_backend",

    "X7.7": "y4_d4_x7_backend",

    "X7.8": "y4_d4_x7_backend",

    "X7.9": "y4_d4_x7_backend",

    "Y4.1": "y4_d4_x7_backend",

    "Y4.10": "y4_d4_x7_backend",

    "Y4.11": "y4_d4_x7_backend",

    "Y4.12": "y4_d4_x7_backend",

    "Y4.13": "y4_d4_x7_backend",

    "Y4.14": "y4_d4_x7_backend",

    "Y4.2": "y4_d4_x7_backend",

    "Y4.3": "y4_d4_x7_backend",

    "Y4.4": "y4_d4_x7_backend",

    "Y4.5": "y4_d4_x7_backend",

    "Y4.6": "y4_d4_x7_backend",

    "Y4.7": "y4_d4_x7_backend",

    "Y4.8": "y4_d4_x7_backend",

    "Y4.9": "y4_d4_x7_backend",

    "X9.1": "z_backend",

    "Y1.29": "z_backend",

    "Y4.1": "z_backend",

    "Z1": "z_backend",

    "Z10": "z_backend",

    "Z11": "z_backend",

    "Z12": "z_backend",

    "Z13": "z_backend",

    "Z14": "z_backend",

    "Z15": "z_backend",

    "Z16": "z_backend",

    "Z2": "z_backend",

    "Z3": "z_backend",

    "Z4": "z_backend",

    "Z5": "z_backend",

    "Z6": "z_backend",

    "Z7": "z_backend",

    "Z8": "z_backend",

    "Z9": "z_backend",

}


class BackendHubError(ValueError):
    """Typed error for invalid hub requests."""


def modules() -> list[str]:
    """Return the names of all integrated backend modules."""
    return sorted(MODULE_FEATURES)


def feature_ids() -> tuple[str, ...]:
    """Return every implemented feature ID, sorted."""
    return tuple(sorted(FEATURE_TO_MODULE))


def describe(module: str | None = None) -> dict:
    """Return a machine-readable contract for one module (or all modules)."""
    if module is not None:
        if module not in MODULE_FEATURES:
            raise BackendHubError(f"unknown backend module: {module}")
        return {
            "module": module,
            "features": list(MODULE_FEATURES[module]),
            "dispatchable": list(DISPATCH.get(module, ())),
        }
    return {
        "modules": len(MODULE_FEATURES),
        "features": len(FEATURE_TO_MODULE),
        "contracts": [describe(m) for m in modules()],
    }


def dispatchable(module: str) -> tuple[str, ...]:
    """Return the allowlisted deterministic callables for a module."""
    if module not in MODULE_FEATURES:
        raise BackendHubError(f"unknown backend module: {module}")
    return DISPATCH.get(module, ())


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if hasattr(value, "__dict__"):
        return {
            "type": type(value).__name__,
            "fields": {k: _jsonable(v) for k, v in vars(value).items()},
        }
    return repr(value)


def invoke(module: str, function: str, params: dict | None = None) -> Any:
    """Execute an allowlisted backend function with real arguments.

    Only functions explicitly declared in DISPATCH may run. Unknown modules,
    unknown functions, non-object params and non-serializable results are
    rejected; real handler exceptions propagate as BackendHubError so the
    capability hub can surface an honest failure rather than fake success.
    """
    if module not in MODULE_FEATURES:
        raise BackendHubError(f"unknown backend module: {module}")
    if function not in DISPATCH.get(module, ()):
        raise BackendHubError(f"function {function!r} is not dispatchable on {module}")
    params = params or {}
    if not isinstance(params, dict):
        raise BackendHubError("params must be an object")
    try:
        mod = importlib.import_module("keel." + module)
        fn = getattr(mod, function)
        result = fn(**params)
    except BackendHubError:
        raise
    except TypeError as exc:
        raise BackendHubError(f"bad arguments for {module}.{function}: {exc}") from exc
    except Exception as exc:  # surface the real failure, never fake success
        raise BackendHubError(
            f"{module}.{function} raised {type(exc).__name__}: {exc}") from exc
    return _jsonable(result)


def verify(module: str) -> dict:
    """Import a backend module and verify its declared feature contract loads.

    Modules declare their feature contracts under different attribute names
    (FEATURE_IDS, FEATURE_IMPLEMENTATIONS, FEATURE_BEHAVIORS, ...). Verify by
    checking the module source text for the declared IDs instead of assuming a
    single attribute name. This is an honest import+declaration check, not a
    claim that every feature acceptance criterion passed here.
    """
    if module not in MODULE_FEATURES:
        raise BackendHubError(f"unknown backend module: {module}")
    import re
    mod = importlib.import_module("keel." + module)
    source = Path(mod.__file__).read_text(encoding="utf-8", errors="replace")
    declared = [f for f in MODULE_FEATURES[module]
                if re.search(r"\b" + re.escape(f) + r"\b", source)]
    return {
        "module": module,
        "imported": True,
        "features": len(MODULE_FEATURES[module]),
        "declared_in_module": len(declared),
        "not_declared": sorted(set(MODULE_FEATURES[module]) - set(declared)),
    }
