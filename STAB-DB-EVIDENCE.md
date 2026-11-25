# STAB-DB — Database & Recovery Hardening Evidence

Branch `agent/stab-db`, worktree `C:\Users\Admin\.local\share\opencode\worktree\stab\db`,
baseline commit `f60b080`. Owner scope: `keel/src/keel/backups.py`,
`keel/src/keel/fleet/db.py`, `keel/src/keel/reliability_contracts.py`, new
`keel/tests/test_stab_db_recovery.py`, this evidence file. No frontend, no push.

Environment: Windows, Python 3.11.9, pytest 9.0.2, cryptography 50.0.1.
Every run used an empty, freshly created HOME (both `HOME` and `USERPROFILE`
pointed at a throwaway directory under `C:\Users\Admin\AppData\Local\Temp\opencode`),
with `PYTHONPATH` set to the worktree's `keel\src`. No real user database,
backup directory or ledger was read or modified.

## Commands and counts

PowerShell preamble (replace `<HOME>` with a fresh empty directory):

```powershell
$env:HOME = "<HOME>"
$env:USERPROFILE = $env:HOME
$env:PYTHONPATH = "C:\Users\Admin\.local\share\opencode\worktree\stab\db\keel\src"
cd "C:\Users\Admin\.local\share\opencode\worktree\stab\db\keel"
```

| Phase | Exact command | Result |
| --- | --- | --- |
| Baseline of the three named regression files | `python -m pytest -q tests/test_prod_db_recovery.py tests/test_db_persistence_hardening.py tests/test_prod_recovery.py` | `51 passed in 13.55s` |
| New tests before source fixes | `python -m pytest -q tests/test_stab_db_recovery.py` | `4 failed, 9 passed in 11.76s` — two genuine defects plus two mistakes in my own new test setup (stale CLI backup path pruned before restore; retry test used the real clock). I corrected the test setup; the two genuine failures then reproduced in isolation: `2 failed in 6.03s`. |
| Final four-file gate (fresh clean HOME) | `python -m pytest -q tests/test_stab_db_recovery.py tests/test_prod_db_recovery.py tests/test_db_persistence_hardening.py tests/test_prod_recovery.py` | `64 passed in 40.77s` (`HOME=C:\Users\Admin\AppData\Local\Temp\opencode\stab-db-clean-final`, log `final-gate.log`) |
| Broader regression sweep (fresh clean HOME) | `python -m pytest -q tests/test_backup_endpoints.py tests/test_backups.py tests/test_concurrency_recovery.py tests/test_db_persistence_hardening.py tests/test_event_bus_persistence.py tests/test_prod_db_recovery.py tests/test_prod_recovery.py tests/test_recovery_hardening.py tests/test_stab_db_recovery.py tests/test_fleet*.py` (file list built with `Get-ChildItem` because PowerShell does not pass that glob through to pytest) | `275 passed in 196.35s (0:03:16)` |

Full-suite collection was checked (`python -m pytest -q --collect-only` →
`4506 tests collected in 52.16s`); the whole 4506-test suite was **not** run.
That is a residual verification limit, not a failure.

## Defects found, reproduced failing, then fixed

### HIGH — concurrent first-open migration races (fixed in `keel/fleet/db.py`)

Reproduction: four child processes plus six threads call `connect()` on the
same brand-new `fleet.db`, all released by a shared gate file. Before the fix:

```
['OK:11', 'FAIL:OperationalError:duplicate column name: kind', ...]
```

Three of four processes and five of six threads failed. Cause: `_migrate()`
read `MAX(version)` before another opener had recorded V10, then both attempts
executed the non-idempotent `ALTER TABLE bots ADD COLUMN kind ...`; a separate
attempt also failed with `database is locked` during the PRAGMA/DDL sequence.
`timeout=30` on `sqlite3.connect` does not serialize DDL.

Fix: `connect()` now takes a bounded, cross-process file lock
(`<db>-migrate.lock`, 600 × 50 ms) around the PRAGMAs and `_migrate()`, in
addition to the in-process RLock. The lock is released by the OS if a process
dies mid-migration, so the documented partial-schema behaviour is unchanged.
A failed `connect()` also closes its connection instead of leaking it.

Test: `test_first_open_migration_is_serialized_across_threads_and_processes`.
Before fix: `FAIL:OperationalError:duplicate column name: kind` for 9 of 10
openers. After fix: all 10 report `OK:11`; `integrity_check=ok`, no FK
violations, final schema version 11.

### MEDIUM — truncated database silently backed up as empty (fixed in `keel/src/keel/backups.py`)

Reproduction: a valid fleet DB was truncated to 0 bytes and passed to
`backup_database`. SQLite treats a zero-byte file as a valid empty database, so
`integrity_check` returned `ok` and the backup was published:

```
BACKUP SUCCEEDED {... 'tables': 0, 'records': 0, 'schema_version': None}
```

This destroys the last good snapshot at the moment the live DB is corrupted.
Fix: `_snapshot_database()` now calls `_assert_sqlite_image()`, which requires
at least one legal SQLite page (512 bytes) and the `SQLite format 3\x00`
header before any snapshot is taken; both 0-byte and 100-byte truncations raise
`DatabaseCorruptionError`, and no `.dbbak` artifact is created.

Test: `test_corruption_detection_rejects_byte_flips_fk_violations_and_truncation`.
Before fix: `Failed: DID NOT RAISE <class '...DatabaseCorruptionError'>`.
After fix: byte-flip → `integrity_check` error, FK violation → "foreign key"
error, 0-byte and 100-byte truncations → corruption error, zero backup files.

## Verification matrix (final verdicts)

| Gate | Verdict | Evidence |
| --- | --- | --- |
| SQLite WAL (`journal_mode=wal`), `busy_timeout=30000`, `foreign_keys=ON` | **PASS** | `test_connect_enables_wal_busy_timeout_and_foreign_keys`, `test_transaction_boundaries_and_foreign_keys_are_real` (explicit commit/rollback, cascade delete, FK insert rejected) |
| Transaction boundaries | **PASS** | Same test; migrations still commit at version boundaries, no whole-upgrade transaction (documented below) |
| Concurrent writes from 6+ threads and 4+ processes | **PASS** | `test_first_open_migration_is_serialized_across_threads_and_processes` (6 threads + 4 processes, 10/10 clean upgrades); pre-existing `test_concurrent_thread_and_process_writes_are_lossless` (6×20 thread + 4×20 process writes, 200 rows, no loss, backup/restore preserves all 200) |
| Empty / populated / legacy migration; repeated upgrade; data preservation | **PASS** | `test_empty_populated_and_legacy_migrations_preserve_data` (fresh v1→11 three times; legacy v1 with bot+row upgraded three times, data and v10/v6/v9 columns intact); pre-existing `test_migration_from_populated_legacy_schema_preserves_data` |
| Interrupted migration | **PASS (forward-only)** | `test_interrupted_migration_is_forward_only_and_restored_explicitly`: V10 ALTER applied, injected crash before version row; blind retry fails with `duplicate column name: kind`; explicit pre-migration snapshot restore upgrades to 11 with data intact |
| Corruption detection | **PASS** | `test_corruption_detection_rejects_byte_flips_fk_violations_and_truncation`; pre-existing `test_corrupt_source_is_refused_before_backup` |
| Encrypted backup + manifest integrity/hash/AAD | **PASS** | `test_manifest_hash_encryption_and_aad_are_all_verified`: AES-GCM ciphertext, PBKDF2 iterations, wrong passphrase, flipped ciphertext, and re-encrypted-but-tampered manifest all fail closed before any target write |
| Existing-target refusal; sidecar refusal | **PASS** | `test_restore_refuses_existing_target_and_active_sidecars`: target bytes unchanged on refusal; non-empty `-wal` refused even with `overwrite=True`; restore succeeds after sidecar removal |
| Rollback on failed restore | **PASS** | `test_failed_post_write_verification_rolls_back_only_our_restore`: injected failure in final `_db_health` check → `DatabaseRestoreError`, destination byte-identical to previous DB, no `.restore.tmp` leftovers |
| Retention and CLI | **PASS** | `test_retention_and_cli_roundtrip` (`db-backup`, `db-verify`, `db-list`, `db-restore`, wrong-passphrase exit 1; keep=2 removes 2 of 4 backups, foreign file untouched, keep=0 → `BackupRetentionError`); pre-existing retention/CLI tests |
| `RecoveryLedger` crash recovery with real process kill | **PASS** | `test_real_subprocess_kill_mid_task_recovers_partial_output`: child claims task, records `HALF-OUTPUT`, signals ready, parent calls `proc.kill()`; `recover()` reports `interrupted=('kill-task',)`, retires worker, preserves partial output, resume completes at attempt 2; second `recover()` is a no-op. Pre-existing `os._exit(7)` test also passes |
| Idempotency under concurrent duplicate submission | **PASS** | `test_cross_process_duplicate_submission_admits_exactly_once` (4 processes: 1 FIRST, 3 DUP, one ledger record, `ops == 1`); pre-existing 12-thread test |
| Bounded retries; destructive quarantine | **PASS** | `test_bounded_retries_and_destructive_quarantine` (max_attempts=2 → attempt 3 refused; destructive claim without token → `ApprovalRequiredError`, failure → `QUARANTINED`, no blind retry, fresh approval required) |
| Forward-only migration policy honestly documented | **PASS** | `fleet/db.py` module docstring and `BACKEND-DATABASE-RECOVERY.md` state no down migrations and no automatic rollback; `backups.py` documents offline-only restore and unescrowed passphrase |

`keel/src/keel/reliability_contracts.py` was scrutinized but **not modified**: no
HIGH/MEDIUM defect was reproduced in `RecoveryLedger`, `RetryPolicy`,
`RuntimeLifecycle` or the JSONL tail-recovery logic.

## Forward-only migration policy (explicit)

`_migrate()` applies schema versions 1..11 in order and records each version in
`schema_version`. There are **no down migrations** and **no automatic rollback**
of a live database. Versions are not one atomic transaction: a crash between
an `ALTER TABLE` and its `schema_version` insert can leave a partially upgraded
schema whose blind retry fails with `duplicate column name`. The supported
recovery is an explicit, verified snapshot taken *before* the upgrade and
restored with `keel.backups.restore_database` into a fresh database while all
Keel processes are stopped. `restore_database` only rolls back **its own failed
write**; it never claims to undo a migration on the live database. The passphrase
is not escrowed; losing it makes a backup unrecoverable.

## Residual blockers

* No functional blockers in the owned scope; all four named test files plus the
  new tests pass in a clean HOME (64/64), and the broader DB/fleet/recovery
  sweep passes (275/275).
* The full 4506-test suite was collected but not executed; CI remains the gate
  for unrelated modules.
* Runtime policy limits by design (not defects): schema upgrades are
  forward-only with restore-based recovery; database restore is offline-only
  and refuses active WAL/SHM/journal sidecars.
