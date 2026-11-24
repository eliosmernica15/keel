# Provider / integration verification — local, no credentials

**Round:** Keel full-plan completion, Agent D (providers / integrations).
**Date:** 2026-11-24.
**Status:** all feasible local requirements closed; exactly one check remains
externally gated (§6).

Everything in this document was executed against the **worktree** at
`C:\Users\Admin\Desktop\keel-frontend-worktree\keel`. No provider key, no
network call to a provider, and no credential of any kind was used.

---

## 0. How to reproduce (important: PYTHONPATH caveat)

The editable install of `keel-harness` in this environment points at a
*different* checkout (`C:\Users\Admin\Desktop\Claude clone\keel`), not at the
worktree. `conftest.py` imports `keel` before any test module, so a plain
`python -m pytest` would silently exercise the other source tree. Set
`PYTHONPATH` to the worktree `src` explicitly:

```powershell
$env:PYTHONPATH = "C:\Users\Admin\Desktop\keel-frontend-worktree\keel\src"
cd "C:\Users\Admin\Desktop\keel-frontend-worktree\keel"
python -m pytest tests/verify_local_provider_credentials.py `
                 tests/verify_local_provider_catalog_and_turns.py `
                 tests/verify_local_provider_echo_integration.py -q
```

Verified import after setting it:

```
using: C:\Users\Admin\Desktop\keel-frontend-worktree\keel\src\keel\providers\registry.py
```

New files owned by this round:

- `tests/verify_local_provider_credentials.py`
- `tests/verify_local_provider_catalog_and_turns.py`
- `tests/verify_local_provider_echo_integration.py`

No provider source, generated file, git state or existing test was modified.

---

## 1. Fixture-based credential lifecycle (requirement 1)

**Label: FIXTURE.** The real HTTP bridge, `settings_store`, `secret_store`
encryption and the real route dispatch run unmodified. Only the authenticated
provider probe (`session_keys._http_json`) is replaced with a deterministic
fixture router; the synthetic bearer value `sk-fixture-…` is never a real key.
`conftest.py`'s global `settings_store.load` stub is overridden inside the
fixture with a real file-backed reader so on-disk assertions are genuine.

| Check | Verified behaviour | Evidence test |
|---|---|---|
| Secure entry | Password field, `autoComplete=off`, `spellCheck=false`, never prefilled; value cleared after every submit attempt | UI source read in `test_ui_source_reads_fixture_and_live_markers`; `ProvidersSettings.tsx:454-462,395-397` |
| Validation | Authenticated probe runs before anything is stored; public `/models` alone cannot validate a key | `test_fixture_entry_validation_creates_session_key`, `test_fixture_invalid_key_is_rejected_before_any_storage` |
| Session key | Held only in bridge-process env; reported as `session: true`, `key_source: session`; never written to disk | `test_fixture_entry_validation_creates_session_key`, `test_fixture_session_key_is_never_written_to_disk` |
| Saved key | AES-256-GCM (`enc: aes256gcm-v1`) at rest in `~/.keel/settings.json`, 0600 + rolling backup; decryptable by the registry | `test_fixture_saved_key_is_encrypted_at_rest_and_masked`, `test_fixture_saved_key_round_trips_through_decryption` |
| Session vs saved | Session = memory only, lost on restart; saved = encrypted local file; shell env always wins | `test_fixture_shell_env_takes_precedence_over_saved_key` |
| Masking | Only a 4-character hint is returned (`key[-4:]`); full key absent from **every** credential response, success or failure | `test_fixture_full_key_absent_from_every_credential_response`; UI renders `••••<hint>` at `ProvidersSettings.tsx:389,451` |
| Clear | `providers/credential/clear` forgets only a process-set session key; a shell-owned key is never touched; second clear is an explicit `not_session_key` | `test_fixture_clear_session_key_is_scope_limited`, `test_fixture_clear_never_touches_env_owned_key` |
| Remove | `providers/remove` deletes the stored entry; shell env untouched; second remove is an explicit `not_saved` | `test_fixture_remove_saved_key_is_scope_limited` |
| Auth | All four credential mutations return 403 without the bridge token | `test_fixture_credentials_require_bridge_token` |

---

## 2. Catalog, per-agent models, errors, cancellation, fixture-vs-live (requirement 2)

**Label: FIXTURE.** Same isolation model; the adapter transport is a scripted
fake, and the provider probe is a fixture router.

| Check | Verified behaviour | Evidence test |
|---|---|---|
| Live catalog | With a validated key, returns `models`, `models_meta` (context length, reasoning efforts) and `key_source` (`session` or `env:…`); no `source:"offline"` | `test_fixture_live_catalog_reports_key_source`, `test_fixture_live_catalog_after_session_key_uses_session_source` |
| Offline catalog | `source:"offline"` + `catalog_version`, works with no key, and provably makes **no** network call | `test_fixture_offline_catalog_needs_no_key_and_no_network` |
| No key | Live catalog returns `not_configured` rather than a fabricated list | `test_fixture_live_catalog_without_key_reports_not_configured` |
| Per-agent model | `POST bots/:id/update {model}` reaches the wire request (`request.model == "fixture/chosen-7b"`) and is recorded on the assistant row | `test_fixture_per_agent_model_is_used_by_provider_turn` |
| Provider errors | `ProviderError(429)` becomes a `notice` row "Provider error …" plus `turn_end.terminal_reason == "provider_error"`; no crash | `test_fixture_provider_error_surfaces_as_error_row` |
| Cancellation (Fleet) | `POST bots/:id/cancel` returns `cancelled:true` and the turn finishes with `terminal_reason == "cancelled"` | `test_fixture_cancel_propagates_to_cancelled_turn` |
| Cancellation (mid-stream) | `ProviderModelClient(cancel_event=…)` raises `TurnCancelled` between deltas when a caller opts in | `test_fixture_mid_stream_cancel_raises_turn_cancelled` |
| Timeout | The configured 120 s timeout reaches `urlopen`; a `URLError` maps to a retryable `ProviderError` | `test_fixture_configured_timeout_reaches_network_edge` |
| Fixture vs live | Bridge payloads carry distinct markers; the shipped UI branches on `catalog.source === "offline"` / `live · <key_source>` and on `engine === "echo"` ("Scripted (Echo)") | `test_fixture_payload_carries_live_and_offline_markers`, `test_ui_source_reads_fixture_and_live_markers` |

**Cancellation note (documented, not a defect):** `turn_core.cancel_active_turn()`
explicitly states that *"the in-flight model round-trip (one HTTP stream)
completes; no further model round-trips or tool executions are issued."* Fleet
therefore stops at the round boundary. True mid-stream abort is an opt-in
capability of `ProviderModelClient` and is verified separately above. The test
records that the post-Stop delta is still observed, so the behaviour is not
overstated.

**Catalog-only note:** providers present in the offline catalog but with no
runtime adapter (e.g. `openai`) are rejected as non-executable by
`resolve_provider_model()`; an offline list is never presented as runnable.

---

## 3. Exact secure steps for a user to configure their own provider locally

All three paths keep keys out of chat, transcripts, commits and browser
storage. Use a dedicated, least-privilege key and rotate it if it is ever
pasted somewhere unintended.

### Path A — session-only key (recommended first try)

1. Start the local bridge; it binds `127.0.0.1` and requires the Keel token for
   every mutation.
2. Open **Settings → Credentials** in the UI. The bridge reports available
   providers; none is assumed.
3. Paste the key into the *password* input for that provider. It is never
   prefilled, never shown again, and cleared from React state immediately after
   the submit attempt (`ProvidersSettings.tsx:454-462,395-397`).
4. Click **Verify for this session** → `POST /api/fleet/providers/credential`.
   The bridge performs an authenticated probe (OpenRouter `/auth/key`; other
   providers use their credential-gated models endpoint), then holds the key
   **in this process's environment only**. Nothing is written to disk;
   restarting the bridge forgets it. A public `/models` response alone never
   validates a key.
5. The UI now shows **Session key active** and the key source. Open
   **Providers & models → Load models** for the live catalog (`models_meta`
   includes context length and reasoning efforts).
6. On **Fleet**, create/edit an agent with engine `provider`, then in
   **Settings → Agent models** set its `model` (or use the offline catalogue
   picker). This goes through `POST bots/:id/update` and is confirmed by the
   bridge. An unset model uses the provider default.
7. Run the turn. Usage and errors come from the real bridge.
8. Click **Forget session key** → `POST providers/credential/clear`. A
   shell-provided key is deliberately never cleared by this action.

### Path B — saved key (encrypted at rest)

1–3 as above, then:

4. Click **Save on this machine** → `POST /api/fleet/providers/save`. The same
   authenticated validation runs first; only then is the key encrypted with
   AES-256-GCM (`secret_store`) and written to `~/.keel/settings.json` with
   owner-only permissions and a rolling `settings.json.bak`. The master key
   comes from the OS keyring, else `KEEL_MASTER_PASSPHRASE`, else a local 0600
   key file.
5. The response contains **only** a four-character hint, rendered as
   `••••<hint>`. The full key is never returned, logged or exported
   (`settings_store.export_view()` omits `providerKeys` entirely).
6. A shell environment variable (e.g. `KEEL_OPENROUTER_API_KEY`) always takes
   precedence over the saved key; the saved key is not used while the shell key
   exists.
7. Click **Remove saved key** → `POST providers/remove` to delete the stored
   entry. Shell environment variables are never touched.

### Path C — shell environment variable only

Set `KEEL_OPENROUTER_API_KEY`, `KEEL_GOOGLE_API_KEY`, `KEEL_NVIDIA_API_KEY`,
`KEEL_ANTHROPIC_API_KEY` or `KEEL_COMPAT_API_KEY` in your shell before starting
the bridge. Keel reads it into memory; it is not copied into Keel settings and
cannot be removed from the UI. Anthropic is opt-in and never a default.

### Rules that hold on all paths

- Never put a key in chat, an agent note, an issue/PR description, a commit, or
  a tool argument. Keel redacts outbound messages and never echoes credentials.
- The browser persists no key: provider keys are absent from `localStorage`;
  only theme, layout and draft text are browser-owned
  (`UI-BACKEND-CONTRACT.md` §4).
- The bridge is local-only; the Next.js BFF injects the token server-side and
  strips cookies/Origin before forwarding.

---

## 4. Genuine local integration — Echo (requirement 4)

**Label: GENUINE LOCAL INTEGRATION — not a fixture, not a live external
provider.** The scripted Echo engine, the real Fleet store and the real HTTP
bridge run unmodified, with **every** provider credential env var asserted
absent. `tests/verify_local_provider_echo_integration.py` exercises:

- a complete turn over HTTP: `POST bots` (engine `echo`) → `POST messages` →
  `step` rows (`analyze-request`, `consider-options`, `compose-reply`, each
  `running` then `done`) → assistant message with `engine:"echo"` and the real
  quoted/reversed reply → `turn_end` with `num_steps:3` and a real duration;
- durability by reopening `FleetStore` on the same DB and finding the user row;
- the Markdown transcript export reflecting the same turn;
- the shipped UI source labelling Echo agents "scripted" and never as a live
  model run.

This proves the agent → bridge → store → transcript path works with zero
credentials. It says nothing about an external provider.

---

## 5. Test evidence (exact output)

Command from §0 (worktree `src` on `PYTHONPATH`):

```
...........................                                             [100%]
27 passed in 21.54s
```

Breakdown: 11 credential-lifecycle tests, 12 catalog/turn/UI-marker tests,
4 genuine Echo integration tests (one of which is a static UI-label check).
All runs used Python 3.11.9, pytest 9.0.2.

### Full-suite regression context

`python -m pytest -q` on the whole worktree (same `PYTHONPATH`) finished with:

```
9 failed, 4020 passed, 48 skipped, 3621 subtests passed in 924.53s (0:15:24)
```

Re-running **only those 9 node IDs in isolation, without any of the new
provider tests**, produced `3 failed, 1 passed, 5 skipped`. Therefore none of
the full-suite failures is attributable to this round:

- 5 release-manifest/checksum tests **skip** when the build-generated
  `release/RELEASE-MANIFEST.json` / `RELEASE-SHA256SUMS.txt` are absent (they
  failed in the full run only because those generated artifacts appeared and
  then disappeared mid-run — other agents are editing this shared worktree).
- `test_plan_index.py::test_authoritative_source_hashes_unchanged` **passes** in
  isolation; the full-run failure tracked a generated file another agent was
  rewriting concurrently.
- 3 failures are pre-existing and unrelated to providers:
  `test_w39_concurrent_approval_writes_are_lossless` (10 of 12 concurrent
  approval patterns persisted), `test_quick_ask_endpoint_uses_real_runtime`
  and `test_webapp.py::test_run_streams_events_and_done_marker` (both
  `TimeoutError` on a local HTTP round-trip under load).

---

## 6. The single externally gated, credential-dependent check (requirement 5)

**Check:** a real live model round-trip with the operator's own genuine key —
`ProviderModelClient.complete()` over real HTTPS to a provider, asserting a
non-empty assistant text and real usage numbers returned by that provider's
model.

**Status:** NOT VERIFIED here, by design. No external-provider credential is
available in this environment, and fabricating one would violate
`AGENTS.md` ("Never fabricate evidence").

**What is already verified around it:** authenticated probe → validation →
session/saved storage → masking → clear/remove (§1); live-catalog payload shape
and key-source reporting with a fixture probe (§2); adapter SSE parsing, tool
calls and usage with fake transports (`tests/test_providers.py`); the honest
no-credential state (`tests/test_provider_validation_ready.py::
test_no_credentials_means_no_live_success`); and a complete real local turn
(§4). The contract gap is recorded in `UI-BACKEND-CONTRACT.md` §5.

**To close it:** the operator supplies a key locally via Path A/B/C above and
runs one real turn while connected to that provider. No code change is needed;
only the credential is missing.
