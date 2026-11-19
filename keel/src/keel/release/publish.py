from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import (
    PROJECT_ROOT,
    build_download_manifest,
    build_release_manifest,
    detect_repo,
    expected_filenames,
    find_artifacts,
    sha256_file,
    validate_artifacts,
    validate_version,
    write_combined_checksums,
)
from .github import GitHubClient, GitHubError, token_from_env
from .verify import verify_manifest, verify_release_manifest, load_manifest


def _flatten_artifacts(artifacts_root: Path, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    found = find_artifacts(artifacts_root)
    # Copy everything flat into out_dir.
    for name, src in found.items():
        shutil.copy2(src, out_dir / name)
    # Copy any checksum/manifest files that exist.
    for path in artifacts_root.rglob("*.txt"):
        if path.name.startswith("SHA256SUMS") or path.name == "RELEASE-SHA256SUMS.txt":
            shutil.copy2(path, out_dir / path.name)
    for path in artifacts_root.rglob("RELEASE-MANIFEST.json"):
        shutil.copy2(path, out_dir / "RELEASE-MANIFEST.json")
    return validate_artifacts(out_dir, validate_version())


def _release_body(version: str, tag: str) -> str:
    return (
        f"Keel {version} installers.\n\n"
        "Every file in this release was built by GitHub Actions and verified by "
        "the Python release manager before the download manifest was published.\n\n"
        "Installers are unsigned: SmartScreen (Windows) and Gatekeeper (macOS) "
        "will warn on first run."
    )


def publish_command(args: argparse.Namespace) -> int:
    version = validate_version(None)
    tag = args.tag or f"v{version}"
    validate_version(tag)
    repo = args.repo or detect_repo()
    artifacts_root = Path(args.artifacts)
    if not artifacts_root.is_absolute():
        artifacts_root = Path.cwd() / artifacts_root
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = Path.cwd() / out_dir

    print(f"Preparing Keel {version} ({tag}) for {repo}")
    artifacts = _flatten_artifacts(artifacts_root, out_dir)
    # Ensure combined checksums exist.
    combined = out_dir / "RELEASE-SHA256SUMS.txt"
    if not combined.exists():
        write_combined_checksums(artifacts, out_dir)

    base_url = f"https://github.com/{repo}/releases/download"
    release_manifest = build_release_manifest(artifacts, version, tag, base_url)
    (out_dir / "RELEASE-MANIFEST.json").write_text(
        json.dumps(release_manifest, indent=2) + "\n", encoding="utf-8"
    )

    dry_run = bool(args.dry_run)
    if dry_run:
        print("DRY RUN - no network writes")
        print(json.dumps(release_manifest, indent=2))
        download_manifest = build_download_manifest(
            artifacts,
            version,
            tag,
            base_url,
            available=True,
            verified=True,
            verified_at=datetime.now(timezone.utc).isoformat(),
            published_at=datetime.now(timezone.utc).isoformat(),
        )
        (out_dir / "download.json").write_text(
            json.dumps(download_manifest, indent=2) + "\n", encoding="utf-8"
        )
        print(f"would publish {len(artifacts)} installers + manifests to {repo}")
        return 0

    token = token_from_env()
    client = GitHubClient(repo, token)

    # Find or create the release (draft first).
    release = client.get_release_by_tag(tag)
    if release is None:
        release = client.create_release(tag, f"Keel {version}", _release_body(version, tag), True)
    release_id = release["id"]
    draft = bool(release.get("draft", False))

    # Remove any pre-existing download.json asset so availability cannot appear
    # before verification.
    for asset in release.get("assets", []) or []:
        if asset.get("name") == "download.json":
            client.delete_asset(asset["id"])

    # Upload installers + checksums + release manifest (NOT download.json yet).
    upload_names = sorted(artifacts) + ["RELEASE-SHA256SUMS.txt", "RELEASE-MANIFEST.json"]
    # De-duplicate while preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for name in upload_names:
        if name in seen:
            continue
        seen.add(name)
        ordered.append(name)

    for name in ordered:
        path = out_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"missing file to upload: {path}")
        # Replace an existing asset of the same name.
        for asset in client.get_release_by_tag(tag).get("assets", []) or []:
            if asset.get("name") == name:
                client.delete_asset(asset["id"])
        print(f"uploading {name} ({path.stat().st_size} bytes)")
        client.upload_asset(release_id, path, name)

    # Verify public installer URLs before publishing the manifest.
    errors = verify_release_manifest(release_manifest, allow_http=False, retries=5, retry_delay=10, timeout=600)
    if errors:
        raise RuntimeError("installer verification failed before manifest publish:\n" + "\n".join(errors))

    # Generate and upload the download manifest (this is the availability gate).
    now = datetime.now(timezone.utc).isoformat()
    download_manifest = build_download_manifest(
        artifacts,
        version,
        tag,
        base_url,
        available=True,
        verified=True,
        verified_at=now,
        published_at=now,
    )
    (out_dir / "download.json").write_text(
        json.dumps(download_manifest, indent=2) + "\n", encoding="utf-8"
    )
    for asset in client.get_release_by_tag(tag).get("assets", []) or []:
        if asset.get("name") == "download.json":
            client.delete_asset(asset["id"])
    print("uploading download.json")
    client.upload_asset(release_id, out_dir / "download.json", "download.json")

    # Publish the release (make it non-draft) if needed.
    if draft:
        client.update_release(release_id, draft=False)

    # Re-verify the published manifest via the stable latest URL, with retries.
    latest_url = f"https://github.com/{repo}/releases/latest/download/download.json"
    published_ok = False
    last_errors: list[str] = []
    for attempt in range(1, 11):
        try:
            published_manifest = load_manifest(latest_url, allow_http=False, timeout=60)
            if published_manifest != download_manifest:
                last_errors = ["published manifest does not match generated manifest"]
            else:
                errs = verify_manifest(
                    published_manifest,
                    allow_http=False,
                    retries=3,
                    retry_delay=5,
                    timeout=600,
                    require_available=True,
                )
                if not errs:
                    published_ok = True
                    break
                last_errors = errs
        except Exception as exc:  # noqa: BLE001
            last_errors = [str(exc)]
        time.sleep(6)
    if not published_ok:
        # Remove the manifest so the site cannot advertise an unverified release.
        try:
            fresh = client.get_release_by_tag(tag)
            if fresh:
                for asset in fresh.get("assets", []) or []:
                    if asset.get("name") == "download.json":
                        client.delete_asset(asset["id"])
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(
            "published manifest verification failed:\n" + "\n".join(last_errors)
        )

    print(f"Published Keel {version}")
    print(f"Manifest: {latest_url}")
    print(f"Release: https://github.com/{repo}/releases/tag/{tag}")
    return 0


def publish_cli(args: argparse.Namespace) -> int:
    try:
        return publish_command(args)
    except (GitHubError, Exception) as exc:  # noqa: BLE001
        print(f"publish failed: {exc}", file=sys.stderr)
        return 1
