"""Contract/regression tests for the E6.*, X5.*, X6.* backend workstream.

Pure and offline: every test operates on caller-supplied data or injectable
seams. No real clipboard, screen, filesystem, network, credential or editor is
touched. Tests are named ``test_<id>_...`` so each of the 27 not_started rows is
individually traceable in the evidence document.
"""

from __future__ import annotations

import ast
import threading
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import keel.e6_x5_x6_backend as b
from keel.e6_x5_x6_backend import (
    EXPORT_SCHEMA_VERSION,
    BackendError,
    Classification,
    ClientUpgradeRequired,
    ConfigField,
    ConfigLayer,
    ConfigSnapshot,
    CredentialEditState,
    CredentialEditor,
    DataPolicy,
    DependencyDecision,
    DiscoveryState,
    EgressRecord,
    FeatureLifecycle,
    FileState,
    HintStatus,
    InMemoryConfigSeam,
    InMemoryCredentialSeam,
    LabeledResource,
    ManagedPolicy,
    ModelDiscoveryError,
    ModelListMode,
    ModelListState,
    ModelPicker,
    ModelRef,
    SandboxProfile,
    SandboxProfileError,
    StandingRule,
    TimeBoxedGrant,
    ApiVersion,
    CapabilityTokenIssuer,
    HotReloadAdapter,
    MockHost,
    SubscriptionRegistry,
    assert_catalog_current,
    assert_no_retention_claims,
    assert_sdk_version_pinned,
    build_candidate,
    build_config_catalog,
    build_data_handling_cards,
    can_open_in_editor,
    catalog_digest,
    check_model_compatibility,
    classification_from_labels,
    compare_event_streams,
    consume_grant,
    deprecation_headers,
    detect_changes,
    detect_env_credential,
    detect_secret_paste,
    diff_against_defaults,
    edit_model_list,
    egress_allowed,
    evaluate_dependency,
    explorer_access,
    export_settings,
    feature_enabled,
    fallback_manual,
    generate_python_sdk,
    generate_typescript_sdk,
    import_settings,
    is_active,
    is_compatible,
    is_sunset,
    issue_grant,
    lookup_troubleshooting,
    parse_models_response,
    parse_semver,
    parse_version,
    permission_denial_check,
    plugin_scaffold,
    prune_unused,
    redaction_required,
    remaining_seconds,
    render_troubleshooting_page,
    reset_section,
    resolve_layers,
    resolve_profile,
    restore_defaults,
    review_rules,
    save_candidate,
    seal_export,
    search_settings,
    should_refresh,
    toggle_model,
    update_published,
    validate_event,
    validate_feature_config,
    verify_import,
)


# ---------------------------------------------------------------------------
# E6.2 -- saved-key edit rules
# ---------------------------------------------------------------------------


def _editor(**kwargs: object) -> CredentialEditor:
    return CredentialEditor(**kwargs)  # type: ignore[arg-type]


def test_e62_typing_replaces_whole_key_no_partial_edit() -> None:
    editor = _editor()
    state = editor.start("provider.openai")
    staged = editor.type_replaces(state, "sk-brand-new-full-value")
    assert staged.staged_value == "sk-brand-new-full-value"
    # No reveal/copy/partial-edit surface exists on the descriptor.
    descriptor = staged.descriptor()
    assert descriptor["revealed"] is False
    assert descriptor["copyable"] is False
    assert descriptor["partial_edit"] is False
    assert "sk-brand-new-full-value" not in staged.to_json()


def test_e62_backspace_stages_removal_applied_only_on_apply() -> None:
    seam = InMemoryCredentialSeam()
    seam.values["k"] = "old"
    editor = _editor(write_seam=seam.write, delete_seam=seam.delete)
    state = editor.start("k")
    staged = editor.stage_removal(state)
    assert staged.remove is True
    assert "k" in seam.values  # still there: only staged
    result = editor.apply(staged)
    assert result.applied is True and result.action == "remove"
    assert "k" not in seam.values


def test_e62_cancel_preserves_original() -> None:
    seam = InMemoryCredentialSeam()
    seam.values["k"] = "original"
    editor = _editor(write_seam=seam.write, delete_seam=seam.delete)
    staged = editor.stage_removal(editor.start("k"))
    result = editor.cancel(staged)
    assert result.applied is False and result.action == "cancelled"
    assert seam.values["k"] == "original"


def test_e62_shared_credential_warning() -> None:
    editor = _editor(
        write_seam=InMemoryCredentialSeam().write,
        delete_seam=InMemoryCredentialSeam().delete,
    )
    state = editor.start("shared", shared_with=["chat", "embeddings"])
    result = editor.apply(editor.stage_removal(state))
    assert b.SHARED_CREDENTIAL_WARNING in result.warnings


def test_e62_delete_succeeds_but_settings_fail_warns_and_offers_retry() -> None:
    class DeleteOkSettingsFail:
        def delete(self, _ref: str) -> bool:
            return True

        def write(self, _ref: str, _val: str | None) -> bool:
            return False

    seam = DeleteOkSettingsFail()
    editor = _editor(write_seam=seam.write, delete_seam=seam.delete)
    result = editor.apply(editor.stage_removal(editor.start("k")))
    assert result.deletion_succeeded is True
    assert result.settings_succeeded is False
    assert result.retry_available is True
    assert b.DELETION_IRREVERSIBLE_WARNING in result.warnings


# ---------------------------------------------------------------------------
# E6.3 -- environment credential hints
# ---------------------------------------------------------------------------


def test_e63_detected_when_env_var_present_and_never_validates() -> None:
    hint = detect_env_credential("openai", "OPENAI_API_KEY", {"OPENAI_API_KEY": "not-a-real-key"})
    assert hint.status is HintStatus.DETECTED
    assert hint.to_dict()["validated"] is False


def test_e63_none_when_env_var_absent() -> None:
    hint = detect_env_credential("openai", "OPENAI_API_KEY", {})
    assert hint.status is HintStatus.NONE


def test_e63_unconfirmed_when_status_read_fails() -> None:
    class BrokenMapping(dict):
        def get(self, _key: str, _default: object = None) -> object:
            raise OSError("status read failed")

    hint = detect_env_credential("openai", "OPENAI_API_KEY", BrokenMapping())
    assert hint.status is HintStatus.UNCONFIRMED


def test_e63_provider_managed_credential_files_are_excluded() -> None:
    hint = detect_env_credential(
        "codex", "CODEX_AUTH", {}, provider_managed_sources=["CODEX_AUTH"]
    )
    assert hint.excluded is True
    assert hint.status is HintStatus.NONE


# ---------------------------------------------------------------------------
# E6.4 -- model list follow/pin policy
# ---------------------------------------------------------------------------


def _model_state() -> ModelListState:
    return ModelListState(
        mode=ModelListMode.FOLLOW,
        models=("m1",),
        builtin_models=("m1", "m2"),
        last_refresh=None,
    )


def test_e64_follow_refreshes_on_first_need_and_after_ttl() -> None:
    state = _model_state()
    assert should_refresh(state, now=100) is True
    refreshed = update_published(state, ("m1", "m2"), now=100)
    assert should_refresh(refreshed, now=100 + 599) is False
    assert should_refresh(refreshed, now=100 + 600) is True


def test_e64_failure_falls_back_to_builtin() -> None:
    refreshed = update_published(_model_state(), None, now=100)
    assert refreshed.models == refreshed.builtin_models
    assert refreshed.version == 1


def test_e64_edit_pins_and_restore_refollows() -> None:
    state = _model_state()
    pinned = edit_model_list(state, ("custom",))
    assert pinned.mode is ModelListMode.PINNED
    assert should_refresh(pinned, now=99999) is False
    restored = restore_defaults(pinned)
    assert restored.mode is ModelListMode.FOLLOW
    assert restored.models == restored.builtin_models


# ---------------------------------------------------------------------------
# E6.6 -- model discovery
# ---------------------------------------------------------------------------


def test_e66_parser_accepts_two_list_formats() -> None:
    assert parse_models_response({"data": [{"id": "m1"}, {"id": "m2"}]}) == ("m1", "m2")
    assert parse_models_response(["m2", "m1", "m2"]) == ("m2", "m1")


def test_e66_parser_rejects_malformed_response_with_clear_error() -> None:
    for bad in ({"nope": []}, {"data": "not-a-list"}, [123], []):
        try:
            parse_models_response(bad)
        except ModelDiscoveryError:
            continue
        raise AssertionError(f"expected ModelDiscoveryError for {bad!r}")


def test_e66_tick_adds_untick_removes_configured_unlisted_stay() -> None:
    state = DiscoveryState(
        configured=("old-local", "m1"), discovered=("m1", "m2"), selected=frozenset({"m1"})
    )
    state = toggle_model(state, "m2", True)
    state = toggle_model(state, "m1", False)
    pending = build_candidate(state)
    assert pending.saved is False
    assert "old-local" in pending.models  # endpoint didn't list it: kept
    assert "m1" not in pending.models  # unticked
    assert "m2" in pending.models  # ticked
    assert save_candidate(pending).saved is True


def test_e66_failure_falls_back_to_manual_entry() -> None:
    state = DiscoveryState(("m1",), (), frozenset())
    failed = fallback_manual(state, "discovery_failed_401")
    assert failed.failure == "discovery_failed_401"
    assert failed.discovered == ()


# ---------------------------------------------------------------------------
# E6.7 -- model picker behavior
# ---------------------------------------------------------------------------


def _picker() -> ModelPicker:
    return ModelPicker(
        [ModelRef("m1", "p1"), ModelRef("m2", "p1"), ModelRef("m3", "p2")],
        default_model="m2",
    )


def test_e67_select_also_sets_default_for_new_sessions() -> None:
    picker = _picker()
    picker.select("m3")
    assert picker.default == "m3"


def test_e67_session_keeps_its_own_recorded_model() -> None:
    picker = _picker()
    picker.record_session("s1", "m1")
    assert picker.session_model("s1") == "m1"
    assert picker.session_model("missing") is None


def test_e67_reorder_keyboard_matches_drag() -> None:
    picker = _picker()
    assert picker.order == ("m1", "m2", "m3")
    assert picker.move_up("m2") is True
    assert picker.order == ("m2", "m1", "m3")
    assert picker.move_down("m2") is True
    assert picker.order == ("m1", "m2", "m3")


def test_e67_deleted_default_provider_blocks_composer() -> None:
    picker = _picker()
    assert picker.default_provider() == "p1"
    picker.delete_provider("p1")
    assert picker.default is None
    # Deleting the default provider blocks input until a model is selected.
    assert picker.composer_blocked() is True
    picker.select("m3")
    assert picker.composer_blocked() is False
    picker.delete_provider("p2")
    assert picker.composer_blocked() is True


# ---------------------------------------------------------------------------
# E6.11 -- troubleshooting catalog
# ---------------------------------------------------------------------------


def test_e611_lookup_by_code_and_by_symptom() -> None:
    assert lookup_troubleshooting("missing_credential")[0].code == "missing_credential"
    assert any(
        e.code == "discovery_401" for e in lookup_troubleshooting("401 on discovery")
    )
    assert lookup_troubleshooting("  ") == ()


def test_e611_catalog_covers_all_named_symptoms_and_page_generated() -> None:
    codes = {e.code for e in b.TROUBLESHOOTING_CATALOG}
    expected = {
        "missing_credential",
        "unknown_model",
        "discovery_401",
        "gateway_refuses_all",
        "reasoning_only_fail",
        "effort_menu_absent",
        "effort_off_still_thinks",
        "image_refused_vs_provider",
        "stale_image_in_session",
    }
    assert expected <= codes
    page = render_troubleshooting_page()
    for code in expected:
        assert code in page


# ---------------------------------------------------------------------------
# E6.12 -- config hot re-read + editor guard
# ---------------------------------------------------------------------------


def test_e612_hot_reload_rereads_on_next_request_without_restart() -> None:
    seam = InMemoryConfigSeam({"a": 1})
    adapter = HotReloadAdapter(seam.read)
    assert adapter.refresh_if_changed() is True
    snapshot = adapter.current
    assert isinstance(snapshot, ConfigSnapshot)
    assert adapter.refresh_if_changed() is False  # unchanged
    seam.config["a"] = 2
    assert adapter.refresh_if_changed() is True
    assert adapter.current is not None and adapter.current.version == snapshot.version + 1


def test_e612_editor_only_when_ui_on_same_machine() -> None:
    assert can_open_in_editor(True).allowed is True
    assert can_open_in_editor(False).allowed is False


def test_e612_no_read_seam_fails_closed() -> None:
    try:
        HotReloadAdapter().refresh_if_changed()
    except b.SeamNotImplemented:
        return
    raise AssertionError("expected SeamNotImplemented")


# ---------------------------------------------------------------------------
# E6.13 -- typed client-upgrade-required error
# ---------------------------------------------------------------------------


def test_e613_compatible_model_returns_descriptor() -> None:
    result = check_model_compatibility("m", "1.2.0", "1.3.0")
    assert result.compatible is True


def test_e613_too_old_model_raises_typed_error_naming_version() -> None:
    try:
        check_model_compatibility("deepseek-r2", "2.0.0", "1.4.0")
    except ClientUpgradeRequired as exc:
        assert "2.0.0" in exc.message()
        assert exc.to_dict()["type"] == "client_upgrade_required"
        return
    raise AssertionError("expected ClientUpgradeRequired")


def test_e613_semver_parser_defaults_missing_parts() -> None:
    assert parse_semver("2") == (2, 0, 0)
    assert parse_semver("v1.4") == (1, 4, 0)


# ---------------------------------------------------------------------------
# E6.14 -- generated config reference
# ---------------------------------------------------------------------------


def test_e614_catalog_is_deterministic_and_drives_detection() -> None:
    fields = (
        ConfigField("model.default", "string", "auto", "Default model", "model"),
        ConfigField("auth.env_var", "string", "OPENAI_API_KEY", "Env var", "auth"),
    )
    rendered = build_config_catalog(fields)
    assert rendered == build_config_catalog(tuple(reversed(fields)))
    assert "model.default" in rendered
    assert assert_catalog_current(fields, rendered) is True
    assert assert_catalog_current(fields, rendered + "\n# drift") is False
    assert len(catalog_digest(rendered)) == 64


# ---------------------------------------------------------------------------
# X5.2 -- data-classification labels
# ---------------------------------------------------------------------------


def test_x52_highest_label_wins_and_unknown_escalates() -> None:
    assert classification_from_labels(["public", "internal"]) is Classification.INTERNAL
    assert classification_from_labels(["internal", "secret"]) is Classification.SECRET
    assert classification_from_labels(["bogus"]) is Classification.SECRET
    assert classification_from_labels([]) is Classification.PUBLIC


def test_x52_redaction_and_egress_feed_decisions() -> None:
    secret = LabeledResource("mem-1", "memory", Classification.SECRET)
    public = LabeledResource("file-1", "file", Classification.PUBLIC)
    assert redaction_required(secret) is True
    assert redaction_required(public) is False
    policy = DataPolicy()
    assert egress_allowed(public, True, policy) is True
    assert egress_allowed(secret, True, policy) is False
    assert egress_allowed(secret, False, policy) is True


# ---------------------------------------------------------------------------
# X5.3 -- time-boxed and just-in-time permissions
# ---------------------------------------------------------------------------


def test_x53_time_box_auto_expires_with_countdown() -> None:
    grant = issue_grant("tool.write", now=1000, duration_seconds=1800)
    assert grant.expires_at == 2800
    assert is_active(grant, 1000) is True
    assert remaining_seconds(grant, 1500) == 1300
    assert is_active(grant, 2801) is False
    assert remaining_seconds(grant, 9999) == 0


def test_x53_just_in_time_grant_is_single_use() -> None:
    grant = issue_grant("clipboard.read", now=100, duration_seconds=60, just_in_time=True)
    first = consume_grant(grant, 100)
    assert first.granted is True and first.reason == "just_in_time_granted"
    # Consumption is enforced inside the API, not by the caller mutating state.
    assert grant.consumed is True
    assert is_active(grant, 101) is False
    second = consume_grant(grant, 101)  # same grant object: replay must be denied
    assert second.granted is False and second.reason == "grant_inactive"
    assert consume_grant(grant, 102).granted is False  # repeated replay stays denied
    # Non-JIT grants remain reusable within their time box.
    boxed = issue_grant("tool.write", now=100, duration_seconds=60)
    assert consume_grant(boxed, 100).granted is True
    assert consume_grant(boxed, 101).granted is True
    assert boxed.consumed is False


def test_x53_jit_grant_concurrent_consumption_succeeds_once() -> None:
    grant = issue_grant("clipboard.read", now=100, duration_seconds=60, just_in_time=True)
    count = 16
    barrier = threading.Barrier(count)
    decisions = []
    collect_lock = threading.Lock()

    def worker():
        barrier.wait()
        decision = consume_grant(grant, 101)
        with collect_lock:
            decisions.append(decision)

    threads = [threading.Thread(target=worker) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(decision.granted for decision in decisions) == 1
    assert grant.consumed is True


def test_x53_jit_grant_snapshot_cannot_replay_after_consume() -> None:
    """C8: single-use lives in shared state, not in this dataclass instance."""
    grant = issue_grant("deploy", 1000, duration_seconds=600, just_in_time=True)
    snapshot = grant.to_dict()
    assert snapshot["consumed"] is False

    first = consume_grant(grant, 1001)
    assert first.granted is True and first.reason == "just_in_time_granted"

    replay = TimeBoxedGrant(**snapshot)  # round-tripped before consumption
    second = consume_grant(replay, 1002)
    assert second.granted is False
    assert second.reason == "grant_inactive"
    assert consume_grant(TimeBoxedGrant(**snapshot), 1003).granted is False


def test_x53_unregistered_grant_is_denied() -> None:
    """A fabricated, unsigned grant descriptor must never be trusted."""
    fabricated = TimeBoxedGrant(
        grant_id="fabricated-grant",
        scope="deploy",
        issued_at=1000,
        expires_at=10**9,
        just_in_time=True,
    )
    decision = consume_grant(fabricated, 1002)
    assert decision.granted is False
    assert decision.reason == "grant_inactive"


# ---------------------------------------------------------------------------
# X5.4 -- capability tokens
# ---------------------------------------------------------------------------


def test_x54_scoped_token_verification_and_scope_checks() -> None:
    issuer = CapabilityTokenIssuer()
    token = issuer.issue("subagent-1", ["file.read", "file.write"], now=100)
    assert issuer.verify(token, ["file.read"], now=101).allowed is True
    assert issuer.verify(token, ["network"], now=101).reason == "out_of_scope"


def test_x54_revocation_and_expiry_fail_closed() -> None:
    issuer = CapabilityTokenIssuer()
    token = issuer.issue("plugin", ["tool.call"], now=100, ttl_seconds=10)
    assert issuer.verify(token, ["tool.call"], now=111).reason == "expired_or_not_yet_valid"
    fresh = issuer.issue("plugin", ["tool.call"], now=100, ttl_seconds=100)
    assert issuer.revoke(fresh.token_id) is True
    assert issuer.verify(fresh, ["tool.call"], now=101).reason == "revoked"
    assert issuer.verify(replace(fresh, token_id="forged"), ["tool.call"], now=101).reason == "unknown_token"


def test_x54_audit_log_records_issue_use_and_revoke() -> None:
    issuer = CapabilityTokenIssuer()
    token = issuer.issue("agent", ["x"], now=1)
    issuer.verify(token, ["x"], now=2)
    issuer.revoke(token.token_id)
    actions = [e.action.value for e in issuer.audit_log]
    assert actions == ["issue", "use", "revoke"]


# ---------------------------------------------------------------------------
# X5.7 -- permission review
# ---------------------------------------------------------------------------


def _rules() -> tuple[StandingRule, ...]:
    return (
        StandingRule("r1", "file.write", 0, last_used_at=59 * 86400),
        StandingRule("r2", "network", 0, last_used_at=None),
    )


def test_x57_review_annotates_last_used_date() -> None:
    now = 60 * 86400
    reviewed = review_rules(_rules(), now=now, stale_days=30)
    assert reviewed[0].stale is False
    assert reviewed[1].stale is True  # never used


def test_x57_prune_removes_only_unused_or_stale_rules() -> None:
    result = prune_unused(_rules(), now=60 * 86400, stale_days=30)
    assert [r.rule_id for r in result.kept] == ["r1"]
    assert [r.rule_id for r in result.pruned] == ["r2"]
    assert len(result.prune_digest) == 64


# ---------------------------------------------------------------------------
# X5.8 -- per-tool sandbox profiles
# ---------------------------------------------------------------------------


def test_x58_frontmatter_profile_defaults_to_strictest() -> None:
    assert resolve_profile({}) is SandboxProfile.READ_ONLY_FS
    assert resolve_profile({"sandbox_profile": "no_network"}) is SandboxProfile.NO_NETWORK


def test_x58_invalid_profile_fails_closed() -> None:
    try:
        resolve_profile({"sandbox_profile": "unrestricted"})
    except SandboxProfileError:
        return
    raise AssertionError("expected SandboxProfileError")


def test_x58_operations_match_profile_capabilities() -> None:
    assert b.operation_allowed(SandboxProfile.READ_ONLY_FS, "fs_read") is True
    assert b.operation_allowed(SandboxProfile.READ_ONLY_FS, "fs_write") is False
    assert b.operation_allowed(SandboxProfile.NO_NETWORK, "network") is False
    assert b.operation_allowed(SandboxProfile.TEMP_ONLY_WRITE, "temp_write") is True


# ---------------------------------------------------------------------------
# X5.10 -- sealed export bundles
# ---------------------------------------------------------------------------


def test_x510_seal_and_verify_roundtrip() -> None:
    bundle = seal_export({"session": "s1", "messages": [1, 2]}, "correct horse", "nonce-1")
    assert bundle.schema_version == EXPORT_SCHEMA_VERSION
    result = verify_import(bundle, "correct horse")
    assert result.valid is True and result.reasons == ()


def test_x510_tampered_payload_and_wrong_passphrase_fail() -> None:
    bundle = seal_export({"a": 1}, "pw", "n")
    tampered = replace(bundle, payload_hex="00" * len(bundle.payload_hex))
    assert verify_import(tampered, "pw").valid is False
    assert verify_import(bundle, "wrong").valid is False


def test_x510_unsupported_schema_version_fails() -> None:
    bundle = seal_export({"a": 1}, "pw", "n")
    bad = replace(bundle, schema_version=EXPORT_SCHEMA_VERSION + 1)
    result = verify_import(bad, "pw")
    assert result.valid is False
    assert "unsupported_schema_version" in result.reasons


# ---------------------------------------------------------------------------
# X5.11 -- provider data-handling cards
# ---------------------------------------------------------------------------


def test_x511_card_reports_only_sent_categories_and_own_link() -> None:
    providers = {
        "openai": {"kind": "remote", "account_settings_url": "https://acct.openai.example"},
        "local": {"kind": "local"},
    }
    log = (
        EgressRecord("openai", "prompt"),
        EgressRecord("openai", "prompt"),
        EgressRecord("openai", "file_content"),
    )
    cards = build_data_handling_cards(providers, log)
    assert len(cards) == 1  # local provider excluded
    assert cards[0].sent_categories == ("file_content", "prompt")
    assert cards[0].account_settings_url == "https://acct.openai.example"
    assert assert_no_retention_claims(cards) is True


# ---------------------------------------------------------------------------
# X5.12 -- allow/deny lists
# ---------------------------------------------------------------------------


def test_x512_deny_wins_and_allowlist_is_required() -> None:
    policy = ManagedPolicy(
        allow_mcp=frozenset({"mcp-a"}),
        deny_mcp=frozenset({"mcp-b"}),
        allow_plugins=frozenset({"p1"}),
        allow_model_hashes=frozenset({"sha256:abc"}),
    )
    assert evaluate_dependency(policy, "mcp_server", "mcp-a") is DependencyDecision.ALLOW
    assert evaluate_dependency(policy, "mcp_server", "mcp-b") is DependencyDecision.DENY
    assert evaluate_dependency(policy, "mcp_server", "mcp-c") is DependencyDecision.DENY
    assert evaluate_dependency(policy, "plugin", "p1") is DependencyDecision.ALLOW
    assert evaluate_dependency(policy, "model_hash", "sha256:abc") is DependencyDecision.ALLOW
    assert evaluate_dependency(policy, "unknown-kind", "x") is DependencyDecision.DENY


# ---------------------------------------------------------------------------
# X5.13 -- safe-paste detector
# ---------------------------------------------------------------------------


def test_x513_detects_key_patterns_without_echoing_secret() -> None:
    warning = detect_secret_paste("here: sk-abcdefghijklmnopqrstuvwxyz0123456789")
    assert warning.detected is True
    assert "openai_key" in warning.matches
    assert "sk-" not in b.canonical_bytes(warning.to_dict()).decode()


def test_x513_clean_text_is_not_flagged() -> None:
    assert detect_secret_paste("just a normal paragraph about models").detected is False


# ---------------------------------------------------------------------------
# X6.1 -- scaffold / hot reload / mock host
# ---------------------------------------------------------------------------


def test_x61_scaffold_is_deterministic_and_content_addressed() -> None:
    first = plugin_scaffold("My Plugin!")
    second = plugin_scaffold("My Plugin!")
    assert first == second
    paths = [f.path for f in first]
    assert all(p.startswith("plugins/my-plugin") for p in paths)
    assert all(len(f.to_dict()["content_digest"]) == 64 for f in first)


def test_x61_hot_reload_change_detection_and_mock_host() -> None:
    before = (FileState("a.py", "h1"), FileState("b.py", "h2"))
    after = (FileState("a.py", "h2"), FileState("b.py", "h2"))
    assert detect_changes(before, after) == ("a.py",)
    host = MockHost()
    host.emit("session.start", {"session_id": "s1"})
    host.call("read_file", {"path": "x"})
    assert len(host.event_stream) == 2
    assert host.event_stream[1]["payload"]["name"] == "read_file"


# ---------------------------------------------------------------------------
# X6.2 -- plugin test harness
# ---------------------------------------------------------------------------


def test_x62_golden_stream_compare_and_order_check() -> None:
    expected = ({"type": "a"}, {"type": "b"})
    assert compare_event_streams(expected, expected).matches is True
    diff = compare_event_streams(({"type": "b"}, {"type": "a"}), expected)
    assert diff.matches is True  # same set
    assert diff.order_matches is False
    missing = compare_event_streams(({"type": "a"},), expected)
    assert len(missing.missing) == 1


def test_x62_permission_denial_check() -> None:
    assert permission_denial_check("network", ["file.read"]).denied is True
    assert permission_denial_check("file.read", ["file.read"]).denied is False


# ---------------------------------------------------------------------------
# X6.3 -- typed SDK generation
# ---------------------------------------------------------------------------


def test_x63_generated_sdks_are_version_pinned_to_daemon() -> None:
    schema = b.ApiSchema(version=b.DAEMON_API_VERSION, methods=({"name": "ping", "path": "/ping"},))
    py = generate_python_sdk(schema)
    ts = generate_typescript_sdk(schema)
    assert "def ping" in py
    assert "DAEMON_API_VERSION" in ts
    assert assert_sdk_version_pinned(py, b.DAEMON_API_VERSION) is True
    assert assert_sdk_version_pinned(ts, b.DAEMON_API_VERSION) is True
    assert assert_sdk_version_pinned(py, "9.9.9") is False


# ---------------------------------------------------------------------------
# X6.4 -- API versioning policy
# ---------------------------------------------------------------------------


def test_x64_deprecation_headers_sunset_and_compatibility() -> None:
    headers = deprecation_headers(ApiVersion(1, 3, 0), "2026-12-01", "v2")
    assert headers["Deprecation"] == "true"
    assert headers["Sunset"] == "2026-12-01"
    assert "successor-version" in headers["Link"]
    assert is_compatible(parse_version("1.4"), parse_version("1.3")) is True
    assert is_compatible(parse_version("2.0"), parse_version("1.4")) is False
    today = date(2026, 11, 24)
    assert is_sunset(ApiVersion(1, 3), "2026-11-01", today) is True
    assert is_sunset(ApiVersion(1, 3), "2026-12-01", today) is False


# ---------------------------------------------------------------------------
# X6.5 -- API explorer guard
# ---------------------------------------------------------------------------


def test_x65_explorer_requires_loopback_and_token_docs_private_without_g7() -> None:
    assert explorer_access(True, True, False).allowed is True
    assert explorer_access(False, True, False).reason == "loopback_required"
    assert explorer_access(True, False, False).reason == "token_required"
    assert explorer_access(True, True, False).docs_public is False
    assert explorer_access(True, True, True).docs_public is True


# ---------------------------------------------------------------------------
# X6.6 -- event schema registry
# ---------------------------------------------------------------------------


def test_x66_every_registered_event_has_schema_and_changelog() -> None:
    for name, schema in b.EVENT_SCHEMAS.items():
        assert schema.name == name
        assert schema.schema["type"] == "object"
        assert schema.schema["required"]
        assert schema.changelog


def test_x66_validation_and_subscription_by_type() -> None:
    assert validate_event("tool.call", {"tool": "fs.read", "session_id": "s1"}).valid is True
    bad = validate_event("tool.call", {"tool": 5})
    assert bad.valid is False and any(e.startswith("missing:") for e in bad.errors)
    assert validate_event("unknown.event", {}).valid is False
    registry = SubscriptionRegistry()
    assert registry.subscribe("plugin-a", "session.start") is True
    assert registry.subscribe("plugin-b", "not.a.real.type") is False
    delivered = registry.dispatch("session.start", {"session_id": "s1", "at": 1})
    assert delivered == (("plugin-a", {"session_id": "s1", "at": 1}),)


# ---------------------------------------------------------------------------
# X6.8 -- layered config viewer
# ---------------------------------------------------------------------------


def test_x68_highest_precedence_layer_wins_with_provenance() -> None:
    layers = {
        ConfigLayer.DEFAULT: {"theme": "dark", "model": "auto"},
        ConfigLayer.GLOBAL: {"theme": "light"},
        ConfigLayer.PROJECT: {"model": "gpt"},
        ConfigLayer.ENV: {"theme": "system"},
    }
    resolved = resolve_layers(layers)
    assert resolved["theme"].value == "system"
    assert resolved["theme"].source_layer is ConfigLayer.ENV
    assert set(resolved["theme"].overridden_layers) == {"default", "global"}
    assert resolved["model"].source_layer is ConfigLayer.PROJECT
    assert resolved["model"].value == "gpt"


# ---------------------------------------------------------------------------
# X6.9 -- settings search / diff / reset / import-export
# ---------------------------------------------------------------------------


def test_x69_search_diff_reset_and_roundtrip() -> None:
    settings = {"provider": {"model": "gpt"}, "ui": {"theme": "dark"}}
    defaults = {"provider": {"model": "auto"}, "ui": {"theme": "dark"}}
    assert "provider.model" in search_settings(settings, "model")
    diff = diff_against_defaults(settings, defaults)
    assert diff.changed == (("provider.model", "auto", "gpt"),)
    reset = reset_section(settings, defaults, "provider")
    assert reset["provider"]["model"] == "auto"
    assert reset["ui"]["theme"] == "dark"  # other sections untouched
    assert import_settings(export_settings(settings)) == settings
    try:
        import_settings("[1,2,3]")
    except BackendError:
        pass
    else:
        raise AssertionError("non-object settings import must fail")


# ---------------------------------------------------------------------------
# X6.10 -- feature lifecycle labels
# ---------------------------------------------------------------------------


def test_x610_experimental_off_by_default_beta_stable_on() -> None:
    assert feature_enabled("X6.5", {}).lifecycle is FeatureLifecycle.EXPERIMENTAL
    assert feature_enabled("X6.5", {}).enabled is False
    assert feature_enabled("X6.8", {}).enabled is True
    assert feature_enabled("X6.5", {"X6.5": True}).enabled is True
    assert feature_enabled("not-registered", {}).enabled is False
    assert validate_feature_config({"X6.8": True, "bogus": 1}) == ("bogus",)


# ---------------------------------------------------------------------------
# Cross-cutting guarantees + verification of already-implemented P0 rows
# ---------------------------------------------------------------------------


def test_module_is_stdlib_only_and_does_no_io() -> None:
    source = Path(b.__file__).read_text(encoding="utf-8")
    imports: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imports.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    forbidden = {
        "cryptography", "keyring", "requests", "urllib", "socket", "subprocess",
        "sqlite3", "PIL", "ctypes", "pyperclip", "pyautogui", "win32clipboard",
    }
    assert imports.isdisjoint(forbidden), imports & forbidden


def test_deterministic_canonical_bytes() -> None:
    value = {"b": 2, "a": 1}
    assert b.canonical_bytes(value) == b'{"a":1,"b":2}'
    assert b.digest(value) == b.digest({"a": 1, "b": 2})


def test_already_implemented_p0_symbols_still_import() -> None:
    """Verify (do not reimplement) the prior P0 rows owned by this prefix group."""
    import keel.builder_contracts as bc
    import keel.clipboard_guard as cg
    import keel.provider_contracts as pc

    # E6.1 / E6.5 / E6.8 / E6.10
    for name in ("SecretDescriptor", "describe_secret", "ProviderDescriptor",
                 "ModelCapabilities", "CompatSwitches", "adapt_request"):
        assert hasattr(pc, name), name
    # X5.5 / X5.6 / X5.9
    for name in ("MassChangeGuard", "ChangeJournal", "ClipboardScreenGuard"):
        assert hasattr(cg, name), name
    # X6.7
    for name in ("did_you_mean", "validate_config_text", "jsonc_key_positions"):
        assert hasattr(bc, name), name


def test_semver_parse_rejects_garbage() -> None:
    for bad in ("", "1..2", "vX.Y"):
        try:
            parse_semver(bad)
        except BackendError:
            continue
        raise AssertionError(f"expected BackendError for {bad!r}")


def test_sunset_invalid_date_fails_closed() -> None:
    try:
        is_sunset(ApiVersion(1, 0), "not-a-date", date.today() + timedelta(days=1))
    except BackendError:
        return
    raise AssertionError("expected BackendError for invalid sunset date")
