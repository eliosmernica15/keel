from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .artifacts import scan_sidecar_payload, scan_tree
from .build import build_command
from .licenses import licenses_command
from .publish import publish_command
from .verify import verify_command


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--out", default="release", help="output directory (default: release)")
    p.add_argument("--repo", default=None, help="GitHub owner/repo (default: auto-detect)")
    p.add_argument("--tag", default=None, help="release tag (default: v<version>)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="keel.release", description="Keel release manager")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="build installers for the current OS")
    build.add_argument("--platform", default="auto", choices=["auto", "windows", "macos", "linux"])
    build.add_argument("--out", default="release")
    build.add_argument("--repo", default=None)
    build.add_argument("--tag", default=None)
    build.add_argument("--base-url", default=None)
    build.set_defaults(func=build_command)

    publish = sub.add_parser("publish", help="publish a verified release to GitHub Releases")
    publish.add_argument("--artifacts", default="release", help="directory containing built installers")
    publish.add_argument("--out", default="release")
    publish.add_argument("--repo", default=None)
    publish.add_argument("--tag", default=None)
    publish.add_argument("--dry-run", action="store_true")
    publish.set_defaults(func=publish_command)

    verify = sub.add_parser("verify", help="verify a release manifest and its files")
    verify.add_argument("--manifest", required=True, help="path or URL to download.json")
    verify.add_argument("--compare", default=None, help="second manifest to compare against")
    verify.add_argument("--allow-http", action="store_true", help="allow http://localhost for local testing")
    verify.add_argument("--retries", type=int, default=3)
    verify.add_argument("--retry-delay", type=int, default=5)
    verify.add_argument("--timeout", type=int, default=300)
    verify.add_argument("--require-available", action="store_true")
    verify.set_defaults(func=verify_command)

    licenses = sub.add_parser("licenses", help="write a dependency license inventory")
    licenses.add_argument("--out", default="release")
    licenses.set_defaults(func=licenses_command)

    check = sub.add_parser("check-artifacts", help="scan a directory for prohibited files")
    check.add_argument("path", help="directory to scan")
    check.set_defaults(func=check_artifacts_command)

    return parser


def check_artifacts_command(args) -> int:
    root = Path(args.path)
    violations = (scan_sidecar_payload(root) if root.name == "keel-sidecar"
                  else scan_tree(root))
    if violations:
        for item in violations:
            print(item)
        print(f"prohibited files: {len(violations)}", file=sys.stderr)
        return 1
    print(f"artifact scan clean: {args.path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
