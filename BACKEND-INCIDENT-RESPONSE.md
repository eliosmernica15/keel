# Backend Incident Response — Keel

**Branch:** `stabilization/post-promotion-production-2026-11-25`
**Exact final stabilization SHA:** `<<LEAD_SUPPLIED_SHA — placeholder; see matrix §A>>`
**Rule of this document:** containment first, evidence second, recovery third, and
never invent a capability that does not exist. Commands below are real; limits are
stated explicitly. Keel is machine-local, so "compromise" normally means a local
integration, token, provider key, or an agent turn doing something unsafe — not a
remote fleet of servers.

**Readiness states (do not conflate):** backend implementation **complete**; backend
locally verified **historical only**, not current; backend production-ready **no**;
desktop release-ready **no**; production deployment completed **no**. Revocation
primitives exist locally; the live revoke round-trip is PR-14
`external_validation_pending` and the platform gates are PR-19 `blocked`.

Evidence sources: `keel/src/keel/webapp.py`, `keel/src/keel/fleet/turn_core.py`,
`keel/src/keel/cli/main.py`, `keel/src/keel/mcp.py`, `keel/src/keel/custom_tools.py`,
`keel/src/keel/pairing.py`, `keel/src/keel/secret_store.py`,
`keel/src/keel/secret_providers.py`, `keel/src/keel/backend_observability.py`,
`keel/src/keel/diagnostics.py`, `keel/src/keel/resilience.py`,
`keel/src/keel/backups.py`, `keel/src/keel/fleet/db.py`,
`keel/src/keel/config_contracts.py`, `keel/src/keel/release/updater.py`.

---

## 0. Immediate containment order

1. **Stop unsafe execution** (§3) — kill switch, gateway stop, or Ctrl+C.
2. **Preserve evidence** (§4) — do this before rotating secrets or rewriting state.
3. **Revoke credentials and disable the integration** (§1, §2).
4. **Recover data** (§5) only after the above.
5. **Rotate affected secrets** (§6) last, then re-verify readiness.

---

## 1. Revoking credentials

### Bridge token (the web/Fleet client credential)

`POST /api/kill-switch` calls `rotate_token()`, which replaces the per-launch token
with a fresh `secrets.token_urlsafe(24)` and returns the new token in the response
(`webapp.py:228-232`, `webapp.py:722-728`). This revokes **every existing client
credential** for the running bridge (`webapp.py:228-229`). Clients must reopen the URL
printed by `keel serve`; `KEEL_TOKEN` was the only override (`webapp.py:79`).

Inspect the current gateway/auth surface with:

```bash
keel gateway status --port 8739 --token <TOKEN>   # GET /api/gateway
keel attach --port 8739 --token <TOKEN>           # list / inspect sessions
```

Evidence: `cli/main.py:396-434`, `cli/main.py:524-577`.

### Paired client / companion

```bash
keel capability invoke release.revoke --params '{"id":"<client-id>"}' --confirm
```

`release.revoke` calls `PairingStore.revoke()`, which marks the entry `revoked`
(`capability_registry.py:1791-1795`, `keel/src/keel/pairing.py:63-68`).

### Provider keys and master key

Provider credentials live in the OS keyring / `KEEL_*_API_KEY` env / encrypted
settings (`secret_store.py:1-8`, `65-104`). Revoke/rotate the credential **at the
provider** first, then update the secret source used here (§6). There is no
`keel secrets rotate` command.

**Important limit:** the Y3.9 sign-out / sign-out-everywhere / disconnect machinery in
`config_contracts.py` is a **descriptor plus an in-memory bookkeeping ledger**:
`build_revocation()` and `RevocationLedger.apply()` record effects but store no tokens
and do not purge stored credentials (`config_contracts.py:888-967`). Do **not** treat
`sign_out_all_clients` as a real credential deletion. Use token rotation, pairing
revoke, and provider-side rotation instead.

---

## 2. Disabling a compromised integration

```bash
keel mcp list
keel mcp revoke <name>                 # recorded approval for a project-scope MCP server is revoked
keel tools list
keel tools revoke <name>               # revoke an approved custom tool
keel capability invoke release.pairing --params '{}'   # list paired clients
keel capability invoke release.pair ...                  # opt-in pairing only
```

Evidence: `cli/main.py:691-739` (`mcp revoke` → `keel/src/keel/mcp.py:77`),
`cli/main.py:580-614` (`tools revoke` → `keel/src/keel/custom_tools.py:68`),
`capability_registry.py:1776-1795`.

For an OpenAPI/PowerShell tool family, the local registries are managed with
`keel openapi list|generate|approve|request` and `keel skills list|show|audit|invoke`;
`skills audit` reports `trusted`, `sha256` and `injection_suspects`
(`cli/main.py:742-804`, `cli/main.py:922-973`). Remove or re-approve the affected
entry via its registry (no universal "disable all integrations" command exists).

Execution posture can be tightened with real policy commands:

```bash
keel execpolicy list
keel execpolicy active
keel execpolicy validate <policy.json>
keel execpolicy activate <name>
keel capability invoke core.flags.list --params '{}'
keel capability invoke core.flags.set --params '{"name":"...","enabled":false,"kill_switch":true}' --confirm
```

Evidence: `cli/main.py:807-877`, `capability_registry.py:177-190`.

---

## 3. Stopping unsafe execution

- **Global kill switch (preferred):** `POST /api/kill-switch` — calls
  `cancel_all_turns()` (signals every in-flight Fleet turn at once) and rotates the
  bridge token (`webapp.py:722-728`, `keel/src/keel/fleet/turn_core.py:71-77`).
- **Single turn:** `cancel_active_turn(bot_id)` is cooperative — the in-flight model
  round-trip completes, but no further model round-trips or tool executions are issued
  (`turn_core.py:56-68`). This is a Python API, not a CLI command.
- **Gateway thread:** `POST /api/gateway/stop` → `Gateway.stop(timeout=5.0)` sets the
  stop event and joins the thread (`webapp.py:714-721`, `keel/src/keel/gateway.py:56-63`).
- **Whole bridge:** Ctrl+C in the `keel serve` terminal → `KeyboardInterrupt` →
  `server.server_close()` (`webapp.py:1321-1327`).
- **Prevent scheduler restarts:** `KEEL_FLEET_SCHEDULER_DISABLED=1` disables the daemon
  (`keel/src/keel/fleet/scheduler.py:346-347`).
- **Policy:** activate a restrictive `execpolicy` (§2); standing policies, deny rules
  and hooks still bind even in autopilot (`turn_core.py:80-94`).
- **Sandbox:** Windows filesystem/process/network enforcement is real and
  adversarial-verified; Linux native and macOS native execution are **not verified on
  this host** and macOS read isolation is BLOCKED
  (`keel/docs/FINAL-RELEASE-OPERATIONS.md:168-178`). Do not rely on those backends as a
  containment control here.

---

## 4. Preserving logs and evidence

1. Copy the append-only event log **before** any cleanup:
   `<state_root>/observability.jsonl` (default state root `~/.keel`; set
   `KEEL_STATE_DIR` explicitly — see runbook §3).
2. Verify its chain first: `verify_chain(state_root)` returns `ok`, `event_count`,
   `first_seq`, `last_seq`, `error` (`backend_observability.py:319-323`, `75-92`). A
   corrupt chain is never extended or returned as trusted
   (`backend_observability.py:386-392`, `436-441`). Truncation is therefore detectable.
3. Export a redacted environment snapshot:
   ```bash
   keel doctor --bundle --file /path/to/incident-bundle.zip
   ```
   The bundle masks credential-like env names and contains no conversation content
   (`diagnostics.py:19-57`); review it before sharing.
4. Capture the startup-health state: `keel capability invoke release.health --params '{"state_root":"..."}'`
   (`capability_registry.py:1735-1739`).
5. Record provider/gateway status with `keel provider validate`, `keel gateway status`,
   `GET /api/gateway` (`cli/main.py:1228-1234`, `396-434`, `webapp.py:714-721`).
6. Do **not** delete or rotate `observability.jsonl` while investigating. The code has
   no automatic rotation; retention is an operator decision
   (`backend_observability.py:1-16`, `45`).

---

## 5. Database recovery and restore

- Check integrity: `from keel.resilience import db_integrity; db_integrity("<state_root>/fleet.db")`
  → `PRAGMA integrity_check == "ok"` (`resilience.py:87-90`).
- Take a live backup before touching anything: `fleet.audit.export` capability
  (`{"db":"...","target":"..."}`, `--confirm`) or `resilience.db_backup`
  (`resilience.py:93-99`, `capability_registry.py:1591-1595`).
- Full state restore: `release.backups.restore` capability with the exact passphrase
  and target (`capability_registry.py:1807-1820`). `backups.restore_backup()` verifies
  the AES-256-GCM archive, the manifest and every SHA-256 before writing, and refuses
  to overwrite files newer than the archive unless `overwrite=True`
  (`backups.py:148-235`). A wrong passphrase/corrupt backup surfaces as `bad_params`
  (HTTP 400), not a 500 (`capability_registry.py:1816-1820`).
- **Migration limit:** `fleet/db.py:_migrate()` applies schema versions 1..11 forward
  only (`fleet/db.py:258-365`); `config_contracts.SchemaApplySeam.apply()` is
  `NotImplementedError` and `MigrationDescriptor` cannot execute SQL
  (`config_contracts.py:760-804`). There is **no schema downgrade**. Restoring an older
  `fleet.db` over a newer schema is unsafe — restore a matching-era full state backup
  and let forward migrations run.
- **Release rollback:** `updater.rollback(install_dir, backup_dir)` requires a backup
  directory and swaps the previous install back in (`release/updater.py:162-167`);
  three consecutive failed starts set `rollback: true` (`start_health.py:40-50`). This
  is a Python API — there is no `keel rollback` command.

---

## 6. Rotating affected secrets

1. **Provider keys:** revoke the old key at the provider, then set the new value in
   the source Keel reads — masked CI secret or the encrypted store, never chat or git
   (`keel/docs/FINAL-RELEASE-OPERATIONS.md:181-201`). `KEEL_*_API_KEY` env values are
   read on each validation/smoke call (`provider_validation.py:30-37`, `68-69`), so
   restart `keel serve` to rebuild any cached adapters.
2. **Verify presence, not value:** `keel secrets has <KEY>` and `keel provider validate`
   (`cli/main.py:903-913`, `1215-1234`). `keel secrets get` reveals the value to stdout —
   use only in a controlled terminal (`cli/main.py:887-890`).
3. **Master key:** comes from OS keyring `keel`/`master-key`, then
   `KEEL_MASTER_PASSPHRASE`, then `0600 <state_dir>/master.key`
   (`secret_store.py:21-22`, `65-104`). If it is suspected compromised, rotate it at
   the keyring/passphrase source and re-encrypt stored secrets. **Limit:** the code
   provides `encrypt_secret`/`decrypt_secret` but no bulk re-encryption CLI
   (`secret_store.py:111-131`), so plan for manual re-entry of stored credentials.
4. **Bridge token:** rotate with `POST /api/kill-switch` (§1) and hand out only the new
   URL.
5. **MCP / tool / pairing approvals:** revoke via `keel mcp revoke`, `keel tools revoke`,
   `release.revoke` (§2); approvals are recorded locally and replay is denied after
   revoke (`keel/src/keel/backend_workflows.py:888-947`).

After rotation, re-run the readiness sequence in `BACKEND-DEPLOYMENT.md` §6 at the exact
final stabilization SHA. **[HISTORICAL]** no live provider call was made on the candidate
host (`PROD-PROVIDER-EVIDENCE.md`). **Current classification:** PR-06 and PR-14 are
`external_validation_pending`; record the live revoke round-trip before claiming either
closed. The Y3.9 descriptor gap G1 remains an owner decision (implement purge or waive).

---

## 7. Post-incident checklist

- [ ] Unsafe turn/gateway stopped; kill switch used if credentials were exposed.
- [ ] `observability.jsonl` copied and `verify_chain()` result recorded.
- [ ] Redacted `keel doctor --bundle` saved.
- [ ] Compromised MCP server / custom tool / paired client revoked.
- [ ] Provider-side key revoked; new key set in the configured source.
- [ ] Bridge token rotated; old URLs rejected.
- [ ] DB integrity checked; backup taken; restore only from a matching schema era.
- [ ] Startup health reset/observed after clean starts (`start_health.reset` is a
      Python API, `start_health.py:53-59`).
- [ ] Full readiness sequence re-run; findings recorded without claiming a production
      release.
