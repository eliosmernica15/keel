"""Closure of the 14 remaining v6 items: local implementation evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from keel.document_gaps import (build_screenshot_gallery, console_network_capture,
                                ocr_image, ocr_tool_status, parse_pdf,
                                visual_diff)
from keel.platform_gaps import (CompanionApprovals, LocalTaskExecutor,
                                OrgAuditExport, SiteToolkit, build_canary,
                                companion_identity)
from keel.release_gaps import (StatusConfig, airgap_bundle, check_status,
                               package_manager_manifests, render_status_html,
                               verify_sideload)

from fixtures.release_tree import build_release_tree


def test_c12_package_manager_manifests(tmp_path):
    release, _ = build_release_tree(tmp_path)
    result = package_manager_manifests(release, tmp_path / "pkgs")
    assert set(result["generated"]) == {
        "scoop.json", "chocolatey.nuspec", "keel.desktop",
        "snapcraft.yaml", "PKGBUILD", "flake.nix"}
    scoop = json.loads((tmp_path / "pkgs" / "scoop.json").read_text())
    assert scoop["version"] and scoop["architecture"] == "64bit"
    assert result["published"] is False
    assert all("verify" in v or "unfree" in v
               for v in result["store_acceptance"].values())


def test_c122_airgap_bundle_and_verification(tmp_path):
    release, _ = build_release_tree(tmp_path)
    bundle = airgap_bundle(release, tmp_path / "bundle")
    assert bundle["version"] and "RELEASE-SHA256SUMS.txt" in bundle["files"]
    doc = json.loads((tmp_path / "bundle" / "AIRGAP-MANIFEST.json").read_text())
    assert doc["format"] == "Keel-Airgap-1.0"
    verdict = verify_sideload(tmp_path / "bundle")
    assert verdict["ok"] is True and verdict["checked"] >= 1
    (tmp_path / "bundle" / "Keel-Setup-0.1.0.exe.blockmap").write_text("tampered")
    assert verify_sideload(tmp_path / "bundle")["ok"] is False


def test_b59_status_config_and_real_check(tmp_path):
    config = StatusConfig(tmp_path)
    assert config.load()["update_feed_url"] == ""
    saved = config.save({"update_feed_url": "http://127.0.0.1:1/manifest",
                         "mirrors": ["http://127.0.0.1:1/mirror"]})
    assert saved["mirrors"]
    result = check_status(saved)
    assert result["update_feed"]["status"] == "unreachable"
    assert "<html" in render_status_html(result)
    try:
        config.save({"update_feed_url": "ftp://example.com"})
    except ValueError:
        pass
    else:
        raise AssertionError("invalid URL accepted")


def test_b212_ocr_honesty(tmp_path):
    status = ocr_tool_status()
    assert "tools" in status and "license_note" in status
    if not status["ocr_available"]:
        assert ocr_image(tmp_path / "missing.png")["ok"] is False
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    parsed = parse_pdf(pdf)
    assert parsed["license"] == "BSD-3-Clause"


def test_b56_screenshot_gallery_uses_real_images(tmp_path):
    from PIL import Image

    shots = tmp_path / "screenshots"
    shots.mkdir()
    Image.new("RGB", (120, 80), (20, 20, 30)).save(shots / "app-screenshot.png")
    result = build_screenshot_gallery([shots], tmp_path / "gallery")
    assert result["count"] == 1
    page = (tmp_path / "gallery" / "index.html").read_text()
    assert "app-screenshot.png" in page and "No stock images" in page


def test_c411_visual_diff_and_capture():
    from PIL import Image

    a, b = Path("/tmp/a.png"), Path("/tmp/b.png")
    Image.new("RGB", (40, 40), (0, 0, 0)).save(a)
    Image.new("RGB", (40, 40), (255, 255, 255)).save(b)
    result = visual_diff(a, b)
    assert result["ok"] is True and result["changed_pct"] > 90
    same = visual_diff(a, a)
    assert same["changed_pixels"] == 0
    capture = console_network_capture([
        {"kind": "console", "level": "error", "text": "boom"},
        {"kind": "network", "status": 500, "url": "/api/x"}])
    assert len(capture["errors"]) == 1 and len(capture["failed_requests"]) == 1


def test_b48_companion_identity_and_approvals(tmp_path):
    ident = companion_identity(tmp_path)
    assert ident["payload"].startswith("keel://pair?")
    assert len(ident["pin"]) == 64
    assert ident["lan_opt_in_required"] is True
    approvals = CompanionApprovals(tmp_path)
    pending = approvals.pending("phone", ident["pin"])
    assert pending["approved"] is False
    assert approvals.approve(pending["id"])["approved"] is True


def test_b66_org_audit_export(tmp_path):
    audit = OrgAuditExport(tmp_path)
    audit.set_config("acme", retention_days=30, format="csv")
    config = audit.config("acme")
    assert config["retention_days"] == 30
    audit.log.write_text(json.dumps({"ts": "2026-01-01T00:00:00Z",
                                     "capability": "x", "ok": True}) + "\n")
    result = audit.export("acme")
    assert result["format"] == "csv" and "capability" in result["body"]


def test_c118_canary(tmp_path):
    first = build_canary(tmp_path)
    second = build_canary(tmp_path)
    assert first["id"] == second["id"]
    assert first["measures"]["nuitka_core"].startswith("not applied")
    assert "not a security boundary" in first["note"]


def test_c111_local_task_executor(tmp_path):
    executor = LocalTaskExecutor(tmp_path)
    task = executor.submit("list", [sys.executable, "-c", "print('ok')"])
    assert task["status"] == "pending"
    try:
        executor.run(task["id"])
    except PermissionError:
        pass
    else:
        raise AssertionError("unapproved task executed")
    executor.approve(task["id"], "owner")
    result = executor.run(task["id"])
    assert result["exit_code"] == 0 and "ok" in result["stdout"]
    try:
        executor.submit("bad", ["dangerous-program"])
    except ValueError:
        pass
    else:
        raise AssertionError("non-allowlisted program accepted")


def test_a38_site_toolkit(tmp_path):
    toolkit = SiteToolkit(tmp_path)
    assert toolkit.secrets_manager(tmp_path)["available"] is True
    assert toolkit.db_browser(tmp_path / "missing.db")["ok"] is False
    job = toolkit.add_job("daily", 3600, "keel capability list")
    assert job["interval_s"] == 3600 and toolkit.scheduled_jobs()
    assert toolkit.analytics([{"kind": "view"}])["by_kind"]["view"] == 1
    assert toolkit.element_editor("p", "<script>x</script>").startswith("<p")
    assert "<script>" not in toolkit.element_editor("p", "<script>x</script>")


def test_capabilities_registered():
    from keel import capability_registry  # noqa: F401
    from keel.capabilities import list_capabilities

    ids = {c["id"] for c in list_capabilities()}
    for cap in ("core.packages.manifests", "core.airgap.bundle",
                "core.status.check", "core.ocr.status", "core.canary.info",
                "core.site.tools", "core.companion.identity"):
        assert cap in ids, cap
