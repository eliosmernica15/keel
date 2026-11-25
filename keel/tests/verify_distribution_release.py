"""Agent B / production distribution round — release-manager Python API checks.

Verifies the manifest fields required by ``docs/DISTRIBUTION-BASELINE.md``,
the availability rule (never fabricate a URL/size/hash/verification), the
manifest validation helpers that do exist (``verify.verify_manifest`` /
``verify.verify_release_manifest``), network failure/timeout handling that the
site's GET-only download-manifest proxy depends on, signing, and the desktop
``release update-check`` API contract.

All I/O is local (tmp_path) or loopback; no GitHub/network service is used.
"""

from __future__ import annotations

import functools
import hashlib
import json
import socket
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from keel.release import common, signing, updater, verify

VERSION = "0.1.1"
TAG = "v0.1.1"
BASE = "https://github.com/owner/keel/releases/download"

# Derive the artifact set from the release manager itself so these checks stay
# valid while the release channels are being finished by another owner. The
# baseline contract is asserted explicitly below (PKG/DEB-or-RPM primaries).
NAMES = common.expected_filenames(VERSION)
ARTIFACTS = {name: f"bytes-for-{name}".encode("utf-8") for name in NAMES}
WINDOWS_PRIMARY = next(
    c["primary"].format(version=VERSION) for c in common.CHANNELS
    if c["key"] == "windows")


@pytest.fixture
def artifacts(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "artifacts"
    root.mkdir()
    for name, payload in ARTIFACTS.items():
        (root / name).write_bytes(payload)
    return {name: root / name for name in ARTIFACTS}


def _verified_manifest(artifacts: dict[str, Path], base: str = BASE) -> dict:
    return common.build_download_manifest(
        artifacts, VERSION, TAG, base,
        available=True, verified=True,
        verified_at="2026-01-01T00:00:00Z",
        published_at="2026-01-01T00:00:00Z",
    )


def _available_channel(url: str) -> dict:
    """A single-channel manifest pointing at *url* (no real download needed)."""
    return {"channels": {"windows": {
        "name": "Windows x64", "arch": "x64", "version": VERSION,
        "file": "Keel-Setup-0.1.1.exe", "size": 4, "sha256": "0" * 64,
        "url": url, "available": True, "verified": True,
        "verified_at": "2026-01-01T00:00:00Z", "notes": "", "installation": "",
        "alternatives": [],
    }}}


def _closed_loopback_url() -> str:
    """Return an http://127.0.0.1 URL on a port that is not listening."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return f"http://127.0.0.1:{port}/missing"


# --------------------------------------------------------- manifest schema fields

def test_download_manifest_has_all_baseline_fields(artifacts):
    doc = _verified_manifest(artifacts)
    for field in ("name", "version", "tag", "generated", "published_at",
                  "verified_at", "base_url", "release_manifest_url", "channels"):
        assert field in doc, f"missing top-level manifest field {field}"
    assert doc["name"] == "Keel Desktop"
    assert doc["version"] == VERSION and doc["tag"] == TAG
    assert doc["generated"] == "release-pipeline"
    assert doc["base_url"] == BASE
    assert doc["release_manifest_url"] == f"{BASE}/{TAG}/RELEASE-MANIFEST.json"

    assert set(doc["channels"]) == {"windows", "macos", "linux"}
    assert doc["channels"]["windows"]["arch"] == "x64"
    assert doc["channels"]["macos"]["arch"] == "arm64"
    assert doc["channels"]["linux"]["arch"] == "x86_64"
    # DISTRIBUTION-BASELINE: native PKG on macOS, DEB/RPM on Linux.
    assert doc["channels"]["macos"]["file"].endswith(".pkg")
    assert doc["channels"]["linux"]["file"].endswith((".deb", ".rpm"))
    for key, ch in doc["channels"].items():
        for field in ("name", "arch", "version", "file", "size", "sha256",
                      "url", "available", "verified", "verified_at", "notes",
                      "installation", "alternatives"):
            assert field in ch, f"{key}: missing field {field}"
        assert ch["available"] is True and ch["verified"] is True
        assert ch["url"].startswith("https://")
        assert f"/{TAG}/" in ch["url"]
        assert ch["size"] == len(ARTIFACTS[ch["file"]])
        assert ch["sha256"] == hashlib.sha256(ARTIFACTS[ch["file"]]).hexdigest().upper()
        assert isinstance(ch["alternatives"], list)
        for alt in ch["alternatives"]:
            assert {"file", "arch", "size", "sha256", "url", "available",
                    "verified", "label"} <= set(alt)

    assert doc["channels"]["windows"]["file"] == WINDOWS_PRIMARY


def test_fallback_manifest_never_fabricates_availability(artifacts):
    doc = common.build_download_manifest(
        artifacts, VERSION, TAG, BASE,
        available=False, verified=False, verified_at=None,
    )
    assert doc["generated"] == "fallback"
    assert doc["verified_at"] is None
    for key, ch in doc["channels"].items():
        assert ch["available"] is False
        assert ch["verified"] is False
        assert ch["url"] is None, key
        assert ch["verified_at"] is None, key
        # Local hashes may still be reported; no public asset is claimed.
        assert ch["size"] == len(ARTIFACTS[ch["file"]])
        for alt in ch["alternatives"]:
            assert alt["url"] is None and alt["verified"] is False


def test_fallback_generator_matches_site_fallback_contract():
    """common.build_fallback_download_manifest() feeds site/download.json."""
    doc = common.build_fallback_download_manifest(VERSION, TAG)
    for field in ("name", "version", "tag", "generated", "published_at",
                  "verified_at", "base_url", "release_manifest_url", "channels"):
        assert field in doc
    assert doc["generated"] == "fallback"
    assert doc["base_url"] is None and doc["release_manifest_url"] is None
    assert set(doc["channels"]) == {"windows", "macos", "linux"}
    for key, ch in doc["channels"].items():
        assert ch["available"] is False and ch["verified"] is False
        assert ch["url"] is None and ch["size"] is None and ch["sha256"] is None
        assert ch["verified_at"] is None
        for alt in ch["alternatives"]:
            assert alt["url"] is None and alt["size"] is None
            assert alt["sha256"] is None and alt["available"] is False


def test_release_manifest_has_all_baseline_fields(artifacts):
    doc = common.build_release_manifest(artifacts, VERSION, TAG, BASE)
    for field in ("name", "version", "tag", "edition", "generated",
                  "published_at", "min_version", "blocked_versions",
                  "security_advisories", "rollout", "files", "checksums_file"):
        assert field in doc, f"missing release-manifest field {field}"
    assert doc["checksums_file"] == "RELEASE-SHA256SUMS.txt"
    assert len(doc["files"]) == len(ARTIFACTS)
    for entry in doc["files"]:
        assert {"platform", "arch", "version", "file", "bytes", "sha256",
                "url"} <= set(entry)
        assert entry["platform"] in {"windows", "macos", "linux"}
        assert entry["url"].startswith("https://github.com/")
        assert entry["bytes"] == len(ARTIFACTS[entry["file"]])
        assert entry["sha256"] == hashlib.sha256(
            ARTIFACTS[entry["file"]]).hexdigest().upper()


# ------------------------------------------------- manifest validation helpers

def test_verify_manifest_rejects_invalid_channel_schema():
    assert verify.verify_manifest({"channels": []}) == [
        "manifest has no channels object"]

    doc = {"channels": {"windows": {
        "available": True, "verified": False, "size": -1,
        "sha256": "bad", "url": "http://example.com/x",
    }}}
    errors = verify.verify_manifest(doc, allow_http=False, retries=1)
    assert any("not marked verified" in e for e in errors)
    assert any("invalid size" in e for e in errors)
    assert any("invalid sha256" in e for e in errors)
    assert any("not a public HTTPS URL" in e for e in errors)


def test_verify_manifest_fallback_and_require_available(artifacts):
    fallback = common.build_download_manifest(
        artifacts, VERSION, TAG, BASE,
        available=False, verified=False, verified_at=None,
    )
    # No available channel => verification is a pure schema check (no network).
    assert verify.verify_manifest(fallback, retries=1, timeout=5) == []
    errors = verify.verify_manifest(
        fallback, retries=1, timeout=5, require_available=True)
    assert len(errors) == 3 and all("not available" in e for e in errors)


def test_verify_release_manifest_rejects_invalid_entries():
    doc = {"files": [
        {"file": "x.exe", "bytes": -1, "sha256": "bad",
         "url": "http://example.com/x"},
        {"file": "y.exe", "bytes": 10, "sha256": "0" * 64,
         "url": "http://example.com/y"},
    ]}
    errors = verify.verify_release_manifest(doc, allow_http=False, retries=1)
    assert any("invalid size" in e for e in errors)
    assert any("invalid sha256" in e for e in errors)
    assert sum("url is not HTTPS" in e for e in errors) == 2
    assert verify.verify_release_manifest({"files": []}) == [
        "release manifest has no files list"]
    assert verify.verify_release_manifest({}) == [
        "release manifest has no files list"]


# --------------------------------------- network failure / timeout (proxy assumptions)

def test_https_enforced_for_fetch_and_load(monkeypatch):
    with pytest.raises(ValueError, match="refusing non-HTTPS URL"):
        verify.fetch_bytes("http://example.com/file", allow_http=False, timeout=5)
    with pytest.raises(ValueError, match="manifest URL must be HTTPS"):
        verify.load_manifest("http://example.com/manifest.json",
                             allow_http=False, timeout=5)


def test_timeout_propagates_from_urlopen(monkeypatch):
    def timed_out(*args, **kwargs):
        raise TimeoutError("timed out")

    # Redirect-validating opener replaced the bare urllib.request.urlopen call.
    monkeypatch.setattr(verify, "_open_url", timed_out)
    with pytest.raises(TimeoutError, match="timed out"):
        verify.fetch_bytes("https://example.com/file", allow_http=False, timeout=1)
    with pytest.raises(TimeoutError, match="timed out"):
        verify.load_manifest("https://example.com/manifest.json",
                             allow_http=False, timeout=1)


def test_verify_manifest_reports_download_failure_without_sleep(monkeypatch):
    def timed_out(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(verify, "fetch_bytes", timed_out)
    errors = verify.verify_manifest(
        _available_channel("https://example.com/missing"),
        retries=1, timeout=1)  # retries=1 => no retry_delay sleep
    assert any("download failed" in e and "timed out" in e for e in errors)


def test_verify_manifest_reports_connection_refused_on_loopback():
    errors = verify.verify_manifest(
        _available_channel(_closed_loopback_url()),
        allow_http=True, retries=1, timeout=5)
    assert any("download failed" in e for e in errors)


def test_loopback_fetch_bytes_and_release_manifest_verify(artifacts, tmp_path):
    """Real download + size/hash checks against a loopback HTTP server."""
    serve_root = tmp_path / "serve"
    tag_dir = serve_root / TAG
    tag_dir.mkdir(parents=True)
    for name, path in artifacts.items():
        (tag_dir / name).write_bytes(path.read_bytes())

    handler = functools.partial(
        SimpleHTTPRequestHandler, directory=str(serve_root))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}"
        data, size = verify.fetch_bytes(
            f"{base}/{TAG}/{WINDOWS_PRIMARY}",
            allow_http=True, timeout=10)
        assert size == len(ARTIFACTS[WINDOWS_PRIMARY])
        assert data == ARTIFACTS[WINDOWS_PRIMARY]

        release = common.build_release_manifest(artifacts, VERSION, TAG, base)
        assert verify.verify_release_manifest(
            release, allow_http=True, retries=1, timeout=10) == []
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


# ------------------------------------------------ signing + update-check APIs

def test_signing_roundtrip_and_gate(artifacts, tmp_path, monkeypatch):
    priv = tmp_path / "ed25519.pem"
    pub = tmp_path / "ed25519.pub.pem"
    signing.generate_keypair(priv, pub)
    key = signing.load_private_key(priv)
    public_key = signing.load_public_key(pub)

    manifest = common.build_release_manifest(artifacts, VERSION, TAG, BASE)
    signed = signing.sign_manifest(manifest, key)
    assert signed["signature_algorithm"] == "ed25519"
    assert signing.verify_manifest(signed, public_key) is True
    tampered = dict(signed, version="9.9.9")
    assert signing.verify_manifest(tampered, public_key) is False

    monkeypatch.delenv(signing.REQUIRE_SIGNED_ENV, raising=False)
    assert signing.require_signed_enabled(False) is False
    assert signing.require_signed_enabled(True) is True
    monkeypatch.setenv(signing.REQUIRE_SIGNED_ENV, "1")
    assert signing.require_signed_enabled(False) is True

    root = tmp_path / "staged"
    root.mkdir()
    (root / signing.MANIFEST_FILENAME).write_text(
        json.dumps(signed, indent=2), encoding="utf-8")
    for name, path in artifacts.items():
        (root / name).write_bytes(path.read_bytes())
        (root / f"{name}.sig").write_bytes(signing.sign_bytes(path.read_bytes(), key))
    assert signing.verify_signed_release(root, pub) == []

    (root / f"{WINDOWS_PRIMARY}.sig").unlink()
    errors = signing.verify_signed_release(root, pub)
    assert any("signature file" in e and "is missing" in e for e in errors)


def test_update_check_contract_from_local_manifest(artifacts, tmp_path):
    """Desktop ``release update-check`` uses check_for_update(); verify its plan."""
    release = common.build_release_manifest(artifacts, VERSION, TAG, BASE)
    path = tmp_path / "RELEASE-MANIFEST.json"
    path.write_text(json.dumps(release), encoding="utf-8")

    plan = updater.check_for_update(
        str(path), current_version="0.1.0", platform="windows")
    assert plan is not None
    assert plan.version == VERSION and plan.platform == "windows"
    assert plan.file == WINDOWS_PRIMARY
    assert plan.size == len(ARTIFACTS[WINDOWS_PRIMARY])
    assert plan.sha256 == hashlib.sha256(
        ARTIFACTS[WINDOWS_PRIMARY]).hexdigest().upper()

    # Not an upgrade when already current.
    assert updater.check_for_update(
        str(path), current_version=VERSION, platform="windows") is None
    # Unknown platform yields no plan.
    assert updater.check_for_update(
        str(path), current_version="0.1.0", platform="solaris") is None
