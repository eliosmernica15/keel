"""Locally achievable release requirements: C1.2, C12.2, B5.9.

All functions operate on the committed release manifest and local files. They
never publish, deploy, or contact a remote service unless the caller explicitly
supplies a URL to check.
"""

from __future__ import annotations

import html
import json
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path

MANIFEST = "RELEASE-MANIFEST.json"


def _manifest(release_dir: str | Path) -> dict:
    path = Path(release_dir) / MANIFEST
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------- C1.2
def package_manager_manifests(release_dir: str | Path,
                              out_dir: str | Path) -> dict:
    """Generate Scoop/Chocolatey/Flatpak/Snap/AUR/Nix manifests locally.

    Store acceptance of proprietary freeware is recorded as an explicit check
    item rather than assumed; no store submission is performed.
    """
    doc = _manifest(release_dir)
    version = str(doc["version"])
    entry = next((f for f in doc.get("files", [])
                  if str(f.get("platform")) == "windows"), None)
    installer = Path(entry["file"]).name if entry else f"Keel-Setup-{version}.exe"
    url = str(entry.get("url", "")) if entry else ""
    sha = str(entry.get("sha256", "")).lower() if entry else ""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    files = {}
    scoop = {
        "version": version,
        "architecture": "64bit",
        "homepage": "https://keel-desktop.vercel.app",
        "description": "Keel local-first AI workspace",
        "license": "Proprietary freeware",
        "url": url or f"https://example.invalid/{installer}",
        "hash": sha,
        "extractor": "nsis",
        "installer": {"file": installer},
    }
    files["scoop.json"] = scoop

    chocolatey = f"""<?xml version="1.0" encoding="utf-8"?>
<package><metadata>
  <id>keel</id><version>{version}</version><title>Keel</title>
  <authors>Keel Team</authors><licenseUrl>https://keel-desktop.vercel.app/eula</licenseUrl>
  <projectUrl>https://keel-desktop.vercel.app</projectUrl>
  <requireLicenseAcceptance>true</requireLicenseAcceptance>
  <description>Local-first AI workspace (proprietary freeware).</description>
</metadata><files><file src="tools/chocolateyinstall.ps1" /></files></package>
"""
    files["chocolatey.nuspec"] = chocolatey

    flatpak = f"""[Desktop Entry]
Name=Keel
Exec=keel
Type=Application
Categories=Development;
# Binary-only Flatpak; verify store accepts proprietary freeware before submission.
X-Keel-Version={version}
"""
    files["keel.desktop"] = flatpak

    snap = f"""name: keel
version: '{version}'
summary: Keel local-first AI workspace
description: |
  Local-first AI workspace. Proprietary freeware; confirm store terms before publishing.
grade: stable
confinement: classic
base: core22
apps:
  keel:
    command: bin/keel
"""
    files["snapcraft.yaml"] = snap

    pkgbuild = f"""# Maintainer: Keel Team
pkgname=keel-bin
pkgver={version}
pkgrel=1
pkgdesc="Keel local-first AI workspace (proprietary freeware)"
arch=('x86_64')
url="https://keel-desktop.vercel.app"
license=('custom:Keel EULA')
source=("{installer}")
sha256sums=('{sha or "SKIP"}')
package() {{
  install -Dm755 "$srcdir/{installer}" "$pkgdir/usr/bin/keel"
}}
"""
    files["PKGBUILD"] = pkgbuild

    nix = f"""{{ lib, stdenv, fetchurl }}:
stdenv.mkDerivation rec {{
  pname = "keel";
  version = "{version}";
  src = fetchurl {{
    url = "{url or "https://example.invalid/" + installer}";
    sha256 = lib.replaceStrings ["-"] ["_"] "{sha or "0" * 64}";
  }};
  installPhase = ''
    install -Dm755 $src $out/bin/keel
  '';
  meta = with lib; {{ description = "Keel local-first AI workspace"; license = licenses.unfree; }};
}}
"""
    files["flake.nix"] = nix

    written = {}
    for name, content in files.items():
        target = out / name
        target.write_text(content if isinstance(content, str)
                          else json.dumps(content, indent=2) + "\n",
                          encoding="utf-8")
        written[name] = str(target)
    return {
        "version": version,
        "generated": written,
        "store_acceptance": {
            "scoop": "verify proprietary freeware policy",
            "chocolatey": "verify proprietary freeware policy",
            "flatpak": "verify proprietary freeware policy",
            "snap": "verify proprietary freeware policy",
            "aur": "verify proprietary freeware policy",
            "nix": "unfree license declaration included",
        },
        "published": False,
    }


# --------------------------------------------------------------- C12.2
def airgap_bundle(release_dir: str | Path, out_dir: str | Path,
                  model_folders: list[str] | None = None) -> dict:
    """Build a reproducible offline install/update bundle (air-gapped)."""
    release = Path(release_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    doc = _manifest(release)
    copied = []
    sums = release / "RELEASE-SHA256SUMS.txt"
    checksummed = []
    if sums.is_file():
        for line in sums.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 2:
                checksummed.append(parts[1])
    for name in dict.fromkeys((MANIFEST, "RELEASE-SHA256SUMS.txt",
                               *checksummed,
                               *(f["file"] for f in doc.get("files", [])))):
        src = release / name
        if src.is_file():
            shutil.copy2(src, out / name)
            copied.append(name)
    models = []
    for folder in model_folders or []:
        path = Path(folder)
        if path.is_dir():
            models.append({"path": str(path),
                           "files": len(list(path.rglob("*")))})
    bundle_doc = {
        "format": "Keel-Airgap-1.0",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "version": str(doc["version"]),
        "files": copied,
        "models": models,
        "verification": "verify RELEASE-SHA256SUMS before sideloading",
    }
    (out / "AIRGAP-MANIFEST.json").write_text(
        json.dumps(bundle_doc, indent=2) + "\n", encoding="utf-8")
    return bundle_doc


def verify_sideload(bundle_dir: str | Path) -> dict:
    """Verify a sideload bundle against its checksum file (offline, real hashes)."""
    import hashlib

    root = Path(bundle_dir)
    sums = root / "RELEASE-SHA256SUMS.txt"
    if not sums.is_file():
        return {"ok": False, "reason": "missing RELEASE-SHA256SUMS.txt"}
    errors = []
    checked = 0
    for line in sums.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        expected, name = parts[0].lower(), parts[1]
        path = root / name
        if not path.is_file():
            errors.append(f"missing {name}")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            errors.append(f"hash mismatch {name}")
        checked += 1
    return {"ok": not errors, "checked": checked, "errors": errors}


# --------------------------------------------------------------- B5.9
DEFAULT_STATUS_CONFIG = {
    "update_feed_url": "",
    "mirrors": [],
    "timeout_s": 8,
    "check_interval_s": 300,
}


class StatusConfig:
    def __init__(self, state_root: str | Path):
        self.path = Path(state_root) / "status-page.json"

    def load(self) -> dict:
        doc = dict(DEFAULT_STATUS_CONFIG)
        if self.path.is_file():
            try:
                doc.update(json.loads(self.path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass
        return doc

    def save(self, config: dict) -> dict:
        current = self.load()
        current.update({k: config[k] for k in DEFAULT_STATUS_CONFIG if k in config})
        for key in ("update_feed_url", *[f"mirror_{i}" for i in range(
                len(current.get("mirrors", [])))]):
            if key in config and not isinstance(config[key], str):
                raise ValueError(f"{key} must be a string")
        if not isinstance(current.get("mirrors"), list):
            raise ValueError("mirrors must be a list")
        for url in [current.get("update_feed_url", ""), *current["mirrors"]]:
            if url and not str(url).startswith(("http://", "https://")):
                raise ValueError("status URLs must be http or https")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(current, indent=2) + "\n",
                             encoding="utf-8")
        return current


def check_status(config: dict) -> dict:
    """Perform real HTTP checks; unknown/unconfigured means 'not configured'."""
    def probe(url: str) -> dict:
        if not url:
            return {"url": "", "status": "not_configured"}
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(
                    req, timeout=float(config.get("timeout_s", 8))) as resp:
                return {"url": url, "status": "operational",
                        "http_status": resp.status}
        except urllib.error.HTTPError as exc:
            return {"url": url, "status": "degraded", "http_status": exc.code}
        except (OSError, ValueError) as exc:
            return {"url": url, "status": "unreachable",
                    "error": type(exc).__name__}

    result = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "update_feed": probe(config.get("update_feed_url", "")),
        "mirrors": [probe(u) for u in config.get("mirrors", [])],
        "note": "Live checks only — no fabricated operational status.",
    }
    return result


def render_status_html(result: dict) -> str:
    def row(label: str, item: dict) -> str:
        status = html.escape(str(item.get("status", "unknown")))
        url = html.escape(str(item.get("url") or "not configured"))
        return f"<li><b>{html.escape(label)}</b>: {status} — <code>{url}</code></li>"
    items = [row("Update feed", result["update_feed"])]
    items += [row(f"Mirror {i+1}", m)
              for i, m in enumerate(result.get("mirrors", []))]
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            "<title>Keel status</title></head><body><h1>Keel status</h1>"
            f"<p>Generated {html.escape(str(result['generated_at']))}</p>"
            "<ul>" + "".join(items) + "</ul>"
            "<p>Live checks only — no simulated status.</p></body></html>")
