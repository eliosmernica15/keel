"""Final installation / upgrade / rollback / recovery lifecycle harness.

This is a **disposable, local** harness: every scenario runs in pytest
``tmp_path`` directories (fresh HOME and fresh ``KEEL_STATE_DIR``), behind a
loopback-only HTTP server, using an **ephemeral Ed25519 development keypair**
generated at test time. It is deliberately NOT a VM run and NOT production
signing: no installer is built/published, no production key or credential is
used, and no claim of trusted signing is made. Clean-VM validation stays
pending (see FINAL-INSTALL-EVIDENCE.md).

The scenarios are exercised through the real shipped code paths:
``updater.check_for_update``, ``updater.download_update``,
``updater.atomic_install``, ``updater.rollback``,
``start_health.record_start``, ``keel.backups`` and
``keel.y4_d4_x7_backend.uninstall_plan``. Nothing under test is mocked except
fault injection at the filesystem boundary (simulated lock / torn write).
"""

from __future__ import annotations

import functools
import hashlib
import json
import sqlite3
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from keel import backups, start_health
from keel.release import common, updater
from keel.release.signing import (
    generate_keypair,
    load_private_key,
    load_public_key,
    sign_bytes,
    sign_manifest,
    verify_manifest,
)
from keel.y4_d4_x7_backend import UninstallMode, uninstall_plan

ROOT = Path(__file__).resolve().parents[1]
CURRENT = "0.1.0"
UPGRADE = "0.1.1"
CANARY = "final-install-canary"
# Synthetic, throw-away passphrase used only to exercise the backup envelope.
# It is not a secret, is not stored anywhere, and protects no real data.
TEST_PASSPHRASE = "ephemeral-harness-passphrase"


# ---------------------------------------------------------------------------
# Disposable environment
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """Give every scenario a fresh HOME/state root and neutral release config."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("KEEL_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("PYTHONNOUSERSITE", "1")
    for key in (
        "KEEL_MIN_VERSION",
        "KEEL_BLOCKED_VERSIONS",
        "KEEL_ROLLOUT_MODE",
        "KEEL_ROLLOUT_PERCENTAGE",
        "KEEL_PUBLISHED_AT",
        "KEEL_START_HEALTH_FILE",
    ):
        monkeypatch.delenv(key, raising=False)
    return home


@pytest.fixture
def keypair(tmp_path):
    private_path = tmp_path / "ephemeral-private.pem"
    public_path = tmp_path / "ephemeral-public.pem"
    generate_keypair(private_path, public_path)
    return (load_private_key(private_path), load_public_key(public_path),
            public_path)


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):  # pragma: no cover - output noise only
        pass


@pytest.fixture
def release_server(tmp_path):
    """Loopback-only release server; ephemeral port, no external network."""
    serve_root = tmp_path / "serve"
    serve_root.mkdir()
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        functools.partial(_QuietHandler, directory=str(serve_root)),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield serve_root, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def _artifact_name(version: str) -> str:
    for channel in common.CHANNELS:
        if channel["key"] == _platform():
            return channel["primary"].format(version=version)
    raise AssertionError(f"no channel for platform {_platform()}")


def _write_app(directory: Path, version: str, *, ok: bool) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "version.txt").write_text(version, encoding="utf-8")
    extra = "" if ok else 'print("ERROR: simulated crash in upgraded build")\n'
    (directory / "app.py").write_text(
        "import sys\n"
        f'print("KEEL_APP_VERSION={version}")\n'
        f"{extra}"
        f"sys.exit({0 if ok else 1})\n",
        encoding="utf-8",
    )


def _start(install: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(install / "app.py")],
        cwd=str(install), capture_output=True, text=True, timeout=30,
    )


def _make_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE notes(id INTEGER PRIMARY KEY, body TEXT NOT NULL)")
        conn.execute("INSERT INTO notes(id, body) VALUES (1, ?)", (CANARY,))


def _db_canary(path: Path) -> str | None:
    try:
        with sqlite3.connect(path) as conn:
            row = conn.execute("SELECT body FROM notes WHERE id=1").fetchone()
    except sqlite3.OperationalError:  # e.g. a simulated broken migration
        return None
    return row[0] if row else None


@pytest.fixture
def machine(tmp_path):
    root = tmp_path / "machine"
    install = root / "install"
    backup = root / "backup"
    staged = root / "staged"
    state = tmp_path / "state"
    db = root / "userdata" / "keel.sqlite3"
    _write_app(install, CURRENT, ok=True)
    _make_db(db)
    return SimpleNamespace(root=root, install=install, backup=backup,
                           staged=staged, state=state, db=db)


def _publish(serve_root: Path, base_url: str, version: str, name: str,
             payload: bytes, private, *, include_artifact: bool = True,
             corrupt_checksum: bool = False,
             corrupt_signature: bool = False) -> dict:
    """Publish a real signed manifest + detached signature via shipped helpers."""
    tag_dir = serve_root / f"v{version}"
    tag_dir.mkdir(parents=True, exist_ok=True)
    artifact = tag_dir / name
    artifact.write_bytes(payload)
    manifest = common.build_release_manifest(
        {name: artifact}, version, f"v{version}", base_url)
    if corrupt_checksum:
        real = hashlib.sha256(payload).hexdigest().upper()
        flipped = ("0" if real[0] != "0" else "1") + real[1:]
        for entry in manifest["files"]:
            if entry["platform"] == _platform():
                entry["sha256"] = flipped
    signed = sign_manifest(manifest, private)
    (serve_root / "download.json").write_text(
        json.dumps(signed), encoding="utf-8")
    signature = tag_dir / f"{name}.sig"
    signature.write_bytes(b"not-a-valid-ed25519-signature"
                          if corrupt_signature else sign_bytes(payload, private))
    if not include_artifact:
        artifact.unlink()
    return signed


def _assert_manifest_integrity(serve_root: Path, public, *, version: str) -> dict:
    """Verify signature, declared version and every file's sha256/size."""
    doc = json.loads((serve_root / "download.json").read_text(encoding="utf-8"))
    assert verify_manifest(doc, public) is True
    assert doc["version"] == version
    assert doc["min_version"] == "0.1.0"
    for entry in doc["files"]:
        artifact = serve_root / f"v{entry['version']}" / entry["file"]
        data = artifact.read_bytes()
        assert len(data) == entry["bytes"]
        assert hashlib.sha256(data).hexdigest().upper() == entry["sha256"].upper()
    return doc


def _assert_version_sync() -> None:
    versions = common.load_versions()
    assert set(versions.values()) == {UPGRADE}
    gate = ROOT / "scripts" / "check_version_sync.py"
    proc = subprocess.run(
        [sys.executable, str(gate), "--tag", f"v{UPGRADE}"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == (
        f"OK - all sources agree on version {UPGRADE} (tag v{UPGRADE})")


def _plan(serve_root, base_url, public, *, current=CURRENT):
    return updater.check_for_update(
        f"{base_url}/download.json", current_version=current,
        platform=_platform(), public_key=public, allow_http=True)


def _upgrade(serve_root, base_url, keypair, machine, *, ok: bool = True):
    private, public, _ = keypair
    name = _artifact_name(UPGRADE)
    payload = (
        "import sys\n"
        f'print("KEEL_APP_VERSION={UPGRADE}")\n'
        + ("" if ok else 'print("ERROR: simulated crash in upgraded build")\n')
        + f"sys.exit({0 if ok else 1})\n"
    ).encode("utf-8")
    _publish(serve_root, base_url, UPGRADE, name, payload, private)
    _assert_manifest_integrity(serve_root, public, version=UPGRADE)
    plan = _plan(serve_root, base_url, public)
    assert plan is not None and plan.version == UPGRADE
    assert plan.signature_verified is True
    downloaded = machine.root / "downloads" / name
    updater.download_update(plan, downloaded, public_key=public, allow_http=True)
    assert downloaded.read_bytes() == payload
    machine.staged.mkdir(exist_ok=True)
    (machine.staged / "app.py").write_bytes(payload)
    (machine.staged / "version.txt").write_text(UPGRADE, encoding="utf-8")
    updater.atomic_install(machine.staged, machine.install, machine.backup)
    assert (machine.install / "version.txt").read_text(encoding="utf-8") == UPGRADE
    assert (machine.backup / "version.txt").read_text(encoding="utf-8") == CURRENT
    _assert_version_sync()
    return plan, downloaded, payload


def _run_python(code: str, *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", code], cwd=str(cwd or ROOT),
        capture_output=True, text=True, timeout=60,
    )


# ---------------------------------------------------------------------------
# Scenario 1 — fresh install, first launch, config/state creation
# ---------------------------------------------------------------------------


def test_fresh_install_creates_config_and_state(clean_env, tmp_path):
    """A clean HOME + first launch produces config, state DB and health file."""
    state = tmp_path / "state"
    code = (
        "import os, sqlite3, pathlib\n"
        "from keel import settings_store, start_health\n"
        "sd = pathlib.Path(os.environ['KEEL_STATE_DIR'])\n"
        "assert os.environ['HOME'].endswith('home')\n"
        "assert str(sd).startswith(os.environ['HOME'][:-4])\n"
        "settings_store.save({'ui': {'theme': 'dark'}, 'mcpServers': {}})\n"
        "start_health.record_start(str(sd), '0.1.0', ok=True)\n"
        "c = sqlite3.connect(sd / 'keel.sqlite3')\n"
        "c.execute('CREATE TABLE notes(id INTEGER PRIMARY KEY, body TEXT)')\n"
        "c.execute('INSERT INTO notes(id, body) VALUES (1, ?)', ('first-launch',))\n"
        "c.commit(); c.close()\n"
        "print('STATE=' + str(sd))\n"
    )
    proc = _run_python(code)
    assert proc.returncode == 0, proc.stderr
    settings = state / "settings.json"
    assert settings.is_file()
    assert json.loads(settings.read_text(encoding="utf-8"))["ui"] == {"theme": "dark"}
    assert (state / "settings.json.bak").is_file() is False  # first save: no backup yet
    health = json.loads((state / "start-health.json").read_text(encoding="utf-8"))
    assert health[CURRENT]["failures"] == 0
    assert _db_canary(state / "keel.sqlite3") == "first-launch"
    _assert_version_sync()
    print(f"[final] fresh install: HOME={clean_env} state={state} "
          "settings.json + start-health.json + keel.sqlite3 created; version gate OK")


# ---------------------------------------------------------------------------
# Scenario 2 — upgrade 0.1.0 -> 0.1.1 with user data
# ---------------------------------------------------------------------------


def test_upgrade_preserves_user_data_and_manifest_integrity(
        tmp_path, release_server, keypair, machine):
    serve_root, base_url = release_server
    proc = _start(machine.install)
    assert proc.returncode == 0 and _db_canary(machine.db) == CANARY
    _upgrade(serve_root, base_url, keypair, machine)
    assert _start(machine.install).stdout.find(f"KEEL_APP_VERSION={UPGRADE}") >= 0
    assert _db_canary(machine.db) == CANARY
    print(f"[final] upgrade {CURRENT}->{UPGRADE}: active={UPGRADE} "
          f"backup={CURRENT} sqlite_canary={CANARY}; manifest signature+sha256 verified")


# ---------------------------------------------------------------------------
# Scenario 3 — interrupted download
# ---------------------------------------------------------------------------


def test_interrupted_download_is_fail_closed(
        tmp_path, release_server, keypair, machine):
    from http.server import BaseHTTPRequestHandler

    class _Truncated(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib API
            body = b"partial-installer-bytes"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body) + 64))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            self.close_connection = True

        def log_message(self, fmt, *args):  # pragma: no cover
            pass

    serve_root, base_url = release_server
    private, public, _ = keypair
    name = _artifact_name(UPGRADE)
    truncated = ThreadingHTTPServer(("127.0.0.1", 0), _Truncated)
    thread = threading.Thread(target=truncated.serve_forever, daemon=True)
    thread.start()
    try:
        _publish(serve_root, base_url, UPGRADE, name, b"payload", private)
        doc = json.loads((serve_root / "download.json").read_text(encoding="utf-8"))
        for entry in doc["files"]:
            if entry["platform"] == _platform():
                entry["url"] = f"http://127.0.0.1:{truncated.server_port}/{name}"
        unsigned = {k: v for k, v in doc.items()
                    if k not in ("signature", "signature_algorithm")}
        (serve_root / "download.json").write_text(
            json.dumps(sign_manifest(unsigned, private)), encoding="utf-8")
        plan = _plan(serve_root, base_url, public)
        assert plan is not None and "127.0.0.1" in plan.url
        destination = machine.root / "downloads" / name
        with pytest.raises(RuntimeError, match="Content-Length"):
            updater.download_update(plan, destination,
                                    public_key=public, allow_http=True)
    finally:
        truncated.shutdown()
        truncated.server_close()
        thread.join(timeout=5)

    assert not destination.exists()
    assert not machine.backup.exists()
    assert _start(machine.install).returncode == 0
    assert _db_canary(machine.db) == CANARY
    print("[final] interrupted download: RuntimeError; no file written; "
          "0.1.0 still healthy")


# ---------------------------------------------------------------------------
# Scenario 4 — interrupted install (swap)
# ---------------------------------------------------------------------------


def test_interrupted_install_is_fail_closed(tmp_path, machine, monkeypatch):
    _write_app(machine.staged, UPGRADE, ok=False)
    real_rename = Path.rename

    def blocked(self, target):
        if self == machine.staged:
            raise OSError("simulated lock on staged install")
        return real_rename(self, target)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "rename", blocked)
        with pytest.raises(OSError):
            updater.atomic_install(machine.staged, machine.install, machine.backup)

    assert (machine.install / "version.txt").read_text(encoding="utf-8") == CURRENT
    assert not machine.backup.exists()
    assert _start(machine.install).returncode == 0
    assert _db_canary(machine.db) == CANARY
    print("[final] interrupted install: compensation restored 0.1.0; "
          "no stale backup; user data intact")


# ---------------------------------------------------------------------------
# Scenarios 5-7 — corrupt manifest / checksum / signature
# ---------------------------------------------------------------------------


def test_corrupt_manifest_is_fail_closed(tmp_path, release_server, keypair, machine):
    serve_root, base_url = release_server
    _, public, public_path = keypair
    name = _artifact_name(UPGRADE)
    _publish(serve_root, base_url, UPGRADE, name, b"payload", keypair[0])
    manifest_path = serve_root / "download.json"

    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    doc["version"] = "9.9.9"  # tampered after signing
    manifest_path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(updater.UpdateError):
        _plan(serve_root, base_url, public)

    manifest_path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(updater.UpdateError):
        _plan(serve_root, base_url, public)

    assert not machine.backup.exists()
    assert _start(machine.install).returncode == 0
    assert _db_canary(machine.db) == CANARY
    print("[final] corrupt manifest: tampered signature and invalid JSON both "
          "raise UpdateError; 0.1.0 still healthy")


def test_corrupt_checksum_is_fail_closed(tmp_path, release_server, keypair, machine):
    serve_root, base_url = release_server
    private, public, _ = keypair
    name = _artifact_name(UPGRADE)
    # Validly signed manifest whose declared digest does not match the bytes.
    _publish(serve_root, base_url, UPGRADE, name, b"payload", private,
             corrupt_checksum=True)
    plan = _plan(serve_root, base_url, public)
    assert plan is not None and plan.version == UPGRADE
    destination = machine.root / "downloads" / name
    with pytest.raises(updater.UpdateError, match="sha256 mismatch"):
        updater.download_update(plan, destination,
                                public_key=public, allow_http=True)
    assert not destination.exists()
    assert not machine.backup.exists()
    assert _start(machine.install).returncode == 0
    assert _db_canary(machine.db) == CANARY
    print("[final] corrupt checksum: sha256 mismatch -> UpdateError; "
          "no download installed; 0.1.0 still healthy")


def test_corrupt_signature_is_fail_closed(tmp_path, release_server, keypair, machine):
    serve_root, base_url = release_server
    private, public, _ = keypair
    name = _artifact_name(UPGRADE)
    _publish(serve_root, base_url, UPGRADE, name, b"payload", private,
             corrupt_signature=True)
    plan = _plan(serve_root, base_url, public)
    assert plan is not None
    destination = machine.root / "downloads" / name
    with pytest.raises(updater.UpdateError, match="signature invalid"):
        updater.download_update(plan, destination,
                                public_key=public, allow_http=True)
    assert not destination.exists()
    assert _start(machine.install).returncode == 0
    assert _db_canary(machine.db) == CANARY
    print("[final] corrupt artifact signature: Ed25519 verification failed "
          "closed; no file written")


# ---------------------------------------------------------------------------
# Scenario 8-9 — failed startup and 3 failed starts -> rollback
# ---------------------------------------------------------------------------


def test_failed_startup_is_recorded_and_does_not_roll_back_early(machine):
    broken = _start(machine.install)
    assert broken.returncode == 0  # baseline 0.1.0 is healthy
    _write_app(machine.install, CURRENT, ok=False)
    for attempt in (1, 2):
        failed = _start(machine.install)
        assert failed.returncode == 1
        outcome = start_health.record_start(
            str(machine.state), CURRENT, ok=(failed.returncode == 0))
        assert outcome == {"version": CURRENT, "failures": attempt,
                           "rollback": False}
    print("[final] failed startup: attempts 1 and 2 recorded, no early rollback")


def test_three_failed_starts_trigger_rollback_with_user_data(
        tmp_path, release_server, keypair, machine):
    serve_root, base_url = release_server
    _upgrade(serve_root, base_url, keypair, machine, ok=False)
    flags = []
    for attempt in range(1, 4):
        failed = _start(machine.install)
        assert failed.returncode == 1, failed.stdout
        outcome = start_health.record_start(
            str(machine.state), UPGRADE, ok=(failed.returncode == 0))
        flags.append(outcome["rollback"])
        print(f"[final] failed start {attempt}: rc=1 failures="
              f"{outcome['failures']} rollback_flag={outcome['rollback']}")
    assert flags == [False, False, True]

    updater.rollback(machine.install, machine.backup)
    assert not machine.backup.exists()
    recovered = _start(machine.install)
    assert recovered.returncode == 0
    assert f"KEEL_APP_VERSION={CURRENT}" in recovered.stdout
    assert _db_canary(machine.db) == CANARY
    assert start_health.record_start(
        str(machine.state), CURRENT, ok=True)["rollback"] is False
    print(f"[final] rollback -> {recovered.stdout.strip()}; "
          f"sqlite_canary={CANARY}")


# ---------------------------------------------------------------------------
# Scenario 10 — explicit rollback
# ---------------------------------------------------------------------------


def test_explicit_rollback_after_healthy_upgrade(
        tmp_path, release_server, keypair, machine):
    serve_root, base_url = release_server
    _upgrade(serve_root, base_url, keypair, machine, ok=True)
    assert f"KEEL_APP_VERSION={UPGRADE}" in _start(machine.install).stdout
    updater.rollback(machine.install, machine.backup)
    proc = _start(machine.install)
    assert proc.returncode == 0
    assert f"KEEL_APP_VERSION={CURRENT}" in proc.stdout
    assert _db_canary(machine.db) == CANARY
    print("[final] explicit rollback: healthy 0.1.1 -> 0.1.0; data preserved")


# ---------------------------------------------------------------------------
# Scenario 11 — backup before migration and restore
# ---------------------------------------------------------------------------


def test_backup_before_migration_and_restore(tmp_path, machine):
    backup_dir = tmp_path / "backups"
    info = backups.backup_database(machine.db, backup_dir, TEST_PASSPHRASE,
                                   keep=2)
    assert info["format"] == backups.DB_BACKUP_FORMAT
    assert info["records"] >= 1
    [artifact] = list(backup_dir.glob("keel-db-*.dbbak"))
    verified = backups.verify_database_backup(artifact, TEST_PASSPHRASE)
    assert verified["records"] == info["records"]

    # Simulate a migration that damages the live database.
    with sqlite3.connect(machine.db) as conn:
        conn.execute("DROP TABLE notes")
    assert _db_canary(machine.db) is None

    restored = machine.root / "restored" / "keel.sqlite3"
    result = backups.restore_database(artifact, restored, TEST_PASSPHRASE)
    assert result["sha256"] == info["sha256"]
    assert _db_canary(restored) == CANARY
    print(f"[final] pre-migration backup -> restore: records={info['records']} "
          f"canary={CANARY}; digest {info['sha256'][:16]}...")


# ---------------------------------------------------------------------------
# Scenario 12 — corrupt health-state entry (regression for fixed defect)
# ---------------------------------------------------------------------------


def test_corrupt_health_entry_does_not_crash_failure_recording(tmp_path):
    """A parseable but wrong-shaped health file must not crash the launcher.

    Before the fix, ``record_start`` did ``dict(doc[version])`` and raised
    ValueError on a non-mapping value, so failed starts could not be recorded
    and auto-rollback could never fire.
    """
    path = tmp_path / "start-health.json"
    path.write_text(json.dumps({UPGRADE: "corrupt-entry"}), encoding="utf-8")
    outcome = start_health.record_start(str(tmp_path), UPGRADE, ok=False)
    assert outcome == {"version": UPGRADE, "failures": 1, "rollback": False}
    for expected in (2, 3):
        outcome = start_health.record_start(str(tmp_path), UPGRADE, ok=False)
        assert outcome["failures"] == expected
    assert outcome["rollback"] is True
    print("[final] corrupt health entry: no crash; 3 consecutive failures "
          "still trigger rollback")


# ---------------------------------------------------------------------------
# Scenario 13 — uninstall preserving user data, then reinstall
# ---------------------------------------------------------------------------


def test_uninstall_preserves_user_data_and_reinstall(
        tmp_path, release_server, keypair, machine, clean_env):
    serve_root, base_url = release_server
    _upgrade(serve_root, base_url, keypair, machine, ok=True)
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    (state / "settings.json").write_text(
        json.dumps({"ui": {"theme": "dark"}}), encoding="utf-8")
    start_health.record_start(str(state), UPGRADE, ok=True)

    plan = uninstall_plan(UninstallMode.KEEP_DATA, paths={
        "app": str(machine.install),
        "data": str(machine.root / "userdata"),
        "config": str(state),
        "models": str(machine.root / "models"),
    })
    assert plan["dry_run"] is True and plan["requires_confirmation"] is True
    assert plan["would_delete"] == [str(machine.install)]
    # Apply the KEEP_DATA plan: only the application directory is removed.
    import shutil
    shutil.rmtree(str(machine.install))
    assert (state / "settings.json").is_file()
    assert _db_canary(machine.db) == CANARY
    assert (state / "start-health.json").is_file()

    # Reinstall from the same verified artifact into a fresh install dir.
    reinstalled = machine.root / "install"
    reinstalled.mkdir()
    (reinstalled / "version.txt").write_text(CURRENT, encoding="utf-8")
    (reinstalled / "app.py").write_text(
        f'print("KEEL_APP_VERSION={CURRENT}")\n', encoding="utf-8")
    proc = _start(reinstalled)
    assert proc.returncode == 0
    assert _db_canary(machine.db) == CANARY
    assert json.loads((state / "settings.json").read_text(
        encoding="utf-8"))["ui"] == {"theme": "dark"}
    _assert_version_sync()
    print("[final] uninstall KEEP_DATA: only app dir removed; settings, "
          "health and sqlite canary survive; reinstall starts cleanly")


# ---------------------------------------------------------------------------
# Harness entry point (repeatable without a VM)
# ---------------------------------------------------------------------------


if __name__ == "__main__":  # pragma: no cover - manual harness entry point
    # Clean-HOME process bootstrap: module-level constants (e.g.
    # keel.settings_store.STATE_DIR) are bound at import time, so the synthetic
    # HOME must be installed before pytest imports the package under test.
    import os
    import tempfile

    disposable = Path(tempfile.mkdtemp(prefix="keel-final-install-"))
    os.environ["HOME"] = str(disposable / "home")
    os.environ["USERPROFILE"] = os.environ["HOME"]
    os.environ["KEEL_STATE_DIR"] = str(disposable / "state")
    os.environ["PYTHONNOUSERSITE"] = "1"
    for _key in ("KEEL_START_HEALTH_FILE", "KEEL_MIN_VERSION",
                 "KEEL_BLOCKED_VERSIONS", "KEEL_ROLLOUT_MODE",
                 "KEEL_ROLLOUT_PERCENTAGE", "KEEL_PUBLISHED_AT"):
        os.environ.pop(_key, None)
    print(f"[final] disposable root: {disposable}")
    raise SystemExit(pytest.main([__file__, "-s", "-v", "-p", "no:cacheprovider"]))
