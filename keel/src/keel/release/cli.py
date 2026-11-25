from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from . import common
from .artifacts import scan_secret_markers, scan_sidecar_payload, scan_tree
from .build import build_command
from .licenses import licenses_command
from .publish import publish_command
from .signing import SigningGateError, SigningMode
from .verify import verify_command


def _add_mode(p: argparse.ArgumentParser, *, help_text: str) -> None:
    p.add_argument(
        "--mode", choices=[mode.value for mode in SigningMode], default=None,
        help=help_text)


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
    build.add_argument(
        "--signing-key", default=None,
        help="optional owner-supplied Ed25519 private key PEM (release signing)")
    build.set_defaults(func=build_command)

    publish = sub.add_parser("publish", help="publish a verified release to GitHub Releases")
    publish.add_argument("--artifacts", default="release", help="directory containing built installers")
    publish.add_argument("--out", default="release")
    publish.add_argument("--repo", default=None)
    publish.add_argument("--tag", default=None)
    publish.add_argument("--dry-run", action="store_true")
    publish.add_argument(
        "--require-signed", action="store_true",
        help="hard-fail when the release manifest or artifacts are unsigned "
             "(also enabled by KEEL_REQUIRE_SIGNED=1; always on for real publish)")
    publish.add_argument(
        "--public-key", default=None,
        help="Ed25519 public key PEM used to verify release signatures")
    _add_mode(publish, help_text=(
        "signing mode: dev (local), test (ephemeral Ed25519), distribution "
        "(owner platform signing; fails closed without verifiers)"))
    publish.set_defaults(func=publish_command)

    verify = sub.add_parser("verify", help="verify a release manifest and its files")
    verify.add_argument("--manifest", required=True, help="path or URL to download.json")
    verify.add_argument("--compare", default=None, help="second manifest to compare against")
    verify.add_argument("--allow-http", action="store_true", help="allow http://localhost for local testing")
    verify.add_argument("--retries", type=int, default=3)
    verify.add_argument("--retry-delay", type=int, default=5)
    verify.add_argument("--timeout", type=int, default=300)
    verify.add_argument("--require-available", action="store_true")
    verify.add_argument(
        "--public-key", default=None,
        help="optional owner-supplied Ed25519 public key PEM for signature verification")
    _add_mode(verify, help_text="signing mode used when reporting signature status")
    verify.set_defaults(func=verify_command)

    signing_status = sub.add_parser(
        "signing-status", help="report honest signing status of a staged release")
    signing_status.add_argument("--artifacts", default="release")
    signing_status.add_argument("--public-key", default=None)
    _add_mode(signing_status, help_text="signing mode to evaluate")
    signing_status.set_defaults(func=signing_status_command)

    licenses = sub.add_parser("licenses", help="write a dependency license inventory")
    licenses.add_argument("--out", default="release")
    licenses.set_defaults(func=licenses_command)

    fallback = sub.add_parser(
        "fallback", help="generate the site fallback download.json (no URLs, all unavailable)")
    fallback.add_argument("--out", default="release/download.fallback.json")
    fallback.set_defaults(func=fallback_command)

    packaging = sub.add_parser(
        "check-packaging", help="static native-packaging acceptance checks (no build required)")
    packaging.add_argument(
        "--installer", default=None,
        help="optional built Windows installer to statically inspect")
    packaging.add_argument(
        "--dist", default=None,
        help="optional dist directory to check for built artifacts")
    packaging.add_argument(
        "--platform", default=None,
        choices=["windows", "macos", "linux"],
        help="platform whose artifacts must be present in --dist")
    packaging.set_defaults(func=check_packaging_command)

    check = sub.add_parser("check-artifacts", help="scan a directory for prohibited files")
    check.add_argument("path", help="directory to scan")
    check.set_defaults(func=check_artifacts_command)

    integrity = sub.add_parser(
        "integrity", help="verify local release artifact integrity")
    integrity.add_argument("--dist", default="dist")
    integrity.add_argument("--artifacts", default="release")
    integrity.set_defaults(func=integrity_command)

    dry_run = sub.add_parser(
        "dry-run", help="run local release checks without publishing")
    dry_run.add_argument("--dist", default="dist")
    dry_run.add_argument("--artifacts", default="release")
    dry_run.add_argument("--public-key", default=None)
    dry_run.add_argument(
        "--require-signed", action="store_true",
        help="hard-fail when the release manifest or artifacts are unsigned "
             "(also enabled by KEEL_REQUIRE_SIGNED=1)")
    _add_mode(dry_run, help_text="signing mode to evaluate during the dry run")
    dry_run.set_defaults(func=dry_run_command)

    update_check = sub.add_parser("update-check", help="check a signed release manifest")
    update_check.add_argument("--manifest", required=True)
    update_check.add_argument("--current", required=True)
    update_check.add_argument(
        "--platform", required=True,
        choices=["windows", "macos", "linux"])
    update_check.add_argument("--public-key", default=None)
    update_check.add_argument("--mirror", action="append", default=[])
    update_check.add_argument("--client-id", default="keel-client")
    update_check.add_argument("--allow-http", action="store_true")
    update_check.add_argument("--timeout", type=int, default=60)
    update_check.set_defaults(func=update_check_command)

    update_download = sub.add_parser("update-download", help="download a verified update artifact")
    update_download.add_argument("--plan", required=True, help="path to an update plan JSON file")
    update_download.add_argument("--out", required=True)
    update_download.add_argument("--public-key", default=None)
    update_download.add_argument("--allow-http", action="store_true")
    update_download.add_argument("--timeout", type=int, default=300)
    update_download.set_defaults(func=update_download_command)

    return parser


def fallback_command(args) -> int:
    version = common.validate_version()
    doc = common.build_fallback_download_manifest(version, f"v{version}")
    out = Path(args.out)
    if not out.is_absolute():
        out = Path.cwd() / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(out),
        "channels": {
            key: {"file": ch["file"], "available": ch["available"],
                  "verified": ch["verified"], "url": ch["url"]}
            for key, ch in doc["channels"].items()
        },
    }, indent=2))
    return 0


def check_packaging_command(args) -> int:
    from .packaging import (check_built_inventory, check_packaging_config,
                            check_windows_installer)

    errors = check_packaging_config()
    if getattr(args, "installer", None):
        errors += [f"installer: {e}" for e in
                   check_windows_installer(args.installer)]
    if getattr(args, "dist", None) and getattr(args, "platform", None):
        errors += [f"inventory: {e}" for e in
                   check_built_inventory(args.dist, args.platform)]
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        print(f"packaging checks: {len(errors)} failure(s)", file=sys.stderr)
        return 1
    print("packaging checks: PASS (config"
          + (", installer" if getattr(args, "installer", None) else "")
          + (", inventory" if getattr(args, "dist", None) else "") + ")")
    return 0


def check_artifacts_command(args) -> int:
    root = Path(args.path)
    violations = (scan_sidecar_payload(root) if root.name == "keel-sidecar"
                  else scan_tree(root) + scan_secret_markers(root))
    if violations:
        for item in violations:
            print(item)
        print(f"prohibited files: {len(violations)}", file=sys.stderr)
        return 1
    print(f"artifact scan clean: {args.path}")
    return 0


def integrity_command(args) -> int:
    from ..release_integrity import run_all

    dist = Path(args.dist)
    artifacts = Path(args.artifacts)
    if not dist.is_absolute():
        dist = Path(common.PROJECT_ROOT) / dist
    if not artifacts.is_absolute():
        artifacts = Path(common.PROJECT_ROOT) / artifacts
    checks = run_all(dist, artifacts)
    for check in checks:
        status = "OK" if check.ok else "FAIL"
        print(f"[{status}] {check.name}: {check.detail}")
    failed = [c for c in checks if not c.ok]
    print(f"integrity: {len(checks) - len(failed)}/{len(checks)} passed")
    return 1 if failed else 0


def dry_run_command(args) -> int:
    from . import common
    from .artifacts import scan_secret_markers, scan_tree
    from .signing import (
        distribution_readiness_errors,
        require_signed_enabled,
        resolve_mode,
        verify_platform_signatures,
        verify_release_bundle,
        verify_signed_release,
    )

    mode = resolve_mode(getattr(args, "mode", None))
    version = common.validate_version()
    dist = Path(args.dist)
    if not dist.is_absolute():
        dist = Path(common.PROJECT_ROOT) / dist
    artifacts = Path(args.artifacts)
    if not artifacts.is_absolute():
        artifacts = Path(common.PROJECT_ROOT) / artifacts

    violations = (scan_tree(dist) + scan_secret_markers(dist)
                  + scan_tree(artifacts) + scan_secret_markers(artifacts))
    if violations:
        print("prohibited files: " + ", ".join(violations[:20]), file=sys.stderr)
        return 1

    require_signed = require_signed_enabled(
        bool(getattr(args, "require_signed", False)))
    if mode is SigningMode.DISTRIBUTION:
        pending = (distribution_readiness_errors()
                   + verify_platform_signatures(artifacts))
        if pending:
            for error in pending:
                print(f"ERROR: {error}", file=sys.stderr)
            print("RELEASE SIGNING GATE FAILED - refusing to claim trusted "
                  "distribution", file=sys.stderr)
            return 1
        require_signed = True  # distribution is always a hard gate
    if require_signed:
        errors = verify_signed_release(artifacts, getattr(args, "public_key", None))
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            print("RELEASE SIGNING GATE FAILED - refusing to treat this "
                  "release as signed", file=sys.stderr)
            return 1
        print("Release signing gate: manifest and all artifacts verified")

    manifest_path = artifacts / "RELEASE-MANIFEST.json"
    if manifest_path.is_file():
        doc = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not require_signed:
            public_key = _optional_public_key(getattr(args, "public_key", None))
            if public_key:
                from .signing import verify_manifest

                if not verify_manifest(doc, public_key):
                    print("manifest signature invalid", file=sys.stderr)
                    return 1
        for field in ("min_version", "blocked_versions", "rollout"):
            if field not in doc:
                print(f"manifest missing {field}", file=sys.stderr)
                return 1

    if not require_signed:
        status = verify_release_bundle(artifacts, mode=mode)
        note = status.errors[0] if status.errors else "no verification performed"
        print(f"Signing status: {status.status} ({note})")

    print(f"OK - dry run passed for {version}; no release published")
    return 0


def _optional_public_key(path: str | None):
    if not path:
        return None
    from .signing import load_public_key

    return load_public_key(Path(path))


def signing_status_command(args) -> int:
    """Report signing status honestly, without leaking key material."""
    from .signing import resolve_mode, verify_release_bundle

    mode = resolve_mode(getattr(args, "mode", None))
    artifacts = Path(args.artifacts)
    if not artifacts.is_absolute():
        artifacts = Path.cwd() / artifacts
    key_ref = getattr(args, "public_key", None)
    result = verify_release_bundle(artifacts, public_key=key_ref, mode=mode)
    payload = {
        "mode": mode.value,
        "status": result.status,
        # "verified" means signature/platform verification actually happened,
        # not merely that the dev-mode advisory pass completed.
        "verified": result.ok and result.status != "unsigned",
        "key_reference": key_ref,
        "key_id": result.key_id,
        "trusted_distribution": result.trusted_distribution,
        "errors": list(result.errors),
    }
    print(json.dumps(payload, indent=2))
    honest = {"unsigned", "dev-verified", "test-verified", "distribution-verified"}
    return 0 if result.status in honest else 1


def update_check_command(args) -> int:
    from .updater import check_for_update

    plan = check_for_update(
        [args.manifest, *args.mirror],
        current_version=args.current,
        platform=args.platform,
        public_key=_optional_public_key(args.public_key),
        allow_http=args.allow_http,
        timeout=args.timeout,
        client_id=args.client_id,
    )
    payload = asdict(plan) if plan else {"available": False}
    # Explicit, truthful advisory flag: an unsigned manifest (no --public-key)
    # must never be presented as signature-verified to the desktop shell.
    payload["signatureVerified"] = bool(plan and plan.signature_verified)
    print(json.dumps(payload))
    return 0


def update_download_command(args) -> int:
    from .updater import UpdatePlan, download_update

    plan = UpdatePlan(**json.loads(Path(args.plan).read_text(encoding="utf-8")))
    target = download_update(
        plan,
        Path(args.out),
        public_key=_optional_public_key(args.public_key),
        allow_http=args.allow_http,
        timeout=args.timeout,
    )
    print(f"downloaded {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        return 130
    except SigningGateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
