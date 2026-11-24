# Backend database recovery runbook

Authoritative, backend-only runbook for production hardening of Keel's SQLite
state. Scope of this change: `keel/src/keel/backups.py` (database backup and
restore API + CLI), `keel/tests/test_prod_db_recovery.py`, and this document.
No application source (fleet store, routes, webapp) was changed. There is
**no automatic rollback** of a live database anywhere in this design.

---

## 1. Audit of actual SQLite usage

| Location | Behaviour | Gap / note |
| --- | --- | --- |
| `keel/src/keel/fleet/db.py` (`connect`, `_migrate`) | `sqlite3.connect(timeout=30, check_same_thread=False)`, `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`. Schema versioned through `schema_version`; target `SCHEMA_VERSION = 11`. | The 30 s connect timeout provides a busy timeout; there is no separate `PRAGMA busy_timeout` or corruption check in `connect`. Migrations use `executescript()` (implicit `COMMIT`) and a final `conn.commit()`, so a version is **not** atomic as a group and the whole migration is not one transaction. `_DDL_V10` contains a non-idempotent `ALTER TABLE bots ADD COLUMN kind`. No checkpoint call and no clean-shutdown hook; SQLite recovers WAL on next open, and WAL/SHM files are left for SQLite to manage. |
| `keel/src/keel/fleet/service.py` (`FleetStore`) | One shared connection, guarded by an `RLock`, per-method writes with `commit()`. Subscription fan-out is in memory only. | Multi-statement service operations are not wrapped in an explicit `BEGIN`/`COMMIT`; a crash between related writes can leave partial state. The module-level `_connection_lock` in `fleet/db.py` guards *connection creation*, not writes; cross-process coordination relies on SQLite's own locking. |
| `keel/src/keel/resilience.py` | `db_integrity()` runs `PRAGMA integrity_check`; `db_backup()` uses `Connection.backup()` from a read-only URI connection. Exposed through `capability_registry._db_backup`. | Useful primitives, but no encryption, no manifest, no record/index/constraint validation, no retention, and no post-restore verification. Not a production recovery path. |
| `keel/src/keel/z_backend.py` (`DriftStore`) | Shared connection with `RLock`, commit per `record()` call. | No WAL, no explicit busy timeout, no FK enforcement, no integrity check. |
| `keel/src/keel/x3_memory_backend.py` (`_receipt_db`, `_finance_db`) | Fresh connection per call, `CREATE TABLE IF NOT EXISTS`, immediate commit. | Default rollback journal, no WAL/busy timeout/FK checks. Backup these only with all writers stopped. |
| `keel/src/keel/db_explorer.py`, `workbench.py`, `platform_gaps.py` | Read-only URI (`mode=ro`) connections; some SQL keyword filtering. | No busy timeout beyond SQLite's default 5 s, so a reader can fail with `database is locked` during heavy writes. |
| `keel/src/keel/webapp.py` (`/api/backups/create`, `/api/backups/restore`) | Wraps the generic encrypted *directory* backup. | Not a database snapshot: copying a live WAL database byte-for-byte is unsafe. Use the database API below for `fleet.db` and other SQLite files. |

Conclusions: WAL and foreign keys are enabled for the primary fleet database;
busy handling is via `timeout=30` (other SQLite users rely on the 5 s default).
There is no explicit checkpoint or shutdown hook, no corruption gate on open,
and migrations are idempotent by version marker but not transactional.

---

## 2. Backup command and API

All commands run from the repository root with `keel/src` importable. Prefer the
environment variable over `--passphrase` (a command-line secret is visible in
the process list).

```powershell
$env:KEEL_BACKUP_PASSPHRASE = "<long-secret>"

# Consistent snapshot + verification + retention (keep newest 7 for this DB)
python -m keel.backups db-backup --db "$env:USERPROFILE\.keel\fleet.db" `
  --dir "$env:USERPROFILE\.keel\backups" --keep 7

# Inspect / verify (header only vs full authenticated verification)
python -m keel.backups db-list  --dir "$env:USERPROFILE\.keel\backups"
python -m keel.backups db-verify --backup <artifact.dbbak>

# Retention audit, then apply
python -m keel.backups db-prune --dir "$env:USERPROFILE\.keel\backups" --keep 7 --dry-run
python -m keel.backups db-prune --dir "$env:USERPROFILE\.keel\backups" --keep 7
```

Python API (`keel.backups`):

```python
from keel.backups import (backup_database, verify_database_backup,
                          restore_database, list_database_backups,
                          prune_database_backups)

meta = backup_database(db, backup_dir, passphrase, keep=7)
info = verify_database_backup(meta["path"], passphrase, expected_source=db)
restored = restore_database(meta["path"], staging_path, passphrase)
```

How the snapshot works:

1. Open the source **read-only** with an escaped `file:` URI and a 30 s busy
   timeout. Run `PRAGMA integrity_check` and `PRAGMA foreign_key_check`; any
   failure aborts before a single byte is written (fail-closed).
2. Use SQLite's online `Connection.backup()` API, so a live WAL snapshot is
   consistent without checkpointing or deleting WAL frames.
3. Normalise only the *staging* copy to rollback-journal mode, then re-run all
   integrity/constraint checks on it. The live database is never modified.
4. Build a manifest containing `schema_version`, table names, index names and
   per-table row counts from the validated snapshot. Encrypt the snapshot with
   AES-256-GCM (PBKDF2-HMAC-SHA256, 200 000 iterations) and bind the manifest
   to the ciphertext as associated data, so metadata tampering is detected.
5. Publish the artifact with a temp-file + atomic rename, then decrypt and
   verify it again from the published path. A failed verification undoes only
   our own write.
6. Apply retention (if `keep` was supplied) only after the artifact passes.

Artifacts are JSON files named `keel-db-<UTC>-<random>.dbbak`. The plaintext
database is never written to disk outside the disposable staging directory.

---

## 3. Restore steps (offline only)

1. **Stop all Keel processes** that can open the target database. No hot
   restore is supported.
2. Confirm there are no non-empty sidecars next to the destination:
   `<db>-wal`, `<db>-shm`, `<db>-journal`. `restore_database` refuses a
   non-empty sidecar with a typed `DatabaseRestoreError`. Do **not** delete a
   non-empty WAL manually — it may contain committed data.
3. Verify the artifact: `python -m keel.backups db-verify --backup <artifact>`.
   A wrong passphrase or tampered ciphertext is rejected.
4. Restore into a **fresh disposable path**, never straight over production:

   ```python
   result = restore_database(artifact, staging_path, passphrase)
   ```

   The whole artifact is validated before any destination write. The image is
   staged next to the destination, renamed atomically, and re-verified in
   place. A post-write mismatch or corruption removes/rolls back only the
   file this call wrote — it does not roll back the live production DB.
5. Open the staged DB with the normal helper
   (`keel.fleet.db.connect(staging_path)`) and confirm `schema_version == 11`,
   the expected record counts, and that no migration errors occur.
6. Take a new backup of the current (bad) database before replacing anything,
   then swap the staged file into place with `os.replace`/`move` while all
   processes are still stopped. `restore_database(..., overwrite=True)` can do
   the swap itself, but only after the sidecar check in step 2 passes.
7. Restart Keel and check logs/health. `connect()` will switch the restored
   database back to WAL mode on first open; that is expected.

### What is and is not rolled back

* **Is rolled back:** only a failed backup publication or a failed restore
  write performed by this module in that single call.
* **Is not rolled back:** the live database, partial multi-statement writes
  made by application code, a migration that crashed halfway, or a WAL that
  was deleted outside this module. Recovery from those requires an explicit
  restore of a pre-incident snapshot.

---

## 4. Migration procedure and limits

* `keel.fleet.db.connect(path)` creates an empty DB if needed and applies all
  migrations up to `SCHEMA_VERSION` (11). Version markers are recorded in
  `schema_version`; already-applied steps are skipped, so repeated invocation
  is safe. Tests cover empty DB, a populated legacy v1 DB, and repeated opens.
* Data preservation is asserted by comparing rows before and after migration.
* **Interrupted migration is a real limit.** Migrations are not a single
  transaction. If a crash occurs after `ALTER TABLE bots ADD COLUMN kind`
  (v10) but before its `schema_version` row is inserted, a blind retry fails
  with `duplicate column name: kind`. There is no automatic repair. Two safe
  options:
  1. Restore a snapshot taken *before* the migration into a fresh DB and let
     `connect()` migrate that copy (the tested path), or
  2. Manually verify the column/index already exists and insert the missing
     `schema_version` row, then continue — this requires operator judgement
     and is not automated here.
* Never run a migration and a production backup concurrently on the same DB
  if you need the backup to represent the pre-migration state; snapshot first.

---

## 5. Corruption detection and typed errors

`BackupError` is the base. Database-specific subclasses:

| Error | Meaning |
| --- | --- |
| `DatabaseBackupError` | Generic backup/restore failure (missing file, missing passphrase, DB not a file). |
| `DatabaseCorruptionError` | Source/snapshot failed `integrity_check`, `foreign_key_check`, or SQLite raised `DatabaseError` while validating. |
| `DatabaseBackupValidationError` | Artifact format/KDF/passphrase/AAD/digest/size/content mismatch. |
| `DatabaseRestoreError` | Unsafe destination (exists without `overwrite`, active sidecar) or failed post-write verification. |
| `BackupRetentionError` | Invalid `keep` or failed deletion during pruning. |

Validation layers: AES-GCM authentication with manifest as AAD, payload
SHA-256 and byte length, SQLite `integrity_check`, `foreign_key_check`, and an
exact comparison of tables, indexes, row counts and `schema_version` against
the manifest — performed on the artifact *and* after restore. A mismatch
always fails closed; no partial destination state is left by the validated
path.

---

## 6. Retention

* `backup_database(..., keep=N)` prunes older verified-format backups of the
  **same source file name** after the new artifact passes verification.
* `prune_database_backups(dir, keep=N, source=..., dry_run=True)` audits what
  would be removed. Sorting uses the manifest `created` timestamp, then file
  mtime, then path. Default CLI `keep` is 5; `keep` must be >= 1.
* Only `keel-db-*.dbbak` files with a readable `keel-db-backup-v1` header are
  eligible. Foreign files and malformed `.dbbak` files are never deleted.
* Listing is header-only and does not decrypt. Run `db-verify` on each artifact
  before relying on it for an incident; retention does not re-verify payloads.
* Retention permanently deletes files; ensure the destination has adequate
  space and that `keep` matches your policy before enabling it.

---

## 7. Incident steps

1. **Suspected corruption or failed migration:** stop writes immediately;
   preserve the database *and* its `-wal`/`-shm` files by copying all of them
   to an evidence directory. Do not delete sidecars.
2. Identify the last known-good artifact (`db-list`, then `db-verify`). If
   verification fails, try older artifacts; never bypass the passphrase check.
3. Restore to a fresh staging DB as in §3. Compare `schema_version`, table
   list, indexes and record counts with the last healthy observation.
4. If the staging DB is healthy, swap it into production while stopped, then
   restart and verify health. If it is not healthy, escalate — do not attempt
   an in-place repair on the only surviving copy.
5. **Lost passphrase:** there is no key escrow or recovery; an encrypted
   artifact is unrecoverable. Rotate to a new passphrase and take a fresh
   backup after recovery.
6. **Lock contention:** the fleet DB waits up to 30 s; other SQLite helpers
   use SQLite's 5 s default. Find the long-running writer/checkpoint rather
   than deleting WAL/SHM files.
7. Record the artifact SHA-256, restore result, and observed counts in the
   incident log.

---

## 8. Verification

```powershell
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_prod_db_recovery.py','keel/tests/test_db_persistence_hardening.py','keel/tests/test_backups.py']))"
```

(The repository has `test_db_persistence_hardening.py`, not
`test_db_persistence.py`.) Tests use disposable `tmp_path` directories only,
including multi-thread and multi-process writers and an interrupted-migration
recovery scenario; no real user database is touched.
