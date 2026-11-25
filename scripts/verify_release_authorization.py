#!/usr/bin/env python3
"""Fail-closed release authorization verification for Keel.

This is the runtime enforcement behind .github/workflows/release-authorization.yml.
It is deliberately dependency-free (stdlib only) so it can run on any hosted
runner with just CPython and the `gh` CLI.

A release is AUTHORIZED only when ALL of the following hold:

  1. TAG        - the requested tag is a semver vX.Y.Z (optional -/+ suffix) and
                  really exists in the target repository.
  2. HEAD BRANCH- the release is anchored on the default branch (or on the tag
                  ref itself for a tag push) and the tagged commit is contained
                  in the default branch. A feature-branch tag is rejected.
  3. ACTOR      - the triggering actor is a non-bot GitHub login in the explicit
                  owner allowlist, the same login that triggered the run, and
                  the target repository is owned by an allowlisted account.
  4. EVIDENCE   - every required evidence file is present and non-empty.
  5. APPROVAL   - the approval file contains exactly one explicit marker line
                  of the form `RELEASE-APPROVED: <tag> by @<owner>`, outside any
                  fenced code block, for this tag and an allowlisted approver.

Every failure is collected and reported; the script exits non-zero if anything
is missing, unreadable, inconsistent, or if a `gh` lookup fails. There is no
"warn only" mode: absence of data is a denial, never an implicit pass.

Network/permission note: all `gh api` calls use the caller-supplied token and
only read metadata that GITHUB_TOKEN can access (`contents: read`). When live
GitHub access is unavailable, pass `--gh <path>` to a stub executable that
implements the four read-only endpoints used below; the trust logic is
unchanged. See FINAL-GOVERNANCE-EVIDENCE.md for the exact stub cases exercised.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

TAG_RE = re.compile(r"^v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
MARKER_RE = re.compile(
    r"^RELEASE-APPROVED:\s*(?P<tag>\S+)\s+by\s+@(?P<actor>[A-Za-z0-9-]+)\s*$"
)

DEFAULT_REQUIRED_EVIDENCE = (
    "FINAL-GOVERNANCE-EVIDENCE.md",
    "PRODUCTION-PROMOTION-MANIFEST.md",
    "FINAL-STABILIZATION-ACCEPTANCE.md",
    "PROD-SUPPLY-CHAIN-EVIDENCE.md",
    "STAB-WORKFLOW-EVIDENCE.md",
)


class Gate:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.failures: list[str] = []
        self.passes: list[str] = []
        self.owners = {
            item.strip().lower()
            for item in args.owners.split(",")
            if item.strip()
        }

    def ok(self, message: str) -> None:
        self.passes.append(message)
        print(f"[PASS] {message}")

    def block(self, message: str) -> None:
        self.failures.append(message)
        print(f"[BLOCKED] {message}", file=sys.stderr)

    # ---------------------------------------------------------------- gh ----
    def gh(self, endpoint: str, jq: str, label: str) -> str | None:
        """Run a single read-only `gh api` query; None means 'fail closed'."""
        cmd = [self.args.gh, "api", endpoint, "--jq", jq]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.args.gh_timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self.block(f"{label}: could not execute gh ({exc})")
            return None
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            tail = detail[-1] if detail else f"exit {proc.returncode}"
            # Trim to avoid dumping a token-bearing URL into the log.
            self.block(f"{label}: gh query failed ({tail[:200]})")
            return None
        value = proc.stdout.strip()
        if not value:
            self.block(f"{label}: gh returned an empty value")
            return None
        return value

    # ------------------------------------------------------------- checks ---
    def check_tag(self) -> None:
        tag = self.args.tag
        if not TAG_RE.match(tag or ""):
            self.block(f"TAG: {tag!r} is not a valid release tag (expected vMAJOR.MINOR.PATCH)")
            return
        self.ok(f"TAG: {tag} matches the required semver pattern")
        ref = self.gh(
            f"repos/{self.args.repository}/git/ref/tags/{tag}",
            ".ref",
            f"TAG {tag} existence",
        )
        if ref is not None:
            if ref == f"refs/tags/{tag}":
                self.ok(f"TAG: {tag} exists in {self.args.repository}")
            else:
                self.block(f"TAG: unexpected ref {ref!r} for {tag}")

    def check_head_branch(self) -> None:
        branch = self.args.head_branch
        default = self.args.default_branch
        if branch not in (default, self.args.tag):
            self.block(
                f"HEAD BRANCH: {branch!r} is neither the default branch "
                f"{default!r} nor the release tag {self.args.tag!r}"
            )
            return
        self.ok(f"HEAD BRANCH: release anchored at {branch!r}")
        status = self.gh(
            f"repos/{self.args.repository}/compare/{default}...{self.args.tag}",
            ".status",
            f"TAG {self.args.tag} containment in {default}",
        )
        if status is None:
            return
        if status in ("behind", "identical"):
            self.ok(f"HEAD BRANCH: {self.args.tag} is contained in {default} (status={status})")
        else:
            self.block(
                f"HEAD BRANCH: {self.args.tag} is not contained in {default} "
                f"(compare status={status!r}); refuse to release an unmerged commit"
            )

    def check_actor(self) -> None:
        actor = self.args.actor
        if not LOGIN_RE.match(actor or "") or actor.endswith("[bot]"):
            self.block(f"ACTOR: {actor!r} is not a valid non-bot GitHub login")
        else:
            self.ok(f"ACTOR: {actor} is a valid GitHub login")
        if actor.lower() not in self.owners:
            self.block(f"ACTOR: {actor!r} is not in the owner allowlist")
        else:
            self.ok(f"ACTOR: {actor} is in the owner allowlist")
        triggering = self.args.triggering_actor
        if triggering and triggering.lower() != actor.lower():
            self.block(f"ACTOR: triggering_actor {triggering!r} differs from actor {actor!r}")
        elif triggering:
            self.ok(f"ACTOR: triggering_actor matches ({triggering})")
        owner = self.gh(
            f"repos/{self.args.repository}",
            ".owner.login",
            "repository owner",
        )
        if owner is not None:
            if owner.lower() in self.owners:
                self.ok(f"ACTOR: repository owner @{owner} is allowlisted")
            else:
                self.block(f"ACTOR: repository owner @{owner} is not allowlisted")
        full_name = self.gh(
            f"repos/{self.args.repository}",
            ".full_name",
            "repository identity",
        )
        if full_name is not None:
            if full_name.lower() == self.args.repository.lower():
                self.ok(f"ACTOR: repository identity confirmed ({full_name})")
            else:
                self.block(
                    f"ACTOR: repository identity mismatch: expected "
                    f"{self.args.repository!r}, got {full_name!r}"
                )

    def check_evidence(self) -> None:
        root = self.args.evidence_root
        for rel in self.args.required_evidence.split(","):
            rel = rel.strip()
            if not rel:
                continue
            path = root / rel
            if not path.is_file():
                self.block(f"EVIDENCE: missing required file {rel}")
                continue
            try:
                size = path.stat().st_size
            except OSError as exc:
                self.block(f"EVIDENCE: cannot stat {rel} ({exc})")
                continue
            if size == 0:
                self.block(f"EVIDENCE: required file {rel} is empty")
            else:
                self.ok(f"EVIDENCE: {rel} present ({size} bytes)")

    def check_approval(self) -> None:
        root = self.args.evidence_root
        approval = root / self.args.approval_file
        if not approval.is_file():
            self.block(f"APPROVAL: missing approval file {self.args.approval_file}")
            return
        try:
            text = approval.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            self.block(f"APPROVAL: cannot read {self.args.approval_file} ({exc})")
            return

        matches: list[tuple[int, str, str]] = []
        in_fence = False
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            if stripped.startswith("RELEASE-APPROVED:"):
                match = MARKER_RE.match(stripped)
                if match is None:
                    self.block(
                        f"APPROVAL: malformed marker at "
                        f"{self.args.approval_file}:{lineno}"
                    )
                    continue
                matches.append((lineno, match.group("tag"), match.group("actor")))

        if not matches:
            self.block(
                "APPROVAL: no explicit RELEASE-APPROVED marker outside a fenced block"
            )
            return
        if len(matches) != 1:
            self.block(
                "APPROVAL: expected exactly one approval marker, found "
                + str(len(matches))
            )
            return
        lineno, marker_tag, marker_actor = matches[0]
        if marker_tag != self.args.tag:
            self.block(
                f"APPROVAL: marker at {self.args.approval_file}:{lineno} approves "
                f"{marker_tag!r}, not {self.args.tag!r}"
            )
        else:
            self.ok(f"APPROVAL: marker names tag {marker_tag}")
        if marker_actor.lower() not in self.owners:
            self.block(
                f"APPROVAL: marker approver @{marker_actor} is not an allowlisted owner"
            )
        else:
            self.ok(f"APPROVAL: marker signed by allowlisted owner @{marker_actor}")

    def run(self) -> int:
        self.check_tag()
        self.check_head_branch()
        self.check_actor()
        self.check_evidence()
        self.check_approval()
        print("=" * 60)
        if self.failures:
            print(f"RESULT: NOT AUTHORIZED ({len(self.failures)} blocking finding(s))")
            for failure in self.failures:
                print(f"  - {failure}")
            return 1
        print("RESULT: AUTHORIZED")
        return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="Release tag, e.g. v1.2.3")
    parser.add_argument(
        "--head-branch",
        required=True,
        help="Source branch of the triggering event (or the tag for a tag push)",
    )
    parser.add_argument("--actor", required=True, help="github.actor login")
    parser.add_argument(
        "--triggering-actor",
        default="",
        help="github.triggering_actor, when available",
    )
    parser.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="owner/repo (default: $GITHUB_REPOSITORY)",
    )
    parser.add_argument("--default-branch", default="main")
    parser.add_argument(
        "--owners",
        default=os.environ.get("KEEL_RELEASE_OWNERS", "eliosmernica15"),
        help="Comma-separated allowlist of owner logins",
    )
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root containing the evidence files",
    )
    parser.add_argument(
        "--required-evidence",
        default=",".join(DEFAULT_REQUIRED_EVIDENCE),
        help="Comma-separated required evidence paths",
    )
    parser.add_argument(
        "--approval-file",
        default="FINAL-GOVERNANCE-EVIDENCE.md",
        help="Repository-relative file carrying the explicit approval marker",
    )
    parser.add_argument(
        "--gh",
        default=os.environ.get("GH_BIN", "gh"),
        help="gh executable (a stub may be supplied when network/permissions are unavailable)",
    )
    parser.add_argument("--gh-timeout", type=int, default=20)
    args = parser.parse_args(argv)
    if not args.repository:
        parser.error("--repository is required (or set GITHUB_REPOSITORY)")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    return Gate(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
