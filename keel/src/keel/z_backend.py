"""Stdlib-only backend behaviour for the 15 ``not_started`` Z-row features.

Scope (from ``PLAN-INDEX.json`` at baseline ``982335d``):

* Z1  Project environment lockfile
* Z2  Agent contract tests
* Z3  Redacted replay export
* Z5  Capability negotiation handshake
* Z6  Local-first sync via the user's own folder
* Z7  Household/OS-user separation
* Z8  Energy and cost estimator for local runs
* Z9  Natural-language policy editor
* Z10 Provider/model drift detector
* Z11 Dormant-integration health board
* Z12 Offline signed catalog updates
* Z13 "Why can't I do X?" explainer
* Z14 Pre-flight installer report
* Z15 Prompt-injection regression corpus
* Z16 Per-project cost budgets and "stop at budget" with summary

Z4 (crash-safe turn journal) is already ``verified`` in ``repo_contracts.py``
and is deliberately not reimplemented here.  This module is backend only: it
renders text/markdown/HTML data and never drives a UI, opens a browser or calls
a network service.  Every implementation uses the Python standard library and
does real work (file hashing, JSONL ledgers, SQLite persistence, RFC 8032
Ed25519 signatures, deterministic simulations); malformed input fails closed.
"""

from __future__ import annotations

import getpass
import hashlib
import hmac
import html
import json
import math
import os
import re
import sqlite3
import tempfile
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

# The 15 rows assigned to this backend workstream.  Z4 is excluded because it
# is already verified at the assigned baseline.
FEATURE_IDS: tuple[str, ...] = (
    "Z1", "Z2", "Z3", "Z5", "Z6", "Z7", "Z8", "Z9",
    "Z10", "Z11", "Z12", "Z13", "Z14", "Z15", "Z16",
)
VERIFIED_EXCLUDED: tuple[str, ...] = ("Z4",)

GENESIS_DIGEST = "0" * 64


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _require_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _require_dict(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _require_number(value: Any, label: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        raise ValueError(f"{label} must be finite and >= {minimum}")
    return number


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _atomic_write_text(path: Path, text: str) -> Path:
    """Write a UTF-8 file atomically inside its own directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=str(path.parent),
        prefix=".keel-write-", suffix=".tmp", delete=False)
    tmp = Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return path


# One reentrant lock per resolved state file.  The registry guard protects only
# the map itself; the per-path lock is what serialises every read-modify-write
# cycle (budget check+append, sync chain append, JSONL reads) across all callers
# on the same file, not merely within one object instance.
_PATH_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}


def _lock_for_path(path: str | Path) -> threading.RLock:
    key = str(Path(path).resolve())
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[key] = lock
        return lock


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    if text and not text.endswith("\n"):
        # A final record without its terminator is a torn append: fail closed
        # instead of silently accepting a partially written ledger.
        raise ValueError(f"corrupt JSONL record in {path}: incomplete final line")
    records = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError as exc:
            raise ValueError(f"corrupt JSONL record in {path}: {exc}") from exc
        if not isinstance(record, dict):
            raise ValueError(f"corrupt JSONL record in {path}: not an object")
        records.append(record)
    return records


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # The path lock makes the primitive safe for every caller, even when the
    # callers are different objects.  A single O_APPEND write followed by fsync
    # keeps each record whole and durable; partial writes are continued under
    # the same lock rather than interleaved with another record.
    data = (_canonical_json(record) + "\n").encode("utf-8")
    with _lock_for_path(path):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
        finally:
            os.close(fd)


def _safe_relpath(raw: Any, label: str = "path") -> Path:
    text = _require_str(raw, label)
    if "\x00" in text:
        raise ValueError(f"{label} contains a NUL byte")
    normalised = text.replace("\\", "/")
    if normalised.startswith("/") or re.match(r"^[A-Za-z]:", normalised):
        raise ValueError(f"{label} must be relative")
    parts = [part for part in normalised.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise ValueError(f"{label} escapes its root")
    return Path(*parts)


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


# ===========================================================================
# Z1 — Project environment lockfile
# ===========================================================================

EXTENSION_KINDS: tuple[str, ...] = (
    "skill", "plugin", "mcp_server", "model_file", "prompt_profile",
)
LOCK_SCHEMA = "keel.project-lock/1"
LOCK_RELPATH = Path(".keel") / "lock.json"


def hash_file(path: str | Path) -> dict:
    """Hash a real file on disk with SHA-256 and report its size."""
    target = Path(path)
    if not target.is_file():
        raise ValueError(f"not a file: {target}")
    digest = hashlib.sha256()
    size = 0
    with open(target, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
            size += len(chunk)
    return {"sha256": digest.hexdigest(), "size": size}


def build_lock(project_root: str | Path,
               extensions: Mapping[str, Sequence[Any]],
               *, ts: float | None = None) -> dict:
    """Pin version + SHA-256 of every installed extension of a project.

    ``extensions`` maps a kind (see ``EXTENSION_KINDS``) to relative paths or
    to ``{"path": ..., "version": ...}`` objects (Y1.29 pin semantics).
    """
    root = Path(project_root)
    _require_dict(extensions, "extensions")
    entries: list[dict] = []
    for kind, items in sorted(extensions.items()):
        if kind not in EXTENSION_KINDS:
            raise ValueError(f"unknown extension kind: {kind}")
        if not isinstance(items, (list, tuple)):
            raise ValueError(f"extensions[{kind}] must be a list")
        for item in items:
            if isinstance(item, dict):
                rel = _safe_relpath(item.get("path"), f"extensions[{kind}].path")
                version = item.get("version")
                if version is not None:
                    version = _require_str(version, "version")
            else:
                rel = _safe_relpath(item, f"extensions[{kind}]")
                version = None
            fingerprint = hash_file(root / rel)
            entry = {
                "kind": kind,
                "path": rel.as_posix(),
                "sha256": fingerprint["sha256"],
                "size": fingerprint["size"],
                "version": version,
            }
            entries.append(entry)
    return {
        "schema": LOCK_SCHEMA,
        "generated_at": _iso(time.time() if ts is None else ts),
        "entries": entries,
    }


def write_lock(project_root: str | Path, lock: dict) -> Path:
    """Persist a lockfile at ``<project_root>/.keel/lock.json``."""
    if lock.get("schema") != LOCK_SCHEMA or not isinstance(lock.get("entries"), list):
        raise ValueError("invalid project lockfile document")
    return _atomic_write_text(Path(project_root) / LOCK_RELPATH,
                              _canonical_json(lock) + "\n")


def load_lock(project_root: str | Path) -> dict:
    """Load a lockfile, failing closed on an invalid document."""
    path = Path(project_root) / LOCK_RELPATH
    if not path.is_file():
        raise ValueError(f"no project lockfile at {path}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"invalid project lockfile at {path}: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("schema") != LOCK_SCHEMA \
            or not isinstance(doc.get("entries"), list):
        raise ValueError(f"invalid project lockfile at {path}")
    return doc


def verify_lock(project_root: str | Path, lock: dict | None = None, *,
                current_versions: Mapping[str, str] | None = None) -> dict:
    """Compare a lockfile against the files currently on disk.

    ``current_versions`` maps an installed-extension path to its observed
    version so Y1.29-style version pins can be checked too.  Returns a report
    with ``mismatches`` (changed hash/size/version), ``missing`` (pinned file
    absent) and ``warnings`` (the "warn before running" part of the feature).
    """
    root = Path(project_root)
    doc = lock if lock is not None else load_lock(root)
    versions = dict(current_versions or {})
    mismatches: list[dict] = []
    missing: list[dict] = []
    for entry in doc["entries"]:
        if not isinstance(entry, dict):
            raise ValueError("invalid lockfile entry")
        rel = _safe_relpath(entry.get("path"), "lockfile entry path")
        target = root / rel
        if not target.is_file():
            missing.append({"kind": entry.get("kind"), "path": rel.as_posix()})
            continue
        current = hash_file(target)
        changes = []
        for field_name, expected, actual in (
            ("sha256", entry.get("sha256"), current["sha256"]),
            ("size", entry.get("size"), current["size"]),
            ("version", entry.get("version"), versions.get(rel.as_posix())),
        ):
            if expected is not None and actual is not None and expected != actual:
                changes.append(field_name)
        if changes:
            mismatches.append({"kind": entry.get("kind"),
                               "path": rel.as_posix(), "fields": changes})
    warnings = []
    if missing:
        warnings.append("project environment changed: missing pinned files: "
                        + ", ".join(item["path"] for item in missing))
    if mismatches:
        warnings.append("project environment changed: modified pinned files: "
                        + ", ".join(item["path"] for item in mismatches))
    return {
        "ok": not missing and not mismatches,
        "mismatches": mismatches,
        "missing": missing,
        "warnings": warnings,
        "entry_count": len(doc["entries"]),
    }


def regenerate_lock(project_root: str | Path, extensions: Mapping[str, Sequence[Any]],
                    *, approved: bool, ts: float | None = None) -> dict:
    """Regenerate a lockfile.  Requires explicit user approval (never implicit)."""
    if not approved:
        raise PermissionError("lockfile regeneration requires explicit approval")
    lock = build_lock(project_root, extensions, ts=ts)
    write_lock(project_root, lock)
    return lock


# ===========================================================================
# Z2 — Agent contract tests
# ===========================================================================

PACK_MANIFEST = "agent.json"
CONTRACT_TESTS_DIR = "tests"


@dataclass(frozen=True)
class ContractCase:
    name: str
    prompt: str
    allowed_tools: tuple[str, ...] = ()
    denied_tools: tuple[str, ...] = ()
    expect_refusal: bool = False
    expect_tool_calls: tuple[str, ...] = ()
    expect_output_keys: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, doc: Mapping[str, Any]) -> "ContractCase":
        data = _require_dict(doc, "contract case")
        name = _require_str(data.get("name"), "case name")
        prompt = _require_str(data.get("prompt"), "case prompt")
        return cls(
            name=name,
            prompt=prompt,
            allowed_tools=tuple(data.get("allowed_tools", ()) or ()),
            denied_tools=tuple(data.get("denied_tools", ()) or ()),
            expect_refusal=bool(data.get("expect_refusal", False)),
            expect_tool_calls=tuple(data.get("expect_tool_calls", ()) or ()),
            expect_output_keys=tuple(data.get("expect_output_keys", ()) or ()),
        )


def discover_contract_tests(pack_root: str | Path) -> list[Path]:
    """Find the ``tests/*.json`` cases shipped inside an agent/skill pack."""
    tests_dir = Path(pack_root) / CONTRACT_TESTS_DIR
    if not tests_dir.is_dir():
        return []
    return sorted(path for path in tests_dir.glob("*.json") if path.is_file())


def load_contract_cases(pack_root: str | Path) -> list[ContractCase]:
    cases = []
    for path in discover_contract_tests(pack_root):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ValueError(f"invalid contract test {path}: {exc}") from exc
        docs = doc.get("cases", []) if isinstance(doc, dict) else doc
        if not isinstance(docs, list):
            raise ValueError(f"invalid contract test {path}")
        for case in docs:
            cases.append(ContractCase.from_dict(case))
    if not cases:
        raise ValueError(f"no contract cases found in {Path(pack_root) / CONTRACT_TESTS_DIR}")
    return cases


def scripted_runner(script: Mapping[str, Any]) -> Callable[[str, dict], dict]:
    """A deterministic fixture-model runner (X9.1) keyed by prompt."""
    _require_dict(script, "script")
    def runner(prompt: str, _context: dict | None = None) -> dict:
        if prompt not in script:
            raise KeyError(f"no scripted response for prompt: {prompt}")
        response = script[prompt]
        if not isinstance(response, dict):
            raise ValueError("scripted response must be an object")
        return response
    return runner


def check_tool_allowlist(response: Mapping[str, Any], case: ContractCase) -> tuple[bool, str]:
    """Assert that every called tool is allowed and none of the denied ones ran."""
    calls = response.get("tool_calls", [])
    if not isinstance(calls, list):
        return False, "tool_calls must be a list"
    names = []
    for call in calls:
        if isinstance(call, dict):
            names.append(str(call.get("tool", "")))
        elif isinstance(call, str):
            names.append(call)
        else:
            return False, "tool call must be a string or object"
    allowed = set(case.allowed_tools)
    for name in names:
        if allowed and name not in allowed:
            return False, f"tool {name!r} is outside the allowlist"
        if name in set(case.denied_tools):
            return False, f"denied tool {name!r} was called"
    return True, ""


def check_refusal(response: Mapping[str, Any], case: ContractCase) -> tuple[bool, str]:
    refused = bool(response.get("refused", False))
    if refused != case.expect_refusal:
        return False, f"refusal mismatch: expected {case.expect_refusal}, got {refused}"
    return True, ""


def check_output_shape(response: Mapping[str, Any], case: ContractCase) -> tuple[bool, str]:
    if not isinstance(response.get("text"), str):
        return False, "text must be a string"
    output = response.get("output", {})
    if not isinstance(output, dict):
        output = {}
    for key in case.expect_output_keys:
        if key not in response and key not in output:
            return False, f"missing output key {key!r}"
    if case.expect_tool_calls:
        calls = response.get("tool_calls", [])
        names = [c.get("tool", "") if isinstance(c, dict) else c for c in calls]
        if tuple(names) != tuple(case.expect_tool_calls):
            return False, f"expected tool calls {case.expect_tool_calls}, got {names}"
    return True, ""


def run_contract_tests(pack_root: str | Path,
                       runner: Callable[[str, dict], dict],
                       *, stage: str = "install") -> dict:
    """Run a pack's shipped contract cases at install or update time."""
    if stage not in ("install", "update"):
        raise ValueError(f"unknown contract-test stage: {stage}")
    cases = load_contract_cases(pack_root)
    results = []
    for case in cases:
        failures = []
        try:
            response = runner(case.prompt, {"stage": stage, "case": case.name})
            if not isinstance(response, dict):
                raise ValueError("runner must return an object")
        except Exception as exc:  # a scripted run failure is a test failure
            response = {}
            failures.append(f"runner error: {type(exc).__name__}: {exc}")
        for check in (check_tool_allowlist, check_refusal, check_output_shape):
            ok, reason = check(response, case)
            if not ok:
                failures.append(reason)
        results.append({"name": case.name, "passed": not failures,
                        "failures": failures})
    passed = sum(1 for item in results if item["passed"])
    return {"stage": stage, "pack": str(pack_root), "total": len(results),
            "passed": passed, "failed": len(results) - passed,
            "ok": passed == len(results), "results": results}


# ===========================================================================
# Z3 — Redacted replay export
# ===========================================================================

# Assignment values must be consumed in full, including spaces: a short
# first word ("token=super secret value") previously prevented any match at
# all.  Stop at the next secret-key assignment or a line break, and treat a quoted
# value as bounded by its closing quote.  Dict keys and Bearer credentials
# keep their existing handling (the rules below run in order).
_SECRET_KEYWORDS = (
    r"api[_-]?key|access[_-]?token|token|password|secret|authorization|pin"
)
_NEXT_ASSIGNMENT = (
    r"['\"]?\b\w*(?:" + _SECRET_KEYWORDS + r")\w*['\"]?\s*[:=]"
)
_ASSIGNED_SECRET_RE = re.compile(
    r"(?i)\b\w*(?:" + _SECRET_KEYWORDS + r")\w*\s*['\"]?\s*[:=]\s*"
    r"(?:"
    r"(?P<q>['\"])(?:(?!(?P=q))[^\r\n])*(?P=q)"
    r"|(?:['\"]?(?:Bearer|Basic)\s+)?"
    r"(?:(?!(?:" + _NEXT_ASSIGNMENT + r"))[^\r\n])*"
    r")"
)
_BARE_BEARER_RE = re.compile(r"(?i)\b(?:Bearer|Basic)\s+[^\s,;'\"\r\n]{4,}")

_REDACTION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("api_key", re.compile(
        r"\b(?:sk-[A-Za-z0-9_\-]{12,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,})\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("secret", _ASSIGNED_SECRET_RE),
    ("secret", _BARE_BEARER_RE),
    ("home_path", re.compile(
        r"(?:[A-Za-z]:[\\/]Users[\\/]|/home/|/Users/)[^\s\"'<>]+")),
    ("abs_path", re.compile(
        r"(?<![\w])(?:/(?:etc|var|tmp|opt|srv|usr|root)/[^\s\"'<>]+|"
        r"[A-Za-z]:[\\/][^\s\"'<>]+)")),
)


def redact_text(text: str) -> tuple[str, list[dict]]:
    """Redact secrets, paths and PII.  Returns the text and an audit preview."""
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    current = text
    preview: list[dict] = []
    for label, pattern in _REDACTION_RULES:
        def replace(match: re.Match[str], *, _label: str = label) -> str:
            snippet = match.group(0)[:80]
            if snippet not in [item["original"] for item in preview]:
                preview.append({"label": _label, "original": snippet,
                                "replacement": f"[REDACTED:{_label}]"})
            return f"[REDACTED:{_label}]"
        current = pattern.sub(replace, current)
    return current, preview


def redact_record(value: Any) -> Any:
    """Recursively redact strings in a session record; keep other JSON types."""
    if isinstance(value, str):
        return redact_text(value)[0]
    if isinstance(value, dict):
        # A credential may be used as a mapping key (e.g. {"sk-...": "ok"}).
        return {redact_text(key)[0] if isinstance(key, str) else key:
                redact_record(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_record(item) for item in value]
    return value


def render_replay(session: Mapping[str, Any], *, title: str = "Keel replay") -> dict:
    """Render a *standalone* redacted HTML replay with an integrity digest.

    No external script, style, font or image is referenced; all CSS is inline.
    """
    data = _require_dict(session, "session")
    events = data.get("events", [])
    if not isinstance(events, list):
        raise ValueError("session events must be a list")
    redacted_events = [redact_record(event) for event in events]
    preview: list[dict] = []
    for event in events:
        parts = tuple(event.keys()) + tuple(event.values()) \
            if isinstance(event, dict) else (event,)
        for part in parts:
            if isinstance(part, str):
                preview.extend(redact_text(part)[1])
    events_digest = _sha256_json(redacted_events)
    manifest = {"schema": "keel.replay-manifest/1", "events": redacted_events,
                "events_sha256": events_digest, "event_count": len(redacted_events)}
    manifest_attr = html.escape(_canonical_json(manifest), quote=True)
    parts = [
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n",
        f"<title>{html.escape(title)}</title>\n",
        f'<meta name="keel-replay-manifest" content="{manifest_attr}">\n',
        "<style>body{font-family:system-ui,sans-serif;max-width:52rem;margin:2rem auto;"
        "color:#222;line-height:1.5}pre{white-space:pre-wrap;background:#f6f6f6;"
        "padding:.75rem;border-radius:.4rem}.role{font-weight:700;text-transform:uppercase}"
        ".msg{margin:1rem 0}footer{font-size:.8rem;color:#666}</style>\n",
        "</head>\n<body>\n",
        f"<h1>{html.escape(title)}</h1>\n",
        '<div id="transcript">\n',
    ]
    for event in redacted_events:
        role = event.get("role", "event") if isinstance(event, dict) else "event"
        content = event.get("content", event) if isinstance(event, dict) else event
        if not isinstance(content, str):
            content = _canonical_json(content)
        parts.append(f'<div class="msg"><span class="role">{html.escape(str(role))}</span>'
                     f'<pre>{html.escape(content)}</pre></div>\n')
    parts.append("</div>\n")
    parts.append(f'<footer>Redactions applied: {len(preview)} · '
                 'no network assets · integrity hash below</footer>\n')
    parts.append("</body>\n</html>\n")
    raw_html = "".join(parts)
    integrity = _sha256_bytes(raw_html.encode("utf-8"))
    final_html = raw_html.replace(
        "</html>", f"<!-- keel-replay-integrity: {integrity} -->\n</html>")
    return {"html": final_html, "sha256": integrity, "events_sha256": events_digest,
            "event_count": len(redacted_events), "redactions": preview,
            "redaction_preview": preview}


def verify_replay(document: str) -> dict:
    """Recompute the HTML integrity digest and the replayed-events digest."""
    if not isinstance(document, str):
        raise ValueError("document must be a string")
    match = re.search(r"<!-- keel-replay-integrity: ([0-9a-f]{64}) -->\n?", document)
    if match is None:
        return {"ok": False, "reason": "missing integrity comment"}
    claimed = match.group(1)
    raw = document[:match.start()] + document[match.end():]
    actual = _sha256_bytes(raw.encode("utf-8"))
    if not hmac.compare_digest(claimed, actual):
        return {"ok": False, "reason": "integrity hash mismatch",
                "claimed": claimed, "actual": actual}
    meta = re.search(r'<meta name="keel-replay-manifest" content="([^"]*)">', raw)
    if meta is None:
        return {"ok": False, "reason": "missing replay manifest"}
    try:
        manifest = json.loads(html.unescape(meta.group(1)))
    except ValueError as exc:
        return {"ok": False, "reason": f"invalid replay manifest: {exc}"}
    if not isinstance(manifest, dict) or not isinstance(manifest.get("events"), list):
        return {"ok": False, "reason": "invalid replay manifest"}
    events_digest = _sha256_json(manifest["events"])
    if not hmac.compare_digest(events_digest, str(manifest.get("events_sha256", ""))):
        return {"ok": False, "reason": "events hash mismatch"}
    return {"ok": True, "sha256": actual, "events_sha256": events_digest,
            "event_count": len(manifest["events"])}


def assert_no_network_assets(document: str) -> bool:
    """Validate that a replay has no external asset references."""
    head = document.split('<div id="transcript">', 1)[0]
    forbidden_head = ("src=", "href=", "url(", "@import", "<script", "<link", "<iframe")
    if any(token in head.lower() for token in forbidden_head):
        return False
    return "<script" not in document.lower() and "<iframe" not in document.lower()


def write_replay(path: str | Path, session: Mapping[str, Any],
                 *, title: str = "Keel replay") -> dict:
    """Write the standalone replay to disk and verify what was written."""
    result = render_replay(session, title=title)
    if not assert_no_network_assets(result["html"]):
        raise ValueError("replay would contain network assets")
    target = _atomic_write_text(Path(path), result["html"])
    verified = verify_replay(target.read_text(encoding="utf-8"))
    if not verified["ok"]:
        raise ValueError(f"written replay failed integrity check: {verified}")
    return {"path": str(target), "sha256": result["sha256"],
            "events_sha256": result["events_sha256"],
            "event_count": result["event_count"],
            "redactions": result["redactions"], "verified": verified}


# ===========================================================================
# Z5 — Capability negotiation handshake
# ===========================================================================

CLIENT_CAPABILITIES: tuple[str, ...] = (
    "question_form", "diff_viewer", "image_display", "plugin_panels",
    "markdown", "streaming",
)
SERVER_CAPABILITIES: tuple[str, ...] = CLIENT_CAPABILITIES
PROTOCOL_VERSION = "keel-capabilities/1"
CAPABILITY_FALLBACKS: dict[str, str] = {
    "question_form": "text_prompt",
    "diff_viewer": "text_diff",
    "image_display": "text_placeholder",
    "plugin_panels": "plain_list",
    "markdown": "plain_text",
    "streaming": "batch",
}


@dataclass(frozen=True)
class Negotiation:
    protocol: str
    enabled: tuple[str, ...]
    disabled: tuple[str, ...]
    unknown: tuple[str, ...]
    fallbacks: dict[str, str]

    def to_dict(self) -> dict:
        return {"protocol": self.protocol, "enabled": list(self.enabled),
                "disabled": list(self.disabled), "unknown": list(self.unknown),
                "fallbacks": dict(self.fallbacks)}


def parse_client_capabilities(payload: Any) -> dict:
    """Strictly parse the JSON capabilities object sent at connect time."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError as exc:
            raise ValueError(f"invalid capabilities JSON: {exc}") from exc
    data = _require_dict(payload, "capabilities")
    declared = data.get("capabilities", [])
    if not isinstance(declared, (list, tuple)):
        raise ValueError("capabilities must be a list")
    for item in declared:
        if not isinstance(item, str) or not item:
            raise ValueError("capability names must be non-empty strings")
    client = data.get("client", {})
    if not isinstance(client, dict):
        raise ValueError("client must be an object")
    return {"capabilities": tuple(dict.fromkeys(declared)), "client": client,
            "protocol": data.get("protocol", PROTOCOL_VERSION)}


def negotiate(client_caps: Any, *,
              server_caps: Iterable[str] = SERVER_CAPABILITIES) -> Negotiation:
    """Intersect client/server capabilities and choose graceful fallbacks."""
    parsed = parse_client_capabilities(client_caps)
    server = set(server_caps)
    declared = set(parsed["capabilities"])
    enabled = tuple(sorted(declared & server))
    disabled = tuple(sorted((declared & set(CLIENT_CAPABILITIES)) - server))
    unknown = tuple(sorted(declared - set(CLIENT_CAPABILITIES)))
    fallbacks = {name: CAPABILITY_FALLBACKS[name] for name in sorted(disabled)}
    fallbacks.update({name: CAPABILITY_FALLBACKS[name]
                      for name in sorted(set(CLIENT_CAPABILITIES) - declared)
                      if name in CAPABILITY_FALLBACKS})
    return Negotiation(protocol=PROTOCOL_VERSION, enabled=enabled,
                       disabled=disabled, unknown=unknown, fallbacks=fallbacks)


def handshake(connect_payload: Any, *,
              server_caps: Iterable[str] = SERVER_CAPABILITIES) -> dict:
    """Full connect-time handshake response (JSON-serialisable)."""
    parsed = parse_client_capabilities(connect_payload)
    result = negotiate({"capabilities": parsed["capabilities"],
                        "client": parsed["client"]}, server_caps=server_caps)
    return {"protocol": PROTOCOL_VERSION, "client": parsed["client"],
            "negotiation": result.to_dict(), "server_capabilities": sorted(server_caps)}


def prompt_payload(negotiation: Negotiation, question: str) -> dict:
    """Choose the input shape a client can actually render (degrade gracefully)."""
    _require_str(question, "question")
    if "question_form" in negotiation.enabled:
        return {"kind": "form", "question": question,
                "options": ["yes", "no", "custom"]}
    return {"kind": negotiation.fallbacks.get("question_form", "text_prompt"),
            "question": question, "hint": "client has no question_form capability"}


# ===========================================================================
# Z6 — Local-first sync via the user's own folder
# ===========================================================================

class SyncError(ValueError):
    """Raised when an append-only change log is corrupt or tampered with."""


@dataclass(frozen=True)
class Change:
    seq: int
    key: str
    value: Any
    ts: float
    device: str
    prev: str
    checksum: str

    def payload(self) -> dict:
        return {"seq": self.seq, "key": self.key, "value": self.value,
                "ts": self.ts, "device": self.device, "prev": self.prev}


def _change_checksum(payload: dict) -> str:
    return _sha256_json({"prev": payload["prev"],
                         "payload": {k: v for k, v in payload.items() if k != "prev"}})


class LocalSync:
    """Append-only JSONL change log with last-writer-wins and visible conflicts."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.changes_path = self.root / "changes.jsonl"
        # Serialises read-chain / compute-seq / append across *all* instances
        # on this file, so concurrent writers cannot reuse the same seq and
        # prev digest.  A per-instance lock cannot protect a shared ledger.
        self._lock = _lock_for_path(self.changes_path)

    def changes(self) -> list[Change]:
        with self._lock:
            records = _read_jsonl(self.changes_path)
        result: list[Change] = []
        prev = GENESIS_DIGEST
        for expected_seq, record in enumerate(records, start=1):
            payload = {key: record.get(key) for key in
                       ("seq", "key", "value", "ts", "device", "prev")}
            if record.get("checksum") != _change_checksum(payload):
                raise SyncError(f"change {expected_seq} failed its checksum")
            if payload["seq"] != expected_seq or payload["prev"] != prev:
                raise SyncError(f"change {expected_seq} is out of order")
            _safe_relpath(payload["key"], "sync key")
            if not isinstance(payload["device"], str) or not payload["device"]:
                raise SyncError("change device must be a non-empty string")
            _require_number(payload["ts"], "change ts")
            change = Change(seq=payload["seq"], key=payload["key"],
                            value=payload["value"], ts=float(payload["ts"]),
                            device=payload["device"], prev=payload["prev"],
                            checksum=record["checksum"])
            result.append(change)
            prev = change.checksum
        return result

    def append(self, key: str, value: Any, *, device: str = "local",
               ts: float | None = None) -> Change:
        _safe_relpath(key, "sync key")
        _require_str(device, "device")
        stamp = time.time() if ts is None else _require_number(ts, "ts")
        with self._lock:
            existing = self.changes()
            payload = {"seq": len(existing) + 1, "key": key, "value": value,
                       "ts": stamp, "device": device,
                       "prev": existing[-1].checksum if existing else GENESIS_DIGEST}
            record = dict(payload)
            record["checksum"] = _change_checksum(payload)
            _append_jsonl(self.changes_path, record)
            return Change(**record)

    def materialize(self) -> dict:
        """Resolve every key with LWW; expose ties as explicit conflicts."""
        by_key: dict[str, list[Change]] = defaultdict(list)
        for change in self.changes():
            by_key[change.key].append(change)
        values: dict[str, Any] = {}
        conflicts: list[dict] = []
        for key in sorted(by_key):
            changes = by_key[key]
            top_ts = max(change.ts for change in changes)
            # Last-writer-wins picks a deterministic winner (timestamp, then
            # device name), but a simultaneous divergent write stays visible
            # as a conflict instead of being silently hidden.
            candidates = [change for change in changes if change.ts == top_ts]
            distinct = {_canonical_json(change.value) for change in candidates}
            chosen = sorted(candidates, key=lambda c: (c.device, _canonical_json(c.value)))[0]
            values[key] = chosen.value
            if len(distinct) > 1:
                conflicts.append({
                    "key": key,
                    "winner": {"value": chosen.value, "device": chosen.device,
                               "ts": chosen.ts},
                    "candidates": [{"value": c.value, "device": c.device,
                                    "ts": c.ts} for c in candidates],
                })
        return {"values": values, "conflicts": conflicts, "ok": not conflicts}

    def resolve(self, key: str, value: Any, *, device: str,
                ts: float) -> Change:
        """Resolve a conflict by appending a strictly newer winning change."""
        materialised = self.materialize()
        if not any(item["key"] == key for item in materialised["conflicts"]):
            raise ValueError(f"no conflict on key {key!r}")
        newest = max(change.ts for change in self.changes() if change.key == key)
        if ts <= newest:
            raise ValueError("resolution timestamp must be newer than all changes")
        return self.append(key, value, device=device, ts=ts)

    def snapshot(self) -> dict:
        return {"schema": "keel.local-sync/1", "changes": [c.payload() for c in self.changes()],
                **self.materialize()}


# ===========================================================================
# Z7 — Household/OS-user separation
# ===========================================================================

def sanitize_user(name: str) -> str:
    """Return a safe single path segment for an OS user name."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", _require_str(name, "user"))
    cleaned = cleaned.strip("._") or "unknown"
    return cleaned[:64]


def current_os_user(environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    raw = env.get("USERNAME") or env.get("USER") or env.get("LOGNAME") or ""
    if not raw:
        try:
            raw = getpass.getuser()
        except Exception:
            raw = "unknown"
    return sanitize_user(raw)


def user_state_root(base_root: str | Path, *, user: str | None = None,
                    environ: Mapping[str, str] | None = None) -> Path:
    """Per-OS-user state directory under the shared installation root."""
    name = sanitize_user(user) if user is not None else current_os_user(environ)
    return Path(base_root) / "users" / name


def keychain_entry(user: str, *, service: str = "keel") -> dict:
    """Describe a *separate* keychain entry for one OS user (no secret stored)."""
    name = sanitize_user(user)
    return {"service": service, "account": name,
            "label": f"{service}:{name}", "secret": None}


class ManagedPolicy:
    """Admin-managed restriction keys (e.g. lock model downloads)."""

    def __init__(self, doc: Mapping[str, Any] | None = None):
        self.doc = dict(doc or {})
        if not isinstance(self.doc.get("admins", []), list) \
                or not isinstance(self.doc.get("locked_users", []), list):
            raise ValueError("invalid managed policy")

    @classmethod
    def load(cls, path: str | Path) -> "ManagedPolicy":
        try:
            doc = json.loads(Path(path).read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ValueError(f"invalid managed policy at {path}: {exc}") from exc
        return cls(doc)

    def locks_downloads(self, user: str) -> tuple[bool, str]:
        name = sanitize_user(user)
        if name in set(self.doc.get("admins", [])):
            return False, "admin exempt from managed download lock"
        if self.doc.get("model_downloads_locked") is True:
            return True, "managed policy locks model downloads for this device"
        if name in set(self.doc.get("locked_users", [])):
            return True, "managed policy locks model downloads for this user"
        return False, "no managed download lock"


def can_download_model(user: str, policy: ManagedPolicy | None = None) -> dict:
    effective = policy or ManagedPolicy()
    locked, reason = effective.locks_downloads(user)
    return {"allowed": not locked, "reason": reason, "user": sanitize_user(user)}


def household_layout(base_root: str | Path, *, user: str | None = None,
                     environ: Mapping[str, str] | None = None) -> dict:
    name = sanitize_user(user) if user is not None else current_os_user(environ)
    root = user_state_root(base_root, user=name)
    return {"user": name, "state_dir": str(root / "state"),
            "workspace": str(root / "workspace"), "cache": str(root / "cache"),
            "keychain": keychain_entry(name)}


# ===========================================================================
# Z8 — Energy and cost estimator for local runs
# ===========================================================================

def measure_throughput(tokens: int, elapsed_s: float) -> float:
    """Measured output throughput in tokens/second (never a fabricated value)."""
    count = _require_number(tokens, "tokens")
    seconds = _require_number(elapsed_s, "elapsed_s", minimum=1e-9)
    if count != int(count):
        raise ValueError("tokens must be an integer")
    return round(count / seconds, 6)


def estimate_energy(*, tokens: int, elapsed_s: float, watts: float,
                    usd_per_kwh: float = 0.15) -> dict:
    """Estimate energy for a local run from measured duration and user watts."""
    rate = measure_throughput(tokens, elapsed_s)
    draw = _require_number(watts, "watts")
    price = _require_number(usd_per_kwh, "usd_per_kwh")
    seconds = float(elapsed_s)
    joules = draw * seconds
    kwh = joules / 3_600_000
    return {"is_estimate": True, "label": "estimate",
            "assumptions": {"watts": draw, "usd_per_kwh": price,
                            "measurement": "user-entered power draw and measured elapsed time"},
            "tokens": int(tokens), "elapsed_s": seconds,
            "tokens_per_second": rate,
            "energy_joules": round(joules, 6), "energy_kwh": round(kwh, 9),
            "estimated_cost_usd": round(kwh * price, 9)}


def estimate_local_run(*, input_tokens: int = 0, output_tokens: int = 0,
                       elapsed_s: float, watts: float,
                       usd_per_kwh: float = 0.15) -> dict:
    """Dashboard-ready estimate; local runs are billed in energy, not API cost."""
    input_count = _require_number(input_tokens, "input_tokens")
    output_count = _require_number(output_tokens, "output_tokens")
    if input_count != int(input_count) or output_count != int(output_count):
        raise ValueError("token counts must be integers")
    total = int(input_count + output_count)
    result = estimate_energy(tokens=total, elapsed_s=elapsed_s, watts=watts,
                             usd_per_kwh=usd_per_kwh)
    result.update({"input_tokens": int(input_count), "output_tokens": int(output_count),
                   "total_tokens": total,
                   "note": "Local-run estimate only: no provider billing is involved."})
    return result


def energy_summary(runs: Sequence[Mapping[str, Any]]) -> dict:
    """Aggregate already-computed estimates (does not invent missing measurements)."""
    total_joules = 0.0
    total_cost = 0.0
    total_tokens = 0
    for run in runs:
        if not run.get("is_estimate"):
            raise ValueError("run is not a labelled estimate")
        total_joules += float(run["energy_joules"])
        total_cost += float(run["estimated_cost_usd"])
        total_tokens += int(run["total_tokens"])
    return {"is_estimate": True, "runs": len(runs), "total_tokens": total_tokens,
            "total_energy_joules": round(total_joules, 6),
            "total_estimated_cost_usd": round(total_cost, 9)}


# ===========================================================================
# Z9 — Natural-language policy editor
# ===========================================================================

TIER2_PROTECTED_TOOLS: tuple[str, ...] = ("read_file", "list_files", "view_image")


@dataclass(frozen=True)
class PolicyRule:
    effect: str
    tool: str
    command_prefix: str = ""
    source_text: str = ""

    def to_dict(self) -> dict:
        return {"effect": self.effect, "tool": self.tool,
                "command_prefix": self.command_prefix,
                "source_text": self.source_text}


_RULE_PATTERNS: tuple[tuple[re.Pattern[str], str, bool], ...] = (
    (re.compile(r"^(?:never|don'?t|do not|stop me from)\s+(?:running|run|execute|executing)\s+(.+?)\.?$", re.I), "deny", True),
    (re.compile(r"^(?:block|forbid|deny)\s+(?:the\s+)?([a-z0-9_.\-]+)\s*(?:tool)?\.?$", re.I), "deny", False),
    (re.compile(r"^(?:never|don'?t|do not)\s+(?:use|using)\s+([a-z0-9_.\-]+)\s*(?:tool)?\.?$", re.I), "deny", False),
    (re.compile(r"^(?:always\s+)?(?:allow|permit|enable)\s+([a-z0-9_.\-]+)\s*(?:tool)?\.?$", re.I), "allow", False),
)


def propose_rule(text: str) -> dict:
    """Translate a natural-language sentence into an exact JSON rule."""
    cleaned = _require_str(text, "policy text").strip()
    for pattern, effect, is_command in _RULE_PATTERNS:
        match = pattern.match(cleaned)
        if match is None:
            continue
        target = match.group(1).strip().strip(".")
        if not target:
            continue
        rule = PolicyRule(
            effect=effect,
            tool="shell" if is_command else target.lower(),
            command_prefix=target.lower() if is_command else "",
            source_text=cleaned,
        )
        ok, conflicts = validate_rule(rule)
        return {"ok": ok, "rule": rule.to_dict() if ok else None,
                "conflicts": conflicts,
                "reason": "ok" if ok else "proposed rule conflicts with tier-2 protections"}
    return {"ok": False, "rule": None, "conflicts": [],
            "reason": "unsupported policy phrase"}


def validate_rule(rule: Any, *, existing: Iterable[Any] = ()) -> tuple[bool, list[str]]:
    """Validate rule shape and reject Tier-2 conflicts (allow/deny on one tool)."""
    data = rule.to_dict() if isinstance(rule, PolicyRule) else _require_dict(rule, "rule")
    allowed_keys = {"effect", "tool", "command_prefix", "source_text"}
    unknown = sorted(set(data) - allowed_keys)
    if unknown:
        return False, [f"unknown rule keys: {unknown}"]
    if data.get("effect") not in ("allow", "deny"):
        return False, ["effect must be 'allow' or 'deny'"]
    tool = _require_str(data.get("tool"), "rule tool").lower()
    conflicts: list[str] = []
    if data["effect"] == "deny" and tool in TIER2_PROTECTED_TOOLS:
        conflicts.append(f"tier-2 conflict: {tool} is a protected read-only tool")
    for other in existing:
        other_data = other.to_dict() if isinstance(other, PolicyRule) else other
        other_tool = str(other_data.get("tool", "")).lower()
        if other_tool == tool and other_data.get("effect") != data["effect"]:
            conflicts.append(f"conflicting rule for {tool}: {other_data.get('effect')}")
    return not conflicts, conflicts


def simulate(rule: Any, actions: Iterable[Mapping[str, Any]]) -> dict:
    """Show exactly which sample actions the proposed rule would match."""
    data = rule.to_dict() if isinstance(rule, PolicyRule) else _require_dict(rule, "rule")
    ok, conflicts = validate_rule(data)
    if not ok:
        return {"ok": False, "conflicts": conflicts, "matched": [], "unmatched": 0}
    prefix = str(data.get("command_prefix", "")).lower()
    tool = str(data["tool"]).lower()
    matched: list[dict] = []
    unmatched = 0
    for action in actions:
        action_data = _require_dict(action, "action")
        action_tool = str(action_data.get("tool", "")).lower()
        command = str(action_data.get("command", "")).lower()
        hit = action_tool == tool and (not prefix or command.startswith(prefix))
        entry = {"action": action_data, "matched": hit,
                 "decision": data["effect"] if hit else "unchanged"}
        if hit:
            matched.append(entry)
        else:
            unmatched += 1
    return {"ok": True, "conflicts": [], "matched": matched, "unmatched": unmatched,
            "decision": data["effect"]}


def policy_editor(text: str, actions: Iterable[Mapping[str, Any]], *,
                  approve: bool = False, existing: Iterable[Any] = ()) -> dict:
    """Propose → simulate → (explicit) approve.  Nothing is applied implicitly."""
    proposal = propose_rule(text)
    actions = list(actions)
    if not proposal["ok"]:
        return {"proposal": proposal, "simulation": {"ok": False, "matched": []},
                "approved_rule": None,
                "reason": "no rule was proposed; nothing to approve"}
    rule = proposal["rule"]
    simulation = simulate(rule, actions)
    ok, conflicts = validate_rule(rule, existing=existing)
    simulation["conflicts"] = conflicts
    simulation["ok"] = simulation["ok"] and ok
    approved = rule if (approve and simulation["ok"]) else None
    reason = ("approved" if approved is not None else
              "tier-2 or existing-policy conflict" if conflicts else
              "approval required" if not approve else "simulation found no valid rule")
    return {"proposal": proposal, "simulation": simulation, "conflicts": conflicts,
            "approved_rule": approved, "reason": reason}


# ===========================================================================
# Z10 — Provider/model drift detector
# ===========================================================================

class DriftStore:
    """SQLite store of model-health scores keyed by model hash + runtime version."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        # One shared connection usable from any thread, with a reentrant lock
        # around every operation.  Keeping a single connection also preserves
        # :memory: state across calls (and across threads).
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS model_health ("
                "seq INTEGER PRIMARY KEY AUTOINCREMENT, model TEXT NOT NULL, "
                "model_hash TEXT NOT NULL, runtime_version TEXT NOT NULL, "
                "score REAL NOT NULL, ts REAL NOT NULL)")
            self.conn.commit()

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def record(self, model: str, model_hash: str, runtime_version: str,
               score: float, *, ts: float | None = None) -> dict:
        _require_str(model, "model")
        _require_str(model_hash, "model_hash")
        _require_str(runtime_version, "runtime_version")
        value = _require_number(score, "score")
        if value > 1.0:
            raise ValueError("score must be <= 1")
        stamp = time.time() if ts is None else _require_number(ts, "ts")
        with self._lock:
            cursor = self.conn.execute(
                "INSERT INTO model_health(model, model_hash, runtime_version, score, ts) "
                "VALUES (?,?,?,?,?)", (model, model_hash, runtime_version, value, stamp))
            self.conn.commit()
        return {"seq": cursor.lastrowid, "model": model, "model_hash": model_hash,
                "runtime_version": runtime_version, "score": value, "ts": stamp}

    def latest(self, model: str, *, before: float | None = None) -> dict | None:
        _require_str(model, "model")
        with self._lock:
            if before is None:
                row = self.conn.execute(
                    "SELECT * FROM model_health WHERE model=? ORDER BY ts DESC, seq DESC LIMIT 1",
                    (model,)).fetchone()
            else:
                row = self.conn.execute(
                    "SELECT * FROM model_health WHERE model=? AND ts < ? "
                    "ORDER BY ts DESC, seq DESC LIMIT 1", (model, before)).fetchone()
        return dict(row) if row is not None else None

    def detect(self, model: str, model_hash: str, runtime_version: str,
               score: float, *, threshold: float = 0.05,
               ts: float | None = None) -> dict:
        """Compare a new score with the previous one and persist the new score."""
        drop_limit = _require_number(threshold, "threshold")
        stamp = time.time() if ts is None else _require_number(ts, "ts")
        value = _require_number(score, "score")
        if value > 1.0:
            raise ValueError("score must be <= 1")
        # The comparison and the persistence are one operation under the lock.
        with self._lock:
            previous = self.latest(model, before=stamp)
            if previous is None:
                report = {"drift": False, "reason": "no_baseline", "previous": None,
                          "delta": 0.0, "changed_model_hash": False,
                          "changed_runtime_version": False}
            else:
                delta = round(float(previous["score"]) - value, 8)
                changed_hash = previous["model_hash"] != model_hash
                changed_runtime = previous["runtime_version"] != runtime_version
                if delta >= drop_limit:
                    reason = "score_drop_after_change" if (changed_hash or changed_runtime) \
                        else "score_regression"
                else:
                    reason = "stable"
                report = {"drift": delta >= drop_limit, "reason": reason,
                          "previous": previous, "delta": delta,
                          "changed_model_hash": changed_hash,
                          "changed_runtime_version": changed_runtime}
            current = self.record(model, model_hash, runtime_version, value, ts=stamp)
        report.update({"model": model, "model_hash": model_hash,
                       "runtime_version": runtime_version, "current": current,
                       "threshold": drop_limit})
        return report

    def weekly_check(self, model: str, model_hash: str, runtime_version: str,
                     score: float, *, now: float, interval_days: int = 7,
                     threshold: float = 0.05) -> dict:
        """Run the scheduled local health check only when it is actually due."""
        if interval_days <= 0:
            raise ValueError("interval_days must be positive")
        reference = self.latest(model)
        interval_s = interval_days * 86400
        if reference is not None and now - float(reference["ts"]) < interval_s:
            return {"due": False, "next_due": float(reference["ts"]) + interval_s,
                    "report": None}
        report = self.detect(model, model_hash, runtime_version, score,
                             threshold=threshold, ts=now)
        return {"due": True, "next_due": now + interval_s, "report": report}


# ===========================================================================
# Z11 — Dormant-integration health board
# ===========================================================================

STATUS_DORMANT = "dormant"
STATUS_CONNECTING = "connecting"
STATUS_ACTIVE = "active"
STATUS_ERROR = "error"
INTEGRATION_STATUSES = (STATUS_DORMANT, STATUS_CONNECTING, STATUS_ACTIVE, STATUS_ERROR)
DEFAULT_REPROBE_INTERVAL_S = 3600


@dataclass(frozen=True)
class Integration:
    id: str
    kind: str  # connector | channel | mcp_server
    required_settings: tuple[str, ...] = ()
    display_name: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind,
                "required_settings": list(self.required_settings),
                "display_name": self.display_name or self.id}


def _setting_present(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def probe(integration: Integration, settings: Mapping[str, Any], *,
          now: float | None = None) -> dict:
    """Probe one integration from the supplied local settings (no network)."""
    if integration.kind not in ("connector", "channel", "mcp_server"):
        raise ValueError(f"unknown integration kind: {integration.kind}")
    _require_dict(settings, "settings")
    missing = [key for key in integration.required_settings
               if not _setting_present(settings.get(key))]
    if missing:
        status = STATUS_ERROR if settings.get(f"{integration.id}.last_error") \
            else STATUS_DORMANT
        last_probe = None
    elif settings.get(f"{integration.id}.connecting"):
        status = STATUS_CONNECTING
        last_probe = None
    elif settings.get(f"{integration.id}.disabled"):
        status = STATUS_DORMANT
        last_probe = None
    else:
        status = STATUS_ACTIVE
        last_probe = time.time() if now is None else _require_number(now, "now")
    return {"id": integration.id, "kind": integration.kind, "status": status,
            "missing_settings": missing, "last_probe": last_probe,
            "display_name": integration.display_name or integration.id}


def reprobe_due(row: Mapping[str, Any], *, now: float,
                interval_s: float = DEFAULT_REPROBE_INTERVAL_S) -> bool:
    """Y4.1-style schedule: dormant rows are always due for a re-probe."""
    stamp = row.get("last_probe")
    if stamp is None:
        return True
    return now - float(stamp) >= _require_number(interval_s, "interval_s", minimum=1e-9)


def health_board(integrations: Iterable[Integration], settings: Mapping[str, Any], *,
                 now: float | None = None,
                 interval_s: float = DEFAULT_REPROBE_INTERVAL_S) -> dict:
    stamp = time.time() if now is None else _require_number(now, "now")
    rows = []
    for integration in integrations:
        row = probe(integration, settings, now=stamp)
        row["next_probe_due"] = reprobe_due(row, now=stamp, interval_s=interval_s)
        rows.append(row)
    rows.sort(key=lambda r: (r["status"], r["id"]))
    summary = {status: sum(1 for row in rows if row["status"] == status)
               for status in INTEGRATION_STATUSES}
    return {"schema": "keel.integration-health/1", "rows": rows,
            "summary": summary, "total": len(rows),
            "ok": summary[STATUS_ERROR] == 0}


# ===========================================================================
# Z12 — Offline signed catalog updates (RFC 8032 Ed25519, stdlib only)
# ===========================================================================

_P = 2 ** 255 - 19
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_I = pow(2, (_P - 1) // 4, _P)
_L = 2 ** 252 + 27742317777372353535851937790883648493
_BY = (4 * pow(5, _P - 2, _P)) % _P
CATALOG_KINDS = ("model_catalog", "mcp_presets", "language_pack")
BUNDLE_SCHEMA = "keel.catalog-bundle/1"
CERT_SCHEMA = "keel.catalog-key/1"


class SignatureError(ValueError):
    """Raised when a catalog bundle or key certificate fails verification."""


def _recover_x(y_squared: int) -> int:
    numerator = (y_squared - 1) % _P
    denominator = pow((_D * y_squared + 1) % _P, _P - 2, _P)
    value = (numerator * denominator) % _P
    x = pow(value, (_P + 3) // 8, _P)
    if (x * x - value) % _P != 0:
        x = (x * _I) % _P
    return x


_BX = _recover_x((_BY * _BY) % _P)
_BASE = (_BX, _BY, 1, (_BX * _BY) % _P)
if (_BX * _BX - ((_BY * _BY - 1) * pow(_D * _BY * _BY + 1, _P - 2, _P))) % _P != 0 \
        or _BX % 2 != 0:
    _BX = _P - _BX
    _BASE = (_BX, _BY, 1, (_BX * _BY) % _P)


def _point_add(p1: tuple[int, int, int, int], p2: tuple[int, int, int, int]) \
        -> tuple[int, int, int, int]:
    x1, y1, z1, t1 = p1
    x2, y2, z2, t2 = p2
    a = ((y1 - x1) * (y2 - x2)) % _P
    b = ((y1 + x1) * (y2 + x2)) % _P
    c = (2 * _D * t1 * t2) % _P
    d = (2 * z1 * z2) % _P
    e, f, g, h = (b - a) % _P, (d - c) % _P, (d + c) % _P, (b + a) % _P
    return ((e * f) % _P, (g * h) % _P, (f * g) % _P, (e * h) % _P)


def _point_mul(scalar: int, point: tuple[int, int, int, int]) \
        -> tuple[int, int, int, int]:
    result = (0, 1, 1, 0)
    addend = point
    while scalar:
        if scalar & 1:
            result = _point_add(result, addend)
        addend = _point_add(addend, addend)
        scalar >>= 1
    return result


def _encode_point(point: tuple[int, int, int, int]) -> bytes:
    x, y, z, _t = point
    inv_z = pow(z, _P - 2, _P)
    ax = (x * inv_z) % _P
    ay = (y * inv_z) % _P
    return ((ay | ((ax & 1) << 255))).to_bytes(32, "little")


def _decode_point(data: bytes) -> tuple[int, int, int, int]:
    if not isinstance(data, bytes) or len(data) != 32:
        raise SignatureError("public key / signature point must be 32 bytes")
    y = int.from_bytes(data, "little") & ((1 << 255) - 1)
    if y >= _P:
        raise SignatureError("non-canonical point encoding")
    sign = (data[31] >> 7) & 1
    y_sq = (y * y) % _P
    numerator = (y_sq - 1) % _P
    denominator = pow((_D * y_sq + 1) % _P, _P - 2, _P)
    value = (numerator * denominator) % _P
    x = _recover_x(y_sq)
    if (x * x - value) % _P != 0:
        raise SignatureError("point is not on the curve")
    if (x & 1) != sign:
        x = _P - x
    return (x, y, 1, (x * y) % _P)


@dataclass(frozen=True)
class KeyPair:
    seed: bytes
    public_key: bytes


def generate_keypair(seed: bytes | None = None) -> KeyPair:
    """Derive an Ed25519 public key from a 32-byte seed (RFC 8032)."""
    if seed is None:
        seed = os.urandom(32)
    if not isinstance(seed, bytes) or len(seed) != 32:
        raise ValueError("seed must be exactly 32 bytes")
    digest = hashlib.sha512(seed).digest()
    scalar_bytes = bytearray(digest[:32])
    scalar_bytes[0] &= 248
    scalar_bytes[31] &= 127
    scalar_bytes[31] |= 64
    scalar = int.from_bytes(scalar_bytes, "little")
    return KeyPair(seed=seed, public_key=_encode_point(_point_mul(scalar, _BASE)))


def sign(message: bytes, keypair: KeyPair) -> bytes:
    """Create a 64-byte RFC 8032 Ed25519 signature."""
    if not isinstance(message, bytes):
        raise ValueError("message must be bytes")
    digest = hashlib.sha512(keypair.seed).digest()
    scalar_bytes = bytearray(digest[:32])
    scalar_bytes[0] &= 248
    scalar_bytes[31] &= 127
    scalar_bytes[31] |= 64
    scalar = int.from_bytes(scalar_bytes, "little")
    prefix = digest[32:]
    nonce = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % _L
    encoded_r = _encode_point(_point_mul(nonce, _BASE))
    challenge = int.from_bytes(
        hashlib.sha512(encoded_r + keypair.public_key + message).digest(), "little") % _L
    response = (nonce + challenge * scalar) % _L
    return encoded_r + response.to_bytes(32, "little")


def verify(message: bytes, signature: bytes, public_key: bytes) -> bool:
    """Verify an Ed25519 signature with a cofactored check (rejects small order)."""
    try:
        if not isinstance(message, bytes) or not isinstance(signature, bytes):
            return False
        if len(signature) != 64:
            return False
        encoded_r, response_bytes = signature[:32], signature[32:]
        response = int.from_bytes(response_bytes, "little")
        if response >= _L:
            return False
        point_r = _decode_point(encoded_r)
        point_a = _decode_point(public_key)
        challenge = int.from_bytes(
            hashlib.sha512(encoded_r + public_key + message).digest(), "little") % _L
        left = _point_mul(8 * response, _BASE)
        right = _point_add(_point_mul(8, point_r), _point_mul(8 * challenge, point_a))
        return hmac.compare_digest(_encode_point(left), _encode_point(right))
    except (SignatureError, ValueError):
        return False


def make_key_certificate(child_public: bytes, key_id: str, root: KeyPair,
                         *, signed_by: str = "root", ts: float | None = None) -> dict:
    """Root-signed certificate binding a catalog key id to an Ed25519 key."""
    body = {"schema": CERT_SCHEMA, "key_id": _require_str(key_id, "key_id"),
            "signed_by": _require_str(signed_by, "signed_by"),
            "public_key": bytes(child_public).hex(),
            "ts": time.time() if ts is None else _require_number(ts, "ts")}
    return {**body, "algorithm": "Ed25519",
            "signature": sign(_canonical_json(body).encode("utf-8"), root).hex()}


def verify_key_certificate(cert: Any, trust_root: Mapping[str, bytes | str]) -> bytes:
    """Verify an offline certificate against a caller-supplied trust root."""
    data = _require_dict(cert, "certificate")
    if data.get("schema") != CERT_SCHEMA or data.get("algorithm") != "Ed25519":
        raise SignatureError("unsupported certificate")
    body = {key: value for key, value in data.items()
            if key not in ("signature", "algorithm")}
    root_key = trust_root.get(str(body.get("signed_by")))
    if root_key is None:
        raise SignatureError("unknown root key")
    root_bytes = bytes.fromhex(root_key) if isinstance(root_key, str) else bytes(root_key)
    try:
        signature = bytes.fromhex(str(data.get("signature", "")))
    except ValueError as exc:
        raise SignatureError("invalid certificate signature encoding") from exc
    if not verify(_canonical_json(body).encode("utf-8"), signature, root_bytes):
        raise SignatureError("certificate signature is invalid")
    return bytes.fromhex(str(body["public_key"]))


def make_catalog_bundle(kind: str, version: int, payload: Mapping[str, Any],
                        signing_key: KeyPair, *, key_id: str,
                        certificate: dict | None = None,
                        ts: float | None = None) -> dict:
    """Create a versioned, signed offline bundle (feed or USB import)."""
    if kind not in CATALOG_KINDS:
        raise ValueError(f"unknown catalog kind: {kind}")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("version must be a positive integer")
    body = {"schema": BUNDLE_SCHEMA, "kind": kind, "version": version,
            "payload": _require_dict(payload, "payload"),
            "key_id": _require_str(key_id, "key_id"),
            "ts": time.time() if ts is None else _require_number(ts, "ts")}
    bundle = dict(body)
    bundle["algorithm"] = "Ed25519"
    bundle["signature"] = sign(_canonical_json(body).encode("utf-8"), signing_key).hex()
    if certificate is not None:
        bundle["certificate"] = certificate
    return bundle


def verify_bundle(bundle: Any, trust_root: Mapping[str, bytes | str]) -> dict:
    """Verify signature (and optional chain) before any import happens."""
    data = _require_dict(bundle, "bundle")
    if data.get("schema") != BUNDLE_SCHEMA or data.get("algorithm") != "Ed25519":
        raise SignatureError("unsupported catalog bundle")
    if data.get("kind") not in CATALOG_KINDS:
        raise SignatureError("unknown catalog kind")
    version = data.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise SignatureError("invalid catalog version")
    body = {key: value for key, value in data.items()
            if key not in ("signature", "algorithm", "certificate")}
    try:
        signature = bytes.fromhex(str(data.get("signature", "")))
    except ValueError as exc:
        raise SignatureError("invalid bundle signature encoding") from exc
    if "certificate" in data:
        public = verify_key_certificate(data["certificate"], trust_root)
        if data["certificate"].get("key_id") != body.get("key_id"):
            raise SignatureError("certificate key_id does not match the bundle")
    else:
        trusted = trust_root.get(str(body.get("key_id")))
        if trusted is None:
            raise SignatureError("unknown signing key")
        public = bytes.fromhex(trusted) if isinstance(trusted, str) else bytes(trusted)
    if not verify(_canonical_json(body).encode("utf-8"), signature, public):
        raise SignatureError("catalog bundle signature is invalid")
    return dict(body["payload"])


def import_bundle(bundle: Any, state_root: str | Path,
                  trust_root: Mapping[str, bytes | str]) -> dict:
    """Verify, reject downgrades, then write the catalog bundle offline."""
    payload = verify_bundle(bundle, trust_root)
    bundle_data = _require_dict(bundle, "bundle")
    root = Path(state_root)
    index_path = root / "catalog-index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8")) \
            if index_path.is_file() else {}
    except ValueError as exc:
        raise ValueError(f"invalid catalog index: {exc}") from exc
    if not isinstance(index, dict):
        raise ValueError("invalid catalog index")
    kind = str(bundle_data["kind"])
    version = int(bundle_data["version"])
    current = index.get(kind, 0)
    if version <= current:
        raise ValueError(f"catalog downgrade rejected: {kind} v{version} <= v{current}")
    target = root / "catalogs" / kind / f"v{version}.json"
    _atomic_write_text(target, _canonical_json(payload) + "\n")
    index[kind] = version
    _atomic_write_text(index_path, _canonical_json(index) + "\n")
    return {"kind": kind, "version": version, "path": str(target),
            "entries": len(payload)}


# ===========================================================================
# Z13 — "Why can't I do X?" explainer
# ===========================================================================

@dataclass(frozen=True)
class Requirement:
    kind: str  # flag | setting | permission | policy | dependency
    name: str
    description: str = ""

    def to_dict(self) -> dict:
        return {"kind": self.kind, "name": self.name,
                "description": self.description}


@dataclass(frozen=True)
class FeatureSpec:
    id: str
    title: str
    requires: tuple[Requirement, ...] = ()

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title,
                "requires": [req.to_dict() for req in self.requires]}


_FEATURES: dict[str, FeatureSpec] = {}


def _register(spec: FeatureSpec) -> None:
    _FEATURES[spec.id] = spec


_register(FeatureSpec("web_fetch", "Web fetch", (
    Requirement("flag", "network", "network access must be enabled"),
    Requirement("setting", "webfetch_enabled", "web fetch must be enabled in settings"),
    Requirement("permission", "network", "the agent needs the network permission"),
)))
_register(FeatureSpec("code_execution", "Shell execution", (
    Requirement("flag", "shell", "shell tools must be enabled"),
    Requirement("permission", "execute", "the agent needs the execute permission"),
    Requirement("policy", "shell_allowed", "no execution policy may deny shell"),
)))
_register(FeatureSpec("model_download", "Model download", (
    Requirement("setting", "allow_model_downloads", "downloads must be enabled"),
    Requirement("dependency", "household_policy", "managed policy must allow downloads"),
)))
_register(FeatureSpec("plugins", "Plugin panels", (
    Requirement("flag", "plugins", "plugins must be enabled"),
    Requirement("dependency", "capability_negotiation", "client must support plugin panels"),
)))


def register_feature(spec: FeatureSpec) -> None:
    """Extend the built-in catalogue with a feature and its requires list."""
    if not isinstance(spec, FeatureSpec) or not spec.id:
        raise ValueError("invalid feature spec")
    _register(spec)


def known_features() -> list[str]:
    return sorted(_FEATURES)


def _context_sections(context: Mapping[str, Any]) -> dict:
    return {
        "flag": _require_dict(context.get("flags", {}), "flags"),
        "setting": _require_dict(context.get("settings", {}), "settings"),
        "policy": _require_dict(context.get("policies", {}), "policies"),
        "dependency": _require_dict(context.get("features", {}), "features"),
        "permission": set(context.get("permissions", []) or []),
    }


def evaluate_requirement(requirement: Requirement, context: Mapping[str, Any]) -> dict:
    if requirement.kind not in ("flag", "setting", "permission", "policy", "dependency"):
        raise ValueError(f"unknown requirement kind: {requirement.kind}")
    sections = _context_sections(context)
    if requirement.kind == "permission":
        ok = requirement.name in sections["permission"]
        observed = "present" if ok else "missing"
    else:
        value = sections[requirement.kind].get(requirement.name)
        ok = bool(value)
        observed = str(value)
    return {"requirement": requirement.to_dict(), "ok": ok, "observed": observed}


def explain(feature_id: str, context: Mapping[str, Any]) -> dict:
    """Explain which requirement, policy or flag blocks a feature."""
    spec = _FEATURES.get(feature_id)
    if spec is None:
        raise ValueError(f"unknown feature: {feature_id}")
    _require_dict(context, "context")
    evaluations = [evaluate_requirement(req, context) for req in spec.requires]
    blockers = [item for item in evaluations if not item["ok"]]
    lines = []
    for item in blockers:
        req = item["requirement"]
        lines.append(f"{feature_id} is disabled: {req['kind']} {req['name']!r} "
                     f"is not satisfied ({item['observed']}). "
                     f"{req['description']}".rstrip())
    return {"feature_id": feature_id, "title": spec.title,
            "enabled": not blockers, "blockers": blockers,
            "requires": [req.to_dict() for req in spec.requires],
            "why": "\n".join(lines) if lines else f"{feature_id} is enabled."}


def why_cant_i(feature_id: str, context: Mapping[str, Any]) -> str:
    """Plain-text backend answer to "Why can't I do X?"."""
    return explain(feature_id, context)["why"]


def feature_matrix(context: Mapping[str, Any]) -> list[dict]:
    return [{"id": feature_id, "enabled": explain(feature_id, context)["enabled"],
             "why": explain(feature_id, context)["why"]}
            for feature_id in known_features()]


# ===========================================================================
# Z14 — Pre-flight installer report
# ===========================================================================

def load_manifest(path: str | Path) -> dict:
    """Load a build manifest; no install action is performed."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"invalid build manifest at {path}: {exc}") from exc
    return _require_dict(doc, "build manifest")


def _manifest_entries(manifest: Mapping[str, Any], key: str) -> list[dict]:
    entries = manifest.get(key, [])
    if not isinstance(entries, list):
        raise ValueError(f"manifest {key} must be a list")
    result = []
    for entry in entries:
        if isinstance(entry, str):
            result.append({"name": entry})
        elif isinstance(entry, dict):
            result.append(dict(entry))
        else:
            raise ValueError(f"manifest {key} entries must be strings or objects")
    return result


def build_preflight_report(manifest: Mapping[str, Any], *,
                           target_root: str | Path | None = None,
                           existing: Iterable[str] = ()) -> dict:
    """Report files/protocols/services an installer *would* touch, without acting."""
    data = _require_dict(manifest, "build manifest")
    existing_set = {str(item) for item in existing}
    root = Path(target_root) if target_root is not None else None
    files: list[dict] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for entry in _manifest_entries(data, "files"):
        rel = _safe_relpath(entry.get("name"), "manifest file")
        name = rel.as_posix()
        if name in seen:
            warnings.append(f"duplicate file in manifest: {name}")
        seen.add(name)
        on_disk = (root / rel).exists() if root is not None else name in existing_set
        files.append({"category": "file", "path": name,
                      "action": "overwrite" if on_disk else "create",
                      "bytes": int(entry.get("bytes", 0)) if "bytes" in entry else None})
    protocols = []
    for entry in _manifest_entries(data, "protocols"):
        name = _require_str(entry.get("name"), "protocol name")
        protocols.append({"category": "protocol", "name": name, "action": "register",
                          "description": str(entry.get("description", ""))})
    services = []
    for entry in _manifest_entries(data, "services"):
        name = _require_str(entry.get("name"), "service name")
        services.append({"category": "service", "name": name, "action": "add",
                         "description": str(entry.get("description", ""))})
    registry = []
    for entry in _manifest_entries(data, "registry"):
        name = _require_str(entry.get("name"), "registry key")
        registry.append({"category": "registry", "name": name, "action": "write"})
    return {
        "schema": "keel.preflight/1",
        "files": files, "protocols": protocols, "services": services,
        "registry": registry, "warnings": warnings,
        "counts": {"files": len(files), "protocols": len(protocols),
                   "services": len(services), "registry": len(registry)},
        "ok": not warnings,
    }


def preflight_gate(report: Mapping[str, Any]) -> dict:
    """A pre-flight report is a gate: unsafe manifests block the install."""
    data = _require_dict(report, "preflight report")
    blockers = list(data.get("warnings", []))
    if data.get("schema") != "keel.preflight/1":
        blockers.append("unknown pre-flight report schema")
    return {"allowed": not blockers, "blockers": blockers,
            "counts": dict(data.get("counts", {}))}


def render_report_md(report: Mapping[str, Any]) -> str:
    """Text/markdown rendering for the installer and the download page."""
    data = _require_dict(report, "preflight report")
    lines = ["# Pre-flight installer report", "",
             "This installer will make the following changes.", ""]
    for title, key, label in (
        ("Files", "files", "create"),
        ("Protocols", "protocols", "register"),
        ("Services", "services", "add"),
        ("Registry", "registry", "write"),
    ):
        lines.extend([f"## {title}", ""])
        entries = data.get(key, [])
        if not entries:
            lines.append("(none)")
        for entry in entries:
            name = entry.get("path", entry.get("name", ""))
            lines.append(f"- {entry.get('action', label)}: {name}")
        lines.append("")
    if data.get("warnings"):
        lines.append("## Warnings")
        lines.append("")
        lines.extend(f"- {warning}" for warning in data["warnings"])
        lines.append("")
    return "\n".join(lines)


# ===========================================================================
# Z15 — Prompt-injection regression corpus
# ===========================================================================

class InjectionCorpus:
    """Opt-in, local-only corpus of hashed + redacted blocked prompt samples."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.corpus_path = self.root / "injection-corpus.jsonl"

    def records(self) -> list[dict]:
        return _read_jsonl(self.corpus_path)

    def add(self, event: Mapping[str, Any], *, consent: bool = False,
            now: float | None = None) -> dict:
        """Store a blocked event only when the user opted in; never store raw text."""
        if not consent:
            return {"stored": False, "reason": "opt-in required"}
        data = _require_dict(event, "blocked event")
        raw = data.get("text", data.get("prompt", ""))
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("blocked event needs text")
        digest = _sha256_bytes(raw.encode("utf-8"))
        redacted = redact_text(raw)[0]
        record = {
            "schema": "keel.injection-sample/1",
            "id": digest[:16],
            "ts": time.time() if now is None else _require_number(now, "ts"),
            "sha256": digest,
            "redacted": redacted,
            "category": str(data.get("category", "prompt_injection")),
            "source": str(data.get("source", "local")),
            "outcome": "blocked",
            "consent": True,
        }
        _append_jsonl(self.corpus_path, record)
        return {"stored": True, "record": record}

    def replay(self, detector: Callable[[str], bool]) -> dict:
        """Replay stored redacted samples through a local red-team detector."""
        results = []
        for record in self.records():
            try:
                detected = bool(detector(record["redacted"]))
                error = ""
            except Exception as exc:
                detected = False
                error = f"{type(exc).__name__}: {exc}"
            results.append({"id": record["id"], "detected": detected, "error": error})
        caught = sum(1 for item in results if item["detected"])
        return {"schema": "keel.injection-replay/1", "total": len(results),
                "detected": caught, "missed": [r["id"] for r in results if not r["detected"]],
                "results": results, "ok": caught == len(results)}

    def summary(self) -> dict:
        records = self.records()
        categories: dict[str, int] = defaultdict(int)
        for record in records:
            categories[str(record.get("category", "unknown"))] += 1
        return {"samples": len(records), "categories": dict(sorted(categories.items())),
                "local_only": True}

    def export_anonymized(self) -> dict:
        """Export hashes + redacted text only: no raw sample ever leaves storage."""
        samples = [{"id": record["id"], "sha256": record["sha256"],
                    "redacted": record["redacted"], "category": record["category"]}
                   for record in self.records()]
        return {"schema": "keel.injection-corpus/1", "local_only": True,
                "samples": samples}


# ===========================================================================
# Z16 — Per-project cost budgets and "stop at budget" with summary
# ===========================================================================

class ProjectBudgets:
    """Project-scoped ledger: tokens for local runs, USD for user-key runs."""

    def __init__(self, state_root: str | Path):
        self.root = Path(state_root)
        self.budgets_path = self.root / "project-budgets.json"
        self.usage_path = self.root / "project-usage.jsonl"

    def _budgets(self) -> dict:
        if not self.budgets_path.is_file():
            return {}
        try:
            doc = json.loads(self.budgets_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ValueError(f"invalid project budgets: {exc}") from exc
        return _require_dict(doc, "project budgets")

    @staticmethod
    def _project(raw: Any) -> str:
        rel = _safe_relpath(raw, "project")
        return rel.as_posix()

    def set_budget(self, project: str, *, local_tokens: float | None = None,
                   remote_usd: float | None = None,
                   stop_at_budget: bool = True) -> dict:
        name = self._project(project)
        doc = self._budgets()
        entry = {
            "local_tokens": None if local_tokens is None
            else _require_number(local_tokens, "local_tokens"),
            "remote_usd": None if remote_usd is None
            else _require_number(remote_usd, "remote_usd"),
            "stop_at_budget": bool(stop_at_budget),
        }
        doc[name] = entry
        _atomic_write_text(self.budgets_path, _canonical_json(doc) + "\n")
        return {"project": name, **entry}

    def record(self, project: str, *, kind: str, tokens: int = 0,
               cost_usd: float = 0.0, provider: str = "", model: str = "",
               ts: float | None = None) -> dict:
        name = self._project(project)
        if kind not in ("local", "remote"):
            raise ValueError("kind must be 'local' or 'remote'")
        count = _require_number(tokens, "tokens")
        if count != int(count):
            raise ValueError("tokens must be an integer")
        cost = _require_number(cost_usd, "cost_usd")
        # check() + append() must be one atomic decision: without the shared
        # path lock every thread reads the same pre-spend usage and overspends.
        with _lock_for_path(self.usage_path):
            decision = self.check(name)
            if not decision["allowed"] and decision.get("stopped"):
                raise BudgetExceeded(decision["reason"])
            entry = {"schema": "keel.project-usage/1", "project": name, "kind": kind,
                     "tokens": int(count), "cost_usd": round(cost, 8),
                     "provider": provider, "model": model,
                     "ts": time.time() if ts is None else _require_number(ts, "ts")}
            _append_jsonl(self.usage_path, entry)
            return entry

    def _usage(self, project: str) -> dict:
        local_tokens = 0
        remote_usd = 0.0
        with _lock_for_path(self.usage_path):
            entries = _read_jsonl(self.usage_path)
        for entry in entries:
            if entry.get("project") != project:
                continue
            if entry.get("kind") == "local":
                local_tokens += int(entry.get("tokens", 0))
            elif entry.get("kind") == "remote":
                remote_usd += float(entry.get("cost_usd", 0))
        return {"local_tokens": local_tokens, "remote_usd": round(remote_usd, 8)}

    def check(self, project: str) -> dict:
        """Stop-at-budget decision computed from the real usage ledger."""
        name = self._project(project)
        budget = self._budgets().get(name)
        if budget is None:
            return {"allowed": True, "reason": "no budget configured",
                    "stopped": False, "project": name}
        usage = self._usage(name)
        stop = bool(budget.get("stop_at_budget", True))
        reasons = []
        for key, used, label in (("local_tokens", usage["local_tokens"], "tokens"),
                                 ("remote_usd", usage["remote_usd"], "USD")):
            limit = budget.get(key)
            if limit is not None and used >= float(limit):
                reasons.append(f"{name} {label} budget reached: {used} >= {limit}")
        return {"allowed": not reasons or not stop, "reason": "; ".join(reasons),
                "stopped": bool(reasons) and stop, "project": name,
                "usage": usage, "budget": budget}

    def summary(self, project: str) -> dict:
        """Budget/usage summary for the dashboard."""
        name = self._project(project)
        budget = self._budgets().get(name, {})
        usage = self._usage(name)
        remaining = {}
        for key, used in (("local_tokens", usage["local_tokens"]),
                          ("remote_usd", usage["remote_usd"])):
            limit = budget.get(key)
            remaining[key] = None if limit is None else round(float(limit) - used, 8)
        decision = self.check(name)
        return {"project": name, "usage": usage, "budget": budget,
                "remaining": remaining, "stop_at_budget": budget.get("stop_at_budget", True),
                "stopped": decision["stopped"], "reason": decision["reason"],
                "is_estimate": True,
                "note": "Local runs are measured in tokens; remote runs in USD."}

    def projects(self) -> list[str]:
        return sorted(self._budgets())


class BudgetExceeded(RuntimeError):
    """Raised when a project's stop-at-budget policy blocks a usage record."""
