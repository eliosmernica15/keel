# Final signing evidence — Keel release pipeline

Branch: `agent/final-signing2` · base HEAD `35fb2b8` · worktree
`C:\Users\Admin\.local\share\opencode\worktree\final\signing2`

## Classification

| Item | Status |
| --- | --- |
| Ed25519 release signing / verification mechanics (test mode, synthetic ephemeral keys) | **VERIFIED** |
| Manifest binding, checksum binding, expiry, rotation, fail-closed gates | **VERIFIED** |
| Honest CLI status for unsigned artifacts | **VERIFIED** |
| Trusted Windows Authenticode / macOS Developer ID + notarization distribution | **PENDING — owner credentials, CI secret names and platform verifiers required** |

No self-signed, ephemeral or test key is presented as a trusted distribution
identity anywhere in the code, CLI output or tests.

## Implemented interface

All code lives in `keel/src/keel/release/signing.py`, `verify.py`, `publish.py`
and `cli.py`; backward-compatible primitives used by `build.py` and
`updater.py` are preserved.

* **Provider-agnostic key loading.** `SecretRef(name, source)` resolves an
  environment-variable name, config key or CI secret *name* to a PEM **file
  path**. Raw PEM values (on a CLI argument or in an env/config value) are
  refused with clear diagnostics that never echo the key bytes.
  Prefixes `env:`, `config:`, `ci:` are also accepted. CI secrets must be
  materialized as files by the runner (`<SECRET>_FILE` or config mapping).
* **Signature generation / verification.** `sign_bytes`, `verify_bytes`,
  `sign_manifest` (legacy), `sign_release_manifest` (v2 envelope),
  `verify_manifest`, `verify_manifest_detailed`. The v2 envelope binds
  `signature_key_id`, `signature_mode`, `signature_signed_at`,
  `signature_expires_at` and `signature_envelope` into the signed payload, so
  rotation and expiry metadata cannot be swapped without invalidating the
  signature.
* **Manifest binding and checksum verification.** `verify_signed_release`
  verifies the manifest signature, each detached artifact `.sig`, every
  manifest SHA-256 against the actual file, and an optional
  `RELEASE-SHA256SUMS.txt` against the signed manifest. Unsafe artifact names
  (path traversal, symlinks) are rejected.
* **Key rotation.** `KeyRing` holds current + previous trusted public keys;
  manifests with `signature_key_id` are verified only against the matching
  key, legacy manifests are tried against all keys. Cutover to a ring without
  the old key rejects old-signed manifests.
* **Explicit modes.** `SigningMode.DEV` (no verification performed, unsigned
  reported honestly), `TEST` (synthetic Ed25519 allowed, never platform
  trust), `DISTRIBUTION` (fails closed without owner identity configuration
  and registered native platform verifiers). Mode is chosen with `--mode` or
  `KEEL_SIGNING_MODE`. `register_platform_verifier()` is the injection point
  for owner/CI tooling (`signtool verify /pa`, `codesign --verify --strict`
  plus notarization staple validation); none is bundled, so distribution
  always fails closed until the owner supplies one.
* **Fail-closed gates.** Missing key, missing/invalid/expired/mismatched
  signature, tampered manifest/artifacts/checksums, wrong key and unsigned
  artifacts produce non-zero exits with `RELEASE SIGNING GATE FAILED` or an
  explicit unsigned status. Real `publish` remains always-gated; local
  dry-runs are backward compatible.

## Exact verification commands and output

Clean HOME (PowerShell), with the worktree source pinned:

```powershell
$env:HOME = 'C:\Users\Admin\AppData\Local\Temp\opencode\clean-home-verify'
$env:USERPROFILE = $env:HOME
New-Item -ItemType Directory -Force -Path $env:HOME | Out-Null
$env:PYTHONPATH = 'C:\Users\Admin\.local\share\opencode\worktree\final\signing2\keel\src'
python -m pytest keel/tests/test_final_signing.py keel/tests/test_signing_gate.py `
  keel/tests/test_release_integrity.py keel/tests/test_release_manager.py `
  keel/tests/test_updater.py -q
```

Actual output:

```text
.................................................                        [100%]
49 passed in 27.45s
```

New tests (18 cases in `keel/tests/test_final_signing.py`) cover: explicit
mode resolution; name-only key references and rejection of raw key values;
detached and manifest round-trips; tampered payload/metadata/envelope;
missing, invalid, expired and future-dated signatures; wrong key; missing key
file; missing/malformed checksum fields; tampered artifacts, manifests and
checksum files; path traversal; unsigned bundles; key-ring rotation and
cutover; distribution-mode fail-closed; registered platform verifier failure;
CLI `signing-status`, `dry-run`, `verify` and `publish --dry-run` honesty.

Full-suite context (same clean HOME, `python -m pytest keel/tests -q`):

```text
2 failed, 4625 passed, 54 skipped, 3707 subtests passed in 1164.36s (0:19:24)
```

The two failures were timing-sensitive async approval tests unrelated to
signing (`test_compat_runtime.py::test_tool_requires_approval_then_approved_runs`
and `test_fleet_delegation.py::test_circular_delegation_refused`). Re-running
exactly those two tests in isolation in a clean HOME produced `2 passed in
4.00s`, confirming they are full-suite flakiness and not a signing regression.

### CLI evidence (ephemeral keys generated in a temp directory)

A throwaway harness (kept outside the repository) stages the standard Keel
artifact set with synthetic Ed25519 keys and invokes the real CLI entry
point. `<TMP>` is a fresh temp directory; no private key bytes are printed.

```text
$ python -m keel.release signing-status --artifacts <TMP>\stage
{
  "mode": "dev",
  "status": "unsigned",
  "verified": false,
  "key_reference": null,
  "key_id": null,
  "trusted_distribution": false,
  "errors": [
    "dev mode: no signature verification performed"
  ]
}
exit: 0

$ python -m keel.release signing-status --artifacts <TMP>\stage --public-key <TMP>\keys\ephemeral-test.pub.pem --mode test
{
  "mode": "test",
  "status": "test-verified",
  "verified": true,
  "key_reference": "...\keys\ephemeral-test.pub.pem",
  "key_id": "ephemeral-test-key",
  "trusted_distribution": false,
  "errors": []
}
exit: 0

$ python -m keel.release dry-run --artifacts <TMP>\stage --dist <TMP>\empty-dist --mode distribution --public-key <TMP>\keys\ephemeral-test.pub.pem
ERROR: trusted distribution pending: missing KEEL_WINDOWS_SIGNING_IDENTITY (Windows Authenticode signing identity (EV/OV certificate))
ERROR: trusted distribution pending: missing KEEL_MACOS_SIGNING_IDENTITY (macOS Developer ID Application signing identity)
ERROR: trusted distribution pending: missing KEEL_MACOS_NOTARY_PROFILE (macOS notarytool credential profile for notarization)
ERROR: trusted distribution pending: missing KEEL_SIGNING_TRUSTED_KEYS (owner-controlled trusted Ed25519 public key path(s), including previous keys for rotation)
ERROR: windows: no trusted platform signature verifier registered; trusted distribution pending
ERROR: macos: no trusted platform signature verifier registered; trusted distribution pending
RELEASE SIGNING GATE FAILED - refusing to claim trusted distribution
exit: 1
```

`verify` reports `Signature status: UNSIGNED / NOT VERIFIED (no --public-key
supplied)` for unsigned manifests and only says `Ed25519 signature VERIFIED
(test-release integrity only; not trusted Windows/macOS platform signing)`
when an owner-supplied public key is present. `publish --dry-run` in `test`
mode prints `Signing status: TEST Ed25519 signatures verified (release
integrity only; not trusted platform signing)`.

## Exact owner requirements before trusted distribution can be claimed

These are **owner-supplied**; this task never generates, commits, prints or
substitutes them. Configuration carries only *names/paths*, never secret
values.

| Requirement | Owner action / CI secret name | Verification hook |
| --- | --- | --- |
| Release Ed25519 key (manifest + artifact integrity) | Generate key outside this repo. Store private key in CI secret `KEEL_RELEASE_ED25519_PRIVATE_KEY`; materialize it to a runner-local PEM file and pass its path via `KEEL_SIGNING_KEY_FILE` or `SecretRef(name, "ci")`. Never commit the PEM. Pin the current **and previous** public keys via `KEEL_SIGNING_TRUSTED_KEYS` (comma-separated file paths) with matching `KEEL_SIGNING_KEY_ID` values for rotation. | Existing `verify_signed_release` / `KeyRing` checks. |
| Windows trusted signing | Obtain an EV (preferred, for SmartScreen reputation) or OV Authenticode code-signing certificate. Put its thumbprint/subject in CI secret whose **name** is exposed as `KEEL_WINDOWS_SIGNING_IDENTITY`. Sign every `.exe` in the owner's CI with `signtool sign /sha1 <thumbprint> /fd SHA256 /tr <RFC3161 timestamp URL> ...` and verify with `signtool verify /pa`. | Register a Windows verifier via `register_platform_verifier("windows", fn)` that runs `signtool verify /pa` on each installer and returns `(bool, detail)`. |
| macOS trusted signing + notarization | Enroll in the Apple Developer Program; obtain a **Developer ID Application** certificate (not a self-signed/ad-hoc cert). Import it into the runner keychain from CI secret `KEEL_MACOS_CERT_P12`; expose the identity name via `KEEL_MACOS_SIGNING_IDENTITY`. Sign with `codesign --force --deep --sign "Developer ID Application: <Owner> (TEAMID)" --options runtime --timestamp`. Notarize with `xcrun notarytool submit --keychain-profile <profile> --wait` using CI secret `KEEL_MACOS_NOTARY_API_KEY`; expose the profile name via `KEEL_MACOS_NOTARY_PROFILE`. Staple with `xcrun stapler staple` and validate with `spctl -a -vvv -t install`. | Register a macOS verifier via `register_platform_verifier("macos", fn)` that runs `codesign --verify --strict` and staple/notarization validation and returns `(bool, detail)`. |
| Mode | Set `KEEL_SIGNING_MODE=distribution` (or pass `--mode distribution`) only in the owner's signed CI job after the above are configured. | Until then distribution mode exits non-zero with `trusted distribution pending`. |

## Blocker status

* **Not blocked:** Ed25519 test signing, manifest/checksum binding, rotation,
  expiry, fail-closed gates and honest CLI status reporting are
  implemented and verified above.
* **Blocked on owner:** trusted distribution. No code-signing certificate,
  Developer ID identity, notary profile or native platform verifier was
  supplied in this environment, so a real Windows/macOS platform signature
  cannot be produced or attested here. The pipeline correctly refuses to
  claim it (`trusted_distribution: false`, non-zero exit in distribution
  mode). This is an explicit, documented pending item, not a silent failure.
