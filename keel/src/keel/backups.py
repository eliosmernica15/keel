"""Encrypted backup and restore (B4.11).

Real AES-256-GCM encrypted backups of a local directory, with a derived key
from a user passphrase (PBKDF2-HMAC-SHA256), authenticated file manifests and
verified restore. All data stays on the user's machine.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
import sqlite3
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath

# Windows keeps a short lock on a file while another thread has it open;
# os.replace onto that path can transiently fail with WinError 5/32. The
# staging file stays intact between attempts, so retrying preserves atomicity.
_REPLACE_ATTEMPTS = 5
_REPLACE_BACKOFF_S = 0.02

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

ITERATIONS = 200_000
SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "dist", "build"})


class BackupError(RuntimeError):
    pass


def _derive(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                    salt=salt, iterations=ITERATIONS)
    return kdf.derive(passphrase.encode("utf-8"))


def _replace_with_retry(tmp: Path, target: Path) -> None:
    """os.replace with a bounded retry for transient Windows file locks.

    Only sharing/access failures are retried; every other OSError is raised
    immediately. Until the rename succeeds the destination is untouched, so
    the previous file remains intact throughout the retries.
    """
    last_exc: OSError | None = None
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(tmp, target)
            return
        except OSError as exc:
            winerror = getattr(exc, "winerror", None)
            if winerror is not None and winerror not in (5, 32):
                raise
            last_exc = exc
            if attempt < _REPLACE_ATTEMPTS - 1:
                time.sleep(_REPLACE_BACKOFF_S)
    raise last_exc  # type: ignore[misc]


def _atomic_write(target: Path, data: bytes) -> None:
    """Write bytes via a sibling temp file + atomic rename.

    An interrupted/failed write must never truncate an existing file: the
    previous version stays byte-for-byte intact until the rename succeeds.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp",
                                    dir=str(target.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        _replace_with_retry(tmp, target)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _safe_member_name(name: str) -> str:
    """Reject archive member names that could escape the destination root."""
    if (not name or name.startswith("/") or "\\" in name or ":" in name
            or name != name.strip() or "\x00" in name):
        raise BackupError(f"unsafe path in backup: {name!r}")
    parts = PurePosixPath(name).parts
    if not parts or any(part in ("..", "") for part in parts):
        raise BackupError(f"unsafe path in backup: {name!r}")
    return str(PurePosixPath(*parts))


def _tar_bytes(source: Path) -> tuple[bytes, list[dict]]:
    buffer = io.BytesIO()
    entries = []
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
                continue
            rel = path.relative_to(source).as_posix()
            data = path.read_bytes()
            info = tarfile.TarInfo(rel)
            info.size = len(data)
            info.mtime = int(path.stat().st_mtime)
            archive.addfile(info, io.BytesIO(data))
            entries.append({"path": rel, "bytes": len(data),
                            "sha256": hashlib.sha256(data).hexdigest(),
                            "mtime": info.mtime})
    return buffer.getvalue(), entries


def create_backup(source: str | Path, target: str | Path,
                  passphrase: str) -> dict:
    """Create an encrypted backup file; returns the manifest metadata."""
    if not passphrase:
        raise BackupError("a passphrase is required")
    source = Path(source)
    if not source.is_dir():
        raise BackupError(f"not a directory: {source}")
    payload, entries = _tar_bytes(source)
    salt = os.urandom(16)
    nonce = os.urandom(12)
    ciphertext = AESGCM(_derive(passphrase, salt)).encrypt(nonce, payload, None)
    doc = {
        "format": "keel-backup-v1",
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "entries": entries,
        "kdf": "PBKDF2-HMAC-SHA256", "iterations": ITERATIONS,
        "salt": salt.hex(), "nonce": nonce.hex(),
        "ciphertext": ciphertext.hex(),
    }
    target = Path(target)
    # Write to a temp file and rename: a crash or a disk error during the
    # write leaves the previous (valid) backup untouched, never a truncated
    # file that passes the format check but fails on restore.
    _atomic_write(target, json.dumps(doc).encode("utf-8"))
    return {"format": doc["format"], "files": len(entries),
            "bytes": len(payload), "path": str(target)}


def restore_backup(backup: str | Path, destination: str | Path,
                   passphrase: str, *, overwrite: bool = False) -> list[str]:
    """Verify and restore an encrypted backup; returns restored file paths.

    The entire archive is authenticated and checked against the manifest
    before *any* file is written, so a damaged backup cannot leave a partial
    restore behind. Files that are newer on disk than the archived version
    are protected unless ``overwrite=True`` is explicitly requested.
    """
    try:
        doc = json.loads(Path(backup).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BackupError(f"cannot read backup: {exc}") from None
    if doc.get("format") != "keel-backup-v1":
        raise BackupError("unsupported backup format")
    try:
        payload = AESGCM(_derive(passphrase, bytes.fromhex(doc["salt"]))).decrypt(
            bytes.fromhex(doc["nonce"]), bytes.fromhex(doc["ciphertext"]), None)
    except Exception:
        raise BackupError("wrong passphrase or corrupted backup") from None
    expected = {}
    for entry in doc.get("entries", []):
        name = _safe_member_name(entry["path"])
        expected[name] = entry
    destination = Path(destination)

    # Pass 1: validate every member and stage its bytes in memory. No
    # destination writes happen until the whole archive has been verified.
    staged: list[tuple[str, bytes, object]] = []
    seen: set[str] = set()
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                name = _safe_member_name(member.name)
                entry = expected.get(name)
                if entry is None:
                    raise BackupError(
                        f"manifest mismatch: {name!r} is not in the backup manifest")
                data = archive.extractfile(member).read()
                if entry["sha256"] != hashlib.sha256(data).hexdigest():
                    raise BackupError(f"integrity check failed: {name}")
                staged.append((name, data, entry.get("mtime")))
                seen.add(name)
    except tarfile.TarError as exc:
        raise BackupError(f"corrupted backup archive: {exc}") from None

    missing = sorted(set(expected) - seen)
    if missing:
        raise BackupError(
            f"manifest mismatch: missing archived files: {', '.join(missing)}")

    # Pass 2: refuse to clobber files changed after the backup was taken.
    if not overwrite:
        for name, data, _mtime in staged:
            target = destination / name
            if not target.is_file():
                continue
            if hashlib.sha256(target.read_bytes()).hexdigest() == hashlib.sha256(
                    data).hexdigest():
                continue  # already identical; no state can be lost
            archived_mtime = expected[name].get("mtime")
            if archived_mtime is None:
                continue  # legacy backup without timestamps: nothing to compare
            try:
                if target.stat().st_mtime > float(archived_mtime) + 1.0:
                    raise BackupError(
                        f"refusing to overwrite newer file: {name} "
                        "(pass overwrite=True to force)")
            except (TypeError, ValueError):
                continue

    # Pass 3: write. Each file is replaced atomically so a mid-restore failure
    # never leaves a half-written file at the destination.
    destination.mkdir(parents=True, exist_ok=True)
    restored = []
    for name, data, mtime in staged:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(target, data)
        if mtime is not None:
            try:
                os.utime(target, (float(mtime), float(mtime)))
            except (OSError, TypeError, ValueError):
                pass
        restored.append(name)
    return sorted(restored)


# ---------------------------------------------------------------------------
# Production database backup / restore (SQLite)
# ---------------------------------------------------------------------------
#
# The generic directory backup above is for arbitrary project files. Database
# state needs a different path: a live WAL database cannot be copied
# byte-for-byte, and an unverified backup is not a backup. This section uses
# the SQLite online backup API to take a consistent snapshot, validates that
# snapshot (integrity + foreign keys + records + indexes), encrypts it with an
# authenticated envelope, and only ever restores into a fresh disposable
# database after full verification. No live database is ever overwritten by
# this module automatically.
#
# Real limits (see BACKEND-DATABASE-RECOVERY.md):
#   * migrations in keel.fleet.db are not a single transaction across versions;
#     an interrupted migration can leave a partially upgraded schema. Recovery
#     is an explicit restore of a pre-migration snapshot, not an auto-rollback.
#   * restore is offline-only: stop all Keel processes first, and remove any
#     non-empty WAL/SHM/journal sidecar before replacing a database.
#   * the passphrase is not escrowed. Losing it makes the backup unrecoverable.

DB_BACKUP_FORMAT = "keel-db-backup-v1"
DB_BACKUP_PREFIX = "keel-db-"
DB_BACKUP_SUFFIX = ".dbbak"
_DB_BUSY_TIMEOUT_MS = 30_000
_AAD_FIELDS = ("format", "created", "source", "schema_version", "tables",
               "counts", "indexes", "sha256", "bytes", "integrity",
               "kdf", "iterations", "salt", "nonce")


class DatabaseBackupError(BackupError):
    """Base class for database backup/restore failures."""


class DatabaseCorruptionError(DatabaseBackupError):
    """A live database or snapshot failed an integrity/constraint check."""


class DatabaseBackupValidationError(DatabaseBackupError):
    """A backup artifact is missing, damaged, tampered with, or inconsistent."""


class DatabaseRestoreError(DatabaseBackupError):
    """A restore could not be completed safely."""


class BackupRetentionError(DatabaseBackupError):
    """Backup retention/cleanup failed."""


def _sqlite_uri(path: Path, *, read_only: bool) -> str:
    """Build an escaped SQLite URI (handles spaces and Windows drive letters)."""
    uri = path.resolve().as_uri()
    return f"{uri}?mode=ro" if read_only else uri


def _db_busy_timeout(conn: sqlite3.Connection) -> None:
    conn.execute(f"PRAGMA busy_timeout={_DB_BUSY_TIMEOUT_MS}")


def _db_health(conn: sqlite3.Connection, *, context: str) -> None:
    """Fail closed on structural corruption or foreign-key violations."""
    try:
        checks = [str(row[0]) for row in conn.execute(
            "PRAGMA integrity_check").fetchall()]
        if not checks or any(result != "ok" for result in checks):
            raise DatabaseCorruptionError(
                f"{context}: integrity_check failed: {', '.join(checks)[:500]}")
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    except sqlite3.DatabaseError as exc:
        raise DatabaseCorruptionError(
            f"{context}: integrity_check failed (SQLite rejected validation): "
            f"{exc}") from None
    if violations:
        raise DatabaseCorruptionError(
            f"{context}: {len(violations)} foreign key violation(s); repair "
            "the live database before backing it up")


def _db_meta(conn: sqlite3.Connection) -> dict:
    """Observable schema/record fingerprint used to validate snapshots."""
    try:
        tables = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        indexes = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        counts: dict[str, int] = {}
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            counts[table] = int(conn.execute(
                f"SELECT COUNT(*) FROM {quoted}").fetchone()[0])
        version = None
        if "schema_version" in tables:
            value = conn.execute(
                "SELECT MAX(version) FROM schema_version").fetchone()[0]
            version = int(value) if value is not None else None
    except sqlite3.DatabaseError as exc:
        raise DatabaseCorruptionError(
            f"SQLite error while reading database schema: {exc}") from None
    return {"tables": tables, "indexes": indexes, "counts": counts,
            "schema_version": version}


def _db_aad(doc: dict) -> bytes:
    """Bind the plaintext manifest to the ciphertext (authenticated data)."""
    try:
        header = {field: doc[field] for field in _AAD_FIELDS}
    except KeyError as exc:
        raise DatabaseBackupValidationError(
            f"missing database backup field: {exc}") from None
    return json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")


_SQLITE_HEADER = b"SQLite format 3\x00"
_MIN_SQLITE_BYTES = 512  # smallest legal SQLite page


def _assert_sqlite_image(source: Path) -> None:
    """Reject truncated/empty files before SQLite can treat them as empty DBs.

    SQLite considers a zero-byte file a valid empty database, so integrity_check
    alone cannot detect a truncated source. Backing one up would silently
    replace a real database's last good snapshot with an empty one.
    """
    try:
        size = source.stat().st_size
        with source.open("rb") as handle:
            header = handle.read(len(_SQLITE_HEADER))
    except OSError as exc:
        raise DatabaseCorruptionError(
            f"cannot read source database {source.name}: {exc}") from None
    if size < _MIN_SQLITE_BYTES or header != _SQLITE_HEADER:
        raise DatabaseCorruptionError(
            f"source database {source.name} is not a valid SQLite image "
            f"({size} bytes); refusing to back up a truncated file")


def _snapshot_database(source: Path, staging: Path) -> dict:
    """Copy a consistent, validated snapshot of *source* into *staging*."""
    _assert_sqlite_image(source)
    src = sqlite3.connect(_sqlite_uri(source, read_only=True), uri=True)
    try:
        _db_busy_timeout(src)
        _db_health(src, context=f"source database {source.name}")
        # No exact row-count comparison against the source: a live WAL writer
        # may legitimately commit while the online backup is running. The
        # manifest describes the consistent snapshot that was actually taken.
        dst = sqlite3.connect(str(staging))
        try:
            _db_busy_timeout(dst)
            dst.execute("PRAGMA foreign_keys=ON")
            src.backup(dst)  # online backup: consistent even with live WAL writers
            dst.commit()
            # A single rollback-journal file can be transported and verified
            # as one byte string. This changes only the staging copy, never
            # the live database's journal mode.
            dst.execute("PRAGMA journal_mode=DELETE")
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()
    check = sqlite3.connect(str(staging))
    try:
        _db_busy_timeout(check)
        _db_health(check, context="database snapshot")
        after = _db_meta(check)
    finally:
        check.close()
    return after


def verify_database_backup(backup: str | Path, passphrase: str, *,
                           expected_source: str | Path | None = None) -> dict:
    """Decrypt and fully verify a database backup without writing anything.

    Verification covers: envelope authentication, payload digest/size, SQLite
    integrity, foreign keys, and the exact table/index/record fingerprint
    recorded in the manifest. Corruption or mismatch raises a typed error.
    """
    doc, payload = _load_db_backup(Path(backup), passphrase)
    if expected_source is not None and doc.get("source") != Path(expected_source).name:
        raise DatabaseBackupValidationError(
            "database backup does not belong to the expected source")
    conn = sqlite3.connect(":memory:")
    try:
        try:
            conn.deserialize(payload)
        except Exception as exc:
            raise DatabaseBackupValidationError(
                f"cannot read database image from backup: {exc}") from None
        try:
            _db_health(conn, context="database backup")
            actual = _db_meta(conn)
        except (sqlite3.DatabaseError, DatabaseCorruptionError) as exc:
            raise DatabaseBackupValidationError(
                f"database backup failed integrity validation: {exc}") from None
    finally:
        conn.close()
    expected = {"tables": doc.get("tables"), "indexes": doc.get("indexes"),
                "counts": doc.get("counts"),
                "schema_version": doc.get("schema_version")}
    if actual != expected:
        raise DatabaseBackupValidationError(
            "database backup contents do not match its manifest")
    return {"format": doc["format"], "path": str(backup),
            "source": doc["source"], "created": doc["created"],
            "sha256": doc["sha256"], "bytes": doc["bytes"],
            "schema_version": actual["schema_version"],
            "tables": actual["tables"], "indexes": actual["indexes"],
            "counts": actual["counts"], "records": sum(actual["counts"].values())}


def _load_db_backup(backup: Path, passphrase: str) -> tuple[dict, bytes]:
    try:
        doc = json.loads(backup.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DatabaseBackupValidationError(
            f"cannot read database backup: {exc}") from None
    if not isinstance(doc, dict) or doc.get("format") != DB_BACKUP_FORMAT:
        raise DatabaseBackupValidationError("unsupported database backup format")
    if not passphrase:
        raise DatabaseBackupValidationError("a passphrase is required")
    aad = _db_aad(doc)
    try:
        if doc.get("iterations") != ITERATIONS or doc.get("kdf") != "PBKDF2-HMAC-SHA256":
            raise ValueError("unsupported KDF parameters")
        key = _derive(passphrase, bytes.fromhex(doc["salt"]))
        payload = AESGCM(key).decrypt(
            bytes.fromhex(doc["nonce"]), bytes.fromhex(doc["ciphertext"]), aad)
    except Exception:
        raise DatabaseBackupValidationError(
            "wrong passphrase or corrupted database backup") from None
    if hashlib.sha256(payload).hexdigest() != doc.get("sha256"):
        raise DatabaseBackupValidationError("database backup digest mismatch")
    if len(payload) != doc.get("bytes"):
        raise DatabaseBackupValidationError("database backup size mismatch")
    return doc, payload


def backup_database(db_path: str | Path, backup_dir: str | Path, passphrase: str,
                    *, keep: int | None = None) -> dict:
    """Create a verified, encrypted, consistent snapshot of a SQLite database.

    The live database is opened read-only; WAL frames are captured through the
    online backup API and are never checkpointed or deleted by this function.
    The returned artifact is verified after it is written, before retention is
    applied. ``keep`` (when set) prunes older backups of the same source.
    """
    source = Path(db_path)
    if not source.is_file():
        raise DatabaseBackupError(f"not a database file: {source}")
    if not passphrase:
        raise DatabaseBackupError("a passphrase is required")
    directory = Path(backup_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    final = directory / (
        f"{DB_BACKUP_PREFIX}{stamp}-{secrets.token_hex(4)}{DB_BACKUP_SUFFIX}")

    with tempfile.TemporaryDirectory(prefix=".keel-db-snapshot-",
                                     dir=str(directory)) as tmp:
        staging = Path(tmp) / "snapshot.db"
        meta = _snapshot_database(source, staging)
        payload = staging.read_bytes()

    salt = os.urandom(16)
    nonce = os.urandom(12)
    digest = hashlib.sha256(payload).hexdigest()
    doc = {
        "format": DB_BACKUP_FORMAT,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": source.name,
        "schema_version": meta["schema_version"],
        "tables": meta["tables"], "indexes": meta["indexes"],
        "counts": meta["counts"],
        "sha256": digest, "bytes": len(payload), "integrity": "ok",
        "kdf": "PBKDF2-HMAC-SHA256", "iterations": ITERATIONS,
        "salt": salt.hex(), "nonce": nonce.hex(),
    }
    doc["ciphertext"] = AESGCM(_derive(passphrase, salt)).encrypt(
        nonce, payload, _db_aad(doc)).hex()

    # The staging file is fully verified before publication; if the published
    # bytes fail verification, undo only our own write (never the live DB).
    previous = final.read_bytes() if final.is_file() else None
    try:
        _atomic_write(final, json.dumps(doc).encode("utf-8"))
        info = verify_database_backup(final, passphrase)
    except BaseException:
        try:
            if previous is not None:
                _atomic_write(final, previous)
            else:
                final.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    result = {"format": doc["format"], "path": str(final),
              "sha256": digest, "bytes": doc["bytes"],
              "schema_version": info["schema_version"],
              "tables": len(info["tables"]), "records": info["records"]}
    if keep is not None:
        result["retention"] = prune_database_backups(
            directory, keep=keep, source=source.name)
    return result


def list_database_backups(backup_dir: str | Path) -> list[dict]:
    """List readable database backup manifests (header only, no decryption)."""
    directory = Path(backup_dir)
    if not directory.is_dir():
        return []
    found = []
    for path in sorted(directory.glob(f"{DB_BACKUP_PREFIX}*{DB_BACKUP_SUFFIX}")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # unknown/corrupt files are left untouched
        if not isinstance(doc, dict) or doc.get("format") != DB_BACKUP_FORMAT:
            continue
        found.append({"path": str(path), "source": doc.get("source"),
                      "created": doc.get("created", ""),
                      "mtime": path.stat().st_mtime,
                      "sha256": doc.get("sha256"),
                      "schema_version": doc.get("schema_version"),
                      "bytes": doc.get("bytes")})
    return found


def prune_database_backups(backup_dir: str | Path, *, keep: int = 5,
                           source: str | Path | None = None,
                           dry_run: bool = False) -> dict:
    """Keep the newest ``keep`` verified-format backups, remove the rest.

    Only this module's own recognizable artifacts are eligible. A malformed
    or foreign file in the directory is never deleted.
    """
    if not isinstance(keep, int) or isinstance(keep, bool) or keep < 1:
        raise BackupRetentionError("keep must be a positive integer")
    entries = list_database_backups(backup_dir)
    if source is not None:
        wanted = Path(source).name
        entries = [entry for entry in entries if entry["source"] == wanted]
    entries.sort(key=lambda e: (str(e.get("created") or ""),
                                 e["mtime"], e["path"]), reverse=True)
    kept = [entry["path"] for entry in entries[:keep]]
    removed = [entry["path"] for entry in entries[keep:]]
    if not dry_run:
        for name in removed:
            try:
                Path(name).unlink()
            except OSError as exc:
                raise BackupRetentionError(
                    f"cannot remove old database backup {name}: {exc}") from None
    return {"kept": kept, "removed": removed, "dry_run": bool(dry_run)}


def restore_database(backup: str | Path, destination: str | Path, passphrase: str,
                     *, overwrite: bool = False) -> dict:
    """Verify a database backup and install it as a fresh disposable database.

    The entire artifact is decrypted and validated before any destination
    write. The verified image is then staged next to the destination, renamed
    atomically, and re-verified in place. A failed post-write check removes or
    restores the destination to its previous bytes; nothing else is touched.
    """
    doc, payload = _load_db_backup(Path(backup), passphrase)
    expected = {"tables": doc.get("tables"), "indexes": doc.get("indexes"),
                "counts": doc.get("counts"),
                "schema_version": doc.get("schema_version")}
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not overwrite:
        raise DatabaseRestoreError(
            "destination already exists; pass overwrite=True to replace it")
    sidecars = [Path(str(destination) + suffix)
                for suffix in ("-wal", "-shm", "-journal")]
    for sidecar in sidecars:
        if sidecar.is_file() and sidecar.stat().st_size > 0:
            raise DatabaseRestoreError(
                f"destination has an active SQLite sidecar ({sidecar.name}); "
                "stop all Keel processes and checkpoint before restoring")
    previous = destination.read_bytes() if destination.is_file() else None

    fd, staging_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".restore.tmp",
        dir=str(destination.parent))
    staging = Path(staging_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        conn = sqlite3.connect(str(staging))
        try:
            _db_busy_timeout(conn)
            try:
                _db_health(conn, context="restore staging database")
                actual = _db_meta(conn)
            except (sqlite3.DatabaseError, DatabaseCorruptionError) as exc:
                raise DatabaseBackupValidationError(
                    f"database backup failed integrity validation: {exc}") from None
        finally:
            conn.close()
        if actual != expected:
            raise DatabaseBackupValidationError(
                "database backup contents do not match its manifest")
        for sidecar in sidecars:
            try:
                sidecar.unlink(missing_ok=True)
            except OSError as exc:
                raise DatabaseRestoreError(
                    f"cannot remove stale sidecar {sidecar.name}: {exc}") from None
        _replace_with_retry(staging, destination)
    except BaseException:
        try:
            staging.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    try:
        check = sqlite3.connect(_sqlite_uri(destination, read_only=True), uri=True)
        try:
            _db_busy_timeout(check)
            _db_health(check, context=f"restored database {destination.name}")
            installed = _db_meta(check)
        finally:
            check.close()
        if installed == expected:
            return {"path": str(destination), "source": doc["source"],
                    "created": doc["created"], "sha256": doc["sha256"],
                    "schema_version": installed["schema_version"],
                    "tables": installed["tables"], "indexes": installed["indexes"],
                    "counts": installed["counts"],
                    "records": sum(installed["counts"].values())}
    except (sqlite3.DatabaseError, DatabaseCorruptionError):
        pass
    # A post-write mismatch or corruption rolls back our own restore write
    # only. No automatic live-DB rollback is attempted or implied.
    try:
        if previous is not None:
            _atomic_write(destination, previous)
        else:
            destination.unlink(missing_ok=True)
    except OSError:
        pass
    raise DatabaseRestoreError("restored database failed post-write verification")


def main(argv: list[str] | None = None) -> int:
    """CLI: python -m keel.backups {db-backup,db-verify,db-restore,db-list,db-prune}."""
    import argparse

    parser = argparse.ArgumentParser(prog="python -m keel.backups")
    sub = parser.add_subparsers(dest="command", required=True)

    def passphrase_arg(cmd):
        cmd.add_argument("--passphrase", default=os.environ.get(
            "KEEL_BACKUP_PASSPHRASE"), help="or set KEEL_BACKUP_PASSPHRASE")

    p = sub.add_parser("db-backup", help="snapshot a SQLite database")
    p.add_argument("--db", required=True)
    p.add_argument("--dir", required=True, dest="backup_dir")
    passphrase_arg(p)
    p.add_argument("--keep", type=int, default=None)

    p = sub.add_parser("db-verify", help="verify a database backup")
    p.add_argument("--backup", required=True)
    passphrase_arg(p)

    p = sub.add_parser("db-restore", help="restore into a fresh database")
    p.add_argument("--backup", required=True)
    p.add_argument("--to", required=True, dest="destination")
    passphrase_arg(p)
    p.add_argument("--overwrite", action="store_true")

    p = sub.add_parser("db-list", help="list database backups")
    p.add_argument("--dir", required=True, dest="backup_dir")

    p = sub.add_parser("db-prune", help="apply retention to database backups")
    p.add_argument("--dir", required=True, dest="backup_dir")
    p.add_argument("--keep", type=int, default=5)
    p.add_argument("--source", default=None)
    p.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "db-backup":
            result = backup_database(args.db, args.backup_dir, args.passphrase,
                                     keep=args.keep)
        elif args.command == "db-verify":
            result = verify_database_backup(args.backup, args.passphrase)
        elif args.command == "db-restore":
            result = restore_database(args.backup, args.destination,
                                      args.passphrase, overwrite=args.overwrite)
        elif args.command == "db-list":
            result = {"backups": list_database_backups(args.backup_dir)}
        else:
            result = prune_database_backups(args.backup_dir, keep=args.keep,
                                            source=args.source,
                                            dry_run=args.dry_run)
    except DatabaseBackupError as exc:
        print(f"{type(exc).__name__}: {exc}")
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via CLI tests below
    raise SystemExit(main())
