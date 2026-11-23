"""Tests for the X0.x P0 plan-correction artifact verifiers.

The tests prove two things: (1) every verifier passes against the real
repository artifacts, and (2) every verifier FAILS when its artifact is
missing or deliberately tampered with. The second class is what distinguishes
real verification from a restatement of a document's claims.

Stdlib only. Runs under pytest or directly via ``python -c`` with this
directory and ``keel/src`` inserted into ``sys.path``.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "keel" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Load by file path so an installed `keel` package cannot shadow this worktree's
# module (the test suite is also run from the repository root).
_MODULE_PATH = SRC / "keel" / "plan_corrections.py"
_spec = importlib.util.spec_from_file_location(
    "keel_plan_corrections_under_test", _MODULE_PATH)
pc = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = pc
_spec.loader.exec_module(pc)

EXPECTED_IDS = {"X0.1", "X0.2", "X0.3", "X0.4",
                "X0.6", "X0.7", "X0.8", "X0.10"}


def _mirror(tmp: Path, *rels: str) -> Path:
    """Copy a subset of real artifacts into a temporary repository root."""
    for rel in rels:
        source = REPO / rel
        target = tmp / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)
    return tmp


def _all_verify_functions() -> list:
    return list(pc.P0_VERIFIERS) + [pc.verify_x0_9_supporting]


# --- Positive: real repository ---------------------------------------------

def test_verify_all_reports_eight_p0_rows_passing():
    report = pc.verify_all(REPO)
    assert report["scope"] == "Addendum 3 X0.x P0 plan corrections"
    assert report["summary"]["total"] == 8
    assert report["summary"]["all_ok"] is True
    assert {item["id"] for item in report["results"]} == EXPECTED_IDS
    assert all(item["ok"] for item in report["results"])
    assert all(item["ok"] for item in report["supporting_checks"])
    assert [item["id"] for item in report["supporting_checks"]] == ["X0.9"]


def test_every_result_carries_real_evidence():
    report = pc.verify_all(REPO)
    for item in report["results"] + report["supporting_checks"]:
        assert item["evidence"], f"{item['id']} produced no evidence"
        assert item["errors"] == [], f"{item['id']} unexpectedly failed"
        assert isinstance(item["ok"], bool)


def test_verifier_ids_match_plan_index_p0_rows():
    registry = json.loads((REPO / pc.PLAN_INDEX).read_text(encoding="utf-8"))
    in_plan = {f["id"] for f in registry["features"]
               if f["id"].startswith("X0.")
               and f["priority"] == "P0"
               and f["status"] == "not_started"}
    assert in_plan == EXPECTED_IDS
    assert {verify(REPO).id for verify in pc.P0_VERIFIERS} == EXPECTED_IDS


def test_module_is_stdlib_only():
    tree = ast.parse((SRC / "keel" / "plan_corrections.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "ast", "hashlib", "json", "re",
                        "collections", "dataclasses", "pathlib", "typing"}


# --- Negative: missing artifacts -------------------------------------------

def test_missing_artifacts_fail_every_verifier():
    with tempfile.TemporaryDirectory() as tmp:
        empty = Path(tmp)
        for verify in _all_verify_functions():
            result = verify(empty)
            assert result.ok is False, f"{verify.__name__} passed on an empty repo"
            assert result.errors, f"{verify.__name__} gave no failure reason"


# --- Negative: tampered artifacts (one per P0 row) -------------------------

def test_x0_1_detects_reinflated_p0_share():
    with tempfile.TemporaryDirectory() as tmp:
        root = _mirror(Path(tmp), pc.PLAN_INDEX)
        path = root / pc.PLAN_INDEX
        doc = json.loads(path.read_text(encoding="utf-8"))
        changed = 0
        for feature in doc["features"]:
            if (feature["priority"] == "P1"
                    and feature.get("original_priority") == "P0"
                    and changed < 25):
                feature["priority"] = "P0"
                changed += 1
        doc["priority_counts"]["P0"] += changed
        doc["priority_counts"]["P1"] -= changed
        path.write_text(json.dumps(doc), encoding="utf-8")
        assert changed == 25
        result = pc.verify_x0_1(root)
        assert result.ok is False
        assert any("roughly 25%" in error for error in result.errors)


def test_x0_2_detects_missing_m19_split_label():
    with tempfile.TemporaryDirectory() as tmp:
        root = _mirror(Path(tmp), pc.DEP_GRAPH_SCRIPT, pc.DEPENDENCY_GRAPH)
        path = root / pc.DEP_GRAPH_SCRIPT
        text = path.read_text(encoding="utf-8").replace(
            "M19f polish/a11y/i18n", "M19f miscellaneous")
        path.write_text(text, encoding="utf-8")
        result = pc.verify_x0_2(root)
        assert result.ok is False
        assert any("M19f polish/a11y/i18n" in error for error in result.errors)


def test_x0_3_detects_stale_dependency_graph():
    with tempfile.TemporaryDirectory() as tmp:
        root = _mirror(Path(tmp), pc.PLAN_INDEX, pc.DEPENDENCY_GRAPH,
                       pc.SPEC_MODE_SRC)
        path = root / pc.DEPENDENCY_GRAPH
        text = path.read_text(encoding="utf-8")
        import re as _re
        text = _re.sub(r"SHA-256 `[0-9a-f]{64}`",
                       "SHA-256 `" + "0" * 64 + "`", text, count=1)
        path.write_text(text, encoding="utf-8")
        result = pc.verify_x0_3(root)
        assert result.ok is False
        assert any("stale artifact" in error for error in result.errors)


def test_x0_4_detects_dueter_losing_one_mode():
    with tempfile.TemporaryDirectory() as tmp:
        root = _mirror(Path(tmp), pc.DECISIONS, pc.DUET_SRC)
        path = root / pc.DECISIONS
        path.write_text(path.read_text(encoding="utf-8").replace(
            "Review Pair", "Solo Review"), encoding="utf-8")
        result = pc.verify_x0_4(root)
        assert result.ok is False
        assert any("Review Pair" in error for error in result.errors)


def test_x0_6_detects_dropped_free_tier_trap():
    with tempfile.TemporaryDirectory() as tmp:
        root = _mirror(Path(tmp), pc.FREE_TIER_REGISTER)
        path = root / pc.FREE_TIER_REGISTER
        lines = [line for line in path.read_text(encoding="utf-8").splitlines(True)
                 if "Vercel Hobby" not in line]
        path.write_text("".join(lines), encoding="utf-8")
        result = pc.verify_x0_6(root)
        assert result.ok is False
        assert any("Vercel Hobby" in error for error in result.errors)


def test_x0_7_detects_non_commercial_bundling():
    with tempfile.TemporaryDirectory() as tmp:
        root = _mirror(Path(tmp), pc.MODEL_LICENSES, pc.LICENSE_GATE_SCRIPT,
                       pc.OFFLINE_WORKFLOW, pc.NOTICES_HTML)
        path = root / pc.MODEL_LICENSES
        doc = json.loads(path.read_text(encoding="utf-8"))
        entry = next(e for e in doc["entries"] if e["id"] == "piper-tts")
        entry["bundled"] = True
        entry["commercial_use_allowed"] = False
        entry["verified_date"] = ""
        path.write_text(json.dumps(doc), encoding="utf-8")
        result = pc.verify_x0_7(root)
        assert result.ok is False
        assert any("bundled" in error for error in result.errors)


def test_x0_8_detects_missing_network_namespace():
    with tempfile.TemporaryDirectory() as tmp:
        root = _mirror(Path(tmp), pc.OFFLINE_WORKFLOW, pc.OFFLINE_TEST)
        path = root / pc.OFFLINE_WORKFLOW
        path.write_text(path.read_text(encoding="utf-8").replace(
            "unshare -n", "python"), encoding="utf-8")
        result = pc.verify_x0_8(root)
        assert result.ok is False
        assert any("network namespace" in error for error in result.errors)


def test_x0_10_detects_missing_behavior_specs():
    with tempfile.TemporaryDirectory() as tmp:
        root = _mirror(Path(tmp), pc.DECISIONS, pc.BEHAVIOR_SPEC_DIR,
                       pc.EDIT_FORMATS_EVIDENCE, pc.THIRD_PARTY_NOTICES)
        specs = sorted((root / pc.BEHAVIOR_SPEC_DIR).glob("*-behavior.md"))
        assert len(specs) >= 6
        for spec in specs[:2]:
            spec.unlink()
        result = pc.verify_x0_10(root)
        assert result.ok is False
        assert any("behavior specs" in error for error in result.errors)


def test_x0_9_supporting_detects_missing_risk_register():
    with tempfile.TemporaryDirectory() as tmp:
        root = _mirror(Path(tmp))
        result = pc.verify_x0_9_supporting(root)
        assert result.ok is False
        assert any(pc.RISKS in error for error in result.errors)
