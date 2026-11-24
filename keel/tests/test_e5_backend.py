"""E5.x remaining backend contracts — packaging, lifecycle, release and updater.

Adversarial, stdlib-only coverage of :mod:`keel.e5_backend`. No network,
subprocess, filesystem write or real credential is used: every side effect
(health check, signature check, liveness probe) is an injected callable whose
call order the tests assert.
"""

from __future__ import annotations

import copy
import hashlib

import pytest

from keel import e5_backend as eb

VERSION = "1.2.3"


def _digests(*names: str) -> dict[str, str]:
    return {name: hashlib.sha256(name.encode("utf-8")).hexdigest() for name in names}


# --------------------------------------------------------------------------
# E5.2 — single release identity
# --------------------------------------------------------------------------

def test_e5_2_shell_and_backend_share_one_exact_version():
    identity = eb.release_identity(VERSION)
    assert identity["version"] == identity["shell_version"] == identity["backend_version"]
    assert identity["single_version"] is True
    assert identity["upgrade_requires_desktop_release"] is True
    assert identity["updates_one_side_only"] is False
    eb.assert_release_identity(identity)


@pytest.mark.parametrize("field,value", [
    ("shell_version", "9.9.9"),
    ("backend_version", "1.2.4"),
    ("single_version", False),
    ("upgrade_requires_desktop_release", False),
    ("updates_one_side_only", True),
])
def test_e5_2_adversarial_split_identity_rejected(field, value):
    identity = eb.release_identity(VERSION)
    identity[field] = value
    with pytest.raises(eb.ReleaseIdentityError):
        eb.assert_release_identity(identity)


def test_e5_2_independent_version_field_forbidden():
    identity = eb.release_identity(VERSION)
    identity["backend_only_version"] = "1.2.3+backend.1"
    with pytest.raises(eb.ReleaseIdentityError, match="independent version"):
        eb.assert_release_identity(identity)


@pytest.mark.parametrize("bad", ["", "1.2", "v1.2.3", "1.2.3.4", None])
def test_e5_2_malformed_version_rejected(bad):
    with pytest.raises(eb.ReleaseIdentityError):
        eb.release_identity(bad)


# --------------------------------------------------------------------------
# E5.3 — bundled runtime only
# --------------------------------------------------------------------------

def test_e5_3_bundled_runtime_descriptor_is_self_consistent():
    descriptor = eb.bundled_runtime_descriptor()
    assert descriptor["python_source"] == "bundled_embedded"
    assert descriptor["backend_runtime"] == "bundled_python"
    assert descriptor["site_packages_source"] == "bundled_seed_only"
    eb.assert_bundled_runtime(descriptor)


@pytest.mark.parametrize("field", [
    "system_python_allowed", "package_manager_state_allowed",
    "reads_system_site_packages", "shell_runtime_for_backend",
])
def test_e5_3_adversarial_system_or_shell_runtime_rejected(field):
    descriptor = eb.bundled_runtime_descriptor()
    descriptor[field] = True
    with pytest.raises(eb.RuntimeIsolationError, match=field):
        eb.assert_bundled_runtime(descriptor)


@pytest.mark.parametrize("field,value", [
    ("python_source", "system"),
    ("backend_runtime", "shell_node_runtime"),
    ("site_packages_source", "system_site_packages"),
])
def test_e5_3_adversarial_runtime_source_rejected(field, value):
    descriptor = eb.bundled_runtime_descriptor()
    descriptor[field] = value
    with pytest.raises(eb.RuntimeIsolationError):
        eb.assert_bundled_runtime(descriptor)


# --------------------------------------------------------------------------
# E5.5 — transactional activation, journal, rollback and lock owner
# --------------------------------------------------------------------------

def test_e5_5_activation_policy_orders_staging_before_swap():
    descriptor = eb.activation_descriptor()
    assert descriptor["steps"][0] == "stage"
    assert descriptor["steps"].index("health_check") < descriptor["steps"].index("swap_active")
    assert descriptor["full_backend_health_check"] is True
    assert descriptor["swap_only_after_success"] is True
    assert descriptor["rollback_profiles"] == 1
    assert descriptor["recovery"] == "journal_plus_actual_directories"
    assert descriptor["orphaned_worker_not_stale"] is True


def test_e5_5_journal_stages_and_retains_one_rollback_profile():
    journal = eb.plan_activation("tx-1", "staged-v2", "active-v1")
    assert journal.state == "staged"
    assert journal.staged_profile == "staged-v2"
    assert journal.active_profile == "active-v1"
    assert journal.rollback_profile == "active-v1--rollback"
    with pytest.raises(eb.ActivationError, match="must differ"):
        eb.plan_activation("tx-2", "same", "same")


def test_e5_5_health_check_probes_staged_profile_and_gates_swap():
    journal = eb.plan_activation("tx-1", "staged-v2", "active-v1")
    probed = []

    def healthy(profile):
        probed.append(profile)
        return True

    committed = eb.execute_activation(journal, health_check=healthy)
    assert probed == ["staged-v2"]  # never probe the currently active profile
    assert committed.state == "committed"
    with pytest.raises(eb.ActivationError, match="already"):
        eb.execute_activation(committed, health_check=healthy)


def test_e5_5_failed_health_check_rolls_back_without_swap():
    journal = eb.plan_activation("tx-1", "staged-v2", "active-v1")
    rolled_back = eb.execute_activation(journal, health_check=lambda profile: False)
    assert rolled_back.state == "rolled_back"
    recovery = eb.recover_activation(
        rolled_back, present_profiles=["active-v1", "active-v1--rollback", "staged-v2"])
    assert recovery == {"action": "keep", "profile": "active-v1",
                        "reason": "rolled_back_active_present"}


def test_e5_5_recovery_combines_journal_with_actual_directories():
    committed = eb.execute_activation(
        eb.plan_activation("tx-1", "staged-v2", "active-v1"),
        health_check=lambda profile: True)
    assert eb.recover_activation(
        committed, present_profiles=["active-v1", "staged-v2"])["action"] == "keep"
    assert eb.recover_activation(
        committed, present_profiles=["active-v1--rollback"]) == {
            "action": "rollback", "profile": "active-v1--rollback",
            "reason": "committed_active_missing"}
    with pytest.raises(eb.ActivationError, match="both missing"):
        eb.recover_activation(committed, present_profiles=[])


def test_e5_5_incomplete_staging_is_discarded():
    journal = eb.plan_activation("tx-1", "staged-v2", "active-v1")
    result = eb.recover_activation(
        journal, present_profiles=["active-v1", "active-v1--rollback", "staged-v2"])
    assert result["action"] == "discard_staged"
    assert result["profile"] == "active-v1"
    with pytest.raises(eb.ActivationError, match="active profile missing"):
        eb.recover_activation(journal, present_profiles=[])


def test_e5_5_lock_records_owner_and_orphan_worker_is_not_stale():
    lock = eb.TransactionLock(owner="worker-7", pid=4242, heartbeat=3)
    eb.assert_transaction_owner(lock, "worker-7")
    with pytest.raises(eb.ActivationError, match="owned by"):
        eb.assert_transaction_owner(lock, "worker-8")
    # Parent may be gone; the worker still answers its liveness probe.
    assert eb.is_transaction_stale(lock, liveness_probe=lambda current: True) is False
    assert eb.is_transaction_stale(lock, liveness_probe=lambda current: False) is True


# --------------------------------------------------------------------------
# E5.6 — deterministic 16-shard offline seed store
# --------------------------------------------------------------------------

def test_e5_6_seed_manifest_is_deterministic_and_uncompressed():
    packages = _digests(*(f"pkg-{i}" for i in range(40)))
    manifest = eb.seed_manifest(packages)
    assert manifest["shard_count"] == 16
    assert manifest["compression"] == "none"
    assert manifest["differential_updates"] is True
    assert len(manifest["shards"]) == 16
    assert [shard["index"] for shard in manifest["shards"]] == list(range(16))
    assert all(shard["compression"] == "none" for shard in manifest["shards"])
    assert eb.seed_manifest(dict(reversed(list(packages.items())))) == manifest
    eb.assert_seed_manifest(manifest, expected_packages=packages)


def test_e5_6_shard_assignment_stable_and_covers_all_packages():
    packages = _digests("alpha", "beta", "gamma")
    manifest = eb.seed_manifest(packages)
    placed = [m["name"] for shard in manifest["shards"] for m in shard["members"]]
    assert sorted(placed) == sorted(packages)
    for shard in manifest["shards"]:
        for member in shard["members"]:
            assert eb.seed_shard_for(member["name"]) == shard["index"]
    assert 0 <= eb.seed_shard_for("alpha") < 16


def test_e5_6_adversarial_manifest_tampering_rejected():
    packages = _digests(*(f"pkg-{i}" for i in range(20)))
    manifest = eb.seed_manifest(packages)
    bad_count = copy.deepcopy(manifest)
    bad_count["shard_count"] = 8
    with pytest.raises(eb.SeedPackagingError, match="16 shards"):
        eb.assert_seed_manifest(bad_count)
    bad_compression = copy.deepcopy(manifest)
    bad_compression["compression"] = "gzip"
    with pytest.raises(eb.SeedPackagingError, match="uncompressed"):
        eb.assert_seed_manifest(bad_compression)
    bad_member = copy.deepcopy(manifest)
    shard = next(s for s in bad_member["shards"] if s["members"])
    shard["members"][0]["sha256"] = "0" * 64
    with pytest.raises(eb.SeedPackagingError, match="digest"):
        eb.assert_seed_manifest(bad_member)
    with pytest.raises(eb.SeedPackagingError, match="expected packages"):
        eb.assert_seed_manifest(manifest, expected_packages={"missing-pkg": "1" * 64})


def test_e5_6_offline_install_gate_and_first_run_descriptor():
    packages = _digests("alpha", "beta")
    manifest = eb.seed_manifest(packages)
    with pytest.raises(eb.SeedPackagingError, match="offline install"):
        eb.offline_install_gate(manifest, verified_offline=False,
                                expected_packages=packages)
    eb.offline_install_gate(manifest, verified_offline=True,
                            expected_packages=packages)
    assert eb.verify_seed_shard(
        manifest["shards"][0],
        expected_digest=manifest["shards"][0]["sha256"].upper()) is True
    descriptor = eb.first_run_extraction_descriptor()
    assert descriptor["when"] == "first_run"
    assert descriptor["verify_each_shard"] is True
    assert descriptor["disk_use_measured_separately_from_download_size"] is True


# --------------------------------------------------------------------------
# E5.7 — signed update unit, schedule, in-flight coalescing, install flow
# --------------------------------------------------------------------------

def _unit(**overrides):
    kwargs = dict(
        version=VERSION,
        shell_digest="a" * 64,
        seed_digest="b" * 64,
        runtime_digest="c" * 64,
        signature="ed25519-signature-material",
    )
    kwargs.update(overrides)
    return eb.update_unit_descriptor(**kwargs)


def test_e5_7_update_unit_binds_all_three_components():
    unit = _unit()
    assert set(unit["components"]) == set(eb.UPDATE_COMPONENTS)
    assert unit["signed"] is True and unit["single_unit"] is True
    eb.assert_update_unit(unit, expected_version=VERSION)


def test_e5_7_adversarial_unit_rejected():
    mismatch = _unit()
    with pytest.raises(eb.UpdateUnitError, match="version"):
        eb.assert_update_unit(mismatch, expected_version="9.9.9")
    unsigned = _unit()
    unsigned["signature"] = ""
    with pytest.raises(eb.UpdateUnitError, match="signature"):
        eb.assert_update_unit(unsigned)
    missing_component = _unit()
    del missing_component["components"]["runtime"]
    with pytest.raises(eb.UpdateUnitError, match="backend_seed"):
        eb.assert_update_unit(missing_component)
    bad_digest = _unit()
    bad_digest["components"]["backend_seed"] = "not-a-digest"
    with pytest.raises(eb.UpdateUnitError, match="SHA-256"):
        eb.assert_update_unit(bad_digest)


def test_e5_7_schedule_and_in_flight_coalescing():
    schedule = eb.update_schedule()
    assert schedule["startup_check_delay_seconds"] == 10
    assert "Check for updates" in schedule["manual_check_menu_item"]
    assert schedule["native_confirmation_dialog"] is True
    assert schedule["wait_for_in_flight_check"] is True
    coordinator = eb.UpdateCheckCoordinator()
    assert coordinator.request_check()["started"] is True
    assert coordinator.request_check() == {
        "started": False, "waited": True, "reason": "check_in_flight"}
    coordinator.finish()
    assert coordinator.request_check()["started"] is True
    coordinator.finish()
    with eb.UpdateCheckCoordinator() as active:
        assert active.in_flight is True
    assert active.in_flight is False


def test_e5_7_install_plan_verifies_before_stopping_backend():
    unit = _unit()
    calls = []

    def verifier(candidate):
        calls.append(("verify", candidate["version"]))
        return True

    plan = eb.update_install_plan(
        unit, expected_version=VERSION, verify_signature=verifier)
    assert calls == [("verify", VERSION)]
    kinds = [op["kind"] for op in plan["operations"]]
    assert kinds == ["verify", "stop_backend", "install", "reconcile_next_launch"]


def test_e5_7_bad_signature_blocks_install():
    calls = []

    def verifier(candidate):
        calls.append(candidate["version"])
        return False

    with pytest.raises(eb.UpdateUnitError, match="signature verification failed"):
        eb.update_install_plan(
            _unit(), expected_version=VERSION, verify_signature=verifier)
    assert calls == [VERSION]  # no install operations are produced on failure


# --------------------------------------------------------------------------
# E5.8 — narrow plugin-manager renderer surface
# --------------------------------------------------------------------------

def test_e5_8_surface_lists_only_structured_operations():
    surface = eb.plugin_manager_surface()
    assert surface["renderer"] == "separate"
    assert surface["operations"] == ["list", "install", "remove", "update"]
    assert surface["no_filesystem"] is True
    assert surface["no_raw_ipc"] is True
    assert surface["no_shell"] is True
    assert surface["no_arbitrary_package_manager_args"] is True


@pytest.mark.parametrize("kind", eb.PLUGIN_MANAGER_OPERATIONS)
def test_e5_8_valid_operations_authorized(kind):
    request = eb.authorize_plugin_operation({"operation": kind, "plugin": "demo-plugin"})
    assert request["authorized"] is True
    assert request["operation"] == kind
    aliased = eb.authorize_plugin_operation({"kind": kind, "plugin": "demo-plugin"})
    assert aliased == request


@pytest.mark.parametrize("bad", [
    {"operation": "exec", "plugin": "demo"},
    {"operation": "install", "plugin": "demo", "path": "/etc/passwd"},
    {"operation": "install", "plugin": "demo", "argv": ["--global"]},
    {"operation": "install", "plugin": "demo", "shell": "rm -rf /"},
    {"operation": "install", "plugin": "demo", "raw_ipc": "{}"},
    {"operation": "install", "plugin": "../escape"},
    {"operation": "install", "plugin": "demo;curl evil"},
    {"operation": "install", "plugin": 42},
])
def test_e5_8_adversarial_request_rejected(bad):
    with pytest.raises(eb.PluginSurfaceError):
        eb.authorize_plugin_operation(bad)


# --------------------------------------------------------------------------
# E5.10 — shared localized shell copy with English fallback
# --------------------------------------------------------------------------

def _catalog():
    return {
        "en": {
            "menus": {"file": "File", "quit": "Quit"},
            "native_dialogs": {"file": "File", "quit": "Quit"},
            "plugin_window": {"file": "File", "quit": "Quit"},
        },
        "fr": {
            "menus": {"file": "Fichier"},  # 'quit' falls back to English
            "native_dialogs": {"file": "Fichier"},
            "plugin_window": {"file": "Fichier"},
        },
    }


def test_e5_10_localized_payload_shared_with_english_fallback():
    payload = eb.locale_payload("fr", _catalog(), ["file", "quit"])
    assert payload["locale"] == "fr"
    assert payload["fallback"] == "en" and payload["shared"] is True
    assert set(payload["surfaces"]) == set(eb.SHELL_LOCALE_SURFACES)
    assert all(row == {"file": "Fichier", "quit": "Quit"}
               for row in payload["surfaces"].values())
    assert payload["missing_keys"] == ()
    eb.assert_locale_payload(payload)


def test_e5_10_missing_english_copy_is_reported_not_dropped():
    catalog = _catalog()
    for table in catalog["en"].values():
        del table["quit"]
    payload = eb.locale_payload("fr", catalog, ["file", "quit"])
    assert len(payload["missing_keys"]) == 3
    with pytest.raises(eb.LocaleError, match="missing"):
        eb.assert_locale_payload(payload)


def test_e5_10_adversarial_payload_rejected():
    payload = eb.locale_payload("en", _catalog(), ["file"])
    payload["shared"] = False
    with pytest.raises(eb.LocaleError, match="share"):
        eb.assert_locale_payload(payload)
    payload = eb.locale_payload("en", _catalog(), ["file"])
    payload["fallback"] = "fr"
    with pytest.raises(eb.LocaleError, match="English"):
        eb.assert_locale_payload(payload)
    payload = eb.locale_payload("en", _catalog(), ["file"])
    del payload["surfaces"]["plugin_window"]
    with pytest.raises(eb.LocaleError, match="plugin window"):
        eb.assert_locale_payload(payload)
    assert eb.i18n_gate_scope()["checks_desktop_shell_sources"] is True


# --------------------------------------------------------------------------
# E5.11 — disposable dev home, env debug ports, packaged override isolation
# --------------------------------------------------------------------------

def test_e5_11_dev_home_is_disposable_and_scoped():
    descriptor = eb.dev_home_descriptor("tmp-dev-home")
    assert descriptor["disposable"] is True
    assert descriptor["environment"] == "development"
    assert set(descriptor["scopes"]) == set(eb.DEV_HOME_SCOPES)
    assert all(path.startswith("tmp-dev-home/") for path in descriptor["scopes"].values())
    with pytest.raises(eb.DevIsolationError):
        eb.dev_home_descriptor("../escape")


def test_e5_11_debug_ports_validated_from_environment():
    ports = eb.dev_debug_ports({
        "KEEL_DEV_DEBUG_PORT": "9222",
        "KEEL_DEV_BROWSER_DEBUG_PORT": "9333",
    })
    assert ports == {"backend_debug_port": 9222, "browser_debug_port": 9333}
    assert eb.dev_debug_ports({}) == {
        "backend_debug_port": None, "browser_debug_port": None}
    for bad in ("0", "70000", "not-a-port"):
        with pytest.raises(eb.DevIsolationError):
            eb.dev_debug_ports({"KEEL_DEV_DEBUG_PORT": bad})


def test_e5_11_devtools_toggle_and_packaged_override_isolation():
    assert eb.devtools_descriptor({"KEEL_DEVTOOLS_AUTO_OPEN": "1"})["auto_open"] is True
    assert eb.devtools_descriptor({})["auto_open"] is False
    overrides = {"KEEL_DEV_DEBUG_PORT": "9222"}
    dev = eb.effective_dev_config(False, overrides)
    assert dev["applied"] == overrides and dev["ignored"] is False
    packaged = eb.effective_dev_config(True, overrides)
    assert packaged["applied"] == {} and packaged["ignored"] is True


# --------------------------------------------------------------------------
# E5.13 — release prerequisite validation
# --------------------------------------------------------------------------

@pytest.mark.parametrize("app_id", ["com.example.keel", "io.keel.desktop", "dev.keel"])
def test_e5_13_valid_app_ids(app_id):
    assert eb.validate_app_id(app_id) == app_id


@pytest.mark.parametrize("app_id", ["", "no-dots", ".leading", "trailing.", "bad..id", "a/b"])
def test_e5_13_malformed_app_id_rejected(app_id):
    with pytest.raises(eb.PrerequisiteError, match="application id"):
        eb.validate_app_id(app_id)


def test_e5_13_release_prerequisites_ready_when_complete():
    env = {name: "credential-value" for name in eb.RELEASE_CREDENTIAL_NAMES}
    result = eb.validate_release_prerequisites(env, app_id="com.example.keel")
    assert result["ready"] is True
    assert result["credentials_present"] == tuple(sorted(eb.RELEASE_CREDENTIAL_NAMES))


def test_e5_13_incomplete_credential_set_rejected():
    env = {name: "credential-value" for name in eb.RELEASE_CREDENTIAL_NAMES[:-1]}
    with pytest.raises(eb.PrerequisiteError, match="incomplete credential set"):
        eb.validate_release_prerequisites(env, app_id="com.example.keel")


def test_e5_13_malformed_identity_value_rejected():
    env = {name: "credential-value" for name in eb.RELEASE_CREDENTIAL_NAMES}
    env["KEEL_RELEASE_TOKEN"] = "token\nwith-newline"
    with pytest.raises(eb.PrerequisiteError, match="control character"):
        eb.validate_release_prerequisites(env, app_id="com.example.keel")
    with pytest.raises(eb.PrerequisiteError, match="application id"):
        eb.validate_release_prerequisites(env, app_id="bad-id")


# --------------------------------------------------------------------------
# E5.16 — distinct test/production update origins
# --------------------------------------------------------------------------

def test_e5_16_named_environments_have_distinct_origins():
    test = eb.update_environment("test")
    production = eb.update_environment("production")
    assert test["channel"] != production["channel"]
    eb.assert_distinct_update_origins({"test": test, "production": production})
    with pytest.raises(eb.UpdateEnvironmentError, match="unknown"):
        eb.update_environment("staging")


def test_e5_16_adversarial_shared_origin_rejected():
    production = eb.update_environment("production")
    # Same host, different path — still the same origin, so must be rejected.
    shared = {"test": {"origin": production["origin"] + "/beta"},
              "production": production}
    with pytest.raises(eb.UpdateEnvironmentError, match="distinct origins"):
        eb.assert_distinct_update_origins(shared)
    with pytest.raises(eb.UpdateEnvironmentError):
        eb.assert_distinct_update_origins({"test": {"origin": "/relative"},
                                           "production": production})
    with pytest.raises(eb.UpdateEnvironmentError, match="missing"):
        eb.assert_distinct_update_origins({"test": eb.update_environment("test")})


# --------------------------------------------------------------------------
# E5.17 — signing/notarization verification pattern
# --------------------------------------------------------------------------

def test_e5_17_signing_plan_covers_required_steps():
    plan = eb.signing_plan("macos-dmg")
    assert plan["steps"] == list(eb.SIGNING_STEPS["macos-dmg"])
    assert "notarize" in plan["steps"] and "staple" in plan["steps"]
    assert plan["timestamp_every_embedded_executable"] is True
    assert plan["pin_persisted"] is False
    assert set(eb.signing_plan("windows-exe")["steps"]) >= {
        "timestamp", "ev_token_sign", "deep_strict_verify"}


def _signed_steps(target="macos-dmg", authority=None):
    authority = authority or eb.EXPECTED_SIGNING_AUTHORITIES[target]
    return [
        {"name": name, "ok": True, "authority": authority}
        for name in eb.SIGNING_STEPS[target]
    ]


def test_e5_17_complete_steps_with_expected_authority_pass():
    eb.assert_signing_steps_complete("macos-dmg", _signed_steps())


def test_e5_17_adversarial_signing_failures():
    with pytest.raises(eb.SigningError, match="notarize"):
        eb.assert_signing_steps_complete(
            "macos-dmg", [s for s in _signed_steps() if s["name"] != "notarize"])
    failed = _signed_steps()
    next(s for s in failed if s["name"] == "staple")["ok"] = False
    with pytest.raises(eb.SigningError, match="did not succeed"):
        eb.assert_signing_steps_complete("macos-dmg", failed)
    with pytest.raises(eb.SigningError, match="unexpected signing authority"):
        eb.assert_signing_steps_complete(
            "macos-dmg", _signed_steps(authority="Untrusted Authority"))


def test_e5_17_diagnostics_redacted_and_pin_never_persisted():
    text = eb.redact_diagnostics(
        "signing failed PIN=1234 token=abcd for KEEL_RELEASE_TOKEN=top-secret",
        secrets=["top-secret"])
    assert "1234" not in text and "abcd" not in text and "top-secret" not in text
    assert text.count("[REDACTED]") >= 3
    eb.assert_signing_pin_not_persisted({"KEEL_SIGNING_MODE": "ev-token"})
    with pytest.raises(eb.SigningError, match="never be persisted"):
        eb.assert_signing_pin_not_persisted({"WINDOWS_SIGNING_PIN": "1234"})


def test_e5_17_multiword_secret_value_is_fully_redacted():
    text = eb.redact_diagnostics("token=super secret value here")
    assert text == "token=[REDACTED]"
    assert "super secret" not in text and "value here" not in text

    bounded = eb.redact_diagnostics(
        "token=super secret value; user=bob\npassword=long pass phrase")
    assert "super secret value" not in bounded
    assert "long pass phrase" not in bounded
    assert "user=bob" in bounded
    assert bounded.count("[REDACTED]") == 2


def test_e5_17_bare_bearer_token_is_redacted():
    """Audit C9: a bare ``Bearer <token>`` has no key assignment to match."""
    for text in ("INFO authorization: Bearer plaintexttoken12345 done",
                 "INFO Bearer plaintexttoken12345 done"):
        cleaned = eb.redact_diagnostics(text)
        assert "plaintexttoken12345" not in cleaned
        assert "Bearer" not in cleaned
        assert "[REDACTED]" in cleaned


# --------------------------------------------------------------------------
# E5.18 — Keel keeps Linux; dsh does not
# --------------------------------------------------------------------------

def test_e5_18_linux_formats_declared_and_validated():
    descriptor = eb.linux_release_targets()
    assert descriptor["keel_supports_linux"] is True
    assert descriptor["reference_dsh_supports_linux"] is False
    assert descriptor["formats"] == ["AppImage", "DEB", "RPM"]
    eb.assert_linux_release_targets(descriptor["formats"])


def test_e5_18_adversarial_format_set_rejected(monkeypatch):
    with pytest.raises(eb.LinuxTargetError, match="appimage"):
        eb.assert_linux_release_targets(["AppImage", "DEB"])
    with pytest.raises(eb.LinuxTargetError, match="appimage"):
        eb.assert_linux_release_targets(["flatpak", "snap", "deb"])
    wrong_reference = eb.linux_release_targets()
    wrong_reference["reference_dsh_supports_linux"] = True
    monkeypatch.setattr(eb, "linux_release_targets", lambda: wrong_reference)
    with pytest.raises(eb.LinuxTargetError, match="dsh"):
        eb.assert_linux_release_targets(eb.LINUX_RELEASE_FORMATS)


# --------------------------------------------------------------------------
# E5.19 — known-limitations section
# --------------------------------------------------------------------------

def test_e5_19_section_documents_every_required_topic():
    text = eb.known_limitations_section()
    assert text.startswith("## Known limitations")
    eb.assert_known_limitations_complete(text)
    for topic in ("server_dependent_features", "shared_vs_separate_state",
                  "release_qualification_needs_production"):
        assert topic in text


def test_e5_19_adversarial_incomplete_section_rejected():
    with pytest.raises(eb.LimitationsError, match="Known limitations"):
        eb.assert_known_limitations_complete("")
    incomplete = eb.known_limitations_section().replace(
        "release_qualification_needs_production", "")
    with pytest.raises(eb.LimitationsError, match="release_qualification"):
        eb.assert_known_limitations_complete(incomplete)
