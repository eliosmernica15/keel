# Signing hard-fail release gate — evidence

Branch `agent/f-signing`, baseline `8867e73`. Files changed:
`keel/src/keel/release/signing.py`, `publish.py`, `cli.py`,
`.github/workflows/build-desktop.yml`, new `keel/tests/test_signing_gate.py`.

## 1. Exact current (baseline) behavior — confirmed by reading the code

- `keel release build --signing-key` was optional. With no key (the current CI
  state), no `<artifact>.sig` files were written and
  `RELEASE-MANIFEST.json` was left unsigned.
- `keel release publish --dry-run` **always** regenerated an unsigned
  `RELEASE-MANIFEST.json`, wrote `download.json` with
  `available=True, verified=True`, printed `would publish ...` and returned 0.
  It performed no signature check — unsigned output was reported as success.
- Real `keel release publish` performed no signature check at all. It uploaded
  the artifacts, published the GitHub Release, wrote `verified=True` into
  `download.json`, verified only HTTPS/SHA-256, and printed `Published Keel X`.
  Unsigned artifacts were therefore publishable as a production release.
- The CI `verify` step did not pass `--public-key`, so it never checked
  signatures either.
- The local `dry-run` release-controls check only verified the manifest when
  `--public-key` was supplied, silently passed when no manifest existed, and
  contained a latent `NameError` (`scan_secret_markers` used but not imported).
- Result: with 0 configured signing secrets, CI builds were unsigned and a tag
  push could publish them as a production release. Nothing failed closed.

## 2. Gate design implemented

- `signing.py`: added `SigningGateError`, `require_signed_enabled()` (flag or
  `KEEL_REQUIRE_SIGNED` = 1/true/yes/on), and `verify_signed_release(dir,
  public_key_path)`. It returns readable errors (never raises on missing key or
  manifest) for: no public key, unreadable/non-Ed25519 key, missing manifest,
  invalid/absent manifest signature, missing/invalid per-artifact `.sig`, and
  artifact SHA-256 disagreement with the signed manifest.
- `cli.py`: `--require-signed` on `publish` and `dry-run`; `--public-key` on
  `publish`. `dry-run` (the release-controls check) now hard-fails with
  `RELEASE SIGNING GATE FAILED` when gated; the missing-import bug is fixed.
  `main()` reports `SigningGateError` explicitly and exits 1.
- `publish.py`: **real publish is always gated**, even without the flag —
  unsigned artifacts can never be sent. Local `publish --dry-run` stays
  backward-compatible unless gated. The gate runs before any network access;
  the signed incoming manifest is preserved (regeneration would strip the
  signature and alter timestamps); `.sig` assets are staged and uploaded;
  remote release verification receives the public key; the release body says
  "signed" only when the gate passed.
- `build-desktop.yml`: new `verify-release-signatures` job (tag pushes only,
  `needs` the three build jobs) downloads the bundles, stages the public key
  from a secret **outside** the artifact tree, and runs
  `python -m keel.release dry-run --require-signed --public-key ... --artifacts <bundle>`
  for every platform bundle. It publishes nothing and fails when the key or
  any signature is absent. The `publish` job now `needs` that gate and also
  passes `--require-signed --public-key` plus verifies the released
  `RELEASE-MANIFEST.json` with the key. Build jobs sign only when the private
  key secret is configured, so an unconfigured owner fails closed at the gate.
  All existing actions remain SHA-pinned and were re-verified with
  `git ls-remote`; **no new action refs were added** (the gate uses plain shell).

## 3. Tests and results

`keel/tests/test_signing_gate.py` (10 tests, ephemeral Ed25519 keys generated
in-test; no real secrets, no credential output): unsigned manifest + require
-> non-zero and clear error; signed manifest -> proceeds; publish path with
unsigned artifacts -> blocked with no network calls; missing/unreadable public
key -> clear error; env-var activation and backward-compatible unsigned
dry-run; tampered artifact; signed-manifest preservation on publish dry-run;
CLI flag exposure.

Commands (run from `keel/` with `PYTHONPATH=<worktree>/keel/src`, necessary
because an editable install points at the original clone):

- `python -m pytest tests/test_signing_gate.py -q` -> **10 passed**
- `python -m pytest tests/test_signing_gate.py tests/test_release_controls.py
  tests/test_release_integrity.py tests/test_distribution_package.py -q`
  -> **36 passed**

Note: `test_release_integrity.py::test_integrity_cli_on_real_artifacts` and two
`test_distribution_package.py` tests require the gitignored generated
`keel/dist` and `keel/release` directories, which do not exist in a fresh
worktree. They failed with `FileNotFoundError`/missing artifacts before those
directories were temporarily copied in for the final run, and passed (7/7)
with them present. They were removed again afterward; no generated artifacts
were committed. No failures are attributable to this change.

## 4. Owner actions still required (no credentials exist here; none fabricated)

New secrets required for the Ed25519 release-signing gate to ever pass:

1. `KEEL_RELEASE_SIGNING_KEY` — Ed25519 **private** key PEM (PKCS#8), used by
   the build jobs' `--signing-key`. Staged only in `$RUNNER_TEMP`, never in
   logs or artifacts.
2. `KEEL_RELEASE_SIGNING_PUBLIC_KEY` — the matching Ed25519 **public** key PEM
   (SubjectPublicKeyInfo), used by the gate and publish verification.

Existing platform-trust secrets still required (unchanged, reported by
`signing-readiness.yml` and documented in `keel/docs/release/SIGNING-PREPARATION.md`):
`WINDOWS_SIGNING_CERTIFICATE_BASE64`, `WINDOWS_SIGNING_PASSWORD`,
`MACOS_SIGNING_CERTIFICATE_BASE64`, `MACOS_SIGNING_PASSWORD`,
`MACOS_NOTARIZATION_APPLE_ID`, `MACOS_NOTARIZATION_TEAM_ID`,
`MACOS_NOTARIZATION_PASSWORD`, `LINUX_SIGNING_KEY_BASE64`,
`LINUX_SIGNING_PASSWORD`.

Until items 1 and 2 are configured, every tagged release fails the gate and
nothing is published — this is the intended fail-closed behavior. Platform
code-signing/notarization secrets are not yet wired into the packaging jobs;
they remain a separate owner task for OS-level trust (SmartScreen/Gatekeeper).
