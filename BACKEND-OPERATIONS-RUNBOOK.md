# Backend Operations Runbook — Keel

**Branch:** `stabilization/post-promotion-production-2026-11-25`
**Exact final stabilization SHA:** `<<CANDIDATE_HEAD_REFERENCE — placeholder; see matrix §A>>`
**Status of this document:** descriptive, not a promise of production readiness. Every
command below was checked against the CLI/release source at the stabilization baseline
tip; line numbers from historical candidate commits are deliberately omitted. Where the
code only provides a Python API / capability, this document says so instead of inventing
a CLI command.

**Readiness states (do not conflate):** backend implementation **complete**; backend
locally verified **historical only** (no evidence at the exact final SHA yet); backend
production-ready **no**; desktop release-ready **no**; production deployment completed
**no**. Gate vocabulary and counts: `PRODUCTION-READINESS-MATRIX.md` §§B/D.

## 0. Scope and hard boundaries

- Keel is a **machine-local** harness. `keel serve` binds `127.0.0.1` only; it is not a
  network service and must not be fronted by a public interface
  (`keel/src/keel/webapp.py:3-32`, `webapp.py:1311`).
- The local web UI is protected by a per-launch random token printed in the URL
  (`webapp.py:79`, `webapp.py:1316-1319`); `KEEL_TOKEN` overrides it. Every `/api/*`
  route is token-gated and non-GET requests must have a matching `Origin`
  (`webapp.py:253-280`).
- **[HISTORICAL — pre-promotion candidate]** The candidate evidence records installers
  unsigned, no live provider credentials, no clean-VM or native Linux/macOS validation,
  and no push/publish (`keel/docs/FINAL-RELEASE-OPERATIONS.md`,
  `master-plan-v6-final-report.md`). The current stabilization baseline instead records
  six failing CI workflows on `origin/main` `9a63be92` with logs unavailable
  (`POST-PROMOTION-STABILIZATION-BASELINE.md:9-20`). Neither establishes production readiness.
- **[HISTORICAL]** Windows sandbox enforcement was adversarial-verified; Linux native
  (Landlock/seccomp) was scoped-verified on WSL2 only, and macOS native execution was not
  run with read isolation BLOCKED on macOS 26. Native runners remain PR-19 `blocked`.

**Authoritative sources for this runbook:** `keel/src/keel/cli/main.py`,
`keel/src/keel/webapp.py`, `keel/src/keel/start_health.py`,
`keel/src/keel/backups.py`, `keel/src/keel/resilience.py`,
`keel/src/keel/fleet/db.py`, `keel/src/keel/backend_observability.py`,
`keel/src/keel/diagnostics.py`, `keel/src/keel/settings.py`,
`keel/src/keel/secret_store.py`, `keel/src/keel/secret_providers.py`,
`keel/src/keel/provider_validation.py`, `keel/src/keel/fleet/scheduler.py`,
`keel/src/keel/gateway.py`, `keel/src/keel/capability_registry.py`, and
`keel/docs/FINAL-RELEASE-OPERATIONS.md`.

---

## 1. Starting and stopping Keel

### Start

```bash
cd keel
keel serve --port 8739        # local web UI + Fleet; default port 8739
keel fleet --port 8739        # same loopback server, /fleet route printed
keel web                       # alias of `keel serve` (cli/main.py:119-121)
```

Evidence: `cli/main.py:122-167`. `keel serve`/`keel fleet` call
`scheduler.start_daemon()` then `serve(port)`; the daemon is idempotent and can be
disabled with `KEEL_FLEET_SCHEDULER_DISABLED=1`
(`keel/src/keel/fleet/scheduler.py:343-357`). The token URL is written to stderr.

### Stop

- Foreground: press **Ctrl+C**. `serve()` catches `KeyboardInterrupt` and calls
  `server.server_close()` (`webapp.py:1314-1327`).
- Stop in-flight agent work first if needed: `POST /api/kill-switch` cancels every
  active Fleet turn and rotates the bridge token (`webapp.py:722-728`,
  `keel/src/keel/fleet/turn_core.py:71-77`).
- Stop the background gateway via `POST /api/gateway/stop` and inspect with
  `GET /api/gateway` (`webapp.py:714-721`, `keel/src/keel/gateway.py:25-63`).
- There is no `keel stop` / systemd unit / service manager in this repository. Do not
  claim one.

### Process model

`keel serve` is a single Python process with a `ThreadingHTTPServer` plus daemon
threads for the fleet scheduler and gateway. `keel -p "prompt"` is one-shot print mode;
`keel tui` is the terminal UI (`cli/main.py:13-33`, `cli/main.py:87-94`).

---

## 2. Health checks

Three distinct signals exist. Do not conflate them.

| Signal | Command / endpoint | What it actually proves |
| --- | --- | --- |
| Liveness of the bridge | `GET /api/health` | `{"ok": true, "version": "0.1.1"}` — the HTTP process is up (`webapp.py:6`, `webapp.py:378`). Token required. |
| Local readiness (environment) | `keel doctor` | Interpreter, platform, required tools, **masked** provider keys, `~/.keel` and project `.keel` presence (`keel/src/keel/commands.py:189-212`, `cli/main.py:68-80`). |
| Backend module health | `keel capability invoke core.diagnostics --params '{}'` and backend observability helpers `health_snapshot()` / `diagnostic_report()` | Real import status of the 20 modules, declared-feature counts, recorded `error` events, hash-chain status (`keel/src/keel/backend_observability.py:481-566`). These are Python/capability APIs, not a dedicated CLI subcommand. |
| Repeated-failed-start state | `keel capability invoke release.health --params '{"state_root":"..."}'` | Reads `<state_root>/start-health.json`; 3 consecutive failures means rollback advised (`start_health.py:15`, `start_health.py:40-50`, `capability_registry.py:1735-1747`). |
| Admin UI health view | Settings → Admin page | Aggregates startup health, resource meters and limits from the same local state (`keel/src/keel/admin_page.py:4-72`). |

Readiness for **release** is a separate, owner-gated process: `keel doctor --bundle`,
`python scripts/validate_desktop.py --dist dist`, `python scripts/verify_backend_operation.py`,
`python -m keel.release integrity --dist dist --artifacts release`. See
`BACKEND-DEPLOYMENT.md`.

---

## 3. Configuration

### Resolution model

Settings fold in this order (highest first): managed > flags > local > project > user >
env > defaults. Monotonic keys (e.g. `dangerouslyAllowWithoutConfirm`,
`bypassPermissionsEnabled`) resolve to the most restrictive value; project scope may
not set either (`keel/src/keel/settings.py:1-10`, `settings.py:44-87`).

### Real commands

```bash
keel settings show                 # resolved value + provenance + diagnostics
keel settings schema               # Draft 2020-12 schema from the typed registry
keel settings validate <directory> # validate every *.json under a directory
keel execpolicy list
keel execpolicy active
keel execpolicy validate <policy.json>
keel execpolicy check <policy.json> <command...>
keel execpolicy network <policy.json> <host> [protocol]
keel execpolicy save <name> <policy.json>
keel execpolicy activate <name>
```

Evidence: `cli/main.py:636-688`, `cli/main.py:807-877`. `keel settings validate`
returns non-zero if any file fails to parse (`cli/main.py:673-686`).

### State root — set it explicitly

`settings.default_state_root()` is `~/.keel` (`settings.py:475-476`) and the Fleet DB
is `~/.keel/fleet.db` (`keel/src/keel/fleet/db.py:237-238`). However, several CLI
subcommands default `KEEL_STATE_DIR` to the **relative** `.keel`
(`cli/main.py:827-847`, `cli/main.py:893`), while others use `~/.keel`
(`cli/main.py:286-287`, `cli/main.py:381`). **In any non-interactive/operator
context set `KEEL_STATE_DIR` to an absolute path** so capabilities, policies,
secrets, observability and backups all address the same root.

Key environment knobs actually read by the code:

| Variable | Purpose | Source |
| --- | --- | --- |
| `KEEL_STATE_DIR` | state root (see warning above) | `admin_ops.py:14`, `cli/main.py:286` |
| `KEEL_TOKEN` | bridge auth token (else random per launch) | `webapp.py:79` |
| `KEEL_START_HEALTH_FILE` | override startup-health JSON path | `start_health.py:18-20` |
| `KEEL_FLEET_SCHEDULER_DISABLED=1` | disable the routine daemon | `scheduler.py:346` |
| `KEEL_FLEET_ROUTINE_TIMEOUT_S` | routine timeout, default 600 | `scheduler.py:40-44` |
| `KEEL_MASTER_PASSPHRASE` | fallback master key for encrypted secrets | `secret_store.py:87-89` |
| `KEEL_EGRESS_ALLOWLIST`, `KEEL_OUTPUT_DLP` | egress hosts / output DLP | `admin_ops.py:16-17` |
| `KEEL_MODEL`, `KEEL_DEFAULT_PROVIDER`, `KEEL_PERMISSION_MODE`, `KEEL_MAX_TURNS`, `KEEL_*_PERMISSIONS_*` | typed setting overrides | `settings.py:45-78` |
| `KEEL_*_API_KEY`, `KEEL_*_MODEL`, `KEEL_COMPAT_BASE_URL` | provider credentials/models | `keel/docs/FINAL-RELEASE-OPERATIONS.md:181-201` |

The full local config reference is `keel/src/keel/admin_ops.py:12-20`.

---

## 4. Secret management

- Provider keys are encrypted with **AES-256-GCM** before being written to settings.
  The master key comes from the OS keyring (`service="keel"`, `name="master-key"`),
  falling back to `KEEL_MASTER_PASSPHRASE` (SHA-256) and then a `0600`
  `<state_dir>/master.key` file (`keel/src/keel/secret_store.py:1-8`, `21-22`, `65-104`).
- No secret is logged or included in an error message (`secret_store.py:1-8`).
- Local secret providers are `env`, `env-file` and `command`; configuration is stored
  in `<state_root>/secret-providers.json` (`0600`) with **no values**
  (`keel/src/keel/secret_providers.py:1-12`, `143-160`). Command providers run with
  `shell=False`, a timeout, and receive only the requested key (`secret_providers.py:72-97`).

```bash
keel secrets providers           # describe chain, presence only
keel secrets has KEEL_OPENROUTER_API_KEY
keel secrets get KEEL_OPENROUTER_API_KEY   # EXPLICITLY reveals to stdout — handle carefully
keel capability invoke core.secrets.providers --params '{}'
```

Evidence: `cli/main.py:880-919`, `capability_registry.py:130-154`. Diagnostics and
capabilities are presence-only; only `resolve(reveal=True)` / `keel secrets get`
returns a value (`keel/docs/FINAL-RELEASE-OPERATIONS.md:199-201`).

**Never** paste credential values into chat, git, or a diagnostics bundle. The bundle
masks any env var whose name contains `KEY`, `TOKEN`, `SECRET`, `PASSWORD`, or
`CREDENTIAL` (`keel/src/keel/diagnostics.py:19-35`).

---

## 5. Database backup, restore, migration and rollback limits

### Database location and migration

- Fleet DB: `~/.keel/fleet.db` (`fleet/db.py:237-238`). `connect()` opens it with WAL
  mode, foreign keys ON, and runs `_migrate()` (`fleet/db.py:246-255`).
- `_migrate()` is **forward-only**, applying schema versions 1 through 11 with
  `CREATE TABLE IF NOT EXISTS` / guarded `ALTER TABLE ... ADD COLUMN`
  (`fleet/db.py:258-365`). There is **no down-migration path**.
- `config_contracts.MigrationDescriptor` is data-only and refuses to execute SQL;
  `SchemaApplySeam.apply()` raises `NotImplementedError`
  (`keel/src/keel/config_contracts.py:760-804`). This is a seam, not a migration runner.

### Integrity and backup

```bash
# Python APIs (no dedicated CLI subcommand):
#   from keel.resilience import db_integrity, db_backup
#   db_integrity("~/.keel/fleet.db")            -> PRAGMA integrity_check == "ok"
#   db_backup("~/.keel/fleet.db", "fleet.db.bak")
# Exposed as a capability:
keel capability invoke fleet.audit.export --params '{"db":"...","target":"..."}' --confirm
```

Evidence: `keel/src/keel/resilience.py:87-99`, `capability_registry.py:1591-1595`.

Full state backup/restore uses AES-256-GCM with PBKDF2-HMAC-SHA256 (200,000
iterations), an authenticated manifest, atomic writes, and a restore that verifies the
whole archive and every SHA-256 **before writing anything**; it refuses to overwrite
files newer than the archive unless `overwrite=True`
(`keel/src/keel/backups.py:29-30`, `119-235`). There is **no `keel backup` CLI**: use
the capabilities:

```bash
keel capability invoke release.backups.create --params '{"source":"...","target":"...","passphrase":"..."}' --confirm
keel capability invoke release.backups.restore --params '{"backup":"...","target":"...","passphrase":"..."}' --confirm
```

Evidence: `capability_registry.py:1798-1820`. Passphrases in shell history are a
local risk; prefer an operator secret manager and never store the passphrase beside
the backup.

### Rollback limits

- Installer rollback: `updater.rollback(install_dir, backup_dir)` swaps the previous
  installation back in; it requires a backup directory
  (`keel/src/keel/release/updater.py:162-167`). `atomic_install` preserves the old
  installation in `backup_dir` (`updater.py:143-159`).
- Auto-rollback: after `DEFAULT_THRESHOLD = 3` consecutive failed starts,
  `start_health` reports `rollback: true`; the caller is expected to invoke
  `updater.rollback` (`start_health.py:1-6`, `15`, `40-50`). No automatic restore of
  the DB is performed.
- Activation is health-gated: `e5_backend.py` boots a staged profile, swaps only when
  `health_check()` returns `True`, journals the transaction and retains rollback
  (`keel/src/keel/e5_backend.py:300-369`).
- **Restoring an older `fleet.db` over a newer schema is unsafe**: there is no
  down-migration and no schema-version downgrade logic. Treat DB recovery as
  restore-to-identical-schema only; for schema regressions, restore the whole state
  directory from a matching-era encrypted backup and re-run forward migrations.

---

## 6. Log locations, bounded logs and diagnostic export

| Artifact | Location | Properties |
| --- | --- | --- |
| Backend event log | `<state_root>/observability.jsonl` | append-only JSONL, monotonic `seq`, UTC timestamp, correlation ID, SHA-256 hash chain, fail-closed on corrupt chain, redacted **before** write (`backend_observability.py:1-16`, `38`, `276-425`). |
| Observability lock | `<state_root>/observability.jsonl.lock` | exclusive-create, stale after 30 s, 10 s acquire timeout (`backend_observability.py:43-44`, `121-184`). |
| Fleet DB | `~/.keel/fleet.db` (WAL) | `fleet/db.py:237-255`. |
| Startup health | `<state_root>/start-health.json` (or `KEEL_START_HEALTH_FILE`) | `start_health.py:18-20`, `34-37`. |
| Secret provider config | `<state_root>/secret-providers.json` (`0600`) | `secret_providers.py:143-160`. |
| Master key fallback | `<state_dir>/master.key` (`0600`) | `secret_store.py:91-104`. |
| Egress records | local JSONL under state root | `redaction.py:1-7`. |
| Web/bridge logs | intentionally quiet; `log_message()` is a no-op | `webapp.py:1308-1309`. |

Logs are **bounded** where exposed: `diagnostic_report()` returns only the last
`_RECENT_ERROR_LIMIT = 20` error events (`backend_observability.py:45`, `551-566`).
The JSONL itself is append-only and grows without an automatic rotation in this code.

Diagnostic export:

```bash
keel doctor --bundle                       # writes keel-diagnostics.zip
keel doctor --bundle --file /path/to/bundle.zip
```

`write_bundle()` produces a ZIP with `diagnostics.json` and `README.txt`, containing
platform/version/tool presence and masked env flags, and **no conversation content or
credential values** (`diagnostics.py:1-6`, `28-57`). The user decides whether to share
it; Keel never uploads it. Re-check the bundle before sending it off-machine.

---

## 7. Worker / scheduler recovery

- The Fleet routine daemon starts with `keel serve`/`keel fleet` and is idempotent
  (`scheduler.py:343-357`); tick interval is 20 s (`scheduler.py:35`, `340`).
- Missed slots: a routine overdue by more than one full period is recorded
  `skipped_missed` and advanced to the next future slot — no backlog storm after a
  restart (`scheduler.py:8-10`, `81-94`, `316-322`).
- Overlap protection: a routine is atomically claimed (`running` 0→1); a second tick
  is a no-op (`scheduler.py:11-12`, `312-314`).
- Failure isolation: a total failure releases the claim, marks the run and task
  `failed`, and pushes the next slot into the future; the scheduler is never stranded
  (`scheduler.py:97-107`, `159-191`). A routine exceeding
  `KEEL_FLEET_ROUTINE_TIMEOUT_S` (default 600) is failed with `terminal_reason=timeout`
  (`scheduler.py:194-238`).
- The gateway is a managed background thread with `status()`, `start()`, `stop()`;
  a failed tick never kills the gateway (`keel/src/keel/gateway.py:14-63`).
  Control it via `POST /api/gateway/start` / `/api/gateway/stop`, inspect via
  `GET /api/gateway` (`webapp.py:714-721`, `webapp.py:519`).

---

## 8. Provider configuration

```bash
keel provider list
keel provider validate                 # static contract checks; live SKIP without creds
keel provider validate --live          # only with a real configured credential
keel provider smoke <name> [--model MODEL]   # names: auto|openrouter|nvidia|google|anthropic|openai-compatible
```

Evidence: `cli/main.py:1215-1257`. The validation matrix reports `PASS | FAIL | SKIP`,
checks auth presence (value never exposed), static model/tool/streaming capability,
and only attempts live calls with `--live` plus a configured credential
(`keel/src/keel/provider_validation.py:23-58`, `106-132`). It explicitly never
fabricates success. Provider credentials and model overrides are listed in
`keel/docs/FINAL-RELEASE-OPERATIONS.md:181-201`; `anthropic` is **opt-in only, never a
default**. **[HISTORICAL]** No `KEEL_*` key was configured on the candidate host and no
live call was made (`PROD-PROVIDER-EVIDENCE.md`). **Current classification:** PR-06 is
`external_validation_pending` — a disposable credential plus a live round-trip must be
executed and recorded at the exact final stabilization SHA; never report SKIP as a pass.

---

## 9. Security incident response (summary)

Full procedure is in `BACKEND-INCIDENT-RESPONSE.md`. Immediate levers that exist in
code:

- `POST /api/kill-switch` — cancels all active turns and rotates the bridge token
  (`webapp.py:722-728`, `turn_core.py:71-77`).
- `keel mcp revoke <name>`, `keel tools revoke <name>` (`cli/main.py:691-739`, `580-614`).
- `keel capability invoke release.revoke --params '{"id":"..."}' --confirm` for a paired
  client (`capability_registry.py:1791-1795`, `keel/src/keel/pairing.py:63-68`).
- `keel execpolicy activate <name>` / `core.flags.set` kill switch to change execution
  posture (`cli/main.py:838-844`, `capability_registry.py:184-190`).
- Preserve `<state_root>/observability.jsonl` and verify with `verify_chain()` before
  any cleanup; generate `keel doctor --bundle` for a redacted snapshot.

Note: `config_contracts` sign-out-everywhere / disconnect are **descriptors and a pure
in-memory ledger** (`config_contracts.py:888-967`); they do not themselves purge stored
credentials. Real credential rotation/revocation must be done at the provider/keyring
and via the token/provider commands above.

---

## 10. Common failures

| Symptom | Diagnosis | Real command / action |
| --- | --- | --- |
| `/api/*` returns 403 | Missing/rotated token or bad Origin | Reopen the URL printed by `keel serve`; `keel gateway status --token ...` (`cli/main.py:396-434`). |
| `keel serve` won't bind | Port in use; only loopback allowed | `keel serve --port <other>` (`cli/main.py:122-143`). |
| Routines stop firing | Daemon disabled or process restarted | Check `KEEL_FLEET_SCHEDULER_DISABLED`; restart `keel serve`; inspect `GET /api/gateway`. |
| Routine stuck / timing out | Worker exceeded timeout | `KEEL_FLEET_ROUTINE_TIMEOUT_S`; scheduler fails closed and releases the claim (`scheduler.py:194-238`). |
| `policy_error` on capability invoke | Malformed saved policy | `keel execpolicy validate <policy.json>` then `activate` (`cli/main.py:851-877`). |
| Version gate fails | `0.1.1` constants out of sync | `python scripts/check_version_sync.py` (`keel/scripts/check_version_sync.py`). |
| Observability writes rejected | Hash chain corrupt / lock stale | `verify_chain()`; 30 s stale-lock recovery (`backend_observability.py:121-184`, `319-323`). |
| Provider check says SKIP | No `--live` or no credential | `keel secrets has <KEY>`; `keel provider validate --live` (`cli/main.py:880-919`, `1215-1234`). |
| Backup restore fails | Wrong passphrase / tampered manifest / newer file | Restore error is `bad_params` (HTTP 400) (`capability_registry.py:1816-1820`); use correct passphrase or explicit overwrite. |
| `keel doctor` shows MISSING tool | Host dependency absent | Install the named tool; doctor reports tool presence (`commands.py:196-205`). |
| Repeated bad launches | start-health threshold reached | `keel capability invoke release.health ...`; `rollback: true` after 3 failures → `updater.rollback` (`start_health.py:40-50`). |

---

## 11. Evidence index

`BACKEND-DEPLOYMENT.md`, `BACKEND-MONITORING.md`, `BACKEND-INCIDENT-RESPONSE.md`,
`PRODUCTION-READINESS-MATRIX.md`, `PRODUCTION-READINESS-REPORT.md`, plus the
root-level `master-plan-v6-*.md` evidence files and
`keel/docs/FINAL-RELEASE-OPERATIONS.md`. All paths above are relative to the worktree
root unless prefixed with `keel/`.
