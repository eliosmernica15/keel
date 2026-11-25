"""Regression tests for release URL scheme / redirect policy.

Covers the lead-routed Agent B load_manifest scheme gap and Agent F findings
SEC-F-03, SEC-F-06 and SEC-F-07. All tests are offline; no network is used.
"""

from __future__ import annotations

import urllib.request

import pytest

from keel.release import verify
from keel.release.updater import UpdatePlan

BAD_SCHEME_URLS = (
    "file:///etc/passwd",
    "ftp://example.com/Keel-Setup.exe",
    "data:text/plain,hello",
    "//example.com/Keel-Setup.exe",
)


@pytest.mark.parametrize("url", BAD_SCHEME_URLS)
def test_load_manifest_rejects_non_http_schemes(url: str):
    with pytest.raises(ValueError, match="manifest URL must be HTTPS"):
        verify.load_manifest(url, allow_http=False, timeout=1)


def test_load_manifest_rejects_public_plaintext_http():
    with pytest.raises(ValueError, match="manifest URL must be HTTPS"):
        verify.load_manifest("http://example.com/download.json",
                             allow_http=False, timeout=1)


@pytest.mark.parametrize("url", BAD_SCHEME_URLS)
def test_fetch_bytes_rejects_non_https_schemes(url: str):
    with pytest.raises(ValueError, match="refusing non-HTTPS URL"):
        verify.fetch_bytes(url, allow_http=False, timeout=1)


def test_release_manifest_file_entry_rejects_non_https_url():
    doc = {"files": [{"file": "Keel-Setup.exe", "bytes": 1,
                      "sha256": "a" * 64, "url": "file:///etc/passwd"}]}
    errors = verify.verify_release_manifest(doc, allow_http=False, retries=1)
    assert any("url is not HTTPS" in e for e in errors), errors


def test_redirect_handler_rejects_disallowed_hop():
    handler = verify._ValidatingRedirectHandler(allow_http=False)
    req = urllib.request.Request("https://example.com/download.json")
    with pytest.raises(ValueError, match="non-HTTPS redirect target"):
        handler.redirect_request(req, None, 302, "Found", {},
                                 "file:///etc/passwd")
    with pytest.raises(ValueError, match="non-HTTPS redirect target"):
        handler.redirect_request(req, None, 302, "Found", {},
                                 "http://example.com/download.json")


def test_redirect_handler_allows_https_hop_and_enforces_limit():
    handler = verify._ValidatingRedirectHandler(allow_http=False)
    req = urllib.request.Request("https://example.com/download.json")
    redirected = handler.redirect_request(
        req, None, 302, "Found", {}, "https://cdn.example.com/download.json")
    assert redirected.full_url == "https://cdn.example.com/download.json"
    # Two hops are allowed; a third must fail closed.
    handler.redirect_request(
        req, None, 302, "Found", {}, "https://cdn2.example.com/download.json")
    with pytest.raises(ValueError, match="too many redirects"):
        handler.redirect_request(
            req, None, 302, "Found", {}, "https://cdn3.example.com/download.json")


def test_update_plan_records_signature_status():
    plan = UpdatePlan(version="0.1.2", platform="windows", file="x.exe",
                      url="https://example.com/x.exe", size=1, sha256="a" * 64,
                      manifest_version="0.1.2")
    assert plan.signature_verified is False
    signed = UpdatePlan(**{**plan.__dict__, "signature_verified": True})
    assert signed.signature_verified is True


def test_update_check_cli_emits_truthful_signature_flag(monkeypatch, capsys):
    from keel.release import cli

    plan = UpdatePlan(version="0.1.2", platform="windows", file="x.exe",
                      url="https://example.com/x.exe", size=1, sha256="a" * 64,
                      manifest_version="0.1.2", signature_verified=False)
    monkeypatch.setattr("keel.release.updater.check_for_update",
                        lambda *a, **k: plan)
    args = cli.build_parser().parse_args([
        "update-check", "--manifest", "https://example.com/manifest.json",
        "--current", "0.1.1", "--platform", "windows"])
    assert cli.update_check_command(args) == 0
    import json
    payload = json.loads(capsys.readouterr().out)
    assert payload["signatureVerified"] is False
