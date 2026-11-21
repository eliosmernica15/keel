from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .common import sha256_file


def _is_loopback_url(url: str) -> bool:
    try:
        from urllib.parse import urlparse

        host = urlparse(url).hostname or ""
    except Exception:
        return False
    return host in {"localhost", "127.0.0.1", "::1"}


def fetch_bytes(url: str, *, allow_http: bool, timeout: int) -> tuple[bytes, int]:
    if url.startswith("http://") and not (allow_http and _is_loopback_url(url)):
        raise ValueError(f"refusing non-HTTPS URL: {url}")
    last_exc: Exception | None = None
    req = urllib.request.Request(url, headers={"Accept": "*/*", "Cache-Control": "no-cache"})
    # urllib follows redirects by default.
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"{url} returned HTTP {resp.status}")
        declared = resp.headers.get("Content-Length")
        declared_size = int(declared) if declared and declared.isdigit() else None
        h = hashlib.sha256()
        total = 0
        chunks: list[bytes] = []
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
            h.update(chunk)
            total += len(chunk)
        data = b"".join(chunks)
        if declared_size is not None and declared_size != total:
            raise RuntimeError(
                f"{url}: Content-Length {declared_size} != downloaded {total}"
            )
        return data, total


def verify_manifest(
    manifest: dict[str, Any],
    *,
    allow_http: bool = False,
    retries: int = 1,
    retry_delay: int = 5,
    timeout: int = 300,
    require_available: bool = False,
) -> list[str]:
    errors: list[str] = []
    channels = manifest.get("channels")
    if not isinstance(channels, dict):
        return ["manifest has no channels object"]

    # Collect unique URLs to download once.
    url_cache: dict[str, tuple[bytes, int]] = {}
    url_errors: dict[str, str] = {}

    def download(url: str) -> tuple[bytes, int] | None:
        if url in url_cache:
            return url_cache[url]
        if url in url_errors:
            return None
        last: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                data, size = fetch_bytes(url, allow_http=allow_http, timeout=timeout)
                url_cache[url] = (data, size)
                return url_cache[url]
            except Exception as exc:  # noqa: BLE001
                last = exc
                if attempt < retries:
                    time.sleep(retry_delay)
        url_errors[url] = str(last)
        return None

    for key, channel in channels.items():
        if not isinstance(channel, dict):
            errors.append(f"{key}: channel is not an object")
            continue
        available = channel.get("available") is True
        verified = channel.get("verified") is True
        if require_available and not available:
            errors.append(f"{key}: not available")
        if not available:
            continue
        # Available channel: full checks.
        if not verified:
            errors.append(f"{key}: not marked verified")
        size = channel.get("size")
        sha = str(channel.get("sha256") or "")
        url = channel.get("url")
        if not isinstance(size, int) or size <= 0:
            errors.append(f"{key}: invalid size")
        if len(sha) != 64 or any(c not in "0123456789abcdefABCDEF" for c in sha):
            errors.append(f"{key}: invalid sha256")
        safe_url = url
        if not isinstance(url, str) or not url:
            errors.append(f"{key}: missing url")
            continue
        if url.startswith("http://") and not (allow_http and _is_loopback_url(url)):
            errors.append(f"{key}: url is not a public HTTPS URL")
            continue
        if url.startswith("https://") is False and not (allow_http and _is_loopback_url(url)):
            errors.append(f"{key}: url is not a public HTTPS URL")
            continue

        result = download(url)
        if result is None:
            errors.append(f"{key}: download failed: {url_errors.get(url)}")
            continue
        data, downloaded_size = result
        if downloaded_size != int(size):
            errors.append(
                f"{key}: size mismatch (manifest {size}, downloaded {downloaded_size})"
            )
        digest = hashlib.sha256(data).hexdigest().upper()
        if digest != sha.upper():
            errors.append(f"{key}: sha256 mismatch (manifest {sha}, downloaded {digest})")

        for alt in channel.get("alternatives") or []:
            if not isinstance(alt, dict):
                errors.append(f"{key}: alternative is not an object")
                continue
            alt_url = alt.get("url")
            alt_size = alt.get("size")
            alt_sha = str(alt.get("sha256") or "")
            if not alt_url:
                continue
            if alt_url.startswith("http://") and not (allow_http and _is_loopback_url(alt_url)):
                errors.append(f"{key} alt {alt.get('file')}: url is not HTTPS")
                continue
            if not isinstance(alt_size, int) or alt_size <= 0:
                errors.append(f"{key} alt {alt.get('file')}: invalid size")
                continue
            if len(alt_sha) != 64:
                errors.append(f"{key} alt {alt.get('file')}: invalid sha256")
                continue
            result = download(alt_url)
            if result is None:
                errors.append(f"{key} alt {alt.get('file')}: download failed")
                continue
            alt_data, alt_downloaded = result
            if alt_downloaded != int(alt_size):
                errors.append(f"{key} alt {alt.get('file')}: size mismatch")
            if hashlib.sha256(alt_data).hexdigest().upper() != alt_sha.upper():
                errors.append(f"{key} alt {alt.get('file')}: sha256 mismatch")

    return errors


def verify_release_manifest(
    manifest: dict[str, Any],
    *,
    allow_http: bool = False,
    retries: int = 1,
    retry_delay: int = 5,
    timeout: int = 300,
    public_key=None,
) -> list[str]:
    errors: list[str] = []
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        return ["release manifest has no files list"]

    url_cache: dict[str, tuple[bytes, int]] = {}
    url_errors: dict[str, str] = {}

    def download(url: str) -> tuple[bytes, int] | None:
        if url in url_cache:
            return url_cache[url]
        if url in url_errors:
            return None
        last: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                data, size = fetch_bytes(url, allow_http=allow_http, timeout=timeout)
                url_cache[url] = (data, size)
                return url_cache[url]
            except Exception as exc:  # noqa: BLE001
                last = exc
                if attempt < retries:
                    time.sleep(retry_delay)
        url_errors[url] = str(last)
        return None

    for entry in files:
        if not isinstance(entry, dict):
            errors.append("file entry is not an object")
            continue
        name = entry.get("file")
        size = entry.get("bytes")
        sha = str(entry.get("sha256") or "")
        url = entry.get("url")
        if not name:
            errors.append("file entry missing name")
            continue
        if not isinstance(size, int) or size <= 0:
            errors.append(f"{name}: invalid size")
        if len(sha) != 64:
            errors.append(f"{name}: invalid sha256")
        if not isinstance(url, str) or not url:
            errors.append(f"{name}: missing url")
            continue
        if url.startswith("http://") and not (allow_http and _is_loopback_url(url)):
            errors.append(f"{name}: url is not HTTPS")
            continue
        result = download(url)
        if result is None:
            errors.append(f"{name}: download failed: {url_errors.get(url)}")
            continue
        data, downloaded_size = result
        if downloaded_size != int(size):
            errors.append(f"{name}: size mismatch (manifest {size}, downloaded {downloaded_size})")
        if hashlib.sha256(data).hexdigest().upper() != sha.upper():
            errors.append(f"{name}: sha256 mismatch")
        if public_key is not None:
            from .signing import verify_bytes

            sig_result = download(url + ".sig")
            if sig_result is None:
                errors.append(f"{name}: signature download failed")
            elif not verify_bytes(data, sig_result[0], public_key):
                errors.append(f"{name}: Ed25519 signature invalid")

    return errors


def load_manifest(path_or_url: str, *, allow_http: bool, timeout: int) -> dict[str, Any]:
    if "://" in path_or_url:
        if path_or_url.startswith("http://") and not (
            allow_http and _is_loopback_url(path_or_url)
        ):
            raise ValueError("manifest URL must be HTTPS")
        req = urllib.request.Request(path_or_url, headers={"Accept": "application/json", "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    else:
        raw = Path(path_or_url).read_bytes()
    return json.loads(raw)


def verify_command(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest, allow_http=args.allow_http, timeout=args.timeout)
    public_key = None
    public_key_path = getattr(args, "public_key", None)
    if public_key_path:
        from pathlib import Path

        from .signing import load_public_key, verify_manifest as verify_sig

        public_key = load_public_key(Path(public_key_path))
        if not verify_sig(manifest, public_key):
            print("ERROR: release manifest signature invalid", file=sys.stderr)
            return 1
    if args.compare:
        other = load_manifest(args.compare, allow_http=args.allow_http, timeout=args.timeout)
        if manifest != other:
            print("manifest mismatch between sources", file=sys.stderr)
            # Show a short diff-ish summary.
            print(json.dumps({"left": manifest}, indent=2)[:2000], file=sys.stderr)
            print(json.dumps({"right": other}, indent=2)[:2000], file=sys.stderr)
            return 1
    if isinstance(manifest.get("channels"), dict):
        errors = verify_manifest(
            manifest,
            allow_http=args.allow_http,
            retries=args.retries,
            retry_delay=args.retry_delay,
            timeout=args.timeout,
            require_available=args.require_available,
        )
    elif isinstance(manifest.get("files"), list):
        errors = verify_release_manifest(
            manifest,
            allow_http=args.allow_http,
            retries=args.retries,
            retry_delay=args.retry_delay,
            timeout=args.timeout,
            public_key=public_key,
        )
    else:
        errors = ["unrecognized manifest format"]
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    # Count available channels.
    channels = manifest.get("channels", {})
    available = [k for k, v in channels.items() if isinstance(v, dict) and v.get("available")]
    print(f"OK - verified {len(available)} available channel(s)")
    return 0
