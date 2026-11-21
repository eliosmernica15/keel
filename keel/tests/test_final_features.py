"""Final local feature descriptors."""

from __future__ import annotations

import pytest

from keel.final_features import (EncryptedBackups, admin_page, browser_devtools,
                                 ci_mode, deep_research, delta_update,
                                 incident_runbook, lan_companion, localized,
                                 composer_accessibility, meeting_recorder,
                                 obfuscation_status, org_audit_retention,
                                 package_manager_targets, private_update_mirror,
                                 remote_target, voice_handoff)


def test_voice_and_meeting(tmp_path):
    assert voice_handoff("s1", "do the thing")["status"] == "queued"
    rec = meeting_recorder(tmp_path / "m.wav")
    assert rec["speaker_labels"] is True and rec["consent_required"] is True


def test_research_backup_updates(tmp_path):
    doc = deep_research("topic", ["a", "b"])
    assert doc["citations"] == []
    backups = EncryptedBackups(tmp_path)
    assert backups.schedule(24, "local")["interval_h"] == 24
    assert delta_update("beta")["beta_opt_in"] is True
    assert delta_update("stable")["beta_opt_in"] is False


def test_companion_localization_and_security():
    assert lan_companion()["pairing"] == "required"
    assert localized("app", "es") == "Keel"
    assert "rotate" in incident_runbook()[0]
    assert obfuscation_status()["nuitka_core"] is False


def test_remote_and_ci():
    assert remote_target("ssh")["enabled"] is False
    with pytest.raises(ValueError):
        remote_target("cloud")
    assert "console" in browser_devtools()
    assert ci_mode()["headless"] is True
    assert admin_page()["health"] is True


def test_distribution_and_accessibility_descriptors():
    assert composer_accessibility()["opt_in"] is True
    assert private_update_mirror("https://mirror.test")["requires_signed_manifest"]
    assert org_audit_retention(30)["retention_days"] == 30
    assert "scoop" in package_manager_targets()
