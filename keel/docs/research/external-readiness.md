# External integration & signing readiness (honest status)

**Baseline:** `origin/main` @ `c662acb5f7f76be878d6b679f10b8231f2b77a6c`
**Assessed:** 2026-11-23
**Branch:** `agent/external-readiness`

This records what was actually verified against external systems on this
machine. No account was created, no service purchased, no chargeable call made,
no certificate fabricated, and no unit test or locally generated QR/PIN is
presented as a real external success.

## Summary

| Area | Status | Why |
| --- | --- | --- |
| 1. Provider (live request) | **BLOCKED** | No runtime provider credential in env or `~/.keel/settings.json`; deterministic fixture validation passes, no real call issued |
| 2. Phone (device pairing) | **BLOCKED** | No device/emulator and no adb / simctl / idevice tooling; only local allowlist + QR/PIN material exists |
| 3. Signing (trusted release) | **BLOCKED** | All signing secrets absent; no signing jobs exist. Missing-secret *detection* works and never prints values |

---

## 1. Provider integration

### Registered providers actually executable by the runtime

`keel/src/keel/providers/registry.py::_PROVIDERS` registers **5** runtime
adapters. The 324 entries in `keel/resources/catalog/providers.json` are
informational only — the resolver explicitly rejects catalog-only providers
(`resolve_provider_model`).

| Provider | Credential env var (name only) | Default model | Note |
| --- | --- | --- | --- |
| `openrouter` | `KEEL_OPENROUTER_API_KEY` | `openrouter/auto` | default auto-chain member |
| `google` | `KEEL_GOOGLE_API_KEY` | `gemini-2.0-flash` | default auto-chain member |
| `nvidia` | `KEEL_NVIDIA_API_KEY` | `meta/llama-3.1-8b-instruct` | default auto-chain member |
| `anthropic` | `KEEL_ANTHROPIC_API_KEY` | `claude-sonnet-4-5` | **opt-in only**, never a default |
| `openai-compatible` | `KEEL_COMPAT_API_KEY` | *(explicit)* | additionally needs `KEEL_COMPAT_BASE_URL` and `KEEL_COMPAT_MODEL` |

### Credential storage inspected

- Env vars above (shell / CI secret injection).
- `~/.keel/settings.json` (or `$KEEL_STATE_DIR/settings.json`), section
  `providerKeys`. `settings_store.py` applies saved keys into the process env
  at import via `apply_stored_keys()`; values are AES-256-GCM encrypted by
  `secret_store.py`, with the master key from the OS keyring, else
  `KEEL_MASTER_PASSPHRASE`, else a local `master.key` file.
- `settings_store.public_view()` / `stored_key_hint()` expose only a last-4
  hint and metadata, never the value. `provider_validation.py` reports only
  `configured` names and env-var names.

### Observed state (names only — no values read or printed)

- All of `KEEL_OPENROUTER_API_KEY`, `KEEL_GOOGLE_API_KEY`,
  `KEEL_NVIDIA_API_KEY`, `KEEL_ANTHROPIC_API_KEY`, `KEEL_COMPAT_API_KEY`,
  `KEEL_COMPAT_BASE_URL`, `KEEL_COMPAT_MODEL`, `KEEL_MASTER_PASSPHRASE`, plus
  generic `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY`: **unset**.
- `C:\Users\Admin\.keel\settings.json` exists; `providerKeys` is **empty**.

### Deterministic validation (PASS — local, no network)

```
python -m pytest -q tests/test_provider_validation_ready.py \
  tests/test_provider_validation.py tests/test_pairing.py \
  tests/test_release_signing.py tests/test_release_no_secrets.py \
  tests/test_secret_storage.py
=> 25 passed
```

`run_validation(live=True)` in this environment returned:

```
configured: []
providers: anthropic, google, nvidia, openai-compatible, openrouter
every live_provider check = SKIP
  ("live validation requires --live and a configured credential")
```

The mock-adapter fixture exercise (`test_mock_adapter_live_matrix`) proves the
live matrix *would* record a PASS for a real response, but that is a fixture,
not an external success.

### Real request

**Not performed — BLOCKED.** There is no usable credential, so issuing a
request would be unauthenticated and could not verify auth.

**Exact missing dependency (any one is sufficient):**
`KEEL_OPENROUTER_API_KEY`, `KEEL_GOOGLE_API_KEY`, `KEEL_NVIDIA_API_KEY`, or
`KEEL_ANTHROPIC_API_KEY` set in the environment / GitHub secret; for a generic
endpoint, `KEEL_COMPAT_API_KEY` **plus** `KEEL_COMPAT_BASE_URL` and
`KEEL_COMPAT_MODEL`; or a key saved to `~/.keel/settings.json` under
`providerKeys`. Use a free-tier/rate-limited key where possible — no
chargeable call was made here.

### Workflow added

`.github/workflows/provider-validation.yml`:
1. always runs the deterministic fixture suite (no network, no credentials);
2. reports credential **presence** only (`CONFIGURED` / `MISSING`, by name);
3. issues exactly **one** minimal non-destructive request
   (`python -m keel provider smoke <provider>` → "Reply with exactly the word:
   pong", 16 output tokens) only when a fully configured credential exists;
4. redacts every known secret value from captured stdout/stderr before
   printing; skips cleanly (exit 0, `SKIP`) when no secret is configured.

---

## 2. Phone / device integration

### What exists in code (not a real pairing)

- `keel/src/keel/pairing.py` — a local JSON allowlist (`pairings.json`) with
  `pair()` / `is_paired()` / `revoke()`. Tests cover only this store logic.
- `keel/src/keel/platform_gaps.py::companion_identity()` — generates a
  self-signed certificate, a SHA-256 DER pin and a `keel://pair?...&token=...&pin=...`
  URI; optional OpenCV renders a QR matrix. `CompanionApprovals` records a
  local `approve()` flag.
- These are *inputs* to a pairing flow. There is no phone client, no TLS
  listener/bridge, no certificate-pin verification at runtime, and no
  authenticated round-trip, approval or revocation over the wire.

### Tooling / device detection (this machine)

| Check | Result |
| --- | --- |
| `adb` | NOT FOUND |
| `xcrun` / `simctl` | NOT FOUND |
| `idevice_id` / `ios-deploy` | NOT FOUND |
| Android SDK (`ANDROID_HOME`, `ANDROID_SDK_ROOT`, `~/AppData/Local/Android/Sdk`) | absent |
| Xcode (`~/Library/Developer/Xcode`) | absent |
| USB PnP scan for Android / iPhone / iPad devices | none (only a BIOS driver matched the loose string filter) |
| `java`, `node` | present (not device tooling) |

### Real tests performed

**None — BLOCKED.** QR generation, PIN creation and unit tests are explicitly
not counted as real pairing.

**Exact missing dependencies:**
- Android: a physical device or emulator **and** `adb` on `PATH` (Android SDK
  platform-tools), plus a companion app that verifies the pinned certificate
  and holds the bridge token.
- iOS: macOS with Xcode and `xcrun simctl` (or a physical device with
  `idevice_id`/`ios-deploy`), plus the same companion app.
- In both cases, a reachable Keel companion bridge so that pairing → pinned
  TLS authentication → approval → revoke → reconnect can be exercised over
  the network.

---

## 3. Signing readiness

### Documentation and current workflows inspected

- `keel/docs/release/SIGNING-PREPARATION.md` lists the exact secrets and
  verification commands for Windows Authenticode, macOS Developer ID +
  notarization, and Linux provenance/integrity.
- `.github/workflows/signing-readiness.yml` checks 8 secret names with
  `[ -n "$value" ]` and prints only `CONFIGURED` / `MISSING`. It never echoes
  a value. **Missing-secret detection: PASS.**
- `.github/workflows/build-desktop.yml` builds Windows/macOS/Linux installers
  and verifies/publishes artifacts by SHA-256 manifest, but contains **no
  signing step** and no signed-output claim. No certificate or key was
  generated here.

### Missing-secret detection (PASS)

The readiness workflow's `check()` reports presence by name only. In this
environment every signing secret is unset (`WINDOWS_SIGNING_*`,
`MACOS_SIGNING_*`, `MACOS_NOTARIZATION_*`, `LINUX_SIGNING_*` all unset), and
`run_validation`-style checks never print values. Deterministic signing tests
(`test_release_signing.py`, ephemeral Ed25519 keys only) pass: 25-test run
above included them.

*Gap noted, not fixed (file ownership):* `signing-readiness.yml` checks
`LINUX_SIGNING_KEY_BASE64` but omits `LINUX_SIGNING_PASSWORD`, which
`SIGNING-PREPARATION.md` lists as required. Adding that one `check` line is
recommended to the workflow owner.

### Platform paths (prepared, not executed)

| Platform | Missing external dependency (exact name) | Verification required |
| --- | --- | --- |
| Windows Authenticode | GitHub secret `WINDOWS_SIGNING_CERTIFICATE_BASE64` (base64 PFX) **and** `WINDOWS_SIGNING_PASSWORD`; public RFC 3161 timestamp server | `signtool verify /pa /v <installer>` |
| macOS Developer ID + notarization | `MACOS_SIGNING_CERTIFICATE_BASE64` (base64 p12), `MACOS_SIGNING_PASSWORD`, `MACOS_NOTARIZATION_APPLE_ID`, `MACOS_NOTARIZATION_TEAM_ID`, `MACOS_NOTARIZATION_PASSWORD` (app-specific) | `codesign --verify --deep --strict`, `spctl -a -vv`, `xcrun stapler validate` |
| Linux provenance | No platform-wide identity; required evidence is committed SHA-256 manifest, release manifest and signed release tag. Optional key: `LINUX_SIGNING_KEY_BASE64` with `LINUX_SIGNING_PASSWORD` | manifest/checksum verification; signature verification if a key is configured |

No release in this state may be described as signed; signing jobs must be
skipped (not failed) when secrets are absent and the summary must say
`unsigned`, per `SIGNING-PREPARATION.md`.

**Actual signing: BLOCKED** — every secret above is absent and no signing job
exists in CI. Nothing was fabricated.

---

## Evidence commands (all non-destructive, no values printed)

1. `git checkout -b agent/external-readiness origin/main` (baseline confirmed
   `c662acb...`).
2. Python env-presence probe printing only `SET` / `unset` per variable name.
3. `settings.json` probe printing only `providerKeys` names (empty list).
4. `shutil.which` probe for adb/xcrun/simctl/idevice_id/etc.; PnP device scan.
5. `python -m pytest -q ...` (25 passed).
6. `python -c "from keel.provider_validation import run_validation; ..."`
   → `configured: []`, all live checks `SKIP`.

## Files changed on this branch

- `keel/docs/research/external-readiness.md` (new — this document)
- `.github/workflows/provider-validation.yml` (new)

No existing workflow or source file was modified.
