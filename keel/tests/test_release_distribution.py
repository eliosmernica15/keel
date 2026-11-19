"""Tests for the release-distribution scripts.

These cover the manifest generator, the public-download verifier and the
published-manifest validator. The verifier test performs a real HTTP download
from a loopback server, so size and SHA-256 comparison are exercised end to
end rather than mocked.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"keel_release_{name}", SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


make_download = _load("make_download_manifest")
check_download = _load("check_download_manifest")
verify_public = _load("verify_public_release")
make_release = _load("make_release_manifest")

VERSION = "0.1.0"
TAG = "v0.1.0"
BASE = "https://download.keel.test"

ARTIFACTS = {
    "Keel-Setup-0.1.0.exe": b"windows-installer-bytes",
    "Keel-0.1.0-macos-arm64.dmg": b"macos-dmg-bytes",
    "Keel-0.1.0-macos-arm64.zip": b"macos-zip-bytes",
    "Keel-0.1.0-linux-x86_64.AppImage": b"linux-appimage-bytes",
    "Keel-0.1.0-linux-amd64.deb": b"linux-deb-bytes",
}


@pytest.fixture()
def artifacts(tmp_path: Path) -> Path:
    root = tmp_path / "release"
    root.mkdir()
    for name, payload in ARTIFACTS.items():
        (root / name).write_bytes(payload)
    return root


def test_download_manifest_marks_all_channels_available(artifacts: Path) -> None:
    doc = make_download.build_manifest(
        artifacts=artifacts,
        version=VERSION,
        tag=TAG,
        base_url=BASE + "/",
        verified_at="2026-11-19T12:00:00Z",
    )

    assert doc["version"] == VERSION
    assert doc["tag"] == TAG
    assert doc["base_url"] == BASE
    assert doc["verified_at"] == "2026-11-19T12:00:00Z"
    assert set(doc["channels"]) == {"windows", "macos", "linux"}

    for key, channel in doc["channels"].items():
        assert channel["available"] is True
        assert channel["verified"] is True
        assert channel["arch"]
        assert channel["url"] == f"{BASE}/{TAG}/{channel['file']}"
        payload = ARTIFACTS[channel["file"]]
        assert channel["size"] == len(payload)
        assert channel["sha256"] == hashlib.sha256(payload).hexdigest()

    mac_alts = {alt["file"]: alt for alt in doc["channels"]["macos"]["alternatives"]}
    assert set(mac_alts) == {"Keel-0.1.0-macos-arm64.zip"}
    assert mac_alts["Keel-0.1.0-macos-arm64.zip"]["url"].startswith(BASE + "/")
    assert mac_alts["Keel-0.1.0-macos-arm64.zip"]["label"] == "ZIP archive"

    linux_alts = {alt["file"]: alt for alt in doc["channels"]["linux"]["alternatives"]}
    assert set(linux_alts) == {"Keel-0.1.0-linux-amd64.deb"}
    assert linux_alts["Keel-0.1.0-linux-amd64.deb"]["label"].startswith("Debian/Ubuntu")


def test_download_manifest_accepts_x86_64_deb_spelling(tmp_path: Path) -> None:
    root = tmp_path / "release"
    root.mkdir()
    for name, payload in ARTIFACTS.items():
        if name.endswith("-linux-amd64.deb"):
            continue
        (root / name).write_bytes(payload)
    (root / "Keel-0.1.0-linux-x86_64.deb").write_bytes(b"alt-deb")

    doc = make_download.build_manifest(
        artifacts=root, version=VERSION, tag=TAG, base_url=BASE
    )
    alt = doc["channels"]["linux"]["alternatives"][0]
    assert alt["file"] == "Keel-0.1.0-linux-x86_64.deb"
    assert alt["sha256"] == hashlib.sha256(b"alt-deb").hexdigest()


def test_download_manifest_rejects_incomplete_release(artifacts: Path) -> None:
    (artifacts / "Keel-0.1.0-macos-arm64.dmg").unlink()
    with pytest.raises(SystemExit) as exc:
        make_download.build_manifest(
            artifacts=artifacts, version=VERSION, tag=TAG, base_url=BASE
        )
    assert "Keel-0.1.0-macos-arm64.dmg" in str(exc.value)


@pytest.mark.parametrize("base_url", ["http://download.keel.test", "download.keel.test", "https://"])
def test_download_manifest_requires_absolute_https(artifacts: Path, base_url: str) -> None:
    with pytest.raises(SystemExit):
        make_download.build_manifest(
            artifacts=artifacts, version=VERSION, tag=TAG, base_url=base_url
        )


def test_download_manifest_requires_matching_tag(artifacts: Path) -> None:
    with pytest.raises(SystemExit):
        make_download.build_manifest(
            artifacts=artifacts, version=VERSION, tag="v9.9.9", base_url=BASE
        )


def test_check_download_manifest_accepts_generated_manifest(artifacts: Path) -> None:
    doc = make_download.build_manifest(
        artifacts=artifacts, version=VERSION, tag=TAG, base_url=BASE
    )
    assert check_download.validate(doc, allow_http=False) == []


def test_check_download_manifest_rejects_unavailable_and_insecure(artifacts: Path) -> None:
    doc = make_download.build_manifest(
        artifacts=artifacts, version=VERSION, tag=TAG, base_url=BASE
    )
    doc["channels"]["windows"]["available"] = False
    doc["channels"]["macos"]["url"] = doc["channels"]["macos"]["url"].replace(
        "https://", "http://"
    )
    doc["channels"]["linux"]["sha256"] = "not-a-hash"
    doc["channels"]["linux"]["verified"] = False
    doc["tag"] = "v9.9.9"

    errors = check_download.validate(doc, allow_http=False)
    assert any("windows: not available" in e for e in errors)
    assert any("macos: url is not a public HTTPS URL" in e for e in errors)
    assert any("linux: invalid sha256" in e for e in errors)
    assert any("linux: not marked verified" in e for e in errors)
    assert any("does not match version" in e for e in errors)


def test_check_download_manifest_rejects_committed_fallback() -> None:
    fallback = json.loads((ROOT / "site" / "download.json").read_text(encoding="utf-8"))
    errors = check_download.validate(fallback, allow_http=False)
    assert any("windows: not available" in e for e in errors)
    assert any("macos: not available" in e for e in errors)
    assert any("linux: not available" in e for e in errors)


def _serve(directory: Path):
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def stop() -> None:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    return server, stop


def _entry(url: str, payload: bytes, sha256: str | None = None) -> dict:
    return {
        "label": "installer.bin",
        "url": url,
        "size": len(payload),
        "sha256": sha256 or hashlib.sha256(payload).hexdigest(),
    }


def test_verify_public_release_downloads_and_hashes(tmp_path: Path) -> None:
    payload = b"installer-payload" * 4096
    served = tmp_path / "served"
    served.mkdir()
    (served / "installer.bin").write_bytes(payload)
    server, stop = _serve(served)
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/installer.bin"
        assert verify_public.verify(
            [_entry(url, payload)],
            head_only=False,
            timeout=5,
            retries=0,
            retry_delay=0,
            allow_http=True,
        ) == 0
        # HEAD is enough when the server reports an exact Content-Length.
        assert verify_public.verify(
            [_entry(url, payload)],
            head_only=True,
            timeout=5,
            retries=0,
            retry_delay=0,
            allow_http=True,
        ) == 0
        # A checksum mismatch must fail the release.
        assert verify_public.verify(
            [_entry(url, payload, sha256="0" * 64)],
            head_only=False,
            timeout=5,
            retries=0,
            retry_delay=0,
            allow_http=True,
        ) == 1
    finally:
        stop()


def test_verify_public_release_rejects_http_by_default() -> None:
    problem = verify_public.validate_entry(
        {"label": "x", "url": "http://example.test/x", "size": 1, "sha256": "a" * 64},
        allow_http=False,
    )
    assert problem and "HTTPS" in problem


def test_verify_public_release_reads_both_manifest_shapes(artifacts: Path) -> None:
    doc = make_download.build_manifest(
        artifacts=artifacts, version=VERSION, tag=TAG, base_url=BASE
    )
    entries = verify_public.entries_from(doc)
    labels = {entry["label"] for entry in entries}
    assert labels == set(ARTIFACTS)
    assert all(entry["size"] > 0 for entry in entries)

    release_doc = {
        "files": [
            {
                "file": "Keel-Setup-0.1.0.exe",
                "url": f"{BASE}/{TAG}/Keel-Setup-0.1.0.exe",
                "bytes": 10,
                "sha256": "a" * 64,
            }
        ]
    }
    assert verify_public.entries_from(release_doc)[0]["label"] == "Keel-Setup-0.1.0.exe"


def test_make_release_manifest_pending_urls_and_checksums_file(
    artifacts: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checksums = artifacts / "SHA256SUMS-windows.txt"
    checksums.write_text("abc  Keel-Setup-0.1.0.exe\n", encoding="utf-8")
    out = tmp_path / "RELEASE-MANIFEST.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "make_release_manifest.py",
            "--artifacts",
            str(artifacts),
            "--version",
            VERSION,
            "--tag",
            TAG,
            "--out",
            str(out),
        ],
    )
    assert make_release.main() == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert len(doc["files"]) == 5
    assert all(entry["url"] == "pending" for entry in doc["files"])
    assert doc["checksums_file"] == "SHA256SUMS-windows.txt"


def test_make_release_manifest_prefers_combined_checksums_file(
    artifacts: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("SHA256SUMS-windows.txt", "SHA256SUMS-linux.txt"):
        (artifacts / name).write_text("abc  file\n", encoding="utf-8")
    combined = artifacts / "RELEASE-SHA256SUMS.txt"
    combined.write_text("abc  file\n", encoding="utf-8")

    out = tmp_path / "RELEASE-MANIFEST.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "make_release_manifest.py",
            "--artifacts",
            str(artifacts),
            "--version",
            VERSION,
            "--tag",
            TAG,
            "--out",
            str(out),
        ],
    )
    assert make_release.main() == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert len(doc["files"]) == 5
    assert doc["checksums_file"] == "RELEASE-SHA256SUMS.txt"


def test_make_release_manifest_rejects_tag_mismatch(
    artifacts: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "make_release_manifest.py",
            "--artifacts",
            str(artifacts),
            "--version",
            VERSION,
            "--tag",
            "v9.9.9",
            "--out",
            str(tmp_path / "m.json"),
        ],
    )
    assert make_release.main() == 1
