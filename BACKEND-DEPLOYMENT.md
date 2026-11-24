# Backend Deployment — Keel

**Candidate:** `e57327378f56062db3b13d3db941ac2cf2a641a3`.
**Scope:** deploying the **backend/harness** from source on an operator machine.
This document deliberately distinguishes **backend deployment readiness** (what the
code and tests prove locally) from **full desktop installer release** (unsigned,
owner-gated, and not performed). Source of truth:
`keel/docs/FINAL-RELEASE-OPERATIONS.md`, `keel/pyproject.toml`,
`keel/src/keel/release/cli.py`, `keel/src/keel/release/updater.py`,
`keel/src/keel/fleet/db.py`, `keel/src/keel/settings.py`, `scripts/verify_backend_operation.py`.

---

## 1. Two different readiness standards

| | Backend deployment readiness | Full desktop installer release |
| --- | --- | --- |
| What it means | Source checks out, dependencies install, config validates, DB initializes, `keel serve` starts and stops, backend evidence gate passes | Signed, published, clean-VM-installed, upgrade/rollback-tested installers on each OS |
| Evidence available | Local source + tests (e.g. 4214 passed / 48 skipped / 0 failed on a clean local HOME, `master-plan-v6-test-evidence.md:200-210`; `verify_backend_operation.py`) | Windows 0.1.1 installer rebuilt with 7/7 local integrity checks but **unsigned**; macOS/Linux installers **not built** (`FINAL-RELEASE-OPERATIONS.md:96-126`, `:168-178`) |
| Blocking items | None for local backend use | Signing identity, provider credentials, clean-VM validation, native runners, push/publish authorization (`FINAL-RELEASE-OPERATIONS.md:262-273`) |
| Claim allowed | "Backend deployable and locally verified" | **Not** "production-ready" |

Do not use a passing backend suite or a 7/7 build-integrity report to claim release
readiness (`master-plan-v6-final-report.md:158`).

---

## 2. Clean setup and dependency install

All commands run with **`keel/` as the working directory** (CI pins Python 3.11 and
Node 22; `FINAL-RELEASE-OPERATIONS.md:22-25`).

```bash
cd keel
python -m pip install --upgrade pip
pip install -e . pyinstaller pillow
```

Evidence: `pyproject.toml:1-18` (`requires-python >=3.11`, dependencies
`tzdata>=2024.1`, `cryptography>=42.0`, `keyring>=24.0`, `Pillow>=10.0`, console
script `keel = keel.cli.main:main`); `FINAL-RELEASE-OPERATIONS.md:40-70`.

**Owner-provided inputs:** no account, subscription or hosted service is required for
local operation; provider keys are optional and never mandatory
(`keel/src/keel/AGENTS.md:39`, `DECISIONS.md:246-249`).

---

## 3. Config generation and environment validation

```bash
keel init [--force]              # generate AGENTS.md for the current repo
keel settings schema             # generated JSON schema for typed settings
keel settings show               # resolved values + provenance + diagnostics
keel settings validate <directory>   # non-zero on any malformed *.json
keel doctor                      # tools / provider keys (masked) / state dirs
```

Evidence: `cli/main.py:54-55`, `617-633`, `636-688`, `commands.py:189-212`.

**Set an absolute `KEEL_STATE_DIR` before any non-interactive deployment**: several
subcommands default to relative `.keel` while others use `~/.keel`
(`cli/main.py:286-287`, `cli/main.py:381`, `cli/main.py:827-847`, `cli/main.py:893`;
`settings.py:475-476`). Without this, capabilities, secrets, policies, observability
and backups can address different roots. Full variable list: `BACKEND-OPERATIONS-RUNBOOK.md`
§3 and `keel/src/keel/admin_ops.py:12-20`.

Secrets: configure via the OS keyring, `KEEL_MASTER_PASSPHRASE`, or a `0600`
`master.key`, and via `keel secrets providers` / `keel secrets has`
(`secret_store.py:65-104`, `secret_providers.py:143-160`). Never write values into
settings files in plaintext or into a release artifact.

Version gate (must pass before any build):

```bash
cd keel
python scripts/check_version_sync.py
# on a v* tag: python scripts/check_version_sync.py --tag "${GITHUB_REF#refs/tags/}"
```

Evidence: `FINAL-RELEASE-OPERATIONS.md:27-33`; version is `0.1.1` in
`keel/__init__.py:1-3`, `pyproject.toml:7`.

---

## 4. Database initialization

DB initialization is **implicit**: `fleet.connect()` creates `~/.keel/fleet.db`,
enables WAL + foreign keys, and runs forward-only `_migrate()` (schema versions 1..11)
on first connect (`keel/src/keel/fleet/db.py:237-255`, `258-365`). There is no
`keel db init` command. Starting `keel serve` (which imports fleet routes) is the
normal way to cause first initialization; alternatively call `connect()` from Python.

Before/after any deployment, verify integrity and take a backup via the real APIs:

```bash
# Python API (no CLI subcommand):
#   from keel.resilience import db_integrity, db_backup
#   assert db_integrity("<state_root>/fleet.db")
#   db_backup("<state_root>/fleet.db", "<backup>/fleet.db.bak")
keel capability invoke fleet.audit.export --params '{"db":"<state_root>/fleet.db","target":"<backup>/fleet.db.bak"}' --confirm
```

Evidence: `resilience.py:87-99`, `capability_registry.py:1591-1595`.

**Migration limit:** `_migrate()` is forward-only. `config_contracts.SchemaApplySeam.apply()`
raises `NotImplementedError` and `MigrationDescriptor.executes_sql` is rejected
(`config_contracts.py:760-804`). There is no down-migration; see
`BACKEND-OPERATIONS-RUNBOOK.md` §5 for restore limits.

---

## 5. Startup

```bash
keel serve --port 8739
# or: keel fleet --port 8739 / keel web
```

Evidence: `cli/main.py:119-167`. Startup sequence: `scheduler.start_daemon()` (idempotent;
disable with `KEEL_FLEET_SCHEDULER_DISABLED=1`), then `serve(port)` which binds
`127.0.0.1` and prints the tokenized URL to stderr
(`scheduler.py:343-357`, `webapp.py:1314-1320`).

Startup health tracking: record outcomes with
`keel capability invoke release.health.record --params '{"state_root":"...","version":"0.1.1","ok":true}' --confirm`;
three consecutive failures set `rollback: true` (`start_health.py:40-50`,
`capability_registry.py:1742-1747`).

---

## 6. Readiness verification (backend deployment)

Run these in order; each is real and exists in the tree:

```bash
cd keel
python -m pytest -q -o faulthandler_timeout=120
python scripts/verify_backend_operation.py          # reported-only evidence gate
python scripts/verify_backend_operation.py --strict # enforces the same gate
python scripts/verify_v6_audit.py                    # registry/plan consistency
python scripts/check_version_sync.py
keel doctor
keel doctor --bundle --file ./keel-diagnostics.zip
keel settings validate <config-directory>
keel provider validate                              # static checks; live SKIP without keys
python -m keel.release integrity --dist dist --artifacts release
```

Backend health/readiness signals: `GET /api/health` (liveness),
`backend_observability.health_snapshot()` / `diagnostic_report()` (module import +
chain health), `keel capability invoke release.health` (failed-start state)
(`webapp.py:378`, `backend_observability.py:481-566`, `start_health.py`).

Observed evidence for the candidate family: definitive clean-HOME suite
**4214 passed, 48 skipped, 3707 subtests passed, 0 failed** in 571.95 s
(`master-plan-v6-test-evidence.md:200-210`); earlier integrated-branch run
1296 passed / 46 skipped (`FINAL-RELEASE-OPERATIONS.md:35-38`). Known limitation:
the release audit records that a "definitive" suite was **not reproducible in a clean
checkout** and that the shipped `python -m pytest -q` CI command was red on the audited
HEAD (`master-plan-v6-release-audit.md:140`, `REVIEW-FINAL-QUALITY.md:134`). Treat a
fresh run on the exact candidate as required, not assumed.

---

## 7. Graceful shutdown

- Foreground: **Ctrl+C** → `KeyboardInterrupt` → `server.server_close()`
  (`webapp.py:1321-1327`).
- Before shutdown, stop unsafe/in-flight work: `POST /api/kill-switch` (cancel all
  turns + rotate token) and `POST /api/gateway/stop`
  (`webapp.py:714-728`, `gateway.py:56-63`).
- There is no signal handler for SIGTERM and no service unit in this repository; a
  process supervisor sending SIGTERM gets Python's default termination, not the
  graceful path. Do not claim graceful SIGTERM handling.

---

## 8. Upgrade and rollback

```bash
python -m keel.release build --platform windows --out release
python -m keel.release licenses --out release
python -m keel.release check-artifacts release
python -m keel.release integrity --dist dist --artifacts release
# owner-authorized only:
python -m keel.release publish --artifacts ../artifacts --tag "$RELEASE_TAG" --out release
python -m keel.release verify --manifest release/download.json \
  --compare "https://github.com/${{ github.repository }}/releases/latest/download/download.json" \
  --retries 10 --retry-delay 6 --timeout 600 --require-available
```

Evidence: `FINAL-RELEASE-OPERATIONS.md:40-92`, `keel/src/keel/release/cli.py:24-111`.
`publish` has `--dry-run` and `KEEL_REQUIRE_SIGNED=1` / `--public-key` gating
(`cli.py:39-52`, `cli.py:150-194`). No release has actually been published.

Upgrade mechanics in code: `updater.atomic_install(staged_dir, install_dir, backup_dir)`
renames the current install into `backup_dir` before swapping in the staged one, with
a restore-on-failure path (`release/updater.py:143-159`); `updater.rollback(install_dir,
backup_dir)` restores it (`updater.py:162-167`). `e5_backend.py` health-gates the swap
and journals the transaction with rollback retained (`e5_backend.py:300-369`).
`start_health` advises rollback after three failed starts (`start_health.py:40-50`).
The clean-VM `upgrade_and_rollback` check (install 0.1.0 then 0.1.1, force three failed
starts, verify rollback) is **UNVERIFIED** and must be run on a disposable VM
(`FINAL-RELEASE-OPERATIONS.md:227-249`).

---

## 9. Recovery

1. Preserve evidence first: copy `<state_root>/observability.jsonl` and run
   `keel doctor --bundle --file ...` (redacted).
2. Verify startup-health state via `release.health`; if `rollback: true`, restore the
   previous install with `updater.rollback` (Python API) — no CLI wrapper exists.
3. For data loss, restore from an encrypted `release.backups.restore` capability using
   the matching passphrase; ensure the destination schema version matches the backup
   (forward-only migrations, no downgrade).
4. For DB-only corruption, use `db_integrity` then `db_backup`/restore; do not restore
   an older-schema DB over a newer one.
5. Re-run the readiness sequence in §6 before declaring the node recovered.

See `BACKEND-INCIDENT-RESPONSE.md` for credential/integration revocation ordering.

---

## 10. Owner gates that block a *full* release (not backend deployment)

| Gate | Owner action | Status |
| --- | --- | --- |
| C11.2 repository security | Plan/forge decision; branch protection, signing, forks, 2FA | BLOCKED (`FINAL-RELEASE-OPERATIONS.md:264-269`) |
| Signing identity | Create `KEEL_RELEASE_SIGNING_KEY` / `..._PUBLIC_KEY` or platform certs; add CI sign job | BLOCKED |
| Push / publish authorization | Authorize merging the branch and publishing | BLOCKED |
| Clean-VM + native runners | Run the six external checks and Linux/macOS native suites | UNVERIFIED / BLOCKED |

No push, publication, signing, deployment or credential rotation was performed for
this candidate (`FINAL-RELEASE-OPERATIONS.md:271-273`).
