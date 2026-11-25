from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from .common import expected_filenames
from .reconciliation import (
    CHECKSUMS_NAME,
    MANIFEST_NAME,
    is_stale_asset_name,
    parse_checksums,
)

RELEASE_METADATA_ASSETS = frozenset(
    {MANIFEST_NAME, CHECKSUMS_NAME, "download.json"}
)


class GitHubError(RuntimeError):
    pass


class GitHubClient:
    def __init__(self, repo: str, token: str):
        self.repo = repo
        self.token = token

    def _request(
        self,
        method: str,
        url: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 120,
    ) -> tuple[int, bytes]:
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"token {self.token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if headers:
            for key, value in headers.items():
                req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read()
            raise GitHubError(
                f"{method} {url} -> {exc.code}: {body.decode('utf-8', 'replace')[:500]}"
            ) from exc

    def get_release_by_tag(self, tag: str) -> dict[str, Any] | None:
        url = f"https://api.github.com/repos/{self.repo}/releases/tags/{urllib.parse.quote(tag, safe='')}"
        last: Exception | None = None
        for _ in range(5):
            try:
                status, body = self._request("GET", url)
                return json.loads(body)
            except GitHubError as exc:
                if " 404:" in str(exc):
                    last = exc
                    time.sleep(2)
                    continue
                raise
        return None

    def get_release(self, release_id: int) -> dict[str, Any]:
        url = f"https://api.github.com/repos/{self.repo}/releases/{release_id}"
        last: Exception | None = None
        for _ in range(5):
            try:
                status, body = self._request("GET", url)
                return json.loads(body)
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(2)
        raise last  # type: ignore[misc]

    def create_release(self, tag: str, name: str, body: str, draft: bool) -> dict[str, Any]:
        url = f"https://api.github.com/repos/{self.repo}/releases"
        payload = {
            "tag_name": tag,
            "name": name,
            "body": body,
            "draft": draft,
            "prerelease": False,
        }
        status, raw = self._request(
            "POST",
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        return json.loads(raw)

    def update_release(self, release_id: int, **fields: Any) -> dict[str, Any]:
        url = f"https://api.github.com/repos/{self.repo}/releases/{release_id}"
        status, raw = self._request(
            "PATCH",
            url,
            data=json.dumps(fields).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        return json.loads(raw)

    def delete_release(self, release_id: int) -> None:
        url = f"https://api.github.com/repos/{self.repo}/releases/{release_id}"
        self._request("DELETE", url)

    def delete_asset(self, asset_id: int) -> None:
        url = f"https://api.github.com/repos/{self.repo}/releases/assets/{asset_id}"
        self._request("DELETE", url)

    def upload_asset(
        self,
        release_id: int,
        path: Path,
        name: str | None = None,
        timeout: int = 600,
    ) -> dict[str, Any]:
        asset_name = name or path.name
        url = (
            f"https://uploads.github.com/repos/{self.repo}/releases/{release_id}/assets"
            f"?name={urllib.parse.quote(asset_name)}"
        )
        content_type = _content_type(asset_name)
        size = path.stat().st_size
        with open(path, "rb") as f:
            status, raw = self._request(
                "POST",
                url,
                data=f,
                headers={
                    "Content-Type": content_type,
                    "Content-Length": str(size),
                },
                timeout=timeout,
            )
        return json.loads(raw)


def _content_type(name: str) -> str:
    """Content type for supported release assets only.

    DMG/ZIP/AppImage are deliberately absent: they are not release formats and
    must not be uploaded by the release manager. The audit helpers below can
    still recognise and report them on an already-published release.
    """
    lower = name.lower()
    if lower.endswith(".deb"):
        return "application/vnd.debian.binary-package"
    if lower.endswith(".rpm"):
        return "application/x-rpm"
    if lower.endswith(".json"):
        return "application/json"
    if lower.endswith(".txt"):
        return "text/plain"
    # .exe, .pkg, .sig and any unexpected binary use the safe generic type.
    return "application/octet-stream"


def release_asset_names(release: Mapping[str, Any]) -> list[str]:
    """Names of all assets currently attached to a GitHub release."""
    return sorted(
        str(asset["name"])
        for asset in (release.get("assets") or [])
        if isinstance(asset, dict) and asset.get("name")
    )


def audit_release_assets(release: Mapping[str, Any], version: str) -> dict[str, Any]:
    """Classify published assets against the configured native formats."""
    names = release_asset_names(release)
    name_set = set(names)
    expected = set(expected_filenames(version))
    metadata = name_set & RELEASE_METADATA_ASSETS
    signatures = {name for name in name_set if name.endswith(".sig")}
    stale = sorted(name for name in names if is_stale_asset_name(name))
    return {
        "names": names,
        "expected_present": sorted(expected & name_set),
        "expected_missing": sorted(expected - name_set),
        "stale_assets": stale,
        "metadata_assets": sorted(metadata),
        "signature_assets": sorted(signatures),
        "unexpected_assets": sorted(name_set - expected - metadata - signatures),
    }


def audit_checksums(
    release: Mapping[str, Any], checksums_text: str,
) -> dict[str, Any]:
    """Compare a published checksum file with the release's real assets."""
    parsed = parse_checksums(checksums_text)
    assets = {
        str(asset["name"]): asset
        for asset in (release.get("assets") or [])
        if isinstance(asset, dict) and asset.get("name")
    }
    installers = sorted(
        name for name in assets
        if name not in RELEASE_METADATA_ASSETS and not name.endswith(".sig")
    )
    digest_mismatches: list[str] = []
    for name, digest in sorted(parsed.items()):
        remote = str(assets.get(name, {}).get("digest") or "")
        if remote and remote.lower() != f"sha256:{digest}":
            digest_mismatches.append(name)
    return {
        "entries": sorted(parsed),
        "installer_assets": installers,
        "missing_coverage": sorted(set(installers) - set(parsed)),
        "orphan_entries": sorted(set(parsed) - set(assets)),
        "digest_mismatches": digest_mismatches,
    }


def audit_published_release(
    release: Mapping[str, Any],
    version: str,
    *,
    checksums_text: str | None = None,
) -> dict[str, Any]:
    """Honest, read-only audit of a published release.

    No local or remote mutation is performed. ``status`` is ``stale`` when
    removed archive formats are advertised, ``incomplete`` when native assets
    or checksum coverage are missing, and ``consistent`` only when neither
    problem exists. Signing is reported separately and never inferred from
    publication.
    """
    assets = audit_release_assets(release, version)
    reasons: list[str] = []
    if assets["stale_assets"]:
        reasons.append(
            "stale archive assets published: " + ", ".join(assets["stale_assets"])
        )
    if assets["expected_missing"]:
        reasons.append(
            "configured native assets missing: " + ", ".join(assets["expected_missing"])
        )

    checksums: dict[str, Any] | None = None
    if checksums_text is not None:
        checksums = audit_checksums(release, checksums_text)
        if checksums["missing_coverage"]:
            reasons.append(
                "published checksums omit assets: "
                + ", ".join(checksums["missing_coverage"])
            )
        if checksums["orphan_entries"]:
            reasons.append(
                "checksums reference unpublished assets: "
                + ", ".join(checksums["orphan_entries"])
            )
        if checksums["digest_mismatches"]:
            reasons.append(
                "checksum digests disagree with GitHub asset digests: "
                + ", ".join(checksums["digest_mismatches"])
            )

    signing = (
        "distribution-verified" if assets["signature_assets"]
        else "unsigned"
    )
    if not assets["signature_assets"]:
        reasons.append("no signature assets published")

    if assets["stale_assets"]:
        status = "stale"
    elif assets["expected_missing"] or (checksums and (
            checksums["missing_coverage"] or checksums["orphan_entries"]
            or checksums["digest_mismatches"])):
        status = "incomplete"
    else:
        status = "consistent"
    return {
        "tag": release.get("tag_name"),
        "status": status,
        "reasons": reasons,
        "assets": assets,
        "checksums": checksums,
        "signing": signing,
    }


def token_from_env() -> str:
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(name)
        if value:
            return value
    raise GitHubError("GITHUB_TOKEN or GH_TOKEN is required")
