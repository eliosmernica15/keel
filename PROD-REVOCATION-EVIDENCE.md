# PR-14 — Credential revocation / disable compromised integration: local evidence

**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\production\revoke`
**Branch:** `agent/final-revoke`  **Candidate HEAD:** `ac84fee`
**New files only:** `PROD-REVOCATION-EVIDENCE.md`, `keel/tests/test_prod_revocation.py`
**No existing source/tests edited. No frontend. No push.**

---

## 1. What the real code does (inspection, not assumption)

| Capability | Real implementation | Durable local effect? |
|---|---|---|
| Store provider key | `keel/src/keel/settings_store.py:168-179` `save_provider_key()` → `secret_store.encrypt_secret()` (AES-256-GCM, `secret_store.py:111-116`) → `apply_stored_keys()` (`settings_store.py:208-227`) | Yes: ciphertext in `settings.json`, plaintext in process env via `_APPLIED_FROM_STORE` (`:39`) |
| Remove provider key | `settings_store.py:182-195` `remove_provider_key()` | Yes: deletes the live `providerKeys` entry and pops the env var only when this process applied it |
| Disable MCP server | `keel/src/keel/fleet/connector_ops.py:191-198` `remove_connector()` (deletes descriptor from `mcpServers`) and `keel/src/keel/mcp.py:77-83` `revoke()` (deletes recorded project-scope approval) | Yes: discovery (`parse_servers`, `mcp.py:92-128`) and the activation gate (`keel/src/keel/fleet/turn_core.py:100-109`) both read that state; `McpManager.call()` (`mcp.py:375-383`) has no client to invoke |
| Revoke pairing | `keel/src/keel/pairing.py:63-71` `PairingStore.revoke()` | Yes: sets `revoked`/`revoked_at` in `pairings.json`; `is_paired()` (`:45-48`) then denies |
| Revoke capability/approval token | `keel/src/keel/backend_workflows.py:1049-1068` `_approval_revoke()`; replay/revocation guards at `:1003-1006` | Yes: append-only `approval-events.jsonl`; subsequent `resolve` is denied |
| Audit record | `keel/src/keel/backend_observability.py:875-914` `record_audit_event()` → `record_event()` (`:583-661`) → `redact()` (`:228-237`) using `keel/redaction.py:18-53` | Yes: hash-chained `observability.jsonl`; `verify_chain()` (`:532`) verifies retention |
| Y3.9 sign-out / disconnect descriptor | `keel/src/keel/config_contracts.py:888-903, 934-967` (`build_revocation`, `RevocationLedger.apply`) | **No** — bookkeeping only; see gap G1 |
| Y3 pairing broker / invite gate | `keel/src/keel/y3_backend.py:687-764, 788-833` | **No** — in-memory dictionaries, no durable store; the durable pairing path is `pairing.PairingStore` above |

---

## 2. Tests built (all in a disposable temp state dir, no network)

`keel/tests/test_prod_revocation.py` (7 tests):

1. `test_provider_key_revocation_clears_env_and_live_store` — saves a real AES-GCM encrypted OpenRouter-style key, proves it is applied to `os.environ`, proves plaintext is absent at rest, removes it, then proves the env var is gone, the live store entry and its ciphertext blob are gone, no plaintext exists anywhere in the state dir, and `apply_stored_keys()` cannot resurrect it.
2. `test_mcp_connector_disable_excludes_discovery_and_invocation` — `add_connector()` registers a real descriptor; disabling via `remove_connector()` removes it from on-disk `settings.json`; `parse_servers()` then yields nothing and `McpManager.call()` returns `not connected`.
3. `test_project_mcp_approval_revoke_denies_activation` — approves a real project-scope descriptor via `mcp.approve()`, verifies the same allow-list gate used by `turn_core._mcp_manager()` admits it, then `mcp.revoke()` excludes it durably from the approvals file and the gate.
4. `test_pairing_revoke_denies_subsequent_use` — pairs a client, verifies a fresh `PairingStore` instance sees it (durable), revokes it, and verifies a fresh store instance denies it; checks `revoked`/`revoked_at` on disk.
5. `test_approval_token_revoke_denies_subsequent_resolve` — real `run_approval_workflow`: unspent token → revoke → `resolve` denied with `revoked`; spent token → consume → revoke → later use denied by `replay_denied`; exact durable event sequence `request, revoke, request, consume, revoke`.
6. `test_revocation_audit_is_redacted_and_retained` — records two real audit events whose detail contains a provider-key-shaped secret, a multi-word secret and a bearer token; proves all are `[REDACTED]` in the returned event and in the raw JSONL, and that `verify_chain()` is `ok` with both events retained.
7. `test_y3_descriptor_is_bookkeeping_only_not_credential_deletion` — **negative evidence**: `ALL_CLIENTS` revocation descriptor reports `delete_stored_credentials=True` / `clients_signed_out=True` and the ledger marks the subject revoked, yet the real stored provider key and its env var are still present. This is reported as a gap, not used as closure evidence.

Isolation details: `KEEL_STATE_DIR`, the `KEEL_*_API_KEY` env var and `KEEL_MASTER_PASSPHRASE` are pinned per test via `monkeypatch`; module-level path constants in `settings_store` are redirected to `tmp_path`; `mcp.approvals_path` is redirected to `tmp_path`; `conftest.py`'s autouse `load` stub is explicitly restored to the real loader so file-backed state is exercised.

---

## 3. Exact commands and output

Command (PowerShell, from the worktree's `keel/` directory):

```powershell
$wt = "C:\Users\Admin\.local\share\opencode\worktree\production\revoke\keel"
$env:PYTHONPATH = "$wt\src"
python -m pytest -v tests/test_prod_revocation.py
```

Output:

```
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.0.2, pluggy-1.6.0 -- C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe
cachedir: .pytest_cache
hypothesis profile 'default'
rootdir: C:\Users\Admin\.local\share\opencode\worktree\production\revoke\keel
configfile: pyproject.toml
plugins: anyio-4.15.1, hypothesis-6.152.9, platformdirs-4.12.4, xdist-3.8.0
collecting ... collected 7 items

tests/test_prod_revocation.py::test_provider_key_revocation_clears_env_and_live_store PASSED [ 14%]
tests/test_prod_revocation.py::test_mcp_connector_disable_excludes_discovery_and_invocation PASSED [ 28%]
tests/test_prod_revocation.py::test_project_mcp_approval_revoke_denies_activation PASSED [ 42%]
tests/test_prod_revocation.py::test_pairing_revoke_denies_subsequent_use PASSED [ 57%]
tests/test_prod_revocation.py::test_approval_token_revoke_denies_subsequent_resolve PASSED [ 71%]
tests/test_prod_revocation.py::test_revocation_audit_is_redacted_and_retained PASSED [ 85%]
tests/test_prod_revocation.py::test_y3_descriptor_is_bookkeeping_only_not_credential_deletion PASSED [100%]

============================== 7 passed in 1.26s ==============================
```

Regression check on the existing neighbouring suites (same `PYTHONPATH`):

```powershell
python -m pytest -q tests/test_prod_provider.py tests/test_prod_mcp.py tests/test_prod_observe.py tests/test_mcp.py tests/test_pairing.py tests/test_backend_workflows.py tests/test_secret_storage.py tests/test_settings.py
```

Output:

```
........................................................................ [ 42%]
........................................................................ [ 84%]
........................................................................ [100%]
170 passed in 13.40s
```

Working tree after the work (only new files):

```
## agent/final-revoke
?? keel/tests/test_prod_revocation.py
```

---

## 4. Local vs live-provider revocation (kept strictly separate)

**Proven locally (cryptographic / state revocation).** With disposable on-disk state and a deterministic local master key, the code actually: encrypts a provider secret with AES-256-GCM, applies it to the process environment, removes both the environment binding and the live stored entry, deletes MCP descriptors and approvals so discovery and invocation stop seeing the server, marks paired clients revoked so fresh readers deny them, appends a revocation event to a capability ledger so later use is denied, and writes redacted, hash-chained audit records that survive verification. These effects are durable across fresh readers/processes within the local state directory.

**Not proven here (live-provider-side revocation).** Nothing in these tests contacts a provider, keyring service, or remote bridge. Whether a real API key is actually disabled at OpenRouter/Google/NVIDIA/Anthropic/OpenAI-compatible, whether a live bridge token is rejected by a deployed server, and whether a remote MCP server stops accepting an already-issued session are **unverified**. Those require real credentials and a live service; `BACKEND-INCIDENT-RESPONSE.md:58-70, 187-208` documents the required operator actions (rotate at the provider, then update the local source). This evidence must not be read as provider-side revocation.

---

## 5. Gaps reported honestly (no closure claimed for these)

- **G1 — Y3.9 sign-out/disconnect is descriptor + in-memory ledger only.** `config_contracts.build_revocation()` and `RevocationLedger.apply()` report `credentials_deleted=True` and `clients_signed_out=True` but delete no credential and invalidate no session (test 7 asserts the key and env var survive). `y3_backend.PairingBroker` / `InviteGate` are in-memory too. Local closure therefore relies on the real paths in §2, never on this descriptor.
- **G2 — rolling backup retains ciphertext.** `settings_store.save()` keeps `settings.json.bak`; after key removal the old *encrypted* blob can remain there. Plaintext is removed and the live entry is gone (test 1 asserts this), but there is no secure-delete of backup ciphertext.
- **G3 — no `enabled=false` MCP descriptor.** There is no persisted boolean "disabled" flag on an MCP server. Disabling is deletion of the descriptor (`remove_connector`) or deletion of its recorded approval (`mcp.revoke`). This is a real durable effect, but it is not a reversible toggle.
- **G4 — live-provider revocation unverified** (see §4). Needs credentials; cannot be closed locally.
- **No helper added:** all four required capabilities have real durable implementations in existing modules. Adding `keel/src/keel/revocation_ops.py` would create a parallel, unwired capability and would not make the Y3.9 descriptor durable; G1 is reported rather than papered over.

---

## 6. PR-14 verdict

**PR-14 can be CLOSED locally for local credential revocation and local integration disablement**, on the basis of 7 passing real-state tests plus 170 passing neighbouring tests: provider keys are removed from both process env and the live encrypted store; MCP servers are excluded from discovery and cannot be invoked once their descriptor/approval is revoked; pairing and capability tokens are denied on subsequent use after revocation; and revocation audit records are redacted and retained with a verified hash chain.

The closure is explicitly scoped: it does **not** cover live-provider-side key revocation (G4), does **not** treat the Y3.9 descriptor/ledger as a revocation control (G1), and does **not** claim secure-delete of backup ciphertext (G2). Commit on `agent/final-revoke`; do not push.
