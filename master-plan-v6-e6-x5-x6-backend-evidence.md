# E6 / X5 / X6 backend evidence

Branch: `agent/b3-mixed1` — backend implementation for all `not_started` E6.*, X5.*, X6.* feature IDs.

## Module
`keel/src/keel/e6_x5_x6_backend.py` — stdlib-only backend contracts/behaviors for the remaining provider-config (E6), clipboard/mass-change/filesystem-journal (X5), and config-validation/component/design-token (X6) features. No frontend UI, no network, no os I/O except injectable seams.

## Verification
Command (from worktree root):
```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_e6_x5_x6_backend.py']))"
```
Result: **65 passed** (independently reproduced by lead integration).

Per-ID classification, implemented behaviors, and excluded frontend-only scopes are documented in the module's `FEATURE_BEHAVIORS` registry and docstrings.

## Integration
Lead-reviewed diff: only 2 new files owned by this agent (module + tests) plus this evidence file. No existing source, test, or registry files modified. Prior verified P0 rows in this prefix group were not reimplemented.

## Per-ID traceability: ID → implementing symbols → behavioral test

The module declares every ID below in `FEATURE_TRACEABILITY` (AST-visible string
keys mapping to real symbol names). Each symbol column names concrete definitions
in `keel/src/keel/e6_x5_x6_backend.py`; each test column names concrete behavioral
test functions in `keel/tests/test_e6_x5_x6_backend.py` (all passing).

| ID | Implementing symbols (`keel.e6_x5_x6_backend`) | Behavioral test function |
| --- | --- | --- |
| E6.2 | `CredentialEditor`, `InMemoryCredentialSeam`, `SHARED_CREDENTIAL_WARNING`, `DELETION_IRREVERSIBLE_WARNING` | `test_e62_typing_replaces_whole_key_no_partial_edit`, `test_e62_backspace_stages_removal_applied_only_on_apply` |
| E6.3 | `detect_env_credential`, `HintStatus`, `CredentialHint` | `test_e63_detected_when_env_var_present_and_never_validates`, `test_e63_none_when_env_var_absent` |
| E6.4 | `should_refresh`, `update_published`, `edit_model_list`, `restore_defaults` | `test_e64_follow_refreshes_on_first_need_and_after_ttl`, `test_e64_edit_pins_and_restore_refollows` |
| E6.6 | `parse_models_response`, `build_candidate`, `save_candidate`, `fallback_manual` | `test_e66_parser_accepts_two_list_formats`, `test_e66_tick_adds_untick_removes_configured_unlisted_stay` |
| E6.7 | `ModelPicker`, `ModelRef` | `test_e67_select_also_sets_default_for_new_sessions`, `test_e67_session_keeps_its_own_recorded_model` |
| E6.11 | `lookup_troubleshooting`, `render_troubleshooting_page`, `TROUBLESHOOTING_CATALOG` | `test_e611_lookup_by_code_and_by_symptom`, `test_e611_catalog_covers_all_named_symptoms_and_page_generated` |
| E6.12 | `HotReloadAdapter`, `InMemoryConfigSeam`, `can_open_in_editor` | `test_e612_hot_reload_rereads_on_next_request_without_restart`, `test_e612_editor_only_when_ui_on_same_machine` |
| E6.13 | `check_model_compatibility`, `ClientUpgradeRequired`, `parse_semver` | `test_e613_compatible_model_returns_descriptor`, `test_e613_too_old_model_raises_typed_error_naming_version` |
| E6.14 | `build_config_catalog`, `catalog_digest`, `assert_catalog_current` | `test_e614_catalog_is_deterministic_and_drives_detection` |
| X5.2 | `classification_from_labels`, `redaction_required`, `egress_allowed`, `DataPolicy` | `test_x52_highest_label_wins_and_unknown_escalates`, `test_x52_redaction_and_egress_feed_decisions` |
| X5.3 | `issue_grant`, `is_active`, `remaining_seconds`, `consume_grant` | `test_x53_time_box_auto_expires_with_countdown`, `test_x53_just_in_time_grant_is_single_use` |
| X5.4 | `CapabilityTokenIssuer`, `CapabilityToken`, `AuditEntry` | `test_x54_scoped_token_verification_and_scope_checks`, `test_x54_audit_log_records_issue_use_and_revoke` |
| X5.7 | `review_rules`, `prune_unused`, `StandingRule` | `test_x57_review_annotates_last_used_date`, `test_x57_prune_removes_only_unused_or_stale_rules` |
| X5.8 | `resolve_profile`, `operation_allowed`, `SandboxProfile` | `test_x58_frontmatter_profile_defaults_to_strictest`, `test_x58_operations_match_profile_capabilities` |
| X5.10 | `seal_export`, `verify_import`, `EXPORT_SCHEMA_VERSION` | `test_x510_seal_and_verify_roundtrip`, `test_x510_tampered_payload_and_wrong_passphrase_fail` |
| X5.11 | `build_data_handling_cards`, `assert_no_retention_claims`, `EgressRecord` | `test_x511_card_reports_only_sent_categories_and_own_link` |
| X5.12 | `evaluate_dependency`, `ManagedPolicy`, `DependencyDecision` | `test_x512_deny_wins_and_allowlist_is_required` |
| X5.13 | `detect_secret_paste`, `PasteWarning` | `test_x513_detects_key_patterns_without_echoing_secret`, `test_x513_clean_text_is_not_flagged` |
| X6.1 | `plugin_scaffold`, `detect_changes`, `MockHost` | `test_x61_scaffold_is_deterministic_and_content_addressed`, `test_x61_hot_reload_change_detection_and_mock_host` |
| X6.2 | `compare_event_streams`, `permission_denial_check`, `GoldenEventStream` | `test_x62_golden_stream_compare_and_order_check`, `test_x62_permission_denial_check` |
| X6.3 | `generate_python_sdk`, `generate_typescript_sdk`, `assert_sdk_version_pinned` | `test_x63_generated_sdks_are_version_pinned_to_daemon` |
| X6.4 | `parse_version`, `deprecation_headers`, `is_compatible`, `is_sunset` | `test_x64_deprecation_headers_sunset_and_compatibility` |
| X6.5 | `explorer_access`, `ExplorerDecision` | `test_x65_explorer_requires_loopback_and_token_docs_private_without_g7` |
| X6.6 | `validate_event`, `SubscriptionRegistry`, `EVENT_SCHEMAS` | `test_x66_every_registered_event_has_schema_and_changelog`, `test_x66_validation_and_subscription_by_type` |
| X6.8 | `resolve_layers`, `ConfigLayer`, `LAYER_PRECEDENCE` | `test_x68_highest_precedence_layer_wins_with_provenance` |
| X6.9 | `search_settings`, `diff_against_defaults`, `reset_section`, `export_settings`, `import_settings` | `test_x69_search_diff_reset_and_roundtrip` |
| X6.10 | `feature_enabled`, `validate_feature_config`, `FEATURE_LIFECYCLES` | `test_x610_experimental_off_by_default_beta_stable_on` |

This table is the per-ID traceability cross-check consumed by
`scripts/verify_backend_operation.py`; it closes the gap where the earlier
document only described behavior in prose and did not spell out any ID.
