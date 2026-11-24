# Master Plan v6 — Remaining Work Closure (verification evidence)

Agent 21 (verification). Baseline SHA: `321bc7a55f2f306365a0f2ee26441fef345e8f41`.
Worktree: `agent/registry-verify`. This file is the only artifact produced; the
registry, parity file, and matrix files were not modified.

## Feature registry integrity

Scope: verify the prior audit's 228-ID registry is intact and that no files
needed changing. All commands below were run from the worktree root.

### 1. Consistency script

Command:

```
python scripts/verify_v6_audit.py
```

Exact output:

```
evidence files: 8 present: 8
registry count: 228 matrix rows: 228
parity identical: True
tier counts: {'operational': 52, 'local_module': 168, 'external_dependency': 3, 'descriptor': 3, 'owner_gated': 2}
verified: 220
flagged: ['B4.8', 'B6.2', 'B6.3', 'B6.5', 'B6.6', 'C11.1', 'C11.2', 'C11.8']
CONSISTENCY OK
```

Note on the "verified: 220" line: the script counts the matrix field
`implementation_verified == True` (220 true, 8 false). This is distinct from the
registry `status` field checked in step 2 (226 `verified`, 2 `blocked`). Both
counts are internally consistent and expected; neither indicates a regression.

### 2. Deep equality, count, tiers, statuses

Verified with a Python one-liner loading `PLAN-INDEX.json`, `parity.json`, and
`master-plan-v6-final-matrix.json`:

- `PLAN-INDEX.json == parity.json` (deep equality): **True**
- Feature counts: index **228**, parity **228**, matrix **228**
- `implementation_tier` counts (index) and `tier` counts (matrix) both:
  `operational 52, local_module 168, external_dependency 3, descriptor 3, owner_gated 2`
- `status` counts: index **226 verified / 2 blocked**; matrix **226 verified / 2 blocked** (exact match to requirements)

### 3. Special-case seams

Inspected all eight non-`implementation_verified` IDs in both the index and the matrix:

- **B6.2, B6.3, B6.5** — tier `descriptor`, `implementation_verified=False`, notes `dormant_owner_directed`. The final report lists them as `DORMANT — owner_directed` and explicitly states `active: False` — i.e. inactive dormant seams. Confirmed.
- **B4.8, B6.6, C11.8** — tier `external_dependency`, status `verified`, `implementation_verified=False`, notes `external_validation_pending`. Confirmed.
- **C11.1, C11.2** — tier `owner_gated`, status `blocked`, `owner_approval_required=True`, notes `source_file_missing, test_file_missing, owner_blocked`, with empty source/test references. Confirmed.

No drift from the expected classification.

### 4. Source/test path resolution

Resolved every path token in `master-plan-v6-final-matrix.json` against the worktree
root (matrix paths carry a leading `keel\` segment):

- `source_files`: **226** tokens checked, **0 missing**
- `test_references`: **260** tokens checked, **0 missing**

Also verified:

- CSV matrix vs JSON matrix: **0 field mismatches** across `source_files`,
  `test_references`, `tier`, `status`, `implementation_verified`,
  `owner_approval_required`.
- Registry (`PLAN-INDEX.json`) paths, tokenized on whitespace and resolved against
  both `keel/` and the worktree root: **486** tokens checked, **0 missing**.

The only empty source/test references are the two owner-gated blocked rows
(C11.1, C11.2), which is intentional and documented in their notes.

### Conclusion

No regression or inconsistency was found. The 228-ID registry, its deep-equality
parity file, tier distribution, status distribution, dormant/external/owner-gated
classifications, and all referenced source/test paths are intact and consistent.

**No registry change is needed.** No files were modified other than this evidence
file.
## Provider integration

Agent 10 (provider integration readiness) ΓÇö read-only audit of the authorized
environment at baseline `321bc7a55f2f306365a0f2ee26441fef345e8f41`.
No secret values are recorded in this document.

### 1. Exact secret names required

Registered runtime providers (`keel/src/keel/providers/registry.py:24-65`,
`_PROVIDERS`), with the exact credential environment variable each consumes:

| Provider | Credential env var | Optional model/base-URL env vars | Notes |
| --- | --- | --- | --- |
| `openrouter` | `KEEL_OPENROUTER_API_KEY` | `KEEL_OPENROUTER_MODEL` | Default chain member; OpenAI-compatible adapter. |
| `nvidia` | `KEEL_NVIDIA_API_KEY` | `KEEL_NVIDIA_MODEL` | Default chain member; OpenAI-compatible adapter. |
| `google` | `KEEL_GOOGLE_API_KEY` | `KEEL_GOOGLE_MODEL` | Default chain member; native Gemini adapter (`x-goog-api-key`). |
| `anthropic` | `KEEL_ANTHROPIC_API_KEY` | `KEEL_ANTHROPIC_MODEL` | **Opt-in only** (`registry.py:4-5`, `registry.py:107`); native adapter (`x-api-key`). Never a default. |
| `openai-compatible` | `KEEL_COMPAT_API_KEY` | `KEEL_COMPAT_BASE_URL`, `KEEL_COMPAT_MODEL` | Default chain member; also requires base URL and model to be usable (`registry.py:125-127`). |

Credential resolution order (`registry.py:72-79`): the environment variable wins;
otherwise the value explicitly saved in Keel's encrypted settings store is used
(`settings_store.stored_key`, `keel/src/keel/settings_store.py:115-122`).
`settings_store.apply_stored_keys()` runs at registry import (`registry.py:67`)
and copies stored keys into the process environment for names not already set
(`settings_store.py:175-204`). Shell-provided keys are never overwritten.

### 2. Credential state in this environment (values never printed)

Direct environment check (SET / NOT SET / non-empty length only):

| Env var | State |
| --- | --- |
| `KEEL_OPENROUTER_API_KEY` | NOT SET |
| `KEEL_GOOGLE_API_KEY` | NOT SET |
| `KEEL_NVIDIA_API_KEY` | NOT SET |
| `KEEL_ANTHROPIC_API_KEY` | NOT SET |
| `KEEL_COMPAT_API_KEY` | NOT SET |

Effective check inside a Python process after importing the registry (so that
both the shell environment and the encrypted settings-store fallback are
included): `configured_providers()` returned `[]`, and `list_providers()`
reported `configured=False`, `key_source=None` for all five providers.
Therefore **no non-empty credential is available in the authorized environment**.

### 3. Live call ΓÇö none made

Because no credential is available, **no live provider request was attempted**
(no model listing, no completion, no auth probe). No chargeable or quota-using
call occurred. Result: N/A ΓÇö deliberately not executed.

### 4. Source scan for stored credentials

A scan for high-signal secret prefixes (`sk-`, `AIza`, `nvapi-`, `gsk_`) and
`api_key = "..."` literals found **no credential stored in source files**.
All matches were documentation examples, synthetic redaction fixtures, or
false positives from identifiers containing `task-`. Representative file:line
locations only (no values):

- `keel/tests/test_live_smoke.py:7` ΓÇö docstring example only.
- `keel/tests/test_live_smoke.py:65` ΓÇö deliberately invalid key fixture.
- `keel/src/keel/red_team.py:42`, `keel/src/keel/red_team.py:43` ΓÇö redaction test input.
- `keel/tests/test_redaction.py:14`, `:16`, `:27`, `:36`, `:57`, `:66`, `:109` ΓÇö synthetic fixtures.
- `keel/tests/test_secret_storage.py:32`, `:56`, `:59`, `:63` ΓÇö synthetic storage fixtures.
- `keel/tests/test_fleet_credentials.py:93`, `:99`, `:111`, `:166` ΓÇö credential-resolution fixtures.
- `keel/desktop/fleet/fleet.js` (e.g. `:801`, `:863-868`, `:949-950`, `:960-976`) ΓÇö `sk-` inside `task-*` UI identifiers.
- Numerous copies under `agent-reference-shots/` and `.verify-*` docs ΓÇö captured documentation examples, not Keel secrets.

No literal `api_key = "..."` assignment was found in `keel/src/**/*.py`.
Adapters take the key at construction time and read it from `cap.env_var`
(`keel/src/keel/providers/anthropic.py:19-30`,
`gemini.py:19-29`, `openai_compatible.py:44-56`).

### 5. Fixtures vs. live calls ΓÇö confirmed

- `keel/tests/test_live_smoke.py` is explicitly opt-in. `_live_enabled()`
  (`:30-31`) checks the real env var; both live tests call `pytest.skip()` when
  it is absent (`:36-37`, `:62-63`). It hits real endpoints only with real keys.
- `keel/tests/test_provider_validation.py` uses `RecordingAdapter` with
  deterministic canned events and `*.invalid` base URLs (`:22-59`); it never
  uses or invents real credentials.
- `keel/tests/test_provider_validation_ready.py:12-30` asserts that with no
  credentials the validation doc has `configured == []` and every
  `live_provider` check is `SKIP`; `:32-58` exercises the live matrix with an
  injected mock adapter only.
- Empirical confirmation (cache disabled):

  `PYTHONPATH=keel/src python -m pytest keel/tests/test_live_smoke.py keel/tests/test_provider_validation.py keel/tests/test_provider_validation_ready.py -q -rs -p no:cacheprovider`
  ΓåÆ `10 passed, 10 skipped` ΓÇö all 10 skips from `test_live_smoke.py` for the five
  missing key env vars; no live call executed.

### 6. Live-validation workflow (for the credential owner)

The validation path is real and honest: it never reports provider success
without a real call (`keel/src/keel/provider_validation.py:106-132`).
Note: the existing live check is a minimal **streaming completion** (prompt
`Reply with exactly: keel-ok` in `provider_validation.py:76-83`), not a
`models/list` endpoint. A smaller single-shot probe also exists at
`keel/src/keel/providers/registry.py:153-183` (`keel provider smoke`, 16 max
output tokens).

Steps, in order:

1. Configure credentials using the secure secret mechanism (Section 7).
2. Confirm presence **without values**: `keel provider list`. It reports only
   `configured`, `key_source` (`env:<VAR>` or `settings.json`) and a masked hint
   (`keel/src/keel/providers/registry.py:88-110`); it does not print keys.
3. Run the offline matrix: `keel provider validate`. Expect `live_provider`
   checks to be `SKIP` (no `--live`).
4. Run live validation: `keel provider validate --live`
   (`keel/src/keel/cli/main.py:1142-1148`). With a credential, the corresponding
   provider's checks become `PASS`/`FAIL` instead of `SKIP`; the result object
   includes `configured`, `live` and a `note` that success requires a real call.
5. Equivalent capability: `core.providers.validate` with `{"live": true}`
   (`keel/src/keel/capability_registry.py:154-158`).
6. Optional tiny live probe: `keel provider smoke <name> [--model MODEL]`
   (`keel/src/keel/cli/main.py:1149-1160`, `registry.py:153-183`).
7. Live pytest suite (dedicated, key-enabled job only):
   `KEEL_<PROVIDER>_API_KEY=... python -m pytest keel/tests/test_live_smoke.py -q`.
   It skips automatically when the key is absent, so CI without keys is safe.

### 7. Owner action to configure credentials (secure mechanism)

Owner must set the exact variable names in Section 1 through the organization's
secret manager ΓÇö **never paste a secret into chat, a ticket, a plan document, or
any git-tracked file**:

- CI/CD: define them as masked repository/environment secrets (e.g. GitHub
  Actions secrets/variables or the equivalent in your CI) and expose only to
  the single job that runs `keel provider validate --live` / the live pytest
  suite. Do not echo them in logs; do not pass them as ordinary command-line
  arguments.
- Local runtime: inject them from the OS keychain / enterprise secret store
  (or a local, git-ignored environment file loaded by the shell) into the
  process environment before launching Keel.
- Keel-native alternative: save each key through Settings ΓåÆ Providers (i.e.
  `settings_store.save_provider_key`, `keel/src/keel/settings_store.py:145-156`),
  which encrypts the value via `secret_store.encrypt_secret` into
  `~/.keel/settings.json` (written with mode `0600`, `settings_store.py:72-81`)
  and applies it to the process env via `apply_stored_keys`. Keep
  `~/.keel/settings.json` and its `.bak` outside version control.

Use a dedicated, low-quota test key for validation. `anthropic` remains opt-in
and must not be added to the default chain. `openai-compatible` additionally
needs `KEEL_COMPAT_BASE_URL` and `KEEL_COMPAT_MODEL`. After configuration,
re-run Steps 2ΓÇô4 above and confirm `configured` lists the intended providers.
## Supply chain and build

Audited worktree: `C:\Users\Admin\.local\share\opencode\worktree\completion\supply-chain`
Branch: `agent/supply-chain` ┬╖ Baseline/final audited commit: `321bc7a55f2f306365a0f2ee26441fef345e8f41` ("Master Plan v6 final audit evidence set (lead verification)", 2026-11-23 09:58:43 +0100 = 2026-11-23T08:58:43Z).
This is a read-only audit; workflows were inspected but not modified, nothing was pushed.

### 1. Version consistency (exact values)

The canonical version gate is `keel/scripts/check_version_sync.py` (six sources) and `keel/src/keel/release/common.py::VERSION_FILES` (the same six). All six agree on **0.1.1**:

| Source | Value |
|---|---|
| `keel/pyproject.toml` `[project].version` | `0.1.1` |
| `keel/desktop-app/package.json` `version` | `0.1.1` |
| `keel/desktop-app/package-lock.json` root `version` (and packages[""]) | `0.1.1` |
| `keel/site/download.json` `version` / `tag` | `0.1.1` / `v0.1.1` |
| `keel/desktop/src-tauri/tauri.conf.json` `version` | `0.1.1` |
| `keel/src/keel/__init__.py` `__version__` | `0.1.1` |

Installer naming is consistent with that version: `package.json` ΓåÆ `build.win.artifactName = "Keel-Setup-${version}.${ext}"`, and `site/download.json` ΓåÆ `Keel-Setup-0.1.1.exe` (macOS/Linux names also `0.1.1`). `release_feed.py` publishes `VERSIONS = ("0.1.1", "0.1.0")` with `0.1.1` dated 2026-11-21 as the latest ΓÇö consistent.

Package-manifest/version-constant mismatches that the six-source gate does **not** catch:

- **`keel/desktop/src-tauri/Cargo.toml` line 3: `version = "0.1.0"`** while `tauri.conf.json` is `0.1.1`. This is a real package-manifest mismatch; neither `check_version_sync.py` nor `VERSION_FILES` includes `Cargo.toml`, so the CI version gate passes despite it.
- `keel/src/keel/release/__init__.py` line 18: `__version__ = "0.1.0"` (sub-package constant; top-level `keel.__version__` is `0.1.1`).
- `keel/src/keel/mcp.py` lines 172 and 511: MCP `clientInfo.version = "0.1.0a0"` (stale literal).
- `keel/fleet-next/package.json` / `package-lock.json`: `0.1.0`. This is the separate Next.js web app, not a release-version source; reported for completeness, not counted as a defect.
- Test data in `test_release_hardening.py` / `test_updater.py` deliberately uses `0.1.2` to exercise upgrade logic; not a mismatch.

### 2. Artifact and manifest availability in the audited commit

The following paths named in the audit task are **not present** in the worktree and **not tracked at commit `321bc7a`** (they are build outputs excluded by `keel/.gitignore`: `dist/`, `build/`, `/release/`):

- `keel/dist/` (including `Keel-Setup-0.1.1.exe` and `latest.yml`)
- `keel/release/RELEASE-MANIFEST.json`, `keel/release/RELEASE-SHA256SUMS.txt`
- Any `DEPENDENCY-LICENSES.json`. At the audited commit the generator `keel/src/keel/release/licenses.py::licenses_command` wrote `<--out>/DEPENDENCY-LICENSES.json` (CI uses `--out release`, i.e. `keel/release/DEPENDENCY-LICENSES.json`), while the consumer `keel/src/keel/commercial_seams.py` read `keel/resources/release/DEPENDENCY-LICENSES.json`. Neither directory/file exists in this commit. **Resolved below:** both sides now share the canonical `keel/release/DEPENDENCY-LICENSES.json` path.

This is by design: `build-desktop.yml` generates these at build time via `python -m keel.release build ...` and `python -m keel.release licenses --out release`. The committed `keel/site/download.json` is an honest fallback (`"generated": "fallback"`, all channels `available: false`, `size`/`sha256`/`url`: `null`, note "Not publicly hosted yet; there is nothing to download"), so **no installer checksum is recorded anywhere in the committed repository**.

### 3. Checksum results (local artifact, outside the audited commit)

The parent working copy (`C:\Users\Admin\Desktop\Claude clone`) does contain uncommitted, gitignored build outputs. Read-only inspection of that copy:

- `keel/dist/Keel-Setup-0.1.1.exe` ΓÇö 141,052,399 bytes; mtime 2026-11-22 18:59:13 local = **2026-11-22T17:59:13Z**.
- Computed SHA-256: **`CC455DE10C4471D6EE5E9D42B23C3CAC21B3DB59C62F17DB9DCA2E6BB6C3657A`**
  (`cc455de10c4471d6ee5e9d42b23c3cac21b3db59c62f17db9dca2e6bb6c3657a` lowercase).
- Recorded checksums in that same working copy:
  - `keel/release/RELEASE-SHA256SUMS.txt`: `cc455de10c4471d6ee5e9d42b23c3cac21b3db59c62f17db9dca2e6bb6c3657a  Keel-Setup-0.1.1.exe` ΓÇö **MATCH** (case-insensitive).
  - `keel/release/RELEASE-MANIFEST.json`: `"bytes": 141052399`, `"sha256": "CC455DE10C4471D6EE5E9D42B23C3CAC21B3DB59C62F17DB9DCA2E6BB6C3657A"` ΓÇö **MATCH**.
  - `keel/dist/latest.yml`: `size: 141052399`, `sha512: yFbUNnDDTdz46ueIkme1RD+Y+NRbUnJi97j6Oa3M/IZxvzhig2c2csDXRd4iiw9AWOV4C70YFM5cQq9SDU0UTA==`, `releaseDate: '2026-11-22T17:59:52Z'` ΓÇö independently recomputed SHA-256/SHA-512 and size **MATCH** (sha512 base64 identical to the yml, so the previously reported stale-`latest.yml` defect is not present in this copy).
- Provenance/timing: the installer's mtime (2026-11-22T17:59:13Z) is ~14 h 59 m **earlier** than the audited HEAD commit (2026-11-23T08:58:43Z). It therefore **predates** the audited source commit and is not derived from it. `master-plan-v6-final-report.md` line 55 likewise states the `keel/dist` artifacts "predate the audited HEAD; rebuild from `cadb343` not performed" (that report audited a different SHA, `cadb343`).

**Conclusion:** the installer **must be rebuilt from the final commit** before any release/verification claim. The existing 0.1.1 installer is internally consistent with its own (uncommitted) manifests, but it cannot be attested as a build of `321bc7a` (or of any final commit), and no committed checksum exists to compare against. Verification must use a fresh CI build plus the release pipeline's generated `RELEASE-SHA256SUMS.txt` / `RELEASE-MANIFEST.json` / `download.json`.

### 4. Repository hygiene configuration

Both files exist at the worktree root and are non-trivial:

- `.gitleaks.toml` ΓÇö 3,551 bytes, `useDefault = true` plus **11** `[[allowlists]]` blocks; each is tightly scoped with `condition = "AND"`, `targetRules = ["generic-api-key"]`, exactly one `commits` SHA and one exact `paths` regex (reviewed historical captures/demo strings). No global allowlist, no secret values recorded.
- `.pre-commit-config.yaml` ΓÇö 315 bytes, gitleaks hook pinned to `rev: v8.30.1` with `args: ["--redact", "--config", ".gitleaks.toml"]`.
- Supporting check `keel/scripts/check_repo_hygiene.py` verifies both files plus `.editorconfig`, `CHANGELOG.md`, `patches/README.md`, `pyproject.toml` and the `[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]` sections.

Workflows were read only: `build-desktop.yml` pins action majors (`actions/checkout@v7`, `setup-python@v7`, `setup-node@v7`, `upload-artifact@v7`, `download-artifact@v8`) and `secret-scan.yml` pins a `GITLEAKS_SHA256` ΓÇö agent 03 owns workflow SHA pinning; no workflow changes made here.

### 5. Locally achievable defects identified (not implemented)

All are independent of workflow SHA pinning:

1. **`Cargo.toml` version drift (primary finding):** set `keel/desktop/src-tauri/Cargo.toml` package version to `0.1.1` and add `Cargo.toml` to `check_version_sync.py` + `keel/release/common.py::VERSION_FILES` (and the version-sync test) so future bumps cannot silently miss it.
2. **Hard-coded installer filename:** `keel/scripts/validate_desktop.py` line 41 hard-codes `Keel-Setup-0.1.1.exe`; after the next version bump the local validation script will report `installer_present: FAIL` even for a correct build. Derive the name from `version`/manifest as `common.py` does.
3. **Stale secondary version constants:** `keel/src/keel/release/__init__.py::__version__ = "0.1.0"` and `keel/src/keel/mcp.py` `clientInfo.version = "0.1.0a0"`; derive from `keel.__version__` or bump them to avoid contradictory self-reports.

No files other than this evidence file were changed; no workflows edited; no push performed.

## Version and supply-chain fixes

Implemented on branch `agent/version-consistency` (baseline `691c4cd`). Canonical
release version remains `0.1.1`; no version bump was performed.

**Files changed**

- `keel/desktop/src-tauri/Cargo.toml` — package version `0.1.0` -> `0.1.1`.
- `keel/scripts/check_version_sync.py` — added `Cargo.toml` `[package].version`
  as a gated source (now seven sources) and documented it in the module docstring.
- `keel/src/keel/release/common.py` — added
  `desktop/src-tauri/Cargo.toml` to `VERSION_FILES` and `load_versions()`, so
  both the CLI gate and `validate_version()` reject Cargo drift; added the
  shared `LICENSE_INVENTORY = PROJECT_ROOT / "release" / "DEPENDENCY-LICENSES.json"`.
- `keel/src/keel/release/__init__.py` — sub-package `__version__` `0.1.0` ->
  `0.1.1`.
- `keel/src/keel/mcp.py` — both stdio and HTTP `clientInfo.version` literals
  `0.1.0a0` replaced with the imported canonical `keel.__version__`
  (`from . import __version__`), so future bumps propagate automatically.
- `keel/src/keel/release/licenses.py` — `licenses --out release` now writes via
  the shared `LICENSE_INVENTORY` constant; explicit non-default `--out` paths
  are still honored.
- `keel/src/keel/commercial_seams.py` — `sbom_export()` now reads the shared
  `LICENSE_INVENTORY` path; the two stale fallback paths were removed. No license
  data is fabricated when the generated inventory is absent (returns count 0).
- `keel/scripts/validate_desktop.py` — installer name now comes from
  `installer_name(read_version())`, where `read_version()` is
  `keel.release.common.read_version()` (pyproject.toml); the upgrade-description
  command also uses that version. For `0.1.1` all output is byte-for-byte
  unchanged.
- Tests: extended `keel/tests/test_version_sync.py` (all gated strings agree,
  gate passes and fails when Cargo.toml is bumped in a copied tree, secondary
  constant), `keel/tests/test_mcp.py` (both transports' `clientInfo.version`),
  `keel/tests/test_validation_script.py` (installer name derived from a mocked
  future version), `keel/tests/test_commercial_seams.py` (generator/consumer
  share the canonical path), `keel/tests/test_enterprise_seams.py` (autouse
  fixture writes a real inventory into `tmp_path` via `write_inventory()`, so
  compliance tests do not depend on gitignored build output).
- This document: corrected the historical path note and added this section.

**Commands and exact results** (run from `keel/`; `PYTHONPATH` was set to this
worktree's `keel/src` for pytest so imports cannot resolve to the sibling
working copy):

```
$ python scripts/check_version_sync.py
OK - all sources agree on version 0.1.1 (tag v0.1.1)

$ python scripts/check_version_sync.py --tag v0.1.1
OK - all sources agree on version 0.1.1 (tag v0.1.1)

$ python -m pytest tests/test_version_sync.py tests/test_mcp.py tests/test_validation_script.py tests/test_commercial_seams.py tests/test_enterprise_seams.py -q
25 passed in 5.98s
```

A broader release-related run produced `3 failed, 42 passed in 8.25s`; all three
failures are pre-existing environment dependencies on gitignored build outputs
absent from a fresh worktree, not regressions:
`tests/test_release_integrity.py::test_integrity_cli_on_real_artifacts`
(`RELEASE-SHA256SUMS.txt`, `RELEASE-MANIFEST.json`, `latest.yml`, sidecar and
inventory missing), and `tests/test_distribution_package.py::test_release_manifest_has_policy_fields`
/ `::test_checksums_file_matches_manifest_artifacts` (missing `keel/release/`
files).

**Deliberately not changed**

- `keel/fleet-next/package.json` / `package-lock.json` (`0.1.0`) — separate
  private Next.js web app, not a release-version source or a gated manifest.
- `keel/src/keel/events.py` default `claude_code_version="keel/0.1.0a0"` —
  outside the five confirmed defects; a telemetry/compat default, not a
  product version gate.
- Workflow files, sandbox code and the feature registry — owned by other agents.
- No `DEPENDENCY-LICENSES.json` content was fabricated or committed; the file
  remains a build-time output.

