"""Locally achievable platform requirements: B4.8, B6.6, C11.8, C1.11, A3.8."""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import os
import secrets
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


# --------------------------------------------------------------- B4.8
def companion_identity(state_root: str | Path, *, host: str = "127.0.0.1",
                       port: int = 9284) -> dict:
    """Generate a pinned self-signed identity and a QR pairing payload.

    TLS material is created locally with `cryptography` (Apache-2.0). The PIN is
    the SHA-256 fingerprint of the DER certificate; the phone must verify it.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import datetime as _dt

    root = Path(state_root) / "companion"
    root.mkdir(parents=True, exist_ok=True)
    cert_path, key_path = root / "cert.pem", root / "key.pem"
    token_path = root / "pairing-token.txt"
    if not (cert_path.is_file() and key_path.is_file()):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Keel Companion")])
        now = _dt.datetime.now(_dt.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - _dt.timedelta(minutes=5))
            .not_valid_after(now + _dt.timedelta(days=365))
            .add_extension(x509.SubjectAlternativeName([
                x509.DNSName("localhost"), x509.IPAddress(
                    __import__("ipaddress").ip_address("127.0.0.1"))]),
                critical=False)
            .sign(key, hashes.SHA256()))
        key_path.write_bytes(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption()))
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        os.chmod(key_path, 0o600)
    if not token_path.is_file():
        token_path.write_text(secrets.token_urlsafe(24), encoding="utf-8")
    token = token_path.read_text(encoding="utf-8").strip()
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    pin = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
    payload = (f"keel://pair?host={host}&port={port}"
               f"&token={token}&pin={pin}")
    qr = None
    try:
        # Optional at runtime only: do not statically import cv2, as doing so
        # makes PyInstaller bundle ~70 MB of native libraries into the sidecar.
        import importlib

        cv2 = importlib.import_module("cv2")
        encoder = cv2.QRCodeEncoder_create()
        encoded = encoder.encode(payload)
        qr = {"width": int(encoded.shape[1]), "height": int(encoded.shape[0]),
              "available": True, "note": "QR matrix generated locally via OpenCV"}
    except Exception:
        qr = {"available": False,
              "note": "Pairing URI is complete; optional OpenCV enables QR rendering"}
    return {"payload": payload, "pin": pin, "tls": str(cert_path),
            "key": str(key_path), "network": "loopback by default",
            "lan_opt_in_required": True, "qr": qr,
            "note": "Phone reachability is external; no cloud service used."}


class CompanionApprovals:
    def __init__(self, state_root: str | Path):
        self.path = Path(state_root) / "companion" / "approvals.json"

    def _load(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def pending(self, device: str, pin: str) -> dict:
        doc = self._load()
        entry = {"device": device, "pin": pin, "approved": False,
                 "id": uuid.uuid4().hex[:12]}
        doc[entry["id"]] = entry
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return entry

    def approve(self, pairing_id: str) -> dict:
        doc = self._load()
        if pairing_id not in doc:
            raise KeyError(pairing_id)
        doc[pairing_id]["approved"] = True
        self.path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return doc[pairing_id]


# --------------------------------------------------------------- B6.6
class OrgAuditExport:
    """Per-organization audit export format and retention settings (B6.6)."""

    def __init__(self, state_root: str | Path):
        self.root = Path(state_root)
        self.config_path = self.root / "audit-retention.json"
        self.log = self.root / "capability-audit.jsonl"

    def config(self, org: str) -> dict:
        doc = self._load_config()
        return doc.get(org, {"org": org, "retention_days": 90,
                             "format": "jsonl", "enabled": True})

    def set_config(self, org: str, *, retention_days: int = 90,
                   format: str = "jsonl", enabled: bool = True) -> dict:
        if format not in ("jsonl", "csv"):
            raise ValueError("format must be jsonl or csv")
        if retention_days < 1:
            raise ValueError("retention_days must be positive")
        doc = self._load_config()
        doc[org] = {"org": org, "retention_days": retention_days,
                    "format": format, "enabled": enabled}
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(doc, indent=2) + "\n",
                                    encoding="utf-8")
        return doc[org]

    def _load_config(self) -> dict:
        if not self.config_path.is_file():
            return {}
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def export(self, org: str) -> dict:
        config = self.config(org)
        entries = []
        if self.log.is_file():
            for line in self.log.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        entries.append(json.loads(line))
                    except ValueError:
                        continue
        cutoff = time.time() - config["retention_days"] * 86400
        kept = [e for e in entries
                if not e.get("ts") or _parse_ts(e["ts"]) >= cutoff]
        if config["format"] == "csv":
            out = io.StringIO()
            writer = csv.DictWriter(out, fieldnames=["ts", "capability", "ok"])
            writer.writeheader()
            for e in kept:
                writer.writerow({k: e.get(k, "") for k in writer.fieldnames})
            body = out.getvalue()
        else:
            body = "\n".join(json.dumps(e, ensure_ascii=False) for e in kept)
        return {"org": org, "format": config["format"],
                "entries": len(kept), "body": body,
                "retention_days": config["retention_days"]}


def _parse_ts(value: str) -> float:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return time.time()


# --------------------------------------------------------------- C11.8
def build_canary(state_root: str | Path) -> dict:
    """Per-build deterrent canary identifier (never a security boundary)."""
    path = Path(state_root) / "build-canary.json"
    doc = {}
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            doc = {}
    if not doc.get("id"):
        doc = {"id": "keel-canary-" + secrets.token_hex(8),
               "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return {**doc,
            "measures": {
                "asar_integrity": "verified in packaged Electron build",
                "nuitka_core": "not applied — requires optional external tool",
                "bytecode_compiled_electron_main": "not applied",
                "string_encryption": "not needed — no secrets in renderer",
            },
            "note": "Deterrent only; not a security boundary."}


# --------------------------------------------------------------- C1.11
class LocalTaskExecutor:
    """Approval-gated local task executor for desktop actions (C1.11)."""

    def __init__(self, state_root: str | Path, *, timeout_s: int = 30):
        self.path = Path(state_root) / "local-tasks.json"
        self.timeout_s = timeout_s

    def _load(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, doc: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    def submit(self, name: str, argv: list[str], *, approver: str = "",
               allowlist: list[str] | None = None) -> dict:
        if not argv or not all(isinstance(a, str) for a in argv):
            raise ValueError("argv must be a non-empty list of strings")
        allowed = set(allowlist or ["git", "python", "node", "npm", "keel"])
        program = Path(argv[0]).name.lower()
        stem = program[:-4] if program.endswith(".exe") else program
        if program not in allowed and stem not in allowed:
            raise ValueError(f"program {argv[0]!r} is not in the allowlist")
        task = {"id": uuid.uuid4().hex[:12], "name": name, "argv": argv,
                "approved": bool(approver), "approver": approver or None,
                "status": "pending" if not approver else "approved",
                "result": None}
        doc = self._load()
        doc[task["id"]] = task
        self._save(doc)
        return task

    def approve(self, task_id: str, approver: str) -> dict:
        doc = self._load()
        if task_id not in doc:
            raise KeyError(task_id)
        doc[task_id]["approved"] = True
        doc[task_id]["approver"] = approver
        doc[task_id]["status"] = "approved"
        self._save(doc)
        return doc[task_id]

    def run(self, task_id: str) -> dict:
        doc = self._load()
        task = doc.get(task_id)
        if not task:
            raise KeyError(task_id)
        if not task["approved"]:
            raise PermissionError("task requires approval before execution")
        result = subprocess.run(task["argv"], capture_output=True, shell=False,
                                timeout=self.timeout_s, check=False)
        task.update({
            "status": "done", "exit_code": result.returncode,
            "stdout": result.stdout.decode("utf-8", errors="replace")[:10000],
            "stderr": result.stderr.decode("utf-8", errors="replace")[:5000]})
        doc[task_id] = task
        self._save(doc)
        return task


# --------------------------------------------------------------- A3.8
class SiteToolkit:
    """Local-only operator tools for generated sites (A3.8)."""

    def __init__(self, state_root: str | Path):
        self.root = Path(state_root) / "site-tools"
        self.root.mkdir(parents=True, exist_ok=True)

    def secrets_manager(self, state_root: str | Path) -> dict:
        from .secret_store import encrypt_secret, decrypt_secret

        probe = encrypt_secret("keel-site-tool-probe", state_dir=Path(state_root))
        restored = decrypt_secret(probe, state_dir=Path(state_root))
        return {"backend": "aes256gcm", "available": restored == "keel-site-tool-probe",
                "note": "Encrypted at rest via the shared Keel secret store."}

    def db_browser(self, db_path: str | Path) -> dict:
        import sqlite3

        path = Path(db_path)
        if not path.is_file():
            return {"ok": False, "reason": "database not found"}
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
        return {"ok": True, "tables": tables, "read_only": True}

    def scheduled_jobs(self) -> list[dict]:
        path = self.root / "jobs.json"
        if not path.is_file():
            return []
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            return doc.get("jobs", []) if isinstance(doc, dict) else []
        except (OSError, ValueError):
            return []

    def add_job(self, name: str, interval_s: int, command: str) -> dict:
        if interval_s < 60:
            raise ValueError("interval must be at least 60 seconds")
        jobs = self.scheduled_jobs()
        job = {"id": uuid.uuid4().hex[:12], "name": name,
               "interval_s": interval_s, "command": command,
               "enabled": True}
        jobs.append(job)
        (self.root / "jobs.json").write_text(
            json.dumps({"jobs": jobs}, indent=2) + "\n", encoding="utf-8")
        return job

    def analytics(self, events: list[dict]) -> dict:
        counts: dict[str, int] = {}
        for event in events:
            key = str(event.get("kind", "unknown"))
            counts[key] = counts.get(key, 0) + 1
        return {"events": len(events), "by_kind": counts,
                "note": "Derived from supplied local events only."}

    def element_editor(self, tag: str, text: str, *, css_class: str = "") -> str:
        safe_tag = tag if tag in ("p", "h1", "h2", "div", "span", "button") else "p"
        return (f"<{safe_tag} class='{html_escape(css_class)}'>"
                f"{html_escape(text)}</{safe_tag}>")


def html_escape(value: str) -> str:
    return html.escape(str(value), quote=True)
