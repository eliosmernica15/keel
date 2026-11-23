"""B6.x — dormant commercial seams (no licensing enforced)."""

from __future__ import annotations

import json

from keel import commercial_seams
from keel.commercial_seams import (compliance_pack_status, edition_field,
                                   license_token_format, silent_install_flags)
from keel.release.common import LICENSE_INVENTORY


def test_edition_is_standard_and_inactive():
    field = edition_field()
    assert field["edition"] == "standard" and field["licensing_enabled"] is False
    assert license_token_format()["active"] is False


def test_silent_flags_and_compliance():
    assert "/VERYSILENT" in silent_install_flags("windows")
    assert compliance_pack_status()["security_whitepaper"] == "draft"


def test_generator_and_sbom_consumer_share_canonical_inventory_path(
        tmp_path, monkeypatch):
    assert LICENSE_INVENTORY.name == "DEPENDENCY-LICENSES.json"
    assert LICENSE_INVENTORY.parent.name == "release"
    assert commercial_seams.LICENSE_INVENTORY == LICENSE_INVENTORY

    inventory = tmp_path / "DEPENDENCY-LICENSES.json"
    inventory.write_text(json.dumps({"packages": {"tzdata": {
        "license": "MIT", "version": "test-only"}}}), encoding="utf-8")
    monkeypatch.setattr(commercial_seams, "LICENSE_INVENTORY", inventory)
    sbom = commercial_seams.sbom_export()
    assert sbom["count"] == 1
    assert sbom["dependencies"][0]["name"] == "tzdata"

    # ``licenses --out release`` (the default) writes that same canonical path.
    from keel.release import licenses

    generated = tmp_path / "generated" / "DEPENDENCY-LICENSES.json"
    monkeypatch.setattr(licenses, "LICENSE_INVENTORY", generated)

    def fake_write_inventory(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"python": [], "electron": [],
                                    "unresolved": []}), encoding="utf-8")
        return path

    monkeypatch.setattr(licenses, "write_inventory", fake_write_inventory)

    class Args:
        out = "release"

    assert licenses.licenses_command(Args()) == 0
    assert generated.is_file()
