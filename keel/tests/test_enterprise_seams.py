"""B6.2/B6.3/B6.5 — authorized edition, enterprise and compliance seams."""

from __future__ import annotations

import pytest

from keel import commercial_seams
from keel.commercial_seams import (compliance_pack, compliance_pack_status,
                                   data_flow_svg, edition_field,
                                   enterprise_templates, license_token_format,
                                   sbom_export, silent_install_flags,
                                   silent_install_matrix)


@pytest.fixture(autouse=True)
def _generated_inventory(tmp_path, monkeypatch):
    """Use a real, freshly generated inventory instead of a build artifact.

    The license data comes from the repo manifests and installed package
    metadata via ``write_inventory``; nothing is fabricated or committed.
    """
    from keel.release.licenses import write_inventory

    path = write_inventory(tmp_path / "DEPENDENCY-LICENSES.json")
    monkeypatch.setattr(commercial_seams, "LICENSE_INVENTORY", path)


def test_edition_remains_standard_and_inactive():
    assert edition_field()["edition"] == "standard"
    assert edition_field()["licensing_enabled"] is False
    assert license_token_format()["active"] is False


def test_manifests_carry_edition():
    from keel.release.common import build_download_manifest, build_release_manifest

    release = build_release_manifest({}, "0.1.1", "v0.1.1", "")
    download = build_download_manifest({}, "0.1.1", "v0.1.1", "",
                                       available=False, verified=False,
                                       verified_at=None)
    assert release["edition"] == "standard"
    assert download["edition"] == "standard"


def test_silent_install_matrix():
    flags = silent_install_matrix()
    for fmt in ("nsis", "msi", "pkg", "deb", "rpm"):
        assert flags[fmt]
    assert "/qn" in flags["msi"]
    assert "-pkg" in flags["pkg"]
    assert "/VERYSILENT" in silent_install_flags("windows")


def test_enterprise_templates_are_real_files():
    templates = enterprise_templates()
    for key in ("windows_admx", "macos_plist"):
        assert templates[key]["exists"] is True
        assert "Keel" in templates[key]["content"]


def test_compliance_pack_artifacts():
    assert "<svg" in data_flow_svg()
    sbom = sbom_export()
    assert sbom["format"] == "Keel-SBOM-1.0" and sbom["count"] > 0
    pack = compliance_pack()
    assert pack["status"]["data_flow_diagram"] == "generated"
    assert pack["status"]["sbom_export"] == "generated"
    assert pack["legal_templates"]["eula"].startswith("draft")
    assert compliance_pack_status()["security_whitepaper"] == "draft"


def test_capabilities():
    from keel import capability_registry  # noqa: F401
    from keel.capabilities import invoke

    assert invoke("core.edition.info", {}, context={})["result"]["edition"][
        "edition"] == "standard"
    t = invoke("core.enterprise.templates", {}, context={})["result"]
    assert t["templates"]["windows_admx"]["exists"] is True
    p = invoke("core.compliance.pack", {}, context={})["result"]
    assert p["sbom"]["count"] > 0
