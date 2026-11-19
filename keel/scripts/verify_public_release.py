"""Verify that published Keel downloads are really live and match their hashes.

Used by the release workflow after uploading to object storage, and by the
site-manifest check after publishing download.json. It performs a real public
download (or HEAD when --head-only is given), then compares HTTP status, byte
count and SHA-256 against the manifest. Any mismatch exits non-zero.

Manifest shapes supported:
  - RELEASE-MANIFEST.json   {"files": [{"file","bytes","sha256","url"}, ...]}
  - download.json           {"channels": {"windows": {...,"alternatives":[]}}}

Usage:
  python scripts/verify_public_release.py --manifest RELEASE-MANIFEST.json
  python scripts/verify_public_release.py --manifest published-download.json --head-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

USER_AGENT = "keel-release-verifier/0.1 (+https://keel-desktop.vercel.app)"


def entries_from(doc: dict) -> list[dict]:
    """Normalize either manifest shape into {label,url,size,sha256}."""
    entries: list[dict] = []
    if isinstance(doc.get("files"), list):
        for item in doc["files"]:
            entries.append({
                "label": item.get("file") or item.get("url"),
                "url": item.get("url") or "",
                "size": int(item.get("bytes") or 0),
                "sha256": (item.get("sha256") or "").lower(),
            })
        return entries

    channels = doc.get("channels") or {}
    for key, ch in channels.items():
        if not isinstance(ch, dict):
            continue
        if ch.get("available") is not True:
            print(f"skip {key}: not marked available")
            continue
        entries.append({
            "label": ch.get("file") or key,
            "url": ch.get("url") or "",
            "size": int(ch.get("size") or 0),
            "sha256": (ch.get("sha256") or "").lower(),
        })
        for alt in ch.get("alternatives") or []:
            if not isinstance(alt, dict):
                continue
            entries.append({
                "label": alt.get("file") or f"{key} alternative",
                "url": alt.get("url") or "",
                "size": int(alt.get("size") or 0),
                "sha256": (alt.get("sha256") or "").lower(),
            })
    return entries


def validate_entry(entry: dict, allow_http: bool) -> str | None:
    """Return an error string, or None when the entry is well-formed."""
    label = entry["label"]
    url = entry["url"]
    parsed = urlparse(url)
    schemes = {"https"} | ({"http"} if allow_http else set())
    if parsed.scheme not in schemes or not parsed.netloc:
        return f"{label}: not an absolute {'HTTPS' if not allow_http else 'HTTP(S)'} URL: {url!r}"
    if not entry["sha256"] or len(entry["sha256"]) != 64:
        return f"{label}: missing or malformed sha256"
    if entry["size"] <= 0:
        return f"{label}: missing byte size"
    return None


def _open(url: str, method: str, timeout: int):
    req = urllib.request.Request(url, method=method, headers={
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Cache-Control": "no-cache",
    })
    return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 - URL from our manifest


def head_check(entry: dict, timeout: int) -> tuple[bool, bool, str]:
    """Cheap status/size check.

    Returns (ok, needs_full_get, message). `needs_full_get` is true when the
    server does not support HEAD or omits Content-Length, in which case the
    caller must fall back to a full download.
    """
    try:
        with _open(entry["url"], "HEAD", timeout) as resp:
            status = getattr(resp, "status", 200)
            length = resp.headers.get("Content-Length")
    except urllib.error.HTTPError as exc:
        if exc.code in (405, 501):
            return False, True, "server does not support HEAD; falling back to GET"
        return False, False, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - reported to the caller
        return False, False, f"request failed: {exc}"

    if status != 200:
        return False, False, f"HTTP {status}"
    if length is None:
        return False, True, "no Content-Length; falling back to GET"
    if int(length) != entry["size"]:
        return False, False, f"size mismatch: public {length} bytes, expected {entry['size']}"
    return True, False, f"HEAD 200, {length} bytes"


def full_check(entry: dict, timeout: int) -> tuple[bool, str]:
    h = hashlib.sha256()
    total = 0
    try:
        with _open(entry["url"], "GET", timeout) as resp:
            status = getattr(resp, "status", 200)
            if status != 200:
                return False, f"HTTP {status}"
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                h.update(chunk)
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - reported to the caller
        return False, f"request failed: {exc}"

    digest = h.hexdigest()
    if total != entry["size"]:
        return False, f"size mismatch: downloaded {total} bytes, expected {entry['size']}"
    if digest != entry["sha256"]:
        return False, f"sha256 mismatch: downloaded {digest}, expected {entry['sha256']}"
    return True, f"200, {total} bytes, sha256 {digest[:12]}..."


def verify(entries: list[dict], *, head_only: bool, timeout: int,
           retries: int, retry_delay: float, allow_http: bool) -> int:
    failures: list[str] = []
    checked: set[str] = set()
    for entry in entries:
        problem = validate_entry(entry, allow_http)
        if problem:
            failures.append(problem)
            continue
        key = entry["url"] + "#" + entry["sha256"]
        if key in checked:
            continue
        checked.add(key)

        attempts = retries + 1
        ok = False
        for attempt in range(1, attempts + 1):
            if head_only:
                ok, needs_full, message = head_check(entry, timeout)
                if needs_full:
                    ok, message = full_check(entry, timeout)
            else:
                ok, message = full_check(entry, timeout)
            print(f"[{attempt}/{attempts}] {entry['label']}: {message}")
            if ok:
                break
            if attempt < attempts:
                time.sleep(retry_delay)

        if not ok:
            failures.append(f"{entry['label']}: {message}")

    if failures:
        print("\nPUBLIC DOWNLOAD VERIFICATION FAILED", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"\nAll {len(checked)} public download(s) verified.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--head-only", action="store_true")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--retry-delay", type=float, default=5.0)
    ap.add_argument("--allow-http", action="store_true",
                    help="allow http:// URLs (local tests only)")
    args = ap.parse_args()

    try:
        doc = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read manifest {args.manifest}: {exc}", file=sys.stderr)
        return 1

    entries = entries_from(doc)
    if not entries:
        print("manifest contains no downloadable entries", file=sys.stderr)
        return 1

    return verify(
        entries,
        head_only=args.head_only,
        timeout=args.timeout,
        retries=max(0, args.retries),
        retry_delay=max(0.0, args.retry_delay),
        allow_http=args.allow_http,
    )


if __name__ == "__main__":
    raise SystemExit(main())
