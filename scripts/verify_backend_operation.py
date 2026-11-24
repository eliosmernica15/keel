#!/usr/bin/env python3
"""Verify the v6 backend-completion operation's final state.

Hard checks (fail the script):
  - 865 canonical features, parity identical, no duplicate IDs
  - backend attribution covers all promised IDs, all attributed IDs verified
  - every attributed source/test path and evidence doc exists
  - all 20 backend modules exist and integrate through backend_hub/capabilities
  - provenance of all review/remediation commits is present

Evidence-based gate (REPORTED by default; ENFORCED with --strict):
  For every attributed ID, the registry claim is audited against real
  artifacts rather than path existence alone:
    * module: file parses and contains an AST code construct for the ID
      (dict key / declared-collection member / function-class-assignment name);
      comments and plain strings do NOT count. This is path (a) below.
    * ALTERNATIVE path (b): the evidence document's per-ID Markdown table row
      names a concrete symbol AND a concrete test function; both must resolve
      to real AST definitions (module function/class/method/assignment and
      test function respectively). This closes a traceability gap: an ID may
      be implemented and tested but mentioned only in prose in the module.
      Bare comments/strings alone still never pass path (a).
    * test: file parses and a test function/class/decorator references the ID
      or a symbol the module maps to the ID. A valid (b) cross-check also
      satisfies this, because it names a real test function.
    * acceptance_criteria is non-empty.
    * evidence doc exists AND mentions the ID (path (b) requires a row for the
      ID, which necessarily mentions it).

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
        "names": set(),            # module-level identifiers (structure only)
        "strings": set(),          # module-level string constants
        "test_names": set(),       # identifiers inside real test functions
        "test_strings": set(),     # string constants inside real test functions
        "normalized": "",          # normalized identifiers inside test functions
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
    # Evidence must live inside an actual test callable. A bare module-level
    # `LABEL = "D6.1"` proves nothing about behavior and is explicitly rejected.
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test"):
            continue
        info["test_names"].add(node.name)
        for inner in ast.walk(node):
            if isinstance(inner, ast.Name):
                info["test_names"].add(inner.id)
            elif isinstance(inner, ast.Attribute):
                info["test_names"].add(inner.attr)
            elif isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                info["test_strings"].add(inner.value)
    info["normalized"] = _norm(" ".join(info["test_names"]))
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
    if _norm(fid) in info["normalized"]:       # e.g. E7.29 -> test E729_*
        return True
    if fid in info["test_strings"]:            # literal ID inside a test body
        return True
    return bool(symbols & (info["test_names"] | info["test_strings"]))


# --- Path (b): evidence-doc per-ID table cross-check -------------------------
_TABLE_ID_RE = re.compile(r"^[A-Z]+\d+\.\d+[a-z]?$")
_TABLE_SEP_RE = re.compile(r"^:?-{3,}:?$")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _table_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _parse_evidence_rows(path: Path) -> dict[str, list[tuple[tuple[str, ...], list[str]]]]:
    """Parse Markdown tables generically: ID -> [(header, row cells), ...]."""
    out: dict[str, list[tuple[tuple[str, ...], list[str]]]] = defaultdict(list)
    if not path.is_file():
        return out
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    header: tuple[str, ...] | None = None
    for i, line in enumerate(lines):
        text = line.strip()
        if not text.startswith("|"):
            header = None
            continue
        cells = _table_cells(text)
        if cells and all(_TABLE_SEP_RE.fullmatch(c) for c in cells):
            if i and lines[i - 1].strip().startswith("|"):
                header = tuple(_table_cells(lines[i - 1]))
            continue
        if header and cells and _TABLE_ID_RE.fullmatch(cells[0]):
            out[cells[0]].append((header, cells))
    return out


def _evidence_columns(header: tuple[str, ...]) -> tuple[list[int], list[int]]:
    """Locate symbol/test columns by header text; fall back to all data cells."""
    symbol_cols: list[int] = []
    test_cols: list[int] = []
    for i, title in enumerate(header):
        if i == 0:
            continue  # ID column
        low = title.lower()
        if "test" in low:
            test_cols.append(i)
        elif re.search(r"symbol|contract|entr|implement|surface|behavio|backend|code", low):
            symbol_cols.append(i)
    return symbol_cols, test_cols


def _backtick_identifiers(text: str) -> set[str]:
    """Backtick-quoted identifiers, e.g. `A.f/x` -> {A, f, x}, `test_y1_*` -> {test_y1_}."""
    out: set[str] = set()
    for match in _BACKTICK_RE.finditer(text):
        out.update(_IDENT_RE.findall(match.group(1)))
    return out


def _module_code_symbols(path: Path) -> set[str]:
    """Real function / class / method / assignment names in the module."""
    if not path.is_file():
        return set()
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
                elif isinstance(target, ast.Attribute):
                    names.add(target.attr)
    return names


def _test_function_names(path: Path) -> set[str]:
    """Real test function names (including test_* wildcards resolved by prefix)."""
    if not path.is_file():
        return set()
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    return {n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name.startswith("test")}


_evidence_rows_cache: dict[str, dict] = {}
_module_symbols_cache: dict[str, set[str]] = {}
_test_functions_cache: dict[str, set[str]] = {}


def _evidence_crosscheck_ok(fid: str, ev_path: Path, src: Path, test: Path) -> bool:
    """True iff a per-ID evidence row names a real symbol AND a real test."""
    key = str(ev_path)
    if key not in _evidence_rows_cache:
        _evidence_rows_cache[key] = _parse_evidence_rows(ev_path)
    rows = _evidence_rows_cache[key].get(fid, [])
    if not rows:
        return False
    mkey, tkey = str(src), str(test)
    if mkey not in _module_symbols_cache:
        _module_symbols_cache[mkey] = _module_code_symbols(src)
    if tkey not in _test_functions_cache:
        _test_functions_cache[tkey] = _test_function_names(test)
    module_symbols = _module_symbols_cache[mkey]
    test_functions = _test_functions_cache[tkey]

    for header, cells in rows:
        symbol_cols, test_cols = _evidence_columns(header)
        symbol_cells = [cells[i] for i in symbol_cols] if symbol_cols else cells[1:]
        test_cells = [cells[i] for i in test_cols] if test_cols else cells[1:]
        symbol_tokens = set().union(*[_backtick_identifiers(c) for c in symbol_cells]) \
            if symbol_cells else set()
        test_tokens = set().union(*[_backtick_identifiers(c) for c in test_cells]) \
            if test_cells else set()
        has_symbol = any(tok in module_symbols for tok in symbol_tokens)
        has_test = any(
            tok in test_functions or
            (tok.startswith("test_") and any(fn.startswith(tok) for fn in test_functions))
            for tok in test_tokens)
        if has_symbol and has_test:
            return True
    return False


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

    ev = row.get("verification_evidence") or ""
    ev_path = ROOT / ev if ev else ROOT
    # Path (b) cross-check: evidence-doc row -> real symbol + real test.
    cross_ok = _evidence_crosscheck_ok(fid, ev_path, sp, tp)

    if not minfo["exists"]:
        reasons.append("module file missing")
    elif not (_module_construct_ok(minfo, fid) or cross_ok):
        reasons.append("module: no AST construct for ID and no evidence-doc "
                       "row mapping the ID to a real symbol + real test")

    mapped_symbols = minfo["symbols"].get(fid, set())
    if not tinfo["exists"]:
        reasons.append("test file missing")
    elif not (_test_reference_ok(tinfo, fid, mapped_symbols) or cross_ok):
        reasons.append("test: no test function/class/decorator references the "
                       "ID or a mapped symbol, and no evidence-doc row names "
                       "a real test function")

    if not row.get("acceptance_criteria"):
        reasons.append("acceptance_criteria empty")

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

strict = "--strict" in sys.argv
print("\n=== EVIDENCE-BASED GATE (" +
      ("ENFORCED" if strict else "reported only; statuses not changed") + ") ===")
print(f"attributed IDs audited: {len(attribution)}")
print(f"passing all checks: {len(attribution) - len(gate_failures)}")
print(f"failing at least one check: {len(gate_failures)}")
for reason, count in sorted(check_totals.items(), key=lambda kv: -kv[1]):
    print(f"  {count:3d} x {reason}")
print("\nper-ID failures:")
for fid in sorted(gate_failures):
    print(f"  {fid:8s} [{attribution[fid]}] " + "; ".join(gate_failures[fid]))
print("NOTE: " + ("ENFORCED: failures cause a non-zero exit." if strict else
      "these failures are reported, not enforced. No status was "
      "downgraded; the lead decides remediation."))

if strict and gate_failures:
    errors.append(f"{len(gate_failures)} attributed IDs fail the evidence gate "
                  "(see per-ID failures above)")
if errors:
    print("\nBACKEND OPERATION VERIFICATION FAILED:")
    for e in errors:
        print("  -", e)
    raise SystemExit(1)
print("\nBACKEND OPERATION VERIFICATION OK")
