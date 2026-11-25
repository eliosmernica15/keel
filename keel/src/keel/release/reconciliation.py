"""Reconcile release metadata with files that actually exist.

This module is the authoritative bridge between the release generator and the
tracked static download manifest. It is deliberately strict:

* no asset is accepted unless a real local file backs it;
* checksums and byte sizes are always recomputed from that file;
* archive formats (DMG/ZIP/AppImage) are rejected even if a stale file is
  present in a staging directory;
* an empty staging directory produces an honest fallback manifest (every
  channel ``available: false`` / ``verified: false``, no URLs) instead of an
  empty-looking "success".

Nothing here publishes or signs anything. Publication and verification are
separate, owner-gated steps; a locally present installer is never treated as
publicly available merely because it exists on disk.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from .common import (
    CHANNELS,
    PROJECT_ROOT,
    build_fallback_download_manifest,
    build_release_manifest,
    expected_filenames,
    read_version,
    sha256_file,
)

MANIFEST_NAME = "RELEASE-MANIFEST.json"
CHECKSUMS_NAME = "RELEASE-SHA256SUMS.txt"
DOWNLOAD_NAME = "download.json"

# Native installer formats only. These are derived from the single channel
# table so the metadata contract cannot drift from the packaging config.
SUPPORTED_ASSET_SUFFIXES = frozenset(
    str(Path(name).suffix).lower()
    for channel in CHANNELS
    for name in [channel["primary"], *channel["alternatives"]]
)
STALE_ASSET_SUFFIXES = (".dmg", ".zip", ".appimage")

_CHECKSUM_LINE = re.compile(r"^([0-9a-fA-F]{64})[ \t]+\*?(\S+)$")


def is_stale_asset_name(name: object) -> bool:
    """True for the archive formats that are no longer shipped."""
    if not isinstance(name, str) or not name:
        return False
    return str(name).strip().lower().endswith(STALE_ASSET_SUFFIXES)


def stale_format_names(values: Iterable[object]) -> list[str]:
    """Return the distinct stale asset names/URLs in *values*."""
    return sorted({str(value) for value in values if is_stale_asset_name(value)})


def release_manifest_asset_names(manifest: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    for entry in manifest.get("files") or []:
        if isinstance(entry, dict) and isinstance(entry.get("file"), str):
            names.append(entry["file"])
    return names


def download_manifest_asset_names(manifest: Mapping[str, Any]) -> list[str]:
    """Every file name or URL advertised by a download manifest."""
    values: list[str] = []
    channels = manifest.get("channels")
    if not isinstance(channels, dict):
        return values
    for channel in channels.values():
        if not isinstance(channel, dict):
            continue
        for key in ("file", "url"):
            if isinstance(channel.get(key), str):
                values.append(channel[key])
        for alt in channel.get("alternatives") or []:
            if isinstance(alt, dict):
                for key in ("file", "url"):
                    if isinstance(alt.get(key), str):
                        values.append(alt[key])
    return values


def _safe_local_path(root: Path, name: str) -> Path | None:
    """Resolve an asset name inside *root*, refusing path traversal."""
    if not isinstance(name, str) or not name:
        return None
    if Path(name).name != name or name in (".", ".."):
        return None
    return root / name


def validate_manifest_files(
    manifest: Mapping[str, Any],
    root: Path,
    *,
    version: str | None = None,
    require_complete: bool = False,
) -> list[str]:
    """Check every release-manifest file entry against bytes on disk.

    With ``require_complete`` the full configured installer set must be
    present; without it a partial, honestly-empty manifest is allowed.
    """
    errors: list[str] = []
    expected_version = version or read_version()
    if manifest.get("version") != expected_version:
        errors.append(
            f"manifest version {manifest.get('version')!r} != {expected_version!r}"
        )
    entries = manifest.get("files")
    if not isinstance(entries, list):
        return [*errors, "release manifest has no files list"]

    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("file entry is not an object")
            continue
        name = entry.get("file")
        if not isinstance(name, str) or not name:
            errors.append("file entry has no name")
            continue
        if name in seen:
            errors.append(f"duplicate manifest entry: {name}")
        seen.add(name)
        if is_stale_asset_name(name):
            errors.append(f"stale archive format in release manifest: {name}")
        if Path(name).suffix.lower() not in SUPPORTED_ASSET_SUFFIXES:
            errors.append(f"unsupported asset format in release manifest: {name}")
        if entry.get("version") not in (None, expected_version):
            errors.append(f"{name}: version {entry.get('version')!r} is out of sync")
        path = _safe_local_path(root, name)
        if path is None:
            errors.append(f"{name}: unsafe asset name")
            continue
        if not path.is_file():
            errors.append(f"{name}: manifest references a missing file")
            continue
        actual_size = path.stat().st_size
        declared_size = entry.get("bytes")
        if not isinstance(declared_size, int) or declared_size != actual_size:
            errors.append(
                f"{name}: size mismatch (manifest {declared_size!r}, disk {actual_size})"
            )
        declared_sha = str(entry.get("sha256") or "").lower()
        actual_sha = sha256_file(path).lower()
        if declared_sha != actual_sha:
            errors.append(
                f"{name}: sha256 mismatch (manifest {declared_sha!r}, disk {actual_sha})"
            )
        url = entry.get("url")
        # "pending" is the generator's honest placeholder for a local,
        # unpublished artifact; it is not an advertised download URL.
        if (isinstance(url, str) and url and url != "pending"
                and not url.startswith("https://")):
            errors.append(f"{name}: asset URL is not HTTPS: {url}")

    if require_complete:
        missing = sorted(set(expected_filenames(expected_version)) - seen)
        if missing:
            errors.append("missing required artifacts: " + ", ".join(missing))
    return errors


def parse_checksums(text: str) -> dict[str, str]:
    """Parse ``RELEASE-SHA256SUMS.txt`` into ``{filename: lowercase sha256}``."""
    result: dict[str, str] = {}
    for lineno, raw in enumerate(str(text).splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _CHECKSUM_LINE.match(line)
        if match is None:
            raise ValueError(f"invalid checksum line {lineno}: {line!r}")
        name = Path(match.group(2)).name
        if name in result:
            raise ValueError(f"duplicate checksum entry: {name}")
        result[name] = match.group(1).lower()
    return result


def combined_checksums_text(artifacts: Mapping[str, Path]) -> str:
    """Deterministic checksum text, identical to the CLI-generated file."""
    lines = [
        f"{sha256_file(artifacts[name]).lower()}  {name}"
        for name in sorted(artifacts)
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def validate_checksums_coverage(
    checksums_text: str,
    manifest: Mapping[str, Any],
    *,
    root: Path | None = None,
) -> list[str]:
    """Require a one-to-one, value-exact mapping between manifest and sums."""
    errors: list[str] = []
    try:
        actual = parse_checksums(checksums_text)
    except ValueError as exc:
        return [str(exc)]
    expected: dict[str, str] = {}
    for name in release_manifest_asset_names(manifest):
        entry = next(
            (e for e in manifest.get("files") or []
             if isinstance(e, dict) and e.get("file") == name),
            None,
        )
        sha = str((entry or {}).get("sha256") or "").lower()
        expected[Path(name).name] = sha
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            errors.append(f"{name}: manifest sha256 is not a 64-hex digest")

    for name in sorted(set(expected) - set(actual)):
        errors.append(f"checksums file missing entry: {name}")
    for name in sorted(set(actual) - set(expected)):
        errors.append(f"checksums file has orphan entry: {name}")
    for name in sorted(set(expected) & set(actual)):
        if actual[name] != expected[name]:
            errors.append(f"checksums file mismatch: {name}")
        if root is not None:
            path = _safe_local_path(root, name)
            if path is None or not path.is_file():
                errors.append(f"checksums file references missing asset: {name}")
            elif sha256_file(path).lower() != actual[name]:
                errors.append(f"checksums file digest does not match disk: {name}")
    return errors


def _validate_channel_entry(
    key: str,
    entry: Mapping[str, Any],
    *,
    root: Path,
    backed: set[str],
) -> list[str]:
    errors: list[str] = []
    label = f"{key} alt {entry.get('file')}" if key.endswith(".alt") else key
    for value in (entry.get("file"), entry.get("url")):
        if is_stale_asset_name(value):
            errors.append(f"{label}: stale archive format advertised: {value}")
    name = entry.get("file")
    if not isinstance(name, str) or not name:
        return [*errors, f"{label}: missing file name"]

    available = entry.get("available") is True
    verified = entry.get("verified") is True
    url = entry.get("url")
    size = entry.get("size")
    sha = entry.get("sha256")

    if name not in backed:
        # Nothing checksum-backed: the channel must not advertise anything.
        if available or verified or url is not None or size is not None or sha is not None:
            errors.append(
                f"{label}: advertises {name} without a checksummed local asset"
            )
        return errors

    path = _safe_local_path(root, name)
    if path is None or not path.is_file():
        errors.append(f"{label}: advertised asset does not exist: {name}")
        return errors
    if not available:
        # A real local file may be staged but not yet published/verified.
        if url is not None or verified or size is not None or sha is not None:
            errors.append(f"{label}: unavailable channel still advertises asset data")
        return errors
    if not verified:
        errors.append(f"{label}: available channel is not marked verified")
    if not isinstance(url, str) or not url.startswith("https://"):
        errors.append(f"{label}: available asset needs an HTTPS URL")
    elif Path(urlparse_path(url)).name != name:
        errors.append(f"{label}: asset URL does not name the advertised file")
    if size != path.stat().st_size:
        errors.append(f"{label}: size mismatch against local asset")
    if str(sha or "").lower() != sha256_file(path).lower():
        errors.append(f"{label}: sha256 mismatch against local asset")
    return errors


def urlparse_path(url: str) -> str:
    """Return the URL path without importing a URL parser into the hot path."""
    from urllib.parse import urlparse

    return urlparse(url).path


def validate_download_manifest(
    download: Mapping[str, Any],
    release: Mapping[str, Any],
    root: Path,
    *,
    version: str | None = None,
) -> list[str]:
    """Ensure every advertised asset exists, is checksummed and is real.

    ``root`` is the directory that holds the actual installer bytes. For the
    tracked site manifest it is the site directory, which intentionally holds
    no installers; only the honest all-unavailable shape can pass there.
    """
    errors: list[str] = []
    expected_version = version or read_version()
    expected_tag = f"v{expected_version}"
    if download.get("version") != expected_version:
        errors.append(f"download version {download.get('version')!r} is out of sync")
    if release.get("version") != expected_version:
        errors.append(f"release manifest version {release.get('version')!r} is out of sync")
    if download.get("tag") != expected_tag or release.get("tag") != expected_tag:
        errors.append(f"release tag must be {expected_tag!r}")
    if download.get("base_url") and not str(download["base_url"]).startswith("https://"):
        errors.append("base_url must be HTTPS or null")

    backed = set(release_manifest_asset_names(release))
    stale = stale_format_names(download_manifest_asset_names(download) + list(backed))
    errors.extend(f"stale archive format in metadata: {name}" for name in stale)

    channels = download.get("channels")
    if not isinstance(channels, dict):
        return [*errors, "download manifest has no channels object"]
    if set(channels) != {c["key"] for c in CHANNELS}:
        errors.append("download manifest channel set does not match CHANNELS")

    for key, channel in channels.items():
        if not isinstance(channel, dict):
            errors.append(f"{key}: channel is not an object")
            continue
        if channel.get("version") not in (None, expected_version):
            errors.append(f"{key}: channel version is out of sync")
        errors.extend(
            _validate_channel_entry(key, channel, root=root, backed=backed)
        )
        alts = channel.get("alternatives") or []
        if not isinstance(alts, list):
            errors.append(f"{key}: alternatives must be a list")
            continue
        for alt in alts:
            if isinstance(alt, dict):
                errors.extend(
                    _validate_channel_entry(f"{key}.alt", alt, root=root, backed=backed)
                )
            else:
                errors.append(f"{key}: alternative is not an object")
    return errors


def _discover_release_files(root: Path) -> dict[str, Path]:
    """Find flat, release-shaped files without picking up site assets.

    A case-sensitive ``Keel-`` prefix is used deliberately: a case-insensitive
    glob on Windows would treat unrelated site files such as
    ``keel-extension.zip`` as stale installers.
    """
    found: dict[str, Path] = {}
    for path in root.iterdir():
        if path.is_file() and path.name.startswith("Keel-"):
            found[path.name] = path
    return found


def build_reconciled_metadata(root: Path, *, version: str | None = None) -> dict[str, Any]:
    """Build metadata solely from real installer files in *root*.

    Local files are staged assets, not a published release, so the returned
    download manifest is always the honest fallback. Publication must set
    ``available``/``verified`` only after an actual public download matches
    the recomputed size and SHA-256 (see ``publish_command``).
    """
    root = Path(root)
    resolved_version = version or read_version()
    tag = f"v{resolved_version}"
    if not root.is_dir():
        raise FileNotFoundError(f"release artifact directory not found: {root}")

    found = _discover_release_files(root)
    stale = stale_format_names(found)
    if stale:
        raise ValueError("stale release formats in artifact directory: " + ", ".join(stale))
    expected = set(expected_filenames(resolved_version))
    unexpected = sorted(set(found) - expected)
    if unexpected:
        raise ValueError("unexpected release assets: " + ", ".join(unexpected))
    staged = {name: found[name] for name in sorted(expected & set(found))}

    release_manifest = build_release_manifest(staged, resolved_version, tag, "")
    # Deterministic: reconciliation records no publication/signature claim.
    release_manifest["generated"] = "tracked-tree-reconciliation"
    release_manifest["published_at"] = None
    release_manifest["publication_status"] = "not_published_by_this_workstream"
    release_manifest["signing_status"] = "unsigned"

    checksums = combined_checksums_text(staged)
    download = build_fallback_download_manifest(resolved_version, tag)
    return {
        "manifest": release_manifest,
        "checksums_text": checksums,
        "download": download,
    }


def assert_metadata_consistent(root: Path, *, version: str | None = None) -> dict[str, Any]:
    """Fail closed unless generated metadata is internally and physically true."""
    result = build_reconciled_metadata(root, version=version)
    resolved_version = version or read_version()
    errors: list[str] = []
    errors.extend(validate_manifest_files(result["manifest"], root, version=resolved_version))
    errors.extend(validate_checksums_coverage(
        result["checksums_text"], result["manifest"], root=root))
    errors.extend(validate_download_manifest(
        result["download"], result["manifest"], root, version=resolved_version))
    if errors:
        raise ValueError("RELEASE METADATA INCONSISTENT:\n  - " + "\n  - ".join(errors))
    return result


def tracked_download_path() -> Path:
    return PROJECT_ROOT / "site" / DOWNLOAD_NAME


def load_tracked_download() -> dict[str, Any]:
    return json.loads(tracked_download_path().read_text(encoding="utf-8"))


def validate_tracked_download(*, version: str | None = None) -> list[str]:
    """Check the committed site manifest against an empty reconciled tree."""
    resolved_version = version or read_version()
    tracked_root = tracked_download_path().parent
    # The tracked site manifest advertises nothing, so the authoritative
    # comparison is against an empty (zero-file) release manifest, not against
    # the site directory (which contains unrelated static assets).
    empty_release = build_release_manifest({}, resolved_version, f"v{resolved_version}", "")
    return validate_download_manifest(
        load_tracked_download(), empty_release, tracked_root,
        version=resolved_version,
    )


def sha256_tracked_files(paths: Iterable[Path]) -> dict[str, str]:
    """Measure real files (e.g. tracked metadata) for an evidence report."""
    result: dict[str, str] = {}
    for path in paths:
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(path)
        result[str(path)] = sha256_file(path)
    return result
