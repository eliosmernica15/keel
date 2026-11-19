from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .build import build_command
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

    return parser


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
