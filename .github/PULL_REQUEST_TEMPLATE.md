## Summary

<!-- What changed and why. Reference the relevant plan/evidence document. -->

## Scope

- [ ] No unrelated frontend/site, CLI/TUI, or source changes outside this PR's stated scope.
- [ ] No generated temp/scratch files, no local absolute paths, no secrets or signed binaries committed.
- [ ] Version constants are consistent across `keel/pyproject.toml`, `keel/src/keel/__init__.py`, `keel/desktop/src-tauri/Cargo.toml` (run `cd keel && python scripts/check_version_sync.py`).

## Verification (paste exact commands and results)

- [ ] Relevant pytest suites pass (`cd keel && python -m pytest -q ...`).
- [ ] Hash-pinned dependencies unchanged or regenerated with hashes (`keel/requirements.lock.txt`, `keel/package-lock.json`); no `npm install` in place of `npm ci`.
- [ ] All `.github/workflows/*.yml` parse as YAML; every `uses:` ref is a full 40-hex commit SHA (not a mutable tag/branch).
- [ ] No `pull_request_target` trigger; least-privilege `permissions:` blocks; no untrusted artifact consumed by a privileged job.
- [ ] New/changed evidence claims match observed results (no false green; `unverified`/`blocked` stays reported as such).

## Release authorization (only when this PR enables a release/tag)

Publishing happens on a `v*` tag and is gated by the `release-authorization` job in `build-desktop.yml`, which calls `.github/workflows/release-authorization.yml`. Confirm:

- [ ] Tag is `vMAJOR.MINOR.PATCH` and points at a commit contained in the default branch (`main`).
- [ ] Triggering actor is the allowlisted owner (`eliosmernica15`), not a bot or fork actor.
- [ ] Required evidence files are present and non-empty, including `FINAL-GOVERNANCE-EVIDENCE.md`.
- [ ] Exactly one explicit marker `RELEASE-APPROVED: <tag> by @eliosmernica15` was added to `FINAL-GOVERNANCE-EVIDENCE.md` for **this** tag (outside a fenced code block). Remove or update the stale marker when superseding a release.
- [ ] Signing/publishing remain owner-gated; no OS signing key, API key, or `GITHUB_TOKEN` with `contents: write` is exposed to an untrusted job.

## Governance reality check

- [ ] I understand `.githooks/pre-push` is a **local** compensating control: it is not remote branch protection, is opt-in per clone (`git config core.hooksPath .githooks`), and can be bypassed with `--no-verify`.
- [ ] On this private GitHub Free repository, remote branch protection, required reviews/checks, signature enforcement, and environment approvals are unavailable (live API returned HTTP 403). `CODEOWNERS` and this template record review intent; they do not enforce it. See `FINAL-GOVERNANCE-EVIDENCE.md`.

## Owner sign-off

- [ ] `@eliosmernica15` reviewed and approved this change.
