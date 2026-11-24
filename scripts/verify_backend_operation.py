#!/usr/bin/env python3
"""Verify the v6 backend-completion operation's final state.

Hard checks (fail the script):
  - 865 canonical features, parity identical, no duplicate IDs
  - backend attribution covers all promised IDs, all attributed IDs verified
  - every attributed source/test path and evidence doc exists
  - all 20 backend modules exist and integrate through backend_hub/capabilities
  - provenance of all review/remediation commits is present

Evidence-based gate (REPORTED, never auto-enforced):
  For every attributed ID, the registry claim is audited against real
  artifacts rather than path existence alone:
    * module: file parses and contains an AST code construct for the ID
      (dict key / declared-collection member / function-class-assignment name);
      comments and plain strings do NOT count.
    * test: file parses and a test function/class/decorator references the ID
      or a symbol the module maps to the ID.
    * acceptance_criteria is non-empty.
    * evidence doc exists AND mentions the ID.

Per the lead's instruction, failures of this gate are printed as a per-ID list
with counts but do NOT change any status and do NOT fail the script; the lead
decides what to do with them. This is deliberately a certification layer over
unit tests, not a claim of native/production verification.
"""
from __future__ import annotations

import ast
import importlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEEL = ROOT / "keel"
sys.path.insert(0, str(KEEL / "src"))

errors: list[str] = []

index = json.loads((ROOT / "PLAN-INDEX.json").read_text(encoding="utf-8"))
parity = json.loads((ROOT / "parity.json").read_text(encoding="utf-8"))
features = index["features"]
if index != parity:
    errors.append("PLAN-INDEX.json != parity.json")
if len(features) != 865:
    errors.append(f"expected 865 features, got {len(features)}")
ids = [f["id"] for f in features]
if len(ids) != len(set(ids)):
    errors.append("duplicate feature IDs")

status = Counter(f["status"] for f in features)
if status != Counter({"verified": 854, "not_started": 9, "blocked": 2}):
    errors.append(f"unexpected status counts: {dict(status)}")

data = json.loads((ROOT / "backend-final-attribution.json").read_text(encoding="utf-8"))
attribution = data["attribution"]
if len(attribution) != 421:
    errors.append(f"expected 421 attributed backend IDs, got {len(attribution)}")
by_id = {f["id"]: f for f in features}


def resolve(rel: str) -> Path:
    """Registry source/test paths are relative to the keel/ project dir."""
    q = Path(rel)
    return KEEL / q if not (ROOT / q).exists() else ROOT / q


# ---------------------------------------------------------------------------
# Hard checks: attributed paths must exist (kept from the original verifier).
# ---------------------------------------------------------------------------
for fid, mod in attribution.items():
    row = by_id.get(fid)
    if row is None:
        errors.append(f"attributed ID missing from registry: {fid}")
        continue
    if row["status"] != "verified":
        errors.append(f"attributed ID not verified: {fid}")
    paths = [resolve(p) for p in (row.get("source_files") or [])] + \
            [resolve(p) for p in (row.get("test_references") or [])]
    if any(not p.exists() for p in paths):
        errors.append(f"missing source/test evidence for {fid}: "
                      f"{[str(p) for p in paths if not p.exists()]}")
    if not row.get("verification_evidence"):
        errors.append(f"missing verification evidence for {fid}")
    if not (ROOT / row["verification_evidence"]).exists():
        errors.append(f"evidence doc missing for {fid}: {row['verification_evidence']}")

from keel import backend_hub as hub
from keel import capabilities

if len(hub.modules()) != 20:
    errors.append(f"expected 20 backend modules, got {len(hub.modules())}")
if not set(attribution) <= set(hub.feature_ids()):
    errors.append(f"hub index missing "
                  f"{len(set(attribution) - set(hub.feature_ids()))} attributed IDs")
caps = {c["id"] for c in capabilities.list_capabilities()}
for needed in ("backend.modules", "backend.describe", "backend.invoke", "backend.verify"):
    if needed not in caps:
        errors.append(f"capability not registered: {needed}")

for fid in attribution:
    if fid not in hub.FEATURE_TO_MODULE:
        errors.append(f"attributed ID absent from hub index: {fid}")

for mod in hub.modules():
    try:
        importlib.import_module("keel." + mod)
    except Exception as exc:
        errors.append(f"module import failed: {mod}: {exc}")

for name in ("BACKEND-IMPLEMENTATION-DETAIL.md", "BACKEND-OPERATION-TASKBOARD.md",
             "master-plan-v6-review-group1.md", "master-plan-v6-review-group2.md",
             "master-plan-v6-review-group3.md", "master-plan-v6-review-group4.md"):
    if not (ROOT / name).is_file():
        errors.append(f"missing operation document: {name}")

# ---------------------------------------------------------------------------
# Evidence-based gate: AST analysis of module, test, criteria and evidence doc.
# ---------------------------------------------------------------------------
_CAMEL_RE = re.compile(r"\b[A-Z][A-Za-z0-9]{2,}\b")
_SNAKE_RE = re.compile(r"\b[a-z_][a-z0-9_]{3,}\b")
_DOC_ID_RE = re.compile(r"^\s*([A-Z]+\d+\.\d+)\b(.*)$")


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def _symbols_from_expr(node: ast.AST) -> set[str]:
    """Symbol names a registry value maps to an ID (names, attrs, tokens)."""
    out: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.update(_CAMEL_RE.findall(n.value))
            out.update(_SNAKE_RE.findall(n.value))
    return out


def _analyze_module(path: Path) -> dict:
    info: dict = {
        "exists": path.is_file(),
        "dict_keys": set(),          # string-literal dict keys (real constructs)
        "collection_members": set(),  # declared registry (list/tuple/set) members
        "code_names": set(),         # function/class/assignment names
        "symbols": defaultdict(set),  # ID -> mapped symbol names
    }
    if not info["exists"]:
        return info
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            info["code_names"].add(n.name)
        elif isinstance(n, ast.Dict):
            for k in n.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    info["dict_keys"].add(k.value)
        elif isinstance(n, (ast.List, ast.Tuple, ast.Set)):
            for e in n.elts:
                if isinstance(e, ast.Constant) and isinstance(e.value, str):
                    info["collection_members"].add(e.value)
    # Module-level registries: dict key -> mapped symbol, and collection member
    # -> the name of the collection it belongs to (registry membership).
    for n in tree.body:
        value = None
        target = None
        if isinstance(n, ast.Assign):
            value = n.value
            if len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                target = n.targets[0].id
        elif isinstance(n, ast.AnnAssign):
            value = n.value
            if isinstance(n.target, ast.Name):
                target = n.target.id
        if value is None:
            continue
        if isinstance(value, ast.Dict):
            for k, v in zip(value.keys, value.values):
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    info["symbols"][k.value] |= _symbols_from_expr(v)
        if target and isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            for e in value.elts:
                if isinstance(e, ast.Constant) and isinstance(e.value, str):
                    info["symbols"][e.value].add(target)
    # Module docstring "ID :class:`Foo` / :func:`bar`" lines are a declared
    # ID->symbol mapping (used only for the test-reference check, never as a
    # module construct: docstrings are strings and must not pass that check).
    doc = ast.get_docstring(tree) or ""
    for line in doc.splitlines():
        m = _DOC_ID_RE.match(line)
        if m:
            info["symbols"][m.group(1)] |= (
                set(_CAMEL_RE.findall(m.group(2))) |
                set(_SNAKE_RE.findall(m.group(2))))
    return info


def _analyze_test(path: Path) -> dict:
    info: dict = {
        "exists": path.is_file(),
        "names": set(),      # function/class/decorator/attribute/name identifiers
        "strings": set(),    # string constants (literal ID references)
        "normalized": "",    # all identifiers normalized for token matching
    }
    if not info["exists"]:
        return info
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            info["names"].add(n.name)
        elif isinstance(n, ast.Name):
            info["names"].add(n.id)
        elif isinstance(n, ast.Attribute):
            info["names"].add(n.attr)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            info["strings"].add(n.value)
    info["normalized"] = _norm(" ".join(info["names"]))
    return info


_module_cache: dict[str, dict] = {}
_test_cache: dict[str, dict] = {}


def _module_construct_ok(info: dict, fid: str) -> bool:
    # Comments and plain strings are excluded by construction: only AST dict
    # keys, declared-collection members and def/class/assignment names count.
    return (fid in info["dict_keys"] or
            fid in info["collection_members"] or
            fid in info["code_names"])


def _test_reference_ok(info: dict, fid: str, symbols: set[str]) -> bool:
    if not info["exists"]:
        return False
    if _norm(fid) in info["normalized"]:       # e.g. E7.29 -> test class E729_*
        return True
    if fid in info["strings"]:                  # literal ID in a test string
        return True
    return bool(symbols & (info["names"] | info["strings"]))


gate_failures: dict[str, list[str]] = {}
for fid, mod in attribution.items():
    row = by_id[fid]
    reasons: list[str] = []

    sp = resolve((row.get("source_files") or [""])[0])
    tp = resolve((row.get("test_references") or [""])[0])
    mkey, tkey = str(sp), str(tp)
    if mkey not in _module_cache:
        _module_cache[mkey] = _analyze_module(sp)
    if tkey not in _test_cache:
        _test_cache[tkey] = _analyze_test(tp)
    minfo = _module_cache[mkey]
    tinfo = _test_cache[tkey]

    if not minfo["exists"]:
        reasons.append("module file missing")
    elif not _module_construct_ok(minfo, fid):
        reasons.append("module: no AST construct for ID (ID appears only in "
                       "comments/docstrings/plain strings)")

    mapped_symbols = minfo["symbols"].get(fid, set())
    if not tinfo["exists"]:
        reasons.append("test file missing")
    elif not _test_reference_ok(tinfo, fid, mapped_symbols):
        reasons.append("test: no test function/class/decorator references the "
                       "ID or a mapped symbol")

    if not row.get("acceptance_criteria"):
        reasons.append("acceptance_criteria empty")

    ev = row.get("verification_evidence") or ""
    ev_path = ROOT / ev if ev else ROOT
    if not ev or not ev_path.is_file():
        reasons.append("evidence doc missing")
    elif fid not in ev_path.read_text(encoding="utf-8", errors="replace"):
        reasons.append("evidence doc does not mention ID")

    if reasons:
        gate_failures[fid] = reasons

check_totals = Counter()
for reasons in gate_failures.values():
    for r in reasons:
        check_totals[r] += 1

print("features:", len(features), "status:", dict(status))
print("backend modules:", len(hub.modules()), "attributed IDs:", len(attribution))
print("capabilities:", sorted(c for c in caps if c.startswith("backend.")))

print("\n=== EVIDENCE-BASED GATE (reported only; statuses not changed) ===")
print(f"attributed IDs audited: {len(attribution)}")
print(f"passing all checks: {len(attribution) - len(gate_failures)}")
print(f"failing at least one check: {len(gate_failures)}")
for reason, count in sorted(check_totals.items(), key=lambda kv: -kv[1]):
    print(f"  {count:3d} x {reason}")
print("\nper-ID failures:")
for fid in sorted(gate_failures):
    print(f"  {fid:8s} [{attribution[fid]}] " + "; ".join(gate_failures[fid]))
print("NOTE: these failures are reported, not enforced. No status was "
      "downgraded; the lead decides remediation.")

if errors:
    print("\nBACKEND OPERATION VERIFICATION FAILED:")
    for e in errors:
        print("  -", e)
    raise SystemExit(1)
print("\nBACKEND OPERATION VERIFICATION OK")
