# FINAL DATABASE & STATE-RELIABILITY EVIDENCE

Branch `agent/final-db` · base HEAD `35fb2b8` · verification date 2026-11-25.
Every probe used disposable temp directories and a **clean HOME** (`<temp>/final-db-cleanhome*`);
no real user database, backup directory or settings file was read, backed up,
migrated or overwritten.

## Scope and ownership

| File | Role |
| --- | --- |
| `keel/src/keel/settings.py` | authoritative `default_state_root()` |
| `keel/src/keel/settings_store.py` | durable settings under that root |
| `keel/src/keel/fleet/db.py` | fleet.db schema, WAL/FK pragmas, migrations, cross-process lock |
| `keel/src/keel/backups.py` | encrypted, verified snapshot / restore / retention / CLI |
| `keel/tests/test_final_db.py` | NEW verification + regression tests |
| this file | exact commands, counts, verdicts, honest policy |

No frontend files were edited. No push was performed.

---

## Verdict summary

| Area | Verdict | Evidence |
| --- | --- | --- |
| Absolute state root, CLI/web/store/DB agreement | **FIXED** (was broken) | Defect D1; tests 1–5 |
| SQLite WAL / busy timeout / FKs / transactions | PASS | tests 6, 7 |
| Concurrent writes (6 threads + 4 processes) | PASS | tests 7, 8 |
| Empty / populated / legacy migrations, repeated upgrade | PASS | test 9 |
| Interrupted migration, data preservation | PASS (explicit restore only) | test 10 |
| Corruption detection (flip / FK / truncation / empty) | PASS | test 11 |
| Encrypted backup: manifest / hash / AES-GCM / AAD | PASS | tests 12, 13 |
| Interrupted writes, existing-target + sidecar refusal | PASS | tests 14, 16 |
| Rollback on failed restore | PASS | test 15 |
| Retention + CLI | PASS | test 17 |
| Forward-only policy documented honestly | PASS | §Forward-only policy, test 18 |

---

## Defect found and fixed

### D1 — fleet.db ignored `KEEL_STATE_DIR` (state-root mismatch)

**Observed before fix** (clean HOME, `KEEL_STATE_DIR` set to a temp dir):

```
state_root: C:\...\Temp\final-db-state
db_path:    C:\...\Temp\final-db-cleanhome2\.keel\fleet.db
equal:      False
```

`keel.fleet.db.default_db_path()` returned `Path.home() / ".keel" / "fleet.db"`,
so `FleetStore()` opened the database in `~/.keel/fleet.db` while the CLI,
web runtime and settings store honoured `KEEL_STATE_DIR`. A relative
`KEEL_STATE_DIR` was also not normalised for an explicitly passed DB path.

**Fix** (`keel/src/keel/fleet/db.py`):

* `default_db_path()` now returns `default_state_root() / "fleet.db"` — the
  single authoritative, absolute root, so DB/CLI/web/store cannot diverge.
* `connect(path)` normalises an explicit path with `os.path.abspath()` so no
  caller can create an accidental relative database file.

**Failing-then-passing:** `tests/test_final_db.py::test_default_db_path_uses_authoritative_state_root`,
`test_connect_without_path_creates_db_only_in_state_root`,
`test_relative_db_path_is_normalised_to_absolute`,
`test_cli_web_store_and_db_share_the_same_root`,
`test_no_relative_keel_fallback_in_database_sources` failed against the
original code (6 failed / 12 passed overall) and pass after the fix.

The remaining 12 new tests — every SQLite, migration, concurrency, corruption,
encrypted backup/restore, rollback, retention and CLI probe — **passed against
the original code as well**. No backup/restore defect was found, so none was
invented or "fixed"; those guarantees are verified as-is. One sixth initial
failure was a test-harness syntax error in the subprocess probe, corrected in
the test itself (not a product defect). No other source file was changed.

---

## Exact commands and counts

All commands were run from `C:\Users\Admin\.local\share\opencode\worktree\final\db\keel`
with:

```powershell
$env:PYTHONPATH = 'C:\Users\Admin\.local\share\opencode\worktree\final\db\keel\src'
$env:HOME = 'C:\Users\Admin\AppData\Local\Temp\opencode\final-db-cleanhome*'
$env:USERPROFILE = $env:HOME
python -m pytest ... -q --tb=short
```

1. **Baseline, four specified suites (before fix):**

   ```
   python -m pytest tests/test_prod_db_recovery.py tests/test_db_persistence_hardening.py `
     tests/test_stab_db_recovery.py tests/test_stab_lifecycle.py -q --tb=short
   ```
   → **52 passed, 1 skipped in 26.53s** (the skip is the POSIX-only SIGINT case).

2. **New test module before fix:**

   ```
   python -m pytest tests/test_final_db.py -q --tb=short
   ```
   → **6 failed, 12 passed in 18.12s** (all six failures are the D1 state-root
   regressions; every backup/migration/concurrency test already passed).

3. **New test module after fix:**

   ```
   python -m pytest tests/test_final_db.py -q --tb=short
   ```
   → **18 passed in 11.92s**.

4. **New + all four specified suites after fix (clean HOME):**

   ```
   python -m pytest tests/test_final_db.py tests/test_prod_db_recovery.py `
     tests/test_db_persistence_hardening.py tests/test_stab_db_recovery.py `
     tests/test_stab_lifecycle.py -q --tb=short
   ```
   → **70 passed, 1 skipped in 64.39s**.

5. **Full repository suite after fix (clean HOME):**

   ```
   python -m pytest -q --tb=short
   ```
   → **4628 passed, 54 skipped, 3707 subtests passed in 1135.85s (0:18:55)**.
   This is the merged-candidate baseline of 4610 passed plus the 18 new
   verification tests; no pre-existing test regressed.

---

## What the tests actually prove

### State root
`default_state_root()` resolves `KEEL_STATE_DIR` (relative values against CWD,
`~` expanded) and otherwise `HOME/.keel`, always absolute. `test_cli_web_store_and_db_share_the_same_root`
starts real subprocesses and checks the CLI `_state_root()`, `webapp._state_root()`,
`settings_store.STATE_DIR` and `fleet.db.default_db_path()` resolve identically.
A source-level guard rejects any `KEEL_STATE_DIR` → `.keel` relative fallback.

### SQLite and concurrency
`connect()` sets WAL, a 30 000 ms busy timeout and `foreign_keys=ON`, and the
tests exercise commit/rollback/`ON DELETE CASCADE`. Six threads and four
separate Python processes perform 20 `BEGIN IMMEDIATE` writes each against one
WAL database: **200 distinct rows, no loss, `integrity_check = ok`**. First-open
migration is serialized by a thread lock + OS file lock: 6 threads and 4
processes all observe schema version 11 with a clean integrity/FK check.

### Migrations
Empty, populated-legacy (v1) and repeated opens all reach schema version 11
without losing rows. The forward-only V10 `ALTER TABLE` is deliberately **not**
rewound: a simulated crash after it leaves a schema on which a blind retry
fails with `duplicate column name`; recovery is an **explicit** verified
snapshot restore, not an automatic downgrade.

### Corruption and backup safety
Byte flips → `integrity_check` failure; orphan rows → `foreign_key_check`
failure; zero/100-byte files → rejected before backup. The encrypted envelope
is `keel-db-backup-v1` (AES-256-GCM, PBKDF2-HMAC-SHA256, 200 000 iterations);
the manifest header is bound as GCM associated data and the payload has a
SHA-256 digest and byte count. Wrong passphrase, flipped ciphertext and
rebound manifest fields are all rejected **before any destination write**.
An existing target and a non-empty `-wal`/`-shm`/`-journal` sidecar are refused
unless `overwrite=True`; a failed post-write check restores the previous bytes
byte-for-byte and leaves no `.restore.tmp`. Retention keeps the newest N format
files and leaves foreign files alone; the CLI round-trips backup/verify/list/
restore/prune with typed exit status 1 on a wrong passphrase.

---

## Forward-only migration policy (honest statement)

* Migrations are numbered 1…11 and recorded in `schema_version`. On a healthy
  database each runs at most once; repeated opens are harmless.
* They are **not** one transaction. A process killed mid-migration can leave a
  partially upgraded schema (e.g. V10's `ALTER TABLE` applied but its version
  row not yet written). A blind retry can then fail.
* **There are no down migrations and no automatic rollback.** Recovery is an
  explicit restore of a pre-migration snapshot taken with
  `keel.backups.backup_database`, into a fresh destination, offline (stop all
  Keel processes and clear WAL/SHM sidecars first).
* The passphrase is not escrowed; losing it makes a backup unrecoverable.
* No automatic "backup before every migration" is claimed: this codebase
  provides the verified snapshot tooling and CLI, not an implicit pre-migration
  hook.
* No previous evidence document named `BACKEND-DATABASE-RECOVERY.md` exists in
  this tree, so the policy is stated here rather than attributed to a missing
  file.

---

## Blockers

None for the verification itself. One pre-existing condition is recorded, not
claimed as fixed here: several non-owned modules (`custom_tools.py`, `trash.py`,
and the workflow-endpoint block of `webapp.py`) still spell a relative
`KEEL_STATE_DIR` fallback directly. They are outside the files owned by this
task; the authoritative resolver and the database path are now consistent.
