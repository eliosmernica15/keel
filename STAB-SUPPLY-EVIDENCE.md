# Stabilization evidence — supply chain & release safety

- Worktree: `C:\Users\Admin\.local\share\opencode\worktree\stab\supply`
- Branch: `agent/stab-supply` (no push)
- Baseline HEAD: `f60b080a1c770608e1ddbf3d888a6e63a7c1b6bb` (`git rev-parse HEAD`, unchanged at close)
- Owned files: `.gitleaks.toml`, `keel/requirements.lock.txt`, `keel/requirements-sbom.json`,
  `scripts/check_model_licenses.py`; created `keel/scripts/verify_supply_chain.py` and this file.
- `.github/workflows/` was **read only** (owned by `agent/stab-ci`). No workflow was edited.
- No secret value is reproduced in this document. All scanner reports were produced with `--redact`
  and all historical lines were re-read locally with the matched value masked before classification.

---

## HIGH findings — none

No real/active secret, no malicious or unpinned dependency, no mutable workflow action ref,
and no untrusted-PR artifact path into a privileged job was found. The findings below are
medium/low process gaps and blockers, listed first.

### MEDIUM — CI enforcement gap for the new cross-artifact verifier
`keel/scripts/verify_supply_chain.py` (lock ↔ SBOM ↔ license cross-check) and the hardened
`scripts/check_model_licenses.py` are **not invoked by any of the 8 workflows**.
`offline-license.yml` invokes only `scripts/check_model_licenses.py`, `scripts/verify_v6_audit.py`
and `keel/scripts/build_dependency_graph.py --check`; `python-tests.yml` runs an inline
lock-freshness snippet that checks presence/version/hash but **does not** compare the lock to
the SBOM or validate SBOM license identifiers.
I could not wire this in because `.github/workflows/` is owned by `agent/stab-ci`.
**Requested follow-up:** add a step in `offline-license.yml` (or `python-tests.yml`) running
`python keel/scripts/verify_supply_chain.py` from the repo root area with `working-directory: keel`.
Until then the SBOM/license cross-check is a documented local verification, not a CI-enforced gate.

### MEDIUM — license gate previously accepted unknown licenses for bundled entries
`check_model_licenses.py` only required a non-empty `license` string for bundled entries; an
entry with `license: "UNKNOWN"` (or any unrecognised string) plus `commercial_use_allowed: true`,
`redistribution_allowed: true` and a `verified_date` would have passed. Today all 11 registry
entries are `bundled: false`, so no unknown license is currently accepted for distribution, but
the gate itself was not fail-closed. **Fixed**: bundled licenses must now be in an explicit
reviewed allowlist, and any UNKNOWN/VARIES/NOT-APPLICABLE entry is surfaced by name and must stay
unbundled with no usage rights granted. Negative tests below confirm fail-closed behavior.

### LOW — artifact integrity checks could not be executed locally
No built release artifacts exist in this worktree (`keel/release`, `keel/dist`, `.build` absent),
so `keel.release integrity` / `verify` could not be run against real installers. The workflow
gates and the implementing code were inspected instead (see §4).

---

## 1. Full-history secret scan

### Tool acquisition (gitleaks was NOT on PATH)
```
$ Get-Command gitleaks -ErrorAction SilentlyContinue   # -> "NOT FOUND on PATH"
$ python -m pip show gitleaks                          # -> WARNING: Package(s) not found
```
The `secret-scan.yml` workflow pins `GITLEAKS_VERSION=8.30.1` and
`GITLEAKS_SHA256=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb`.
The GitHub release API confirms that digest belongs to `gitleaks_8.30.1_linux_x64.tar.gz`
(`sha256:551f6fc8...`), so the CI pin is correct. Because this host is Windows, the Windows x64
asset of the same pinned release was downloaded and verified locally:
```
downloaded_sha256=d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e
expected_sha256=d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e
SHA MATCH - extracting
```
`gitleaks version` -> `8.30.1`.

### Commands and outputs
```
gitleaks.exe detect --no-banner --redact --config .gitleaks.toml \
  --report-format json --report-path <tmp>\gitleaks-report.json .
```
Initial (pre-fix) run:
```
INF 625 commits scanned.
INF scanned ~84467515 bytes (84.47 MB) in 29.5s
WRN leaks found: 36
EXITCODE=1
```
Re-run after adding the exact allowlists below:
```
INF 626 commits scanned.
INF scanned ~84486805 bytes (84.49 MB) in 42.9s
INF no leaks found
EXITCODE=0  findings=0
```
Note: the scanned-commit count is reported by gitleaks as 625 on the first pass and 626 on the
re-pass; `git rev-list --count HEAD` remained 328 and HEAD was unchanged. This is a gitleaks
traversal-count detail, not a history change.

### Classification of the 36 initial findings
Every finding's exact historical line was re-read with the matched value masked. A second
programmatic check tested all 36 values for placeholder shape (`fixture|test|example|dummy|
abcdef|12345|secret|plaintext|sk-|AKIAABCDE`, or ≤8 distinct characters); 33 matched
placeholder shapes and the 3 remaining ones were verified by context:
`artifacts.js` uses the value only as `window.localStorage.getItem/setItem(STORAGE_KEY)` key name,
and `AUDIT-MODULES-B.md:187` is a mock webhook payload with `url: https://example.com/hook`.

| Commit(s) | Path | Rule | Findings | Classification |
|---|---|---|---|---|
| 0454836f, 64722bd3 | `keel/site/ui/artifacts.js` | generic-api-key | 2 | False positive — localStorage key identifier, not a credential |
| d4b0288c | `AUDIT-SECURITY.md` | jwt | 2 | False positive — captured example JWT in a redaction-bug audit note |
| cbdfc28d, e6e7efc5, 5fc5b985 | `keel/tests/test_composition_contracts.py` | aws-access-token | 3 | Synthetic fixture — `AKIAABCDEFGHIJKLMNOP` placeholder |
| cbdfc28d, e6e7efc5, d32dc16a | `keel/tests/test_config_contracts.py` | generic-api-key | 3 | Synthetic fixture — generated `config/secrets.env` test data |
| b11cdf84, cbdfc28d, e6e7efc5 | `keel/tests/test_w1_security_backend.py` | generic-api-key | 3 | Synthetic fixture — redaction test string with `alice@example.com` |
| b33ae3f8, cbdfc28d, e6e7efc5 | `keel/tests/test_w4_backend.py` | jwt | 3 | Synthetic fixture — example JWT `…sub=1234567890…abcdefghij` |
| 244e0710, b33ae3f8, cbdfc28d, e6e7efc5, f29dbeb7 | `keel/tests/test_z_backend.py` | generic-api-key | 9 | Synthetic fixture — `sk-abcdefghijklmnop` / redaction test tokens |
| 7a5cd22e | `keel/tests/verify_local_provider_credentials.py` | generic-api-key | 3 | Synthetic fixture — functions explicitly docstringed `FIXTURE`, `_accept_fixture_key` |
| 840cd5d6 | `keel/tests/test_secret_storage.py` | generic-api-key | 2 | Synthetic fixture — local plaintext-key migration test |
| 902f8718 | `keel/tests/test_redaction.py` | generic-api-key | 1 | Synthetic fixture — known-format redaction test |
| 13799853 | `keel/tests/test_release_no_secrets.py` | generic-api-key | 1 | Synthetic fixture — credential-shape detector test |
| 12020801 | `AUDIT-MODULES-B.md` | generic-api-key | 1 | Synthetic fixture — mock webhook `signing_secret` in audit doc |
| d4b0288c | `probes/probe_redaction.py` | jwt + generic-api-key | 2 | Synthetic fixture — probe inputs `Bearer …abcdefghij`, `api_key: …` |
| d4b0288c | `probes/probe_reach_and_dispatch.py` | generic-api-key | 1 | Synthetic fixture — probe input string |

Totals: **0 real secrets; 32 synthetic-fixture findings (14 groups), 4 false positives (2 groups).**
**No owner rotation is required** for any finding.

### Allowlist policy applied
16 `[[allowlists]]` blocks were added to `.gitleaks.toml`, each with
`condition = "AND"`, one `targetRules` entry, an exact anchored path regex, and an exact
full commit SHA (or list of exact SHAs). No directory-wide, rule-wide, commit-wide or
repo-wide allowlist was added, and no secret value is stored in the config.

---

## 2. Lockfile / SBOM / license verification

### Required pins
`pyproject.toml` declares project deps `tzdata`, `cryptography`, `keyring`, `Pillow`;
build-system requires `setuptools`; plus mandatory `pip`, `pytest`, `pyinstaller` = 8 required pins.

CI-equivalent snippet from `python-tests.yml`, run verbatim from `keel/`:
```
LOCK FRESHNESS OK: 34 pinned packages, 8 required pins checked
```
All 34 lock entries are `==<exact version>` with at least one `--hash=sha256:<64 hex>`;
no range specifier, wildcard, or hashless entry exists.

### Authoritative hash verification (PyPI JSON API)
For all 34 package/version pairs, every pinned hash was checked against
`https://pypi.org/pypi/<name>/<version>/json` `urls[].digests.sha256`:
```
packages_checked= 34 hash_sets_verified_against_pypi= 34 hash_mismatches= 0 errors= 0
```

### Cross-artifact verifier
Created `keel/scripts/verify_supply_chain.py`; output of `python scripts/verify_supply_chain.py`:
```
lock: 34 entries, 8 required pins checked (cryptography, keyring, pillow, pip, pyinstaller, pytest, setuptools, tzdata)
sbom: 34 packages matched against lock (version, SHA-256 set, marker, source, license)
  gate: license registry: 11 entries, 0 bundled
  gate: unbundled entries with UNKNOWN license (informational, blocked from bundling): piper-tts, kokoro-voices, whisper-weights, whisper-cpp-engine, diarization-models, ffmpeg-build, silero-vad, elevenlabs, ollama-local-models, openai-compatible-local-models
  gate: LICENSE GATE OK
SUPPLY CHAIN VERIFICATION OK
EXITCODE=0
```
It validates package set, exact version, SHA-256 **set**, marker, PyPI source URL and license for
every package, then invokes the real model/voice license gate. Unknown/unlisted licenses fail closed.

### License gate hardening and negative tests
```
$ python scripts/check_model_licenses.py
license registry: 11 entries, 0 bundled
unbundled entries with UNKNOWN license (informational, blocked from bundling): piper-tts,
  kokoro-voices, whisper-weights, whisper-cpp-engine, diarization-models, ffmpeg-build,
  silero-vad, elevenlabs, ollama-local-models, openai-compatible-local-models
LICENSE GATE OK
EXITCODE=0

bundled+UNKNOWN:        rc=1 | - bundled but license is unknown/unreviewed; - unknown license but usage rights granted
bundled+unlisted license: rc=1 | - bundled license not in reviewed allowlist: UnreviewedLicense-9.9
bundled+MIT control:    rc=0
```
The 10 UNKNOWN/VARIES/NOT-APPLICABLE entries are all `bundled: false`,
`commercial_use_allowed: false`, `redistribution_allowed: false` — explicitly surfaced and blocked
from bundling, not silently accepted.

---

## 3. Workflow action pinning, token permissions, untrusted artifacts

### Third-party `uses:` refs — count built from the files, not hardcoded
```
workflow_files= 8
uses_lines_total= 31
distinct_action_ref_pairs= 5
OK  actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 count=12 files=6
OK  actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333 count=2 files=1
OK  actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 count=4 files=2
OK  actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 count=10 files=4
OK  actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 count=3 files=1
non_sha_refs= 0
```
All 31 refs are full 40-hex SHAs (no tag/branch refs, no local actions). Upstream resolution via
`git ls-remote --tags` confirmed every pinned SHA exists and points at the claimed major tag:
```
actions/checkout        -> refs/tags/v7, refs/tags/v7.0.1
actions/setup-python    -> refs/tags/v7, refs/tags/v7.1.0
actions/setup-node      -> refs/tags/v7, refs/tags/v7.1.0
actions/upload-artifact -> refs/tags/v7, refs/tags/v7.0.2
actions/download-artifact -> refs/tags/v8, refs/tags/v8.0.2
```

### Token permissions (extracted from all 8 workflow files)
| Workflow | Permissions |
|---|---|
| `build-desktop.yml` | top `contents: read`; signing gate `contents: read`; **publish `contents: write`** |
| `lifecycle.yml` | `contents: read, actions: read` (`gh run download` needs actions:read) |
| `offline-license.yml` | `contents: read` |
| `provider-validation.yml` | `contents: read` |
| `python-tests.yml` | `contents: read` |
| `secret-scan.yml` | `contents: read` |
| `signing-readiness.yml` | `contents: read` |
| `verify-install.yml` | `contents: read, actions: read` |

The only write scope is the `publish` job, which is gated by
`if: startsWith(github.ref, 'refs/tags/v')` and depends on `verify-release-signatures`.

### Untrusted PR artifacts
- No `pull_request_target` trigger exists in any workflow (triggers are `push`, `pull_request`,
  `workflow_dispatch`, and one `workflow_run`).
- `verify-install.yml` (the only `workflow_run` consumer, with `contents: read, actions: read`)
  places a fail-closed `trust-gate` before every install/package job
  (`needs: trust-gate` at lines 64, 124, 147). The gate blocks the run unless
  `conclusion == success`, `source_event == push`, `source_repo == this repo` and
  `source_branch == default branch`; `workflow_dispatch` is an explicit operator action.
- `lifecycle.yml` is `workflow_dispatch` only; its `gh run download`/`gh release download` steps
  use an operator-supplied `run_id` and published release assets.
- `build-desktop.yml` build jobs run on PRs, but the write-capable `publish` job is tag-only, and
  `actions/download-artifact` without a `run-id` reads only the current run's artifacts.
**Result: no untrusted PR artifact reaches a privileged job.**

---

## 4. Build artifact integrity / provenance and version sync

Workflow-level gates inspected in `build-desktop.yml` (not edited):
- `validate-versions` runs `keel/scripts/check_version_sync.py` before any build job.
- Windows/macOS/Linux builds use `npm ci` (lockfile integrity) plus an explicit check that the
  installed `electron-builder` version equals `package-lock.json`'s pinned version;
  `npm_config_offline=true` prevents registry resolution during packaging.
- Signing key is staged outside the artifact tree; `verify-release-signatures` fails closed when
  the owner public key is absent and runs `keel.release dry-run --require-signed` on every bundle.
- `publish` re-checks `--require-signed`, then `keel.release verify` checks the manifest and all
  detached signatures, re-downloads the published `download.json` over HTTPS and compares it.
- `python-tests.yml` regenerates artifacts and runs the suite; `offline-license.yml` runs the
  license gate; `secret-scan.yml` scans all history with the checksum-pinned gitleaks binary.

Implementation confirmed in `keel/src/keel/release/signing.py` (Ed25519 keypair load, canonical
manifest signing/verification, `verify_signed_release` checking manifest signatures, each artifact
signature and `sha256`), `release/verify.py` (download + SHA-256 comparison, loopback/HTTP guard)
and `release_integrity.py` (SHA256SUMS, manifest hashes, detected signature paths, secret scan).

### Version sync — executed
```
$ cd keel && python scripts/check_version_sync.py
OK - all sources agree on version 0.1.1 (tag v0.1.1)
EXITCODE=0

$ python scripts/check_version_sync.py --tag v0.1.1
OK - all sources agree on version 0.1.1 (tag v0.1.1)
EXITCODE=0

$ python scripts/check_version_sync.py --tag v9.9.9     # negative control
VERSION MISMATCH
  git tag  9.9.9   (all 7 file sources remain 0.1.1)
EXITCODE=1
```
Seven sources are compared: `pyproject.toml`, `desktop-app/package.json`,
`desktop-app/package-lock.json`, `site/download.json` (version + `tag == v<version>`),
`desktop/src-tauri/tauri.conf.json`, `desktop/src-tauri/Cargo.toml`, `src/keel/__init__.py`.

---

## Changes committed on `agent/stab-supply`
- `.gitleaks.toml` — 16 narrow per-commit/per-path/per-rule allowlists from the classification above.
- `scripts/check_model_licenses.py` — fail-closed license validation plus explicit UNKNOWN reporting.
- `keel/scripts/verify_supply_chain.py` — new lock/SBOM/license verifier.
- `STAB-SUPPLY-EVIDENCE.md` — this file.
- `keel/requirements.lock.txt` and `keel/requirements-sbom.json`: verified unchanged (no edit needed).
- No workflow, frontend, or push.
