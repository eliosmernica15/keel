"""Validate a published Keel download manifest.

Checks that every channel is genuinely downloadable: HTTPS URL, non-zero
size, a 64-hex SHA-256, and that the URL points at the named file. With
--compare, also requires a fetched manifest to be byte-for-byte equivalent
(as parsed JSON) to the generated one.

Usage:
  python scripts/check_download_manifest.py release/download.json \
      --compare published-download.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

SHA_RE = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_CHANNELS = ("windows", "macos", "linux")


def load(path: Path) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot read {path}: {exc}")
    if not isinstance(doc, dict):
        raise SystemExit(f"{path} is not a JSON object")
    return doc


def validate(doc: dict, allow_http: bool) -> list[str]:
    errors: list[str] = []
    schemes = {"https"} | ({"http"} if allow_http else set())

    for key in ("version", "tag"):
        if not isinstance(doc.get(key), str) or not doc[key]:
            errors.append(f"missing {key}")
    version, tag = doc.get("version"), doc.get("tag")
    if isinstance(version, str) and isinstance(tag, str) and tag != f"v{version}":
        errors.append(f"tag {tag!r} does not match version {version!r}")

    channels = doc.get("channels")
    if not isinstance(channels, dict):
        return errors + ["missing channels object"]

    for key in REQUIRED_CHANNELS:
        ch = channels.get(key)
        if not isinstance(ch, dict):
            errors.append(f"{key}: channel missing")
            continue
        if ch.get("available") is not True:
            errors.append(f"{key}: not available")
        if ch.get("verified") is not True:
            errors.append(f"{key}: not marked verified")
        if not ch.get("file"):
            errors.append(f"{key}: missing file name")
        size = ch.get("size")
        if not isinstance(size, int) or size <= 0:
            errors.append(f"{key}: missing byte size")
        digest = str(ch.get("sha256") or "").lower()
        if not SHA_RE.match(digest):
            errors.append(f"{key}: invalid sha256")
        url = str(ch.get("url") or "")
        parsed = urlparse(url)
        if parsed.scheme not in schemes or not parsed.netloc:
            errors.append(f"{key}: url is not a public {'HTTPS' if not allow_http else 'HTTP(S)'} URL")
        elif ch.get("file") and parsed.path.rsplit("/", 1)[-1] != ch["file"]:
            errors.append(f"{key}: url does not point at {ch['file']}")

        for alt in ch.get("alternatives") or []:
            if not isinstance(alt, dict):
                errors.append(f"{key}: malformed alternative")
                continue
            alt_url = urlparse(str(alt.get("url") or ""))
            if alt_url.scheme not in schemes or not alt_url.netloc:
                errors.append(f"{key}: alternative {alt.get('file')!r} has no public URL")
            alt_size = alt.get("size")
            if not isinstance(alt_size, int) or alt_size <= 0:
                errors.append(f"{key}: alternative {alt.get('file')!r} has no size")
            if not SHA_RE.match(str(alt.get("sha256") or "").lower()):
                errors.append(f"{key}: alternative {alt.get('file')!r} has an invalid sha256")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--compare", type=Path, default=None,
                    help="freshly fetched manifest that must equal the first")
    ap.add_argument("--allow-http", action="store_true")
    args = ap.parse_args()

    doc = load(args.manifest)
    errors = validate(doc, args.allow_http)
    if errors:
        print("INVALID DOWNLOAD MANIFEST", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    if args.compare:
        public = load(args.compare)
        if public != doc:
            print(f"{args.compare} differs from {args.manifest}", file=sys.stderr)
            return 1
        print(f"manifest matches {args.compare}")

    print(
        f"valid download manifest: Keel {doc['version']} ({doc['tag']}), "
        f"{len(doc['channels'])} channels"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
