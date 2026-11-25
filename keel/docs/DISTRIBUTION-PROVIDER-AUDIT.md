# Distribution provider / first-run integration audit (Agent D, 2026-11-25)

**Scope:** providers, first-run onboarding, native packaging and browser/PWA
surfaces in the worktree `C:\Users\Admin\Desktop\keel-frontend-worktree\keel`
(branch `feat/frontend-completion-2026-11-24`).

**Ownership used:** only two new test files and this document. No provider
source, generated file, other agent's file, commit or push was made. No real
provider credential was requested, generated, stored or committed; all
verification keys below are synthetic `sk-fixture-…` values.

---

## 1. Provider configuration, masking, validation, catalog, status

| Area | Finding | Evidence |
|---|---|---|
| Registry | Five providers only: `openrouter`, `google`, `nvidia`, `anthropic`, `openai-compatible`. Auto chain excludes Anthropic (opt-in). No baked key, no new provider from distribution. | `verify_distribution_provider_hardening.py::test_provider_registry_is_unchanged_and_has_no_baked_credentials` |
| Key precedence | Shell env wins; an explicitly saved key from `~/.keel/settings.json` is the fallback and is only applied when the shell did not provide one. | `settings_store.apply_stored_keys()`, `registry._key_for()`; prior `verify_local_provider_credentials.py` suite |
| Validation | Credential call performs an authenticated probe before anything is stored (OpenRouter `/auth/key`; other providers use their credential-gated models endpoint). A public `/models` response alone cannot validate. Key length is bounded to 1–512 characters; all four mutations require the bridge token. | `fleet/session_keys.py::_verify_request`, `fleet/routes.py:625-732` |
| Masking | Save returns only a 4-character hint (`key[-4:]`). `public_view()` and `export_view()` omit secret material. Stored keys are AES-256-GCM (`enc: aes256gcm-v1`) in the owner-only settings file. | `test_save_returns_only_a_hint_and_encrypts_at_rest`, `test_export_and_public_view_never_include_secret_values` |
| Clear / remove | Session clear forgets only a process-set session key; a shell key is never touched. Remove deletes the stored entry and leaves env untouched; repeated calls report `not_session_key` / `not_saved` explicitly. | `test_clear_and_remove_are_scope_limited` |
| Catalog | Offline catalog works with no key and provably makes no network call (`source:"offline"`, `catalog_version`, `model_count`). Live catalog requires a key and reports `key_source` (`session` or `env:…`) plus `models_meta`. | `test_onboarding_offline_catalog_makes_no_network_call`; prior `verify_local_provider_catalog_and_turns.py` |
| Connection status | `GET /api/fleet/providers` returns `configured`, `key_source`, `key_hint`, `session` and `session_keys`; with no key it honestly reports "not configured" and never returns a key. | `test_provider_status_is_honest_and_unmasked_without_keys` |

**Merge result:** the merge `c80c2e1` did not change `src/keel/providers/**`,
`settings_store.py`, `secret_store.py`, `config_schema.py`, `provider_catalog.py`
or `fleet/session_keys.py`. The only provider-adjacent runtime diff in the
distribution range was in `fleet/routes.py`, and it *strengthens* workspace
trust: untrusted projects now get `403 workspace_not_trusted` before tree
listing, review, file read, terminal execution or file write. No permission was
weakened.

## 2. Onboarding after the merge

The shipped wizard uses the real bridge client; it adds no local provider
shortcut. The exact payloads built by `Onboarding.tsx` were exercised against
the real HTTP bridge with a fixture probe:

- `bridge.catalog({ name, source: "offline" })` → offline browsing is labelled
  "not a connection test";
- `bridge.setCredential({ name, key })` → `{ok, models, model_count,
  models_meta, key_source:"session", note}`; the key is held in bridge-process
  memory only and is never returned;
- `bridge.saveProvider({ name, key })` → separate, optional encrypted save with
  only a 4-character hint;
- failed verification returns `ok:false` with a safe category/detail and does
  not mark the provider done or expose the "Save on this device" control;
- `bridge.addProject({ path })` registers an untrusted folder; trust requires a
  separate `bridge.trustProject(id, true)` call. A file read before that call
  returns `403 workspace_not_trusted`.

The provider input is `type="password"`, `autoComplete="off"`,
`spellCheck={false}`; the secret is cleared from React state on leaving the step
and after a successful save. No `localStorage` call exists in `Onboarding.tsx`;
`progress.ts` persists only `keel-onboarding:step`,
`keel-onboarding:checklist` and `keel-mode`.

The Next.js BFF forwards through `/api/bridge/*`, injects
`x-keel-token` server-side from `KEEL_BRIDGE_TOKEN`, and deletes `cookie`,
`origin`, `referer`, `host` and `connection` headers before forwarding.

## 3. Native installation / distribution changes

- `desktop-app/main.js` bundles and prefers the full local `desktop/ui`; the
  restricted `site` mirror is reachable only through explicit
  `KEEL_UI_PROFILE=mirror` or `KEEL_UI_DIR`. No provider variable is written,
  no settings file is created, no project is trusted and no permission mode is
  changed by the Electron shell. Its only key-related read is the update
  signature public-key path.
- The window open handler allows loopback `http(s)` in the shell, sends other
  `http(s)` links to the OS browser, and denies other schemes; the sidecar URL
  is parsed and validated as loopback with a token before use.
- `desktop/sw.js` (`keel-shell-v6`) caches only the app shell (`/`, UI assets,
  manifest, icons). `/api/*` is network-only; no installer binary or release
  manifest is cached.

## 4. PWA / browser constraints

- **Full application** (`fleet-next` + `desktop/ui`): no provider key or bridge
  token is written to `localStorage`. Browser storage holds UI preferences,
  drafts and onboarding progress only. `desktop/ui` keeps the local bridge
  token in `sessionStorage` (ephemeral), not `localStorage`.
- **Public mirror** (`site/app.html` + `site/ui/app.js`) is explicitly labelled
  `PUBLIC MIRROR · NO BACKEND`. It has no `/api/fleet/` calls and no
  `providers/credential`, `providers/save`, `providers/remove`, `projects/`,
  `bots/` or `terminal/exec` routes, so it cannot invoke desktop-only bridge
  APIs. Its `keel_mirror_settings_v1` localStorage entry contains *user-entered*
  keys for direct browser-to-provider calls only; these are not privileged
  bridge/desktop keys and cannot authenticate to the local runtime. This is a
  pre-existing, documented browser-only product, not a distribution addition.

## 5. Test evidence (exact output)

Command (from `keel/`, with the worktree `src` explicitly on `PYTHONPATH` —
without it Python imports `keel` from `C:\Users\Admin\Desktop\Claude clone\keel`):

```powershell
$env:PYTHONPATH = 'src'
python -m pytest tests/verify_distribution_provider_onboarding.py `
                 tests/verify_distribution_provider_hardening.py -q
```

```
.................                                                        [100%]
17 passed in 12.14s
```

Regression against the previously shipped provider suites in the same
worktree and environment:

```powershell
$env:PYTHONPATH = 'src'
python -m pytest tests/verify_local_provider_credentials.py `
                 tests/verify_local_provider_catalog_and_turns.py `
                 tests/verify_local_provider_echo_integration.py `
                 tests/test_fleet_credentials.py -q
```

```
...........................................                              [100%]
43 passed in 33.22s
```

Environment: Python 3.11.9, pytest 9.0.2. New files:
`tests/verify_distribution_provider_onboarding.py`,
`tests/verify_distribution_provider_hardening.py`. No existing test was changed.

## 6. The one externally gated, credential-dependent check

**Check (NOT VERIFIED here, by design):** one real live model round-trip with
the operator's own genuine key — `ProviderModelClient.complete()` over real
HTTPS to a provider, asserting non-empty assistant text and the real usage
numbers returned by that provider's model. No external-provider credential is
available in this environment, and fabricating one would violate `AGENTS.md`
("Never fabricate evidence"). No code change is needed; only the operator's
credential is missing.

Everything around it is verified locally: authenticated probe → validation →
session/saved storage → 4-character masking → clear/remove (§1); offline and
live catalog payload shapes with a fixture probe (§1–2); adapter SSE parsing,
tool calls and usage with fake transports; the honest no-credential state; and
a complete real local Echo turn with every provider env var asserted absent
(`verify_local_provider_echo_integration.py`).

### Exact secure local setup steps (operator-supplied key; do not send it here)

Use a dedicated, least-privilege key created in your own provider console.
Never paste it into chat, a transcript, an issue/PR, a commit, a test file or a
tool argument. Rotate it immediately if it is ever pasted somewhere unintended.

1. Start the local bridge. It binds `127.0.0.1` and requires the Keel token for
   every mutation.
2. **Session-only (recommended first try):** open Settings → Credentials (or
   the onboarding provider step), choose the provider, paste the key into the
   *password* field, then click **Verify for this session**
   (`POST /api/fleet/providers/credential`). The bridge performs the
   authenticated probe and holds the key in this process environment only;
   nothing is written to disk and restarting the bridge forgets it. Confirm
   "Session key active", then load the live catalog. Finish with **Forget
   session key** (`POST providers/credential/clear`).
3. **Saved on this machine (optional):** after step 2, click **Save on this
   device** (`POST /api/fleet/providers/save`). The same authenticated probe
   runs first; the key is then encrypted with AES-256-GCM into
   `~/.keel/settings.json` with owner-only permissions and a rolling backup.
   The response contains only a four-character hint. Remove it later with
   **Remove saved key** (`POST providers/remove`).
4. **Shell environment only (alternative):** set
   `KEEL_OPENROUTER_API_KEY`, `KEEL_GOOGLE_API_KEY`, `KEEL_NVIDIA_API_KEY`,
   `KEEL_ANTHROPIC_API_KEY` or `KEEL_COMPAT_API_KEY` in your shell before
   starting the bridge. Keel reads it into memory; it is not copied into Keel
   settings and cannot be removed from the UI. Anthropic is opt-in, never a
   default.
5. Create/edit an agent with engine `provider`, set its `model`, run one turn,
   and confirm the assistant text and usage numbers returned by the provider.
   That closes the gate; no source change is required.

## 7. Limitations / observations

- The Playwright onboarding specs under `fleet-next/tests/features/onboarding/`
  were not executed in this round; their route and payload contract is
  asserted here against the real Python bridge, and those spec files were not
  modified.
- `registry.smoke()` reports `key_source: env:<var>` even when the key was
  resolved from the encrypted settings store. This is a pre-existing CLI
  reporting nuance, not introduced by distribution, so no provider source was
  changed in this audit; the HTTP `providers` and `catalog` routes report the
  source correctly (`settings.json` / `session` / `env:…`).
- Other agents are editing the shared worktree concurrently (release and
  security files). This audit did not touch those files.
