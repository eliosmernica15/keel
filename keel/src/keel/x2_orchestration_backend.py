"""X2.* coding-workflow backend (PLAN-INDEX.json, addendum 3 section B).

Stdlib-only, local-first backend behavior for the sixteen ``not_started``
X2 feature IDs.  Each feature has one cohesive entry point (a class or a
small group of functions) that performs real work: it parses, compares,
gates, schedules, records evidence, or supervises processes.  Nothing here
talks to a network service and nothing is silently enabled -- destructive or
out-of-order actions are guarded with :class:`GuardError`.

Feature map
-----------
X2.1  attach_diagnostics / DiagnosticsLedger
X2.2  CodeActionRouter
X2.3  TDDRunner / run_tdd
X2.4  BugReproGuard
X2.5  CodeReviewEngine / parse_unified_diff
X2.6  MergeQueue / preview_conflicts
X2.7  summarize / detect_runner
X2.8  CoverageHints
X2.9  DependencyUpgradeAssistant
X2.10 MigrationAssistant / MigrationSkill
X2.11 NotebookDoc / cell_diff / NotebookOutputStore / run_cell
X2.12 CommitHygiene
X2.13 MonorepoGraph
X2.14 SymbolIndex / ExplanationBuilder
X2.15 LanguagePacks
X2.16 ProcessSupervisor

UI surfaces (buttons, panels) are deliberately out of scope; these are the
backend capabilities those surfaces call into.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

__all__ = [
    "FEATURE_IDS",
    "BackendError",
    "GuardError",
    # X2.1
    "Diagnostic", "collect_diagnostics", "attach_diagnostics", "DiagnosticsLedger",
    # X2.2
    "CodeActionRouter",
    # X2.3
    "TestOutcome", "normalize_outcome", "TDDRunner", "run_tdd",
    # X2.4
    "BugReproGuard",
    # X2.5
    "parse_unified_diff", "ReviewComment", "CodeReviewEngine",
    # X2.6
    "preview_conflicts", "MergeQueue",
    # X2.7
    "TestSummary", "detect_runner", "summarize",
    # X2.8
    "CoverageHints",
    # X2.9
    "DependencyUpgradeAssistant",
    # X2.10
    "MigrationSkill", "MIGRATION_SKILLS", "MigrationAssistant",
    # X2.11
    "NotebookDoc", "cell_diff", "NotebookOutputStore", "run_cell",
    # X2.12
    "CommitHygiene",
    # X2.13
    "MonorepoGraph",
    # X2.14
    "SymbolIndex", "ExplanationBuilder",
    # X2.15
    "LanguagePacks",
    # X2.16
    "ProcessSupervisor",
]

FEATURE_IDS = tuple(f"X2.{i}" for i in range(1, 17))


# ---------------------------------------------------------------------------
# Shared helpers and error taxonomy
# ---------------------------------------------------------------------------
class BackendError(Exception):
    """A well-formed request that the backend refused."""

    code = "backend_error"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code is not None:
            self.code = code

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


class GuardError(BackendError):
    """An action was attempted out of order or without its prerequisite."""

    code = "guard_violation"


def _now() -> float:
    return time.time()


def _iso(ts: float | None = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_now() if ts is None else ts))


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return value if isinstance(value, str) else str(value)


def _clamp(value: Any, lo: int, hi: int, default: int = 0) -> int:
    return max(lo, min(hi, _as_int(value, default)))


def _dedupe(values: Iterable[Any]) -> list[Any]:
    seen: set[Any] = set()
    out: list[Any] = []
    for value in values:
        marker = repr(value)
        if marker not in seen:
            seen.add(marker)
            out.append(value)
    return out


def _read_json(path: str | Path | None, default: Any) -> Any:
    if path is None:
        return default
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        return doc if doc is not None else default
    except (OSError, ValueError, TypeError):
        return default


def _write_json(path: str | Path | None, payload: Any) -> None:
    if path is None:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(target.name + ".tmp")
    staging.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(staging, target)


def _within_root(root: str | Path, candidate: str | Path) -> bool:
    """True only when ``candidate`` resolves inside ``root`` (no escapes)."""
    try:
        base = Path(root).resolve()
        target = Path(candidate)
        if not target.is_absolute():
            target = base / target
        target = target.resolve()
        return target == base or base in target.parents
    except (OSError, ValueError, RuntimeError):
        return False


def _resolve_in_root(root: str | Path, candidate: str | Path) -> Path:
    base = Path(root).resolve()
    target = Path(candidate)
    if not target.is_absolute():
        target = base / target
    target = target.resolve()
    if not (target == base or base in target.parents):
        raise BackendError(f"path escapes workspace root: {candidate}", code="path_escape")
    return target


def _clean_lines(text: Any) -> list[str]:
    return [_as_text(line).rstrip("\r") for line in _as_text(text).splitlines()]


# ===========================================================================
# X2.1 -- Diagnostics feedback after every edit
# ===========================================================================
_ACTIONABLE = ("error", "warning")


@dataclass(frozen=True)
class Diagnostic:
    file: str
    line: int
    column: int
    code: str
    message: str
    severity: str = "warning"

    def key(self) -> tuple[str, str, int, int]:
        return (self.file, self.code, self.line, self.column)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file, "line": self.line, "column": self.column,
            "code": self.code, "message": self.message, "severity": self.severity,
        }


def normalize_diagnostic(raw: Any, default_file: str = "") -> Diagnostic | None:
    """Coerce a provider payload into a Diagnostic; drop malformed entries."""
    if not isinstance(raw, dict):
        return None
    message = _as_text(raw.get("message") or raw.get("text")).strip()
    if not message:
        return None
    severity = _as_text(raw.get("severity") or "warning").lower()
    if severity not in ("error", "warning", "info", "hint"):
        severity = "warning"
    line = _clamp(raw.get("line", raw.get("lineNumber", 0)), 0, 1_000_000)
    column = _clamp(raw.get("column", raw.get("character", 0)), 0, 1_000_000)
    file = _as_text(raw.get("file") or raw.get("path") or default_file)
    code = _as_text(raw.get("code") or raw.get("ruleId") or "diagnostic")
    return Diagnostic(file=file, line=line, column=column, code=code,
                      message=message[:2000], severity=severity)


def collect_diagnostics(
    touched_paths: Iterable[str | Path],
    provider: Callable[[str], Iterable[dict[str, Any]]] | None,
) -> dict[str, Any]:
    """Query an LSP-like provider for each touched file.

    Provider failures are reported, never fatal: a broken LSP must not hide
    the result of the edit itself.  ``degraded=True`` tells the agent that the
    diagnostic feed is incomplete.
    """
    paths = _dedupe([_as_text(p) for p in touched_paths])[:200]
    diagnostics: list[Diagnostic] = []
    errors: list[str] = []
    if provider is None:
        return {"diagnostics": [], "degraded": True,
                "errors": ["no diagnostics provider configured"], "files_checked": []}
    for path in paths:
        try:
            raw_items = provider(path)
            items = list(raw_items) if raw_items is not None else []
        except Exception as exc:  # noqa: BLE001 - third-party provider boundary
            errors.append(f"{path}: {type(exc).__name__}: {exc}")
            continue
        for raw in items[:1000]:
            diag = normalize_diagnostic(raw, path)
            if diag is not None and diag.severity in _ACTIONABLE:
                diagnostics.append(diag)
    unique = _dedupe(diagnostics)
    return {
        "diagnostics": [d.to_dict() for d in unique],
        "degraded": bool(errors),
        "errors": errors[:50],
        "files_checked": paths,
    }


def attach_diagnostics(
    tool_result: dict[str, Any],
    touched_paths: Iterable[str | Path],
    provider: Callable[[str], Iterable[dict[str, Any]]] | None,
) -> dict[str, Any]:
    """X2.1: append actionable diagnostics to a tool result (non-mutating)."""
    if not isinstance(tool_result, dict):
        raise BackendError("tool_result must be a dict")
    report = collect_diagnostics(touched_paths, provider)
    out = dict(tool_result)
    out["diagnostics"] = report
    out["diagnostics_appended"] = True
    out["needs_resolution"] = bool(report["diagnostics"])
    return out


class DiagnosticsLedger:
    """Tracks outstanding diagnostics; an edit is gated until they are
    resolved or explicitly justified with a non-empty reason."""

    def __init__(self, state_path: str | Path | None = None):
        self.path = Path(state_path) if state_path is not None else None
        stored = _read_json(self.path, {})
        self._open: dict[tuple[str, str, int, int], dict[str, Any]] = {}
        for item in (stored.get("open", []) if isinstance(stored, dict) else []):
            diag = normalize_diagnostic(item)
            if diag is not None:
                self._open[diag.key()] = {
                    "diagnostic": diag.to_dict(),
                    "justification": _as_text(item.get("justification")).strip() or None,
                    "observed_at": _as_text(item.get("observed_at")) or _iso(),
                }

    def _save(self) -> None:
        _write_json(self.path, {"open": list(self._open.values())})

    def observe(self, diagnostics: Iterable[dict[str, Any]]) -> list[str]:
        """Add new actionable diagnostics; return their keys."""
        added: list[str] = []
        for raw in diagnostics:
            diag = normalize_diagnostic(raw)
            if diag is None or diag.severity not in _ACTIONABLE:
                continue
            if diag.key() not in self._open:
                self._open[diag.key()] = {
                    "diagnostic": diag.to_dict(), "justification": None,
                    "observed_at": _iso(),
                }
                added.append(str(diag.key()))
        self._save()
        return added

    def resolve(self, file: str, code: str, line: int, column: int = 0) -> bool:
        key = (_as_text(file), _as_text(code), _as_int(line), _as_int(column))
        existed = self._open.pop(key, None) is not None
        if existed:
            self._save()
        return existed

    def justify(self, file: str, code: str, line: int, reason: str,
                column: int = 0) -> bool:
        reason = _as_text(reason).strip()
        if not reason:
            raise BackendError("justification must be a non-empty reason")
        key = (_as_text(file), _as_text(code), _as_int(line), _as_int(column))
        entry = self._open.get(key)
        if entry is None:
            return False
        entry["justification"] = reason[:3000]
        entry["justified_at"] = _iso()
        self._save()
        return True

    def outstanding(self) -> list[dict[str, Any]]:
        return [entry["diagnostic"] for entry in self._open.values()
                if not entry.get("justification")]

    def gate(self, reason: str = "") -> dict[str, Any]:
        pending = self.outstanding()
        return {"allowed": not pending, "outstanding": pending,
                "justified": len(self._open) - len(pending), "reason": reason}

    def require_clear(self, reason: str = "") -> None:
        report = self.gate(reason)
        if not report["allowed"]:
            raise GuardError(
                f"{len(report['outstanding'])} diagnostic(s) unresolved or unjustified"
                + (f": {reason}" if reason else ""))


# ===========================================================================
# X2.2 -- Rename / extract / move through LSP code actions
# ===========================================================================
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ACTIONS = ("rename", "extract", "move")
_OPS = ("replace", "insert", "delete", "create")


class CodeActionRouter:
    """Prefers semantic LSP workspace edits and falls back to explicit
    text edits -- never silently: a fallback is always flagged."""

    def __init__(self, root: str | Path,
                 provider: Any | None = None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.provider = provider

    def _supports(self, action: str) -> bool:
        if self.provider is None:
            return False
        try:
            if isinstance(self.provider, dict):
                return callable(self.provider.get(action))
            supports = getattr(self.provider, "supports", None)
            return bool(supports(action)) if callable(supports) else callable(self.provider)
        except Exception:  # noqa: BLE001
            return False

    def _compute(self, action: str, payload: dict[str, Any]) -> Any:
        if isinstance(self.provider, dict):
            return self.provider[action](payload)
        compute = getattr(self.provider, "compute", None)
        if callable(compute):
            return compute(action, payload)
        return self.provider(action, payload)

    def _validate_changes(self, changes: Any) -> dict[str, list[dict[str, Any]]] | None:
        if not isinstance(changes, dict) or not changes:
            return None
        clean: dict[str, list[dict[str, Any]]] = {}
        for file, edits in changes.items():
            if not isinstance(edits, list) or not edits:
                return None
            resolved = _resolve_in_root(self.root, _as_text(file))
            rel = resolved.relative_to(self.root).as_posix()
            bucket: list[dict[str, Any]] = []
            for edit in edits[:1000]:
                if not isinstance(edit, dict):
                    return None
                op = _as_text(edit.get("op") or "replace")
                if op not in _OPS:
                    return None
                rng = edit.get("range")
                if not isinstance(rng, dict):
                    return None
                start = _clamp(rng.get("start_line", 1), 1, 10_000_000, 1)
                end = _clamp(rng.get("end_line", start), start, 10_000_000, start)
                bucket.append({
                    "op": op,
                    "range": {"start_line": start, "end_line": end,
                              "start_column": _clamp(rng.get("start_column", 0), 0, 10_000),
                              "end_column": _clamp(rng.get("end_column", 0), 0, 10_000)},
                    "new_text": _as_text(edit.get("new_text"))[:100_000],
                })
            clean[rel] = bucket
        return clean

    def plan(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        """X2.2: produce a validated workspace-edit plan for one action."""
        if action not in _ACTIONS:
            raise BackendError(f"unsupported code action: {action}")
        if not isinstance(payload, dict):
            raise BackendError("payload must be a dict")
        file = _as_text(payload.get("file") or payload.get("path"))
        if not file:
            raise BackendError(f"{action} requires a file")
        resolved = _resolve_in_root(self.root, file)
        rel = resolved.relative_to(self.root).as_posix()

        if action == "rename":
            new_name = _as_text(payload.get("new_name")).strip()
            if not _IDENTIFIER.match(new_name):
                raise BackendError("rename target is not a valid identifier")
            if not _as_text(payload.get("old_name")).strip():
                raise BackendError("rename source identifier is required")
        elif action == "extract":
            new_name = _as_text(payload.get("new_name")).strip()
            if not _IDENTIFIER.match(new_name):
                raise BackendError("extracted symbol name is not a valid identifier")
            start = _as_int(payload.get("start_line"), 0)
            end = _as_int(payload.get("end_line"), 0)
            if start < 1 or end < start:
                raise BackendError("extract range must satisfy 1 <= start <= end")
        else:  # move
            src = _as_text(payload.get("src") or file)
            dst = _as_text(payload.get("dst") or payload.get("target"))
            if not dst:
                raise BackendError("move requires a destination")
            src_path = _resolve_in_root(self.root, src)
            dst_path = _resolve_in_root(self.root, dst)
            if src_path == dst_path:
                raise BackendError("move source and destination are identical")

        reason = ""
        changes = None
        source = "text_edit"
        if self._supports(action):
            try:
                raw = self._compute(action, dict(payload))
                candidate = self._validate_changes(
                    raw.get("changes") if isinstance(raw, dict) else raw)
                if candidate is not None:
                    changes, source = candidate, "lsp"
                else:
                    reason = "malformed_lsp_edit"
            except Exception as exc:  # noqa: BLE001
                reason = f"lsp_provider_error: {type(exc).__name__}"
        else:
            reason = "lsp_action_unavailable"

        if changes is None:
            changes = {rel: [self._fallback_edit(action, payload)]}
        return {
            "action": action, "source": source, "changes": changes,
            "fallback_used": source == "text_edit", "reason": reason,
            "requires_semantic_verification": source == "text_edit",
        }

    @staticmethod
    def _fallback_edit(action: str, payload: dict[str, Any]) -> dict[str, Any]:
        line = _clamp(payload.get("line", payload.get("start_line", 1)), 1, 10_000_000, 1)
        if action == "rename":
            return {"op": "replace", "range": {"start_line": line, "end_line": line},
                    "new_text": _as_text(payload.get("new_name"))}
        if action == "extract":
            return {"op": "insert", "range": {"start_line": line, "end_line": line},
                    "new_text": f"def {_as_text(payload.get('new_name'))}(): ...\n"}
        return {"op": "create", "range": {"start_line": 1, "end_line": 1},
                "new_text": _as_text(payload.get("dst") or payload.get("target"))}

    def apply(self, plan: dict[str, Any],
              apply_text_edit: Callable[[str, dict[str, Any]], Any]) -> dict[str, Any]:
        """Apply a validated plan through the provided text-edit executor."""
        if not isinstance(plan, dict) or not isinstance(plan.get("changes"), dict):
            raise BackendError("invalid plan")
        applied = 0
        errors: list[str] = []
        for file, edits in plan["changes"].items():
            # A plan may be hand-crafted, persisted or otherwise stale: never
            # trust the paths it carries. Re-resolve every target immediately
            # before writing so symlink/normalisation changes cannot escape.
            try:
                target = _resolve_in_root(self.root, _as_text(file))
                rel = target.relative_to(self.root).as_posix()
            except (BackendError, OSError, ValueError, RuntimeError) as exc:
                raise BackendError(
                    f"refusing to apply edit outside workspace root: {file!r}",
                    code="path_escape",
                ) from exc
            if not isinstance(edits, list):
                raise BackendError("invalid plan: changes must map to edit lists")
            for edit in edits:
                try:
                    apply_text_edit(rel, edit)
                    applied += 1
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{rel}: {type(exc).__name__}: {exc}")
        warnings = list(plan.get("warnings", []))
        if plan.get("fallback_used"):
            warnings.append("semantic LSP action unavailable; verify text-edit result")
        return {"applied": applied, "errors": errors, "warnings": warnings,
                "ok": applied > 0 and not errors}


# ===========================================================================
# X2.3 -- TDD mode: RED -> implement -> GREEN with evidence
# ===========================================================================
@dataclass
class TestOutcome:
    ok: bool
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    test_ids: list[str] = field(default_factory=list)
    raw: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "passed": self.passed, "failed": self.failed,
                "errors": self.errors, "skipped": self.skipped,
                "test_ids": list(self.test_ids)[:100], "raw": self.raw[:4000]}


def normalize_outcome(value: Any) -> TestOutcome:
    if isinstance(value, TestOutcome):
        return value
    if isinstance(value, bool):
        return TestOutcome(ok=value, passed=1 if value else 0,
                           failed=0 if value else 1, raw="boolean outcome")
    if isinstance(value, dict):
        failed = _clamp(value.get("failed"), 0, 1_000_000)
        errors = _clamp(value.get("errors"), 0, 1_000_000)
        ok = bool(value.get("ok")) if "ok" in value else (failed == 0 and errors == 0)
        ids = value.get("test_ids") or []
        return TestOutcome(
            ok=ok, passed=_clamp(value.get("passed"), 0, 1_000_000),
            failed=failed, errors=errors, skipped=_clamp(value.get("skipped"), 0, 1_000_000),
            test_ids=[_as_text(i) for i in ids[:100]] if isinstance(ids, (list, tuple)) else [],
            raw=_as_text(value.get("raw"))[:4000])
    if isinstance(value, (tuple, list)) and len(value) == 2:
        passed, failed = _as_int(value[0]), _as_int(value[1])
        return TestOutcome(ok=(failed == 0), passed=passed, failed=failed)
    raise BackendError("unrecognized test outcome")


class TDDRunner:
    """Enforces RED -> implement -> GREEN and records both runs as evidence.

    A passing first run is *not* RED; a failing second run is *not* GREEN.
    Every rejected attempt is kept in the evidence trail so the agent cannot
    quietly relabel a green run as the red one.
    """

    RED_REQUIRED = "red_required"
    RED_CONFIRMED = "red_confirmed"
    IMPLEMENTED = "implemented"
    IMPLEMENT_FAILED = "implementation_failed"
    COMPLETE = "complete"

    def __init__(self, state_path: str | Path | None = None):
        self.path = Path(state_path) if state_path is not None else None
        self._state = self._fresh()
        stored = _read_json(self.path, {})
        if isinstance(stored, dict) and stored.get("evidence"):
            self._state = dict(self._fresh(), **stored)

    @staticmethod
    def _fresh() -> dict[str, Any]:
        return {"test_id": "", "phase": "idle", "evidence": {"attempts": []}, "verified": False}

    def _save(self) -> None:
        _write_json(self.path, self._state)

    def start(self, test_id: str) -> dict[str, Any]:
        self._state = self._fresh()
        self._state["test_id"] = _as_text(test_id)
        self._state["phase"] = self.RED_REQUIRED
        self._save()
        return self.status()

    def _attempt(self, phase: str, outcome: Any, accepted: bool, note: str) -> None:
        self._state["evidence"].setdefault("attempts", []).append({
            "phase": phase, "accepted": accepted, "note": note,
            "outcome": normalize_outcome(outcome).to_dict(), "at": _iso(),
        })

    def record_red(self, outcome: Any) -> dict[str, Any]:
        if self._state["phase"] != self.RED_REQUIRED:
            raise GuardError(f"RED phase not pending (phase={self._state['phase']})")
        normalized = normalize_outcome(outcome)
        if normalized.ok:
            self._attempt("red", outcome, False, "RED run passed; a failing test is required")
            self._save()
            raise BackendError("RED run must fail before implementation")
        self._attempt("red", outcome, True, "failing test confirmed")
        self._state["evidence"]["red"] = {"outcome": normalized.to_dict(), "at": _iso()}
        self._state["phase"] = self.RED_CONFIRMED
        self._save()
        return self.status()

    def implement(self, apply_change: Callable[[], Any]) -> Any:
        if self._state["phase"] not in (self.RED_CONFIRMED, self.IMPLEMENT_FAILED):
            raise GuardError("implementation requires a confirmed RED run")
        started = _now()
        try:
            result = apply_change()
        except Exception as exc:  # noqa: BLE001
            self._state["phase"] = self.IMPLEMENT_FAILED
            self._state["evidence"].setdefault("attempts", []).append({
                "phase": "implement", "accepted": False,
                "note": f"{type(exc).__name__}: {exc}", "at": _iso(),
            })
            self._save()
            raise
        self._state["evidence"]["implementation"] = {
            "ok": True, "duration_s": round(_now() - started, 6), "at": _iso(),
        }
        self._state["phase"] = self.IMPLEMENTED
        self._save()
        return result

    def record_green(self, outcome: Any) -> dict[str, Any]:
        if self._state["phase"] != self.IMPLEMENTED:
            raise GuardError(f"GREEN phase not pending (phase={self._state['phase']})")
        normalized = normalize_outcome(outcome)
        if not normalized.ok:
            self._attempt("green", outcome, False, "GREEN run failed")
            self._save()
            raise BackendError("GREEN run must pass before TDD can complete")
        self._attempt("green", outcome, True, "all tests passing")
        self._state["evidence"]["green"] = {"outcome": normalized.to_dict(), "at": _iso()}
        self._state["phase"] = self.COMPLETE
        self._state["verified"] = True
        self._save()
        return self.status()

    def evidence(self) -> dict[str, Any]:
        """Return a defensive copy of the full evidence record."""
        return json.loads(json.dumps(self._state))

    def status(self) -> dict[str, Any]:
        return {"test_id": self._state["test_id"], "phase": self._state["phase"],
                "verified": self._state["verified"],
                "has_red": "red" in self._state["evidence"],
                "has_green": "green" in self._state["evidence"]}


def run_tdd(test_id: str, red: Any, implement: Callable[[], Any], green: Any,
            state_path: str | Path | None = None) -> dict[str, Any]:
    """X2.3 convenience orchestration for the full three-phase loop."""
    runner = TDDRunner(state_path)
    runner.start(test_id)
    runner.record_red(red)
    runner.implement(implement)
    runner.record_green(green)
    return runner.evidence()


# ===========================================================================
# X2.4 -- Bug-repro mode: a failing repro before any code change
# ===========================================================================
class BugReproGuard:
    def __init__(self, state_path: str | Path | None = None):
        self.path = Path(state_path) if state_path is not None else None
        self._state: dict[str, Any] = _read_json(self.path, {}) or {}
        self._state.setdefault("repro_id", "")
        self._state.setdefault("detail", "")
        self._state.setdefault("confirmed", False)
        self._state.setdefault("edits", [])
        self._state.setdefault("fix_verified", False)
        self._state.setdefault("history", [])

    def _save(self) -> None:
        _write_json(self.path, self._state)

    def require_repro(self, repro_id: str, detail: str) -> dict[str, Any]:
        repro_id = _as_text(repro_id).strip()
        detail = _as_text(detail).strip()
        if not repro_id or not detail:
            raise BackendError("repro id and description are required")
        self._state.update({"repro_id": repro_id, "detail": detail[:3000],
                            "confirmed": False, "edits": [], "fix_verified": False})
        self._save()
        return self.status()

    def confirm_repro(self, outcome: Any) -> dict[str, Any]:
        normalized = normalize_outcome(outcome)
        if not self._state["repro_id"]:
            raise GuardError("register a repro with require_repro() first")
        if normalized.ok:
            self._state["history"].append({"repro": self._state["repro_id"],
                                           "accepted": False, "reason": "repro passed",
                                           "at": _iso()})
            self._save()
            raise BackendError("reproduction passed; a failing run is required")
        if not normalized.failed and not normalized.errors:
            raise BackendError("failing reproduction has no failure detail")
        self._state["confirmed"] = True
        self._state["history"].append({
            "repro": self._state["repro_id"], "accepted": True, "at": _iso(),
            "outcome": normalized.to_dict(),
        })
        self._save()
        return self.status()

    def attempt_edit(self, what: str) -> dict[str, Any]:
        if not self._state["confirmed"]:
            raise GuardError("code change blocked: no confirmed failing reproduction")
        entry = {"what": _as_text(what)[:500], "at": _iso()}
        self._state["edits"].append(entry)
        self._state["fix_verified"] = False
        self._save()
        return entry

    def verify_fix(self, outcome: Any) -> dict[str, Any]:
        if not self._state["edits"]:
            raise GuardError("verify_fix requires an edit after the reproduction")
        normalized = normalize_outcome(outcome)
        if not normalized.ok:
            self._state["history"].append({"repro": self._state["repro_id"],
                                           "accepted": False, "reason": "fix still failing",
                                           "at": _iso()})
            self._save()
            raise BackendError("fix run is still failing")
        self._state["fix_verified"] = True
        self._state["history"].append({"repro": self._state["repro_id"],
                                       "accepted": True, "reason": "fix verified",
                                       "at": _iso(), "outcome": normalized.to_dict()})
        self._save()
        return self.status()

    def reopen(self) -> dict[str, Any]:
        """Start the next bug: the previous confirmation may not be reused."""
        self._state.update({"repro_id": "", "detail": "", "confirmed": False,
                            "edits": [], "fix_verified": False})
        self._save()
        return self.status()

    def status(self) -> dict[str, Any]:
        return {"repro_id": self._state["repro_id"], "detail": self._state["detail"],
                "confirmed": self._state["confirmed"],
                "edit_count": len(self._state["edits"]),
                "fix_verified": self._state["fix_verified"]}


# ===========================================================================
# X2.5 -- Code review mode with inline comments accepted as tasks
# ===========================================================================
_HUNK_RE = re.compile(r"^@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@")
_PLUS_FILE_RE = re.compile(r"^\+\+\+\s+(.+?)(?:\t.*)?$")


def parse_unified_diff(text: Any) -> dict[str, list[int]]:
    """Map each file to the *new-file* line numbers of its added lines.

    Non-text input is refused instead of silently producing an empty (successful)
    result; an empty *text* diff is a legitimate empty mapping.
    """
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    if not isinstance(text, str):
        raise BackendError("unified diff must be text")
    files: dict[str, list[int]] = {}
    current: str | None = None
    new_line = 0
    for raw in _clean_lines(text):
        if raw.startswith("+++ "):
            match = _PLUS_FILE_RE.match(raw)
            name = match.group(1).strip() if match else ""
            if name.startswith("b/"):
                name = name[2:]
            current = None if name in ("", "/dev/null") else name
            continue
        if raw.startswith("--- ") or raw.startswith("diff ") or raw.startswith("index "):
            continue
        match = _HUNK_RE.match(raw)
        if match:
            new_line = max(0, _as_int(match.group(1), 1) - 1)
            continue
        if current is None:
            continue
        if raw.startswith("+"):
            new_line += 1
            files.setdefault(current, []).append(new_line)
        elif raw.startswith("-"):
            continue
        elif raw.startswith("\\"):
            continue
        else:  # context line (including an empty context line)
            new_line += 1
    return files


def added_lines(text: Any) -> list[tuple[str, int, str]]:
    """Same walk as :func:`parse_unified_diff`, keeping the added text."""
    out: list[tuple[str, int, str]] = []
    current: str | None = None
    new_line = 0
    for raw in _clean_lines(text):
        if raw.startswith("+++ "):
            match = _PLUS_FILE_RE.match(raw)
            name = match.group(1).strip() if match else ""
            if name.startswith("b/"):
                name = name[2:]
            current = None if name in ("", "/dev/null") else name
            continue
        if raw.startswith("--- ") or raw.startswith("diff ") or raw.startswith("index "):
            continue
        match = _HUNK_RE.match(raw)
        if match:
            new_line = max(0, _as_int(match.group(1), 1) - 1)
            continue
        if current is None:
            continue
        if raw.startswith("+"):
            new_line += 1
            out.append((current, new_line, raw[1:]))
        elif raw.startswith("-") or raw.startswith("\\"):
            continue
        else:
            new_line += 1
    return out


@dataclass(frozen=True)
class ReviewComment:
    file: str
    line: int
    category: str
    severity: str
    message: str

    def key(self) -> tuple[str, int, str, str]:
        return (self.file, self.line, self.category, self.message)

    def to_dict(self, comment_id: str = "") -> dict[str, Any]:
        return {"id": comment_id, "file": self.file, "line": self.line,
                "category": self.category, "severity": self.severity,
                "message": self.message}


class CodeReviewEngine:
    """Runs pluggable reviewers over added lines and turns accepted comments
    into tasks.  Reviewer exceptions are isolated per reviewer."""

    CATEGORIES = ("style", "bugs", "security", "test-gaps")
    SEVERITIES = ("blocker", "major", "minor", "nit")

    def __init__(self, reviewers: Iterable[Callable[[str, list[int], str], Iterable[dict]]] | None = None,
                 state_path: str | Path | None = None):
        self.reviewers = list(reviewers) if reviewers else [self._builtin_reviewer]
        self.path = Path(state_path) if state_path is not None else None
        stored = _read_json(self.path, {})
        self._comments: dict[str, dict[str, Any]] = {}
        self._tasks: dict[str, dict[str, Any]] = {}
        if isinstance(stored, dict):
            self._comments = {str(c.get("id")): c for c in stored.get("comments", [])
                              if isinstance(c, dict) and c.get("id")}
            self._tasks = {str(t.get("task_id")): t for t in stored.get("tasks", [])
                           if isinstance(t, dict) and t.get("task_id")}

    def _save(self) -> None:
        _write_json(self.path, {"comments": list(self._comments.values()),
                                "tasks": list(self._tasks.values())})

    @staticmethod
    def _builtin_reviewer(file: str, lines: list[int], diff_text: str) -> list[dict]:
        """Review every added line; emit ``file``/``line`` for later validation."""
        findings: list[dict] = []
        for file_name, line_no, content in added_lines(diff_text):
            lowered = content.lower()
            if "todo" in lowered or "fixme" in lowered:
                findings.append({"file": file_name, "line": line_no, "category": "style",
                                 "severity": "minor",
                                 "message": "leftover TODO/FIXME in added line"})
            if any(token in lowered for token in
                   ("eval(", "exec(", "shell=true", "password=", "secret=")):
                findings.append({"file": file_name, "line": line_no, "category": "security",
                                 "severity": "major",
                                 "message": "potentially unsafe or secret-bearing line"})
        return findings

    def review(self, diff_text: Any, categories: Iterable[str] | None = None) -> list[dict[str, Any]]:
        """X2.5: review a unified diff and return deduplicated inline comments."""
        allowed = set(categories) if categories else set(self.CATEGORIES)
        added = parse_unified_diff(diff_text)
        candidates: list[ReviewComment] = []
        errors: list[str] = []
        for reviewer in self.reviewers[:50]:
            try:
                produced = reviewer("", [], _as_text(diff_text))
                for item in (produced or []):
                    if not isinstance(item, dict):
                        continue
                    file = _as_text(item.get("file"))
                    line = _as_int(item.get("line"), 0)
                    # A comment must land on a line actually added in this diff.
                    if not file or line not in added.get(file, []):
                        continue
                    category = _as_text(item.get("category") or "style")
                    severity = _as_text(item.get("severity") or "minor")
                    message = _as_text(item.get("message")).strip()
                    if category not in allowed or category not in self.CATEGORIES:
                        continue
                    if severity not in self.SEVERITIES or not message:
                        continue
                    candidates.append(ReviewComment(file, line, category, severity, message[:2000]))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{type(exc).__name__}: {exc}")
        seen: set[tuple[str, int, str, str]] = set()
        result: list[dict[str, Any]] = []
        for comment in candidates[:500]:
            if comment.key() in seen:
                continue
            seen.add(comment.key())
            comment_id = f"{comment.file}:{comment.line}:{comment.category}:{len(self._comments) + len(result)}"
            payload = comment.to_dict(comment_id)
            self._comments[comment_id] = payload
            result.append(payload)
        self._save()
        return result

    def accept(self, comment_id: str) -> dict[str, Any]:
        comment = self._comments.get(_as_text(comment_id))
        if comment is None:
            raise BackendError(f"unknown comment: {comment_id}")
        task_id = f"task:{comment_id}"
        if task_id not in self._tasks:
            self._tasks[task_id] = {"task_id": task_id, "comment": dict(comment),
                                    "status": "open", "created_at": _iso()}
            self._save()
        return dict(self._tasks[task_id])

    def dismiss(self, comment_id: str) -> bool:
        existed = self._comments.pop(_as_text(comment_id), None) is not None
        task_id = f"task:{comment_id}"
        self._tasks.pop(task_id, None)
        if existed:
            self._save()
        return existed

    def tasks(self) -> list[dict[str, Any]]:
        return [dict(t) for t in self._tasks.values()]


# ===========================================================================
# X2.6 -- Merge queue with conflict preview and land-when-green gate
# ===========================================================================
def _change_map(value: Any) -> dict[str, set[int]]:
    """Accept either a unified diff or a {file: [line, ...]} mapping."""
    if isinstance(value, str):
        parsed = parse_unified_diff(value)
        return {file: set(lines) for file, lines in parsed.items()}
    if isinstance(value, dict):
        out: dict[str, set[int]] = {}
        for file, lines in value.items():
            if isinstance(lines, (list, tuple, set)):
                out[_as_text(file)] = {_as_int(n) for n in lines if _as_int(n) > 0}
        return out
    return {}


def preview_conflicts(base_changes: Any, head_changes: Any) -> dict[str, Any]:
    """X2.6: overlapping changed lines are conflict candidates."""
    base, head = _change_map(base_changes), _change_map(head_changes)
    conflicts: list[dict[str, Any]] = []
    for file in sorted(set(base) & set(head)):
        overlap = sorted(base[file] & head[file])
        if overlap:
            conflicts.append({"file": file, "lines": overlap[:200]})
    return {"conflicts": conflicts, "clean": not conflicts,
            "files_compared": len(set(base) | set(head))}


class MergeQueue:
    def __init__(self, state_path: str | Path | None = None):
        self.path = Path(state_path) if state_path is not None else None
        self._entries: list[dict[str, Any]] = []
        stored = _read_json(self.path, {})
        if isinstance(stored, dict) and isinstance(stored.get("entries"), list):
            self._entries = [e for e in stored["entries"] if isinstance(e, dict)]

    def _save(self) -> None:
        _write_json(self.path, {"entries": self._entries})

    def _find(self, task_id: str) -> dict[str, Any]:
        for entry in self._entries:
            if entry["task_id"] == task_id:
                return entry
        raise BackendError(f"unknown queued task: {task_id}")

    def enqueue(self, task_id: str, branch: str, worktree: str = "") -> dict[str, Any]:
        task_id = _as_text(task_id).strip()
        if not task_id or not _as_text(branch).strip():
            raise BackendError("task_id and branch are required")
        if any(e["task_id"] == task_id for e in self._entries):
            raise BackendError(f"task already queued: {task_id}")
        entry = {"task_id": task_id, "branch": _as_text(branch),
                 "worktree": _as_text(worktree), "status": "queued",
                 "ci_green": False, "conflicts": None, "queued_at": _iso()}
        self._entries.append(entry)
        self._save()
        return dict(entry)

    def preview(self, task_id: str, base_changes: Any, head_changes: Any) -> dict[str, Any]:
        entry = self._find(task_id)
        report = preview_conflicts(base_changes, head_changes)
        entry["conflicts"] = report["conflicts"]
        entry["status"] = "previewed" if report["clean"] else "conflicted"
        # A fresh preview describes a new candidate state; a green signal
        # recorded before it cannot be reused ("land when green" must be live).
        entry["ci_green"] = False
        self._save()
        return {"task_id": task_id, **report}

    def mark_green(self, task_id: str, ok: bool) -> dict[str, Any]:
        entry = self._find(task_id)
        if entry["status"] == "landed":
            raise GuardError(f"task {task_id} already landed")
        if entry["conflicts"]:
            # Conflicts make a "green" claim meaningless; keep it recorded as
            # false so the landing gate cannot be tricked.
            entry["ci_green"] = False
            self._save()
            return {"task_id": task_id, "ci_green": False,
                    "reason": "conflicts present; green ignored"}
        entry["ci_green"] = bool(ok)
        self._save()
        return {"task_id": task_id, "ci_green": entry["ci_green"]}

    def land(self, task_id: str) -> dict[str, Any]:
        entry = self._find(task_id)
        if entry["status"] == "landed":
            raise GuardError(f"task {task_id} already landed")
        if entry["conflicts"] is None:
            raise GuardError("conflict preview is required before landing")
        if entry["conflicts"]:
            raise GuardError("unresolved conflicts block landing")
        if not entry["ci_green"]:
            raise GuardError("CI is not green; land-when-green refused")
        entry["status"] = "landed"
        entry["landed_at"] = _iso()
        self._save()
        return dict(entry)

    def list(self) -> list[dict[str, Any]]:
        return [dict(e) for e in self._entries]


# ===========================================================================
# X2.7 -- Test-runner adapters with failure summaries
# ===========================================================================
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


@dataclass
class TestSummary:
    runner: str
    ok: bool
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    failures: list[dict[str, str]] = field(default_factory=list)
    guessed: bool = False
    truncated: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"runner": self.runner, "ok": self.ok, "passed": self.passed,
                "failed": self.failed, "errors": self.errors, "skipped": self.skipped,
                "failures": list(self.failures)[:50], "guessed": self.guessed,
                "truncated": self.truncated, "note": self.note}

    def failure_digest(self, limit: int = 20) -> str:
        """Concise replacement for a raw log."""
        head = (f"{self.runner}: {self.passed} passed, {self.failed} failed, "
                f"{self.errors} errors, {self.skipped} skipped")
        lines = [head]
        for failure in self.failures[:limit]:
            lines.append(f"  - {failure.get('name', '?')}: "
                         f"{failure.get('message', '')[:200]}")
        return "\n".join(lines)


def _failures_from_lines(pattern: re.Pattern[str], text: str,
                         message_after: re.Pattern[str] | None = None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = pattern.search(line)
        if not match:
            continue
        name = match.group(1).strip() if match.groups() else line.strip()
        message = ""
        if message_after is not None:
            for following in lines[index + 1: index + 4]:
                sub = message_after.search(following)
                if sub:
                    message = sub.group(1).strip()
                    break
        out.append({"name": name[:300], "message": message[:1000]})
        if len(out) >= 200:
            break
    return out


_PYTEST_COUNT = re.compile(r"(\d+)\s+(passed|failed|errors?|skipped|xpassed|xfailed)")
_FAILED_LINE = re.compile(r"^FAILED\s+(\S+)\s+-\s+(.+)$", re.MULTILINE)
_UNIT_RAN = re.compile(r"Ran\s+(\d+)\s+tests?")
_UNIT_FAIL = re.compile(r"^FAIL(?:URE|ERROR)?:\s*(.+)$", re.MULTILINE)
_JEST_TOTAL = re.compile(r"Tests:\s*(?:(\d+)\s+failed,\s*)?(?:(\d+)\s+passed,?\s*)?(\d+)\s+total")
_JEST_FAIL = re.compile(r"^\s*[\u25cf\u2022]\s+(.+)$", re.MULTILINE)
_GO_FAIL = re.compile(r"^---\s+FAIL:\s*(\S+)", re.MULTILINE)
_CARGO_RESULT = re.compile(r"test result:\s*(\w+)\.\s*(\d+)\s+passed;\s*(\d+)\s+failed")
_CARGO_FAIL = re.compile(r"^test\s+(\S+)\s+\.\.\.\s+FAILED", re.MULTILINE)


def _parse_pytest(text: str) -> TestSummary:
    counts: dict[str, int] = {}
    for value, label in _PYTEST_COUNT.findall(text):
        counts[label.rstrip("e") if label.startswith("error") else label] = _as_int(value)
    failed = counts.get("failed", 0)
    errors = counts.get("error", 0)
    failures = [{"name": m.group(1), "message": m.group(2)} for m in _FAILED_LINE.finditer(text)]
    if not counts:  # truncated or summary-less log: derive from FAILED lines
        failed = len(failures)
    return TestSummary("pytest", failed == 0 and errors == 0,
                       counts.get("passed", 0), failed, errors, counts.get("skipped", 0),
                       failures[:200])


def _parse_unittest(text: str) -> TestSummary:
    ran = _UNIT_RAN.search(text)
    total = _as_int(ran.group(1)) if ran else 0
    failed_match = re.search(r"FAILED\s*\(failures=(\d+),\s*errors=(\d+)\)", text)
    failed = _as_int(failed_match.group(1)) if failed_match else 0
    errors = _as_int(failed_match.group(2)) if failed_match else 0
    ok = "OK" in text and failed_match is None
    failures = [{"name": m.group(1).strip(), "message": ""} for m in _UNIT_FAIL.finditer(text)]
    return TestSummary("unittest", ok, max(0, total - failed - errors),
                       failed, errors, 0, failures[:200])


def _parse_jest(text: str) -> TestSummary:
    total_match = _JEST_TOTAL.search(text)
    failed = _as_int(total_match.group(1)) if total_match and total_match.group(1) else 0
    passed = _as_int(total_match.group(2)) if total_match and total_match.group(2) else 0
    total = _as_int(total_match.group(3)) if total_match else passed + failed
    failures = [{"name": m.group(1).strip(), "message": ""} for m in _JEST_FAIL.finditer(text)]
    return TestSummary("jest", failed == 0 and bool(total_match), passed, failed, 0,
                       max(0, total - passed - failed), failures[:200])


def _parse_go(text: str) -> TestSummary:
    failures = [{"name": m.group(1), "message": ""} for m in _GO_FAIL.finditer(text)]
    passed = len(re.findall(r"^ok\s+", text, re.MULTILINE))
    failed = len(failures)
    return TestSummary("go test", failed == 0, passed, failed, 0, 0, failures[:200])


def _parse_cargo(text: str) -> TestSummary:
    match = _CARGO_RESULT.search(text)
    passed = _as_int(match.group(2)) if match else len(re.findall(r"\.\.\.\s+ok", text))
    failed = _as_int(match.group(3)) if match else 0
    failures = [{"name": m.group(1), "message": ""} for m in _CARGO_FAIL.finditer(text)]
    ok = bool(match and match.group(1) == "ok")
    return TestSummary("cargo test", ok, passed, failed, 0, 0, failures[:200])


def _parse_junit(text: str) -> TestSummary:
    root = ET.fromstring(text)
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    passed = failed = errors = skipped = 0
    failures: list[dict[str, str]] = []
    for suite in suites:
        passed += _as_int(suite.get("passed")) if suite.get("passed") else 0
        failed += _as_int(suite.get("failures"))
        errors += _as_int(suite.get("errors"))
        skipped += _as_int(suite.get("skipped"))
        for case in suite.iter("testcase"):
            bad = case.find("failure") if case.find("failure") is not None else case.find("error")
            if bad is not None:
                failures.append({
                    "name": _as_text(case.get("name")),
                    "message": _as_text(bad.get("message") or bad.text)[:1000],
                })
            elif case.find("skipped") is not None:
                skipped += 1
    declared = sum(_as_int(s.get("tests")) for s in suites)
    if not passed and declared:
        passed = max(0, declared - failed - errors - skipped)
    return TestSummary("junit", failed == 0 and errors == 0, passed, failed,
                       errors, skipped, failures[:200])


def _parse_generic(text: str) -> TestSummary:
    lines = [line.strip() for line in text.splitlines()
             if re.search(r"\b(FAIL|FAILED|ERROR|Traceback|AssertionError)\b", line)]
    failures = [{"name": line[:200], "message": ""} for line in lines[:200]]
    return TestSummary("unknown", not failures, 0, len(failures), 0, 0,
                       failures, guessed=True)


def detect_runner(text: str, hint: str | None = None) -> str:
    """Pick the most likely adapter, honoring an explicit hint first."""
    if hint:
        candidate = _as_text(hint).lower()
        # "cargo test" contains "go test", so check the longer name first.
        for name in ("pytest", "unittest", "jest", "cargo test", "go test", "junit"):
            if name in candidate:
                return name
    stripped = strip_ansi(text)
    if "<testsuite" in stripped or "<?xml" in stripped:
        return "junit"
    if "short test summary info" in stripped or "pytest" in stripped:
        return "pytest"
    if re.search(r"Ran\s+\d+\s+tests?", stripped):
        return "unittest"
    if "Snapshots:" in stripped or re.search(r"Tests:\s*\d+", stripped):
        return "jest"
    if re.search(r"^---\s+FAIL:", stripped, re.MULTILINE):
        return "go test"
    if "test result:" in stripped:
        return "cargo test"
    return "unknown"


_PARSERS: dict[str, Callable[[str], TestSummary]] = {
    "pytest": _parse_pytest, "unittest": _parse_unittest, "jest": _parse_jest,
    "go test": _parse_go, "cargo test": _parse_cargo, "junit": _parse_junit,
}


def summarize(raw: Any, runner: str | None = None) -> TestSummary:
    """X2.7: turn raw runner output into a bounded failure summary.

    Missing, mistyped or evidence-free output is an honest failure: it raises a
    typed ``BackendError`` (invalid input) or returns ``ok=False`` with a note
    (empty output), never ``ok=True`` on no evidence.
    """
    if raw is None:
        raise BackendError("no test output to summarize")
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if not isinstance(raw, str):
        raise BackendError("test output must be text")
    text = strip_ansi(raw)
    truncated = len(text) > 200_000
    if truncated:
        text = text[:200_000]
    chosen = detect_runner(text, runner)
    if not text.strip():
        return TestSummary(chosen, False, guessed=True,
                           note="no test output; cannot confirm success")
    parser = _PARSERS.get(chosen, _parse_generic)
    try:
        summary = parser(text)
    except (ET.ParseError, ValueError, TypeError) as exc:
        summary = _parse_generic(text)
        summary.note = f"fallback after {type(exc).__name__}"
        summary.guessed = True
    summary.truncated = truncated
    summary.runner = chosen
    return summary


# ===========================================================================
# X2.8 -- Coverage-guided hints for untested changed lines
# ===========================================================================
def _line_set(value: Any) -> set[int]:
    if isinstance(value, dict):
        value = value.get("executed_lines", value.get("covered_lines", []))
    if not isinstance(value, (list, tuple, set)):
        return set()
    return {n for n in (_as_int(item, -1) for item in value) if n > 0}


def _ranges(lines: Iterable[int]) -> list[dict[str, int]]:
    ordered = sorted(set(lines))
    if not ordered:
        return []
    out: list[dict[str, int]] = []
    start = previous = ordered[0]
    for value in ordered[1:]:
        if value == previous + 1:
            previous = value
            continue
        out.append({"start": start, "end": previous})
        start = previous = value
    out.append({"start": start, "end": previous})
    return out


class CoverageHints:
    def hint(self, changed: dict[str, Any], coverage: dict[str, Any] | None,
             max_hints: int = 50) -> dict[str, Any]:
        """X2.8: report changed lines that the coverage report never executed."""
        if not isinstance(changed, dict):
            raise BackendError("changed lines must be a {file: [lines]} mapping")
        coverage = coverage if isinstance(coverage, dict) else {}
        hints: list[dict[str, Any]] = []
        missing: list[str] = []
        total = 0
        for file, value in changed.items():
            changed_lines = _line_set(value)
            if not changed_lines:
                continue
            name = _as_text(file)
            if name not in coverage:
                missing.append(name)
                hints.append({"file": name, "reason": "no coverage data",
                              "ranges": _ranges(changed_lines),
                              "uncovered_lines": sorted(changed_lines)[:500]})
                continue
            uncovered = changed_lines - _line_set(coverage[name])
            if not uncovered:
                continue
            total += len(uncovered)
            hints.append({"file": name, "reason": "untested changed lines",
                          "ranges": _ranges(uncovered),
                          "uncovered_lines": sorted(uncovered)[:500]})
        return {"hints": hints[:max(0, _clamp(max_hints, 0, 1000, 50))],
                "total_uncovered": total, "files_without_coverage": missing}


# ===========================================================================
# X2.9 -- Dependency upgrade assistant (offline changelogs, one at a time)
# ===========================================================================
class DependencyUpgradeAssistant:
    """Upgrades one dependency at a time and rolls back on a failing test.

    Changelogs are read only from a local package cache: there is no network
    path in this module.  A journal records every step for evidence.
    """

    def __init__(self, cache_root: str | Path, state_path: str | Path | None = None):
        self.root = Path(cache_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = Path(state_path) if state_path is not None else None
        self._journal: list[dict[str, Any]] = []
        stored = _read_json(self.path, {})
        if isinstance(stored, dict) and isinstance(stored.get("journal"), list):
            self._journal = [e for e in stored["journal"] if isinstance(e, dict)]
        self._busy = False

    def _save(self) -> None:
        _write_json(self.path, {"journal": self._journal})

    def _changelog_path(self, package: str) -> Path | None:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", _as_text(package))[:200]
        if not safe or safe in (".", ".."):
            return None
        candidates = [self.root / safe / "CHANGELOG.md", self.root / safe / "CHANGELOG",
                      self.root / f"{safe}.changelog"]
        for candidate in candidates:
            if not _within_root(self.root, candidate):
                continue
            try:
                if candidate.is_file():
                    return candidate
            except OSError:
                continue
        return None

    def read_changelog(self, package: str, max_chars: int = 4000) -> dict[str, Any]:
        path = self._changelog_path(package)
        if path is None:
            return {"package": _as_text(package), "found": False, "excerpt": ""}
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return {"package": _as_text(package), "found": False, "excerpt": ""}
        return {"package": _as_text(package), "found": True,
                "excerpt": text[:max(0, _clamp(max_chars, 1, 100_000, 4000))]}

    def plan(self, packages: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        """X2.9: read each changelog offline before touching any dependency."""
        result: list[dict[str, Any]] = []
        for item in list(packages)[:200]:
            if not isinstance(item, dict):
                continue
            name = _as_text(item.get("name"))
            if not name:
                continue
            result.append({"name": name, "from": _as_text(item.get("from")),
                           "to": _as_text(item.get("to")),
                           "changelog": self.read_changelog(name)})
        return result

    def upgrade_one(self, package: dict[str, Any],
                    apply: Callable[[dict[str, Any]], Any],
                    test: Callable[[dict[str, Any]], Any],
                    rollback: Callable[[dict[str, Any]], Any] | None = None,
                    verify: Callable[[dict[str, Any]], Any] | None = None) -> dict[str, Any]:
        """One dependency, applied and tested atomically with rollback."""
        if self._busy:
            raise GuardError("another dependency upgrade is already in progress")
        if not isinstance(package, dict) or not _as_text(package.get("name")):
            raise BackendError("package requires a name")
        self._busy = True
        name = _as_text(package["name"])
        result: dict[str, Any] = {"name": name, "applied": False, "tests_ok": False,
                                  "rolled_back": False, "rollback_ok": False,
                                  "ok": False, "steps": []}
        try:
            try:
                apply(package)
                result["applied"] = True
                result["steps"].append({"step": "apply", "ok": True, "at": _iso()})
            except Exception as exc:  # noqa: BLE001
                result["steps"].append({"step": "apply", "ok": False,
                                        "error": f"{type(exc).__name__}: {exc}", "at": _iso()})
                if rollback is not None:
                    result["rolled_back"] = True
                    try:
                        rollback(package)
                        result["rollback_ok"] = True
                        result["steps"].append({"step": "rollback", "ok": True, "at": _iso()})
                    except Exception as rb_exc:  # noqa: BLE001
                        result["steps"].append({"step": "rollback", "ok": False,
                                                "error": f"{type(rb_exc).__name__}: {rb_exc}",
                                                "at": _iso()})
                return result
            try:
                outcome = normalize_outcome(test(package))
            except Exception as exc:  # noqa: BLE001
                outcome = TestOutcome(ok=False, failed=1, raw=f"{type(exc).__name__}: {exc}")
            result["tests_ok"] = outcome.ok
            result["steps"].append({"step": "test", "ok": outcome.ok,
                                    "detail": outcome.to_dict(), "at": _iso()})
            if not outcome.ok:
                if rollback is not None:
                    result["rolled_back"] = True
                    try:
                        rollback(package)
                        result["rollback_ok"] = True
                        result["steps"].append({"step": "rollback", "ok": True, "at": _iso()})
                    except Exception as rb_exc:  # noqa: BLE001
                        result["steps"].append({"step": "rollback", "ok": False,
                                                "error": f"{type(rb_exc).__name__}: {rb_exc}",
                                                "at": _iso()})
                if verify is not None and result["rollback_ok"]:
                    try:
                        restored = normalize_outcome(verify(package))
                        result["steps"].append({"step": "verify_rollback", "ok": restored.ok,
                                                "detail": restored.to_dict(), "at": _iso()})
                    except Exception as exc:  # noqa: BLE001
                        result["steps"].append({"step": "verify_rollback", "ok": False,
                                                "error": str(exc), "at": _iso()})
                return result
            result["ok"] = True
            return result
        finally:
            self._journal.append({"package": name, "at": _iso(), **{k: v for k, v in result.items()
                                                                      if k != "steps"}})
            self._save()
            self._busy = False

    def run_all(self, packages: Iterable[dict[str, Any]],
                apply: Callable[[dict[str, Any]], Any],
                test: Callable[[dict[str, Any]], Any],
                rollback: Callable[[dict[str, Any]], Any] | None = None) -> list[dict[str, Any]]:
        """Sequential by construction: stop at the first failure."""
        results: list[dict[str, Any]] = []
        for package in list(packages)[:200]:
            result = self.upgrade_one(package, apply, test, rollback)
            results.append(result)
            if not result["ok"]:
                break
        return results

    def journal(self) -> list[dict[str, Any]]:
        return [dict(e) for e in self._journal]


# ===========================================================================
# X2.10 -- Migration assistants as bundled skills with verification steps
# ===========================================================================
@dataclass(frozen=True)
class MigrationSkill:
    name: str
    from_version: str
    to_version: str
    steps: tuple[str, ...]
    verification: tuple[str, ...]
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "from_version": self.from_version,
                "to_version": self.to_version, "steps": list(self.steps),
                "verification": list(self.verification), "notes": self.notes}


MIGRATION_SKILLS: tuple[MigrationSkill, ...] = (
    MigrationSkill("python-3.8-to-3.11", "3.8", "3.11",
                   ("inspect deprecated APIs", "update dependencies", "rewrite syntax", "run tests"),
                   ("tests", "imports", "type-check"), "stdlib-first; no network required"),
    MigrationSkill("typescript-4-to-5", "4.x", "5.x",
                   ("update tsconfig", "replace deprecated flags", "run typecheck", "run tests"),
                   ("typecheck", "tests", "build"), "offline guidance only"),
    MigrationSkill("go-1-20-to-1-22", "1.20", "1.22",
                   ("update go.mod", "fix loop-variable captures", "go vet", "go test"),
                   ("vet", "tests"), "uses local Go toolchain"),
    MigrationSkill("rust-2021-edition", "2018", "2021",
                   ("set edition in Cargo.toml", "fix into_iter semantics", "cargo check", "cargo test"),
                   ("check", "tests"), "uses local Cargo cache"),
)


class MigrationAssistant:
    def __init__(self, skills: Iterable[MigrationSkill] | None = None,
                 state_path: str | Path | None = None):
        self.path = Path(state_path) if state_path is not None else None
        self._skills: dict[str, MigrationSkill] = {}
        for skill in (MIGRATION_SKILLS if skills is None else skills):
            self.register(skill)
        self._active: dict[str, dict[str, Any]] = {}
        stored = _read_json(self.path, {})
        if isinstance(stored, dict) and isinstance(stored.get("active"), dict):
            self._active = stored["active"]

    def _save(self) -> None:
        _write_json(self.path, {"active": self._active})

    def register(self, skill: MigrationSkill) -> dict[str, Any]:
        if not isinstance(skill, MigrationSkill):
            raise BackendError("skill must be a MigrationSkill")
        if not skill.name or skill.name in self._skills:
            raise BackendError(f"duplicate or empty skill name: {skill.name}")
        if not skill.steps or not skill.verification:
            raise BackendError("skill needs steps and verification steps")
        self._skills[skill.name] = skill
        return skill.to_dict()

    def list_skills(self) -> list[dict[str, Any]]:
        return [self._skills[name].to_dict() for name in sorted(self._skills)]

    def get(self, name: str) -> MigrationSkill:
        try:
            return self._skills[_as_text(name)]
        except KeyError as exc:
            raise BackendError(f"unknown migration skill: {name}") from exc

    def start(self, name: str) -> dict[str, Any]:
        skill = self.get(name)
        self._active[name] = {"step_index": 0, "steps_done": [], "verification": {},
                              "status": "in_progress", "started_at": _iso()}
        self._save()
        return {"name": name, "steps": list(skill.steps),
                "verification": list(skill.verification)}

    def complete_step(self, name: str, index: int) -> dict[str, Any]:
        skill = self.get(name)
        state = self._active.get(name)
        if state is None:
            raise GuardError(f"migration {name} has not been started")
        if state["status"] != "in_progress":
            raise GuardError(f"migration {name} is {state['status']}")
        if _as_int(index) != state["step_index"] or state["step_index"] >= len(skill.steps):
            raise GuardError(f"out-of-order migration step: {index} "
                             f"(expected {state['step_index']})")
        state["steps_done"].append(skill.steps[state["step_index"]])
        state["step_index"] += 1
        self._save()
        return {"name": name, "next_step": state["step_index"],
                "done": state["step_index"] == len(skill.steps)}

    def verify(self, name: str, checks: dict[str, bool]) -> dict[str, Any]:
        skill = self.get(name)
        state = self._active.get(name)
        if state is None:
            raise GuardError(f"migration {name} has not been started")
        if state["step_index"] != len(skill.steps):
            raise GuardError("verification requires all migration steps to be completed")
        evaluated = {key: bool(checks.get(key, False)) for key in skill.verification}
        state["verification"] = evaluated
        state["status"] = "verified" if all(evaluated.values()) else "incomplete"
        state["verified_at"] = _iso()
        self._save()
        return {"name": name, "status": state["status"], "checks": evaluated}

    def status(self, name: str) -> dict[str, Any]:
        self.get(name)
        state = self._active.get(name, {"step_index": 0, "steps_done": [],
                                        "verification": {}, "status": "not_started"})
        return dict(state)


# ===========================================================================
# X2.11 -- Notebook-aware editing (cell diff, run cell, external outputs)
# ===========================================================================
class NotebookDoc:
    def __init__(self, cells: list[dict[str, Any]]):
        self.cells = cells

    @classmethod
    def from_json(cls, text: Any) -> "NotebookDoc":
        try:
            doc = json.loads(_as_text(text))
        except (ValueError, TypeError) as exc:
            raise BackendError("invalid notebook JSON") from exc
        if not isinstance(doc, dict) or not isinstance(doc.get("cells"), list):
            raise BackendError("notebook must contain a cells list")
        cells: list[dict[str, Any]] = []
        for raw in doc["cells"]:
            if not isinstance(raw, dict):
                continue
            source = raw.get("source", "")
            if isinstance(source, list):
                source = "".join(_as_text(part) for part in source)
            cells.append({
                "cell_type": _as_text(raw.get("cell_type") or "code"),
                "id": _as_text(raw.get("id")) or f"cell-{len(cells)}",
                "source": _as_text(source),
                # Outputs are retained on the document but are explicitly
                # excluded from diffs (stored externally by the output store).
                "outputs": raw.get("outputs", []) if isinstance(raw.get("outputs"), list) else [],
                "execution_count": raw.get("execution_count"),
            })
        return cls(cells)

    @classmethod
    def from_cells(cls, cells: Iterable[dict[str, Any]]) -> "NotebookDoc":
        return cls([dict(c) for c in cells])

    def sources(self) -> list[str]:
        return [c["source"] for c in self.cells]

    def cell_count(self) -> int:
        return len(self.cells)


def cell_diff(old: NotebookDoc | dict[str, Any], new: NotebookDoc | dict[str, Any]) -> list[dict[str, Any]]:
    """X2.11: diff cell sources by index; ignore outputs/execution counts."""
    before = old.sources() if isinstance(old, NotebookDoc) else [c["source"] for c in old["cells"]]
    after = new.sources() if isinstance(new, NotebookDoc) else [c["source"] for c in new["cells"]]
    changes: list[dict[str, Any]] = []
    for index in range(max(len(before), len(after))):
        if index >= len(before):
            changes.append({"index": index, "change": "added", "after": after[index]})
        elif index >= len(after):
            changes.append({"index": index, "change": "removed", "before": before[index]})
        elif before[index] != after[index]:
            changes.append({"index": index, "change": "modified",
                            "before": before[index], "after": after[index]})
    return changes


class NotebookOutputStore:
    """Persists cell outputs outside the notebook so diffs stay source-only."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, cell_id: str) -> Path:
        cell_id = _as_text(cell_id)
        if not cell_id or "/" in cell_id or "\\" in cell_id or ".." in cell_id:
            raise BackendError("cell id must be a plain name (no path traversal)")
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", cell_id)[:150]
        if not safe or safe in (".", ".."):
            raise BackendError("invalid cell id")
        path = self.root / f"{safe}.json"
        if not _within_root(self.root, path):
            raise BackendError("cell id escapes output store")
        return path

    def save(self, cell_id: str, outputs: Any,
             execution_count: Any = None) -> dict[str, Any]:
        path = self._path(cell_id)
        payload = {"cell_id": _as_text(cell_id),
                   "outputs": outputs if isinstance(outputs, list) else [],
                   "execution_count": _as_int(execution_count, None) if execution_count is not None else None,
                   "saved_at": _iso()}
        _write_json(path, payload)
        return {"cell_id": cell_id, "stored_at": str(path),
                "outputs_count": len(payload["outputs"])}

    def load(self, cell_id: str) -> dict[str, Any] | None:
        path = self._path(cell_id)
        doc = _read_json(path, None)
        return doc if isinstance(doc, dict) else None


def run_cell(doc: NotebookDoc, index: int, runner: Callable[[str], dict[str, Any]],
             store: NotebookOutputStore) -> dict[str, Any]:
    """X2.11: execute one cell and store its outputs outside the notebook."""
    if not isinstance(doc, NotebookDoc) or index < 0 or index >= doc.cell_count():
        raise BackendError("cell index out of range")
    result = runner(doc.cells[index]["source"])
    if not isinstance(result, dict):
        raise BackendError("cell runner must return a dict")
    return store.save(doc.cells[index]["id"], result.get("outputs", []),
                      result.get("execution_count"))


# ===========================================================================
# X2.12 -- Commit hygiene: conventional suggestions, secret scan, hooks
# ===========================================================================
_CONVENTIONAL = re.compile(r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\(.+\))?(!)?:")
_SCOPED = re.compile(r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)\(([^)]+)\)")
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9._-]{24,}")),
    ("api_key", re.compile(r"(?:api[_-]?key|secret|token)\s*[:=]\s*['\"][A-Za-z0-9/+_-]{20,}['\"]", re.I)),
)


class CommitHygiene:
    def __init__(self, history: Iterable[str] | None = None,
                 state_path: str | Path | None = None):
        self.history = [_as_text(m) for m in (history or [])][:5000]
        self.path = Path(state_path) if state_path is not None else None

    def suggest_type(self, changed_paths: Iterable[str], message_hint: str = "") -> dict[str, Any]:
        """X2.12: derive a conventional-commit type from history + paths."""
        counts: dict[str, int] = {}
        for message in self.history:
            match = _CONVENTIONAL.match(message.strip())
            if match:
                counts[match.group(1)] = counts.get(match.group(1), 0) + 1
        scope_match = _SCOPED.match(message_hint.strip())
        scope = scope_match.group(2) if scope_match else ""
        paths = [_as_text(p) for p in changed_paths]
        heuristic = ""
        if any("test" in p for p in paths):
            heuristic = "test"
        elif any(p.startswith("docs/") or p.endswith((".md", ".rst")) for p in paths):
            heuristic = "docs"
        elif any(".github/" in p or "ci/" in p for p in paths):
            heuristic = "ci"
        lowered = message_hint.lower()
        if any(word in lowered for word in ("fix", "bug", "repair", "hotfix")):
            heuristic = "fix"
        elif any(word in lowered for word in ("add", "feat", "implement", "introduce")):
            heuristic = "feat"
        if counts:
            choice = max(sorted(counts), key=lambda key: counts[key])
            source = "history"
        else:
            choice = heuristic or "chore"
            source = "heuristic"
        alternatives = sorted(counts, key=lambda key: -counts[key])[:4]
        return {"type": choice, "scope": scope, "source": source,
                "alternatives": alternatives,
                "subject": f"{choice}{f'({scope})' if scope else ''}: "}

    def scan_staged_diff(self, diff_text: Any) -> dict[str, Any]:
        """X2.12: find secrets on added lines and redact every finding."""
        findings: list[dict[str, Any]] = []
        flagged_lines: set[tuple[str, int]] = set()
        for file, line_no, content in added_lines(diff_text)[:10000]:
            if (file, line_no) in flagged_lines:
                continue  # one finding per line; overlapping patterns add no value
            for label, pattern in _SECRET_PATTERNS:
                match = pattern.search(content)
                if match is None:
                    continue
                secret = match.group(0)
                flagged_lines.add((file, line_no))
                redacted = content.replace(secret, f"<redacted:{label}>")
                findings.append({"file": file, "line": line_no, "label": label,
                                 "redacted": redacted[:500]})
                break
            if len(findings) >= 100:
                break
        return {"findings": findings, "clean": not findings,
                "note": "redacted values only; never log the raw secret"}

    @staticmethod
    def hook_aware(has_precommit: bool) -> dict[str, Any]:
        """Never bypass an existing pre-commit hook."""
        return {"mode": "delegate" if has_precommit else "native",
                "respect_hook": True, "bypass": False}

    def commit_gate(self, diff_text: Any, has_precommit: bool = False) -> dict[str, Any]:
        scan = self.scan_staged_diff(diff_text)
        hook = self.hook_aware(has_precommit)
        return {"allowed": scan["clean"], "findings": scan["findings"],
                "hook": hook}


# ===========================================================================
# X2.13 -- Monorepo task graph awareness
# ===========================================================================
class MonorepoGraph:
    """Packages map path prefixes to dependency edges and test commands."""

    def __init__(self, packages: dict[str, dict[str, Any]]):
        if not isinstance(packages, dict):
            raise BackendError("packages must be a mapping")
        self.packages: dict[str, dict[str, Any]] = {}
        for name, spec in packages.items():
            spec = spec if isinstance(spec, dict) else {}
            paths = [_as_text(p).replace("\\", "/").strip("/")
                     for p in (spec.get("paths") or []) if _as_text(p)]
            deps = [_as_text(d) for d in (spec.get("depends_on") or []) if _as_text(d)]
            self.packages[_as_text(name)] = {
                "paths": sorted(paths, key=len, reverse=True),
                "depends_on": _dedupe(deps),
                "test_command": _as_text(spec.get("test_command")),
            }
        self._check_cycles()

    def _check_cycles(self) -> None:
        state: dict[str, int] = {}

        def visit(name: str) -> None:
            mark = state.get(name, 0)
            if mark == 1:
                raise BackendError(f"dependency cycle involving {name}", code="dependency_cycle")
            if mark == 2:
                return
            state[name] = 1
            for dep in self.packages.get(name, {}).get("depends_on", []):
                if dep in self.packages:
                    visit(dep)
            state[name] = 2

        for name in self.packages:
            visit(name)

    def package_for_path(self, path: str) -> str | None:
        normalized = _as_text(path).replace("\\", "/").strip("/")
        best: tuple[int, str] | None = None
        for name, spec in self.packages.items():
            for prefix in spec["paths"]:
                if normalized == prefix or normalized.startswith(prefix + "/"):
                    if best is None or len(prefix) > best[0]:
                        best = (len(prefix), name)
        return best[1] if best else None

    def affected(self, changed_paths: Iterable[str]) -> list[str]:
        """Directly touched packages plus all transitive dependents."""
        direct = {name for name in (self.package_for_path(p) for p in changed_paths) if name}
        reverse: dict[str, list[str]] = {name: [] for name in self.packages}
        for name, spec in self.packages.items():
            for dep in spec["depends_on"]:
                if dep in reverse:
                    reverse[dep].append(name)
        pending = list(direct)
        affected = set(direct)
        while pending:
            current = pending.pop()
            for dependent in reverse.get(current, []):
                if dependent not in affected:
                    affected.add(dependent)
                    pending.append(dependent)
        return sorted(affected)

    def scope_tests(self, changed_paths: Iterable[str]) -> dict[str, Any]:
        names = self.affected(changed_paths)
        commands = _dedupe([self.packages[name]["test_command"] for name in names
                            if self.packages[name]["test_command"]])
        return {"packages": names, "commands": commands}


# ===========================================================================
# X2.14 -- Explain a change/file with symbol-level citations
# ===========================================================================
class SymbolIndex:
    def __init__(self, symbols: dict[str, list[dict[str, Any]]] | None = None):
        self.symbols: dict[str, list[dict[str, Any]]] = {}
        for file, items in (symbols or {}).items():
            clean: list[dict[str, Any]] = []
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    continue
                start = _as_int(item.get("start_line"), 0)
                end = _as_int(item.get("end_line"), start)
                name = _as_text(item.get("name")).strip()
                if start < 1 or end < start or not name:
                    continue
                clean.append({"name": name[:200], "kind": _as_text(item.get("kind") or "symbol"),
                              "start_line": start, "end_line": end})
            self.symbols[_as_text(file)] = clean

    def symbols_at(self, file: str, line: int) -> list[dict[str, Any]]:
        return [dict(s) for s in self.symbols.get(_as_text(file), [])
                if s["start_line"] <= line <= s["end_line"]]

    def for_file(self, file: str) -> list[dict[str, Any]]:
        return [dict(s) for s in self.symbols.get(_as_text(file), [])]


class ExplanationBuilder:
    def __init__(self, index: SymbolIndex):
        self.index = index

    def explain_change(self, diff_text: Any, limit: int = 200) -> dict[str, Any]:
        """X2.14: cite every changed line that maps to a known symbol."""
        added = parse_unified_diff(diff_text)
        cited: list[dict[str, Any]] = []
        uncited: list[dict[str, Any]] = []
        total = 0
        for file, lines in added.items():
            for line in sorted(set(lines))[:limit]:
                total += 1
                matches = self.index.symbols_at(file, line)
                if matches:
                    for symbol in matches[:5]:
                        cited.append({"file": file, "line": line,
                                      "symbol": symbol["name"], "kind": symbol["kind"]})
                else:
                    uncited.append({"file": file, "line": line})
        cited = _dedupe(cited)[:limit]
        return {"cited": cited, "uncited": uncited[:limit], "lines_examined": total,
                "coverage": (len(cited) / total) if total else 0.0}

    def explain_file(self, file: str) -> dict[str, Any]:
        symbols = self.index.for_file(file)
        return {"file": _as_text(file), "symbols": symbols,
                "summary": ", ".join(f"{s['name']} ({s['start_line']}-{s['end_line']})"
                                     for s in symbols[:20])}


# ===========================================================================
# X2.15 -- Language packs (guidance, tool wiring, install hints, detection)
# ===========================================================================
LANGUAGE_PACKS: dict[str, dict[str, Any]] = {
    "python": {
        "extensions": [".py", ".pyi"], "lsp": "pyright",
        "install": ["python -m pip install pyright", "python -m pip install pytest"],
        "markers": [("pyproject.toml", "python -m pytest -q"),
                    ("pytest.ini", "python -m pytest -q"),
                    ("setup.cfg", "python -m pytest -q")],
        "tools": ["python", "pytest", "pyright"],
    },
    "typescript": {
        "extensions": [".ts", ".tsx", ".js", ".jsx"], "lsp": "typescript-language-server",
        "install": ["npm i -D typescript", "npm i -D typescript-language-server"],
        "markers": [("package.json", "npm test -- --runInBand")],
        "tools": ["node", "npm", "tsc"],
    },
    "go": {
        "extensions": [".go"], "lsp": "gopls",
        "install": ["go install golang.org/x/tools/gopls@latest"],
        "markers": [("go.mod", "go test ./...")],
        "tools": ["go", "gopls", "gofmt"],
    },
    "rust": {
        "extensions": [".rs"], "lsp": "rust-analyzer",
        "install": ["rustup component add rust-analyzer"],
        "markers": [("Cargo.toml", "cargo test")],
        "tools": ["cargo", "rustc", "rust-analyzer"],
    },
    "java": {
        "extensions": [".java"], "lsp": "jdtls",
        "install": ["install a JDK 17+", "install jdtls from your package manager"],
        "markers": [("pom.xml", "mvn test"), ("build.gradle", "gradle test")],
        "tools": ["javac", "mvn", "gradle"],
    },
    "cpp": {
        "extensions": [".c", ".h", ".cc", ".cpp", ".hpp"], "lsp": "clangd",
        "install": ["install clang/llvm (includes clangd)", "install cmake"],
        "markers": [("CMakeLists.txt", "ctest --output-on-failure"),
                    ("Makefile", "make test")],
        "tools": ["clang", "clangd", "cmake"],
    },
    "csharp": {
        "extensions": [".cs"], "lsp": "csharp-ls",
        "install": ["install the .NET SDK", "dotnet tool install -g csharp-ls"],
        "markers": [(".csproj", "dotnet test"), ("*.sln", "dotnet test")],
        "tools": ["dotnet", "csharp-ls"],
    },
    "php": {
        "extensions": [".php"], "lsp": "phpactor",
        "install": ["install PHP 8+", "composer global require phpactor/phpactor"],
        "markers": [("composer.json", "composer test")],
        "tools": ["php", "composer", "phpactor"],
    },
    "ruby": {
        "extensions": [".rb"], "lsp": "solargraph",
        "install": ["gem install solargraph", "bundle install"],
        "markers": [("Gemfile", "bundle exec rspec")],
        "tools": ["ruby", "bundle", "solargraph"],
    },
    "shell": {
        "extensions": [".sh", ".bash", ".ps1"], "lsp": "bash-language-server",
        "install": ["npm i -g bash-language-server", "shellcheck from your package manager"],
        "markers": [("Makefile", "make test")],
        "tools": ["bash", "shellcheck"],
    },
}


class LanguagePacks:
    """Bundled, immutable-by-copy language guidance for ten language packs."""

    def list(self) -> list[str]:
        return sorted(LANGUAGE_PACKS)

    def get(self, name: str) -> dict[str, Any]:
        pack = LANGUAGE_PACKS.get(_as_text(name).lower())
        if pack is None:
            raise BackendError(f"unknown language pack: {name}")
        return json.loads(json.dumps(pack))

    def detect(self, path: str) -> str | None:
        suffix = Path(_as_text(path)).suffix.lower()
        for name, pack in LANGUAGE_PACKS.items():
            if suffix in pack["extensions"]:
                return name
        return None

    def detect_test_command(self, project: str | Path | Iterable[str]) -> dict[str, Any]:
        """Inspect marker files (directory or an explicit filename list)."""
        if isinstance(project, (str, Path)):
            root = Path(project)
            try:
                present = {p.name for p in root.iterdir()} if root.is_dir() else set()
            except OSError:
                present = set()
        else:
            present = {Path(_as_text(p)).name for p in project}
        for language in self.list():
            for marker, command in LANGUAGE_PACKS[language]["markers"]:
                if marker.startswith("*."):
                    if any(name.endswith(marker[1:]) for name in present):
                        return {"command": command, "marker": marker, "language": language}
                elif marker in present:
                    return {"command": command, "marker": marker, "language": language}
        return {"command": "", "marker": "", "language": "", "guessed": True}

    def install_hints(self, name: str) -> list[str]:
        return list(self.get(name)["install"])


# ===========================================================================
# X2.16 -- Long-running process supervisor
# ===========================================================================
class ProcessSupervisor:
    """Named background jobs with tail/stop/restart and crash reporting.

    Commands run without a shell (argv lists only) and every byte of output
    goes to a log file under ``state_root``.  A non-zero exit is surfaced as a
    crash record with a bounded output tail so the agent sees it.
    """

    _NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")

    def __init__(self, state_root: str | Path | None = None, tail_limit: int = 50):
        self.root = Path(state_root).resolve() if state_root is not None else Path(tempfile.mkdtemp(prefix="keel-jobs-"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.tail_limit = _clamp(tail_limit, 1, 1000, 50)
        self._jobs: dict[str, dict[str, Any]] = {}
        self._crashes: list[dict[str, Any]] = []

    @staticmethod
    def _argv(command: Any) -> list[str]:
        if isinstance(command, str):
            return shlex.split(command)
        if isinstance(command, (list, tuple)) and command and all(isinstance(c, str) for c in command):
            return list(command)
        raise BackendError("command must be a non-empty argv list or string")

    def start(self, name: str, command: Any, cwd: str | Path | None = None) -> dict[str, Any]:
        name = _as_text(name)
        if not self._NAME_RE.match(name):
            raise BackendError("job name must match [A-Za-z0-9][A-Za-z0-9_.-]*")
        if name in self._jobs and self._jobs[name]["handle"].poll() is None:
            raise GuardError(f"job already running: {name}")
        argv = self._argv(command)
        log_path = self.root / f"{name}.log"
        handle = subprocess.Popen(
            argv,
            cwd=str(cwd) if cwd is not None else None,
            stdin=subprocess.DEVNULL,
            stdout=open(log_path, "wb"),
            stderr=subprocess.STDOUT,
            shell=False,
        )
        if name in self._jobs:
            self._close(name)
        self._jobs[name] = {"command": argv, "cwd": _as_text(cwd) if cwd else None,
                            "handle": handle, "log_path": str(log_path),
                            "started_at": _iso(), "crash_recorded": False}
        return {"name": name, "pid": handle.pid, "status": "running",
                "log_path": str(log_path)}

    def _job(self, name: str) -> dict[str, Any]:
        try:
            return self._jobs[_as_text(name)]
        except KeyError as exc:
            raise BackendError(f"unknown job: {name}") from exc

    def _close(self, name: str) -> None:
        job = self._jobs.get(name)
        if not job:
            return
        stream = job.get("stream")
        if stream is not None and not stream.closed:
            stream.close()

    def _reap(self, name: str) -> dict[str, Any]:
        job = self._job(name)
        handle = job["handle"]
        code = handle.poll()
        if code is None:
            return {"name": name, "status": "running", "pid": handle.pid,
                    "log_path": job["log_path"]}
        if not job["crash_recorded"] and code != 0:
            job["crash_recorded"] = True
            self._crashes.append({
                "name": name, "returncode": code, "at": _iso(),
                "output_tail": self.tail(name, self.tail_limit)["lines"],
            })
            if len(self._crashes) > 100:
                self._crashes = self._crashes[-100:]
        return {"name": name, "status": "exited", "returncode": code,
                "pid": handle.pid, "log_path": job["log_path"]}

    def status(self, name: str) -> dict[str, Any]:
        return self._reap(name)

    def wait(self, name: str, timeout: float = 5.0) -> dict[str, Any]:
        """Wait for a job to exit (bounded), then report/crash-record it."""
        job = self._job(name)
        try:
            job["handle"].wait(timeout=max(0.0, float(timeout)))
        except subprocess.TimeoutExpired:
            pass
        return self._reap(name)

    def tail(self, name: str, lines: int | None = None) -> dict[str, Any]:
        job = self._job(name)
        count = _clamp(lines, 1, 1000, self.tail_limit)
        try:
            content = Path(job["log_path"]).read_text(encoding="utf-8", errors="replace")
        except OSError:
            content = ""
        all_lines = content.splitlines()
        return {"name": name, "lines": all_lines[-count:], "total_lines": len(all_lines)}

    def stop(self, name: str) -> dict[str, Any]:
        job = self._job(name)
        handle = job["handle"]
        if handle.poll() is None:
            handle.terminate()
            try:
                handle.wait(timeout=3)
            except subprocess.TimeoutExpired:
                handle.kill()
                handle.wait(timeout=3)
        return self._reap(name)

    def restart(self, name: str) -> dict[str, Any]:
        job = self._job(name)
        command, cwd = job["command"], job["cwd"]
        if job["handle"].poll() is None:
            self.stop(name)
        return self.start(name, command, cwd)

    def crashes(self) -> list[dict[str, Any]]:
        for name in list(self._jobs):
            self._reap(name)
        return [dict(c) for c in self._crashes]

    def stop_all(self) -> list[dict[str, Any]]:
        results = [self.stop(name) for name in list(self._jobs)]
        for name in list(self._jobs):
            self._close(name)
        return results
