"""B6.x — dormant commercial seams (no licensing enforced)."""

from __future__ import annotations

from keel.commercial_seams import (compliance_pack_status, edition_field,
                                   license_token_format, silent_install_flags)


def test_edition_is_standard_and_inactive():
    field = edition_field()
    assert field["edition"] == "standard" and field["licensing_enabled"] is False
    assert license_token_format()["active"] is False


def test_silent_flags_and_compliance():
    assert "/VERYSILENT" in silent_install_flags("windows")
    assert compliance_pack_status()["security_whitepaper"] == "draft"
