"""Adversarial acceptance tests for the X2.* backend (all 16 feature IDs).

Self-contained: run with pytest, or directly with
``python -c "import sys; sys.path.insert(0,'keel/src'); exec(open(...).read())"``.
Only the standard library and the module under test are used.
"""

from __future__ import annotations

import json
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

# Make the module importable whether this file is executed directly, collected
# by pytest, or exec'd from a ``python -c`` harness with cwd at the repo root.
_CANDIDATES = [Path.cwd(), Path.cwd() / "keel"]
try:
    _CANDIDATES.append(Path(__file__).resolve().parents[1])
except NameError:
    pass
for _root in _CANDIDATES:
    if (_root / "src" / "keel" / "x2_orchestration_backend.py").exists():
        sys.path.insert(0, str(_root / "src"))
        break

from keel.x2_orchestration_backend import (  # noqa: E402
    FEATURE_IDS, BackendError, GuardError,
    # X2.1
    DiagnosticsLedger, attach_diagnostics,
    # X2.2
    CodeActionRouter,
    # X2.3
    TDDRunner, run_tdd,
    # X2.4
    BugReproGuard,
    # X2.5
    CodeReviewEngine, parse_unified_diff,
    # X2.6
    MergeQueue, preview_conflicts,
    # X2.7
    detect_runner, strip_ansi, summarize,
    # X2.8
    CoverageHints,
    # X2.9
    DependencyUpgradeAssistant,
    # X2.10
    MIGRATION_SKILLS, MigrationAssistant, MigrationSkill,
    # X2.11
    NotebookDoc, NotebookOutputStore, cell_diff, run_cell,
    # X2.12
    CommitHygiene,
    # X2.13
    MonorepoGraph,
    # X2.14
    ExplanationBuilder, SymbolIndex,
    # X2.15
    LanguagePacks,
    # X2.16
    ProcessSupervisor,
)


@contextmanager
def must_raise(exc_type):
    try:
        yield
    except exc_type:
        return
    raise AssertionError(f"expected {exc_type.__name__}")


DIFF = (
    "diff --git a/src/app.py b/src/app.py\n"
    "--- a/src/app.py\n"
    "+++ b/src/app.py\n"
    "@@ -10,3 +10,4 @@ def main():\n"
    "     keep = 1\n"
    "-    old = 2\n"
    "+    new = 2\n"
    "+    TODO: clean this up\n"
    "+    token = 'AKIAIOSFODNN7EXAMPLE'\n"
    "     return keep\n"
)


# ---------------------------------------------------------------------------
# X2.1 -- Diagnostics feedback after every edit
# ---------------------------------------------------------------------------
def test_x2_1_attach_filters_and_preserves_result():
    def provider(path):
        if path == "boom.py":
            raise RuntimeError("lsp crashed")
        return [
            {"file": path, "line": 3, "code": "E1", "severity": "error", "message": "bad"},
            {"file": path, "line": 4, "code": "W1", "severity": "warning", "message": "warn"},
            {"file": path, "line": 5, "code": "I1", "severity": "info", "message": "fyi"},
            {"garbage": True},
            "not a dict",
            {"file": path, "line": 3, "code": "E1", "severity": "error", "message": "bad"},
        ]

    result = {"ok": True, "edited": "src/app.py"}
    out = attach_diagnostics(result, ["src/app.py", "src/app.py"], provider)
    assert result == {"ok": True, "edited": "src/app.py"}, "tool result must not be mutated"
    diags = out["diagnostics"]["diagnostics"]
    assert [d["severity"] for d in diags] == ["error", "warning"], diags
    assert out["needs_resolution"] is True and out["diagnostics_appended"] is True
    assert out["diagnostics"]["degraded"] is False

    broken = attach_diagnostics({"ok": True}, ["boom.py"], provider)
    assert broken["diagnostics"]["degraded"] is True
    assert "lsp crashed" in broken["diagnostics"]["errors"][0]


def test_x2_1_ledger_resolve_justify_and_gate():
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "diag.json"
        ledger = DiagnosticsLedger(store)
        ledger.observe([
            {"file": "a.py", "line": 2, "code": "E9", "severity": "error", "message": "oops"},
            {"file": "b.py", "line": 9, "code": "W9", "severity": "info", "message": "noise"},
        ])
        assert len(ledger.outstanding()) == 1, "info diagnostics are not actionable"
        assert ledger.gate()["allowed"] is False
        with must_raise(GuardError):
            ledger.require_clear("next edit")
        with must_raise(BackendError):
            ledger.justify("a.py", "E9", 2, "   "), "blank justification must be refused"
        assert ledger.justify("a.py", "E9", 2, "third-party stub") is True
        assert ledger.outstanding() == [] and ledger.gate()["allowed"] is True
        reloaded = DiagnosticsLedger(store)
        assert reloaded.gate()["allowed"] is True, "justification must persist"
        ledger.observe([{"file": "a.py", "line": 2, "code": "E9", "severity": "error",
                         "message": "oops"}])
        assert ledger.resolve("a.py", "E9", 2) is True


# ---------------------------------------------------------------------------
# X2.2 -- LSP code actions with honest fallback
# ---------------------------------------------------------------------------
def test_x2_2_fallback_and_validation():
    with tempfile.TemporaryDirectory() as tmp:
        router = CodeActionRouter(tmp)
        with must_raise(BackendError):
            router.plan("rename", {"file": "a.py", "old_name": "x", "new_name": "1bad"})
        with must_raise(BackendError):
            router.plan("rename", {"file": "../escape.py", "old_name": "x", "new_name": "y"})
        with must_raise(BackendError):
            router.plan("extract", {"file": "a.py", "new_name": "f", "start_line": 9, "end_line": 2})
        with must_raise(BackendError):
            router.plan("move", {"file": "a.py", "src": "a.py", "dst": "a.py"})

        plan = router.plan("rename", {"file": "a.py", "old_name": "x", "new_name": "y", "line": 7})
        assert plan["fallback_used"] is True and plan["source"] == "text_edit"
        assert plan["requires_semantic_verification"] is True
        applied = []
        result = router.apply(plan, lambda f, e: applied.append((f, e)))
        assert result["ok"] is True and result["applied"] == 1
        assert "verify text-edit result" in " ".join(result["warnings"])
        failed = router.apply(plan, lambda f, e: (_ for _ in ()).throw(RuntimeError("denied")))
        assert failed["ok"] is False and "denied" in failed["errors"][0]


def test_x2_2_lsp_provider_validated_and_falls_back_on_malformed():
    with tempfile.TemporaryDirectory() as tmp:
        good = CodeActionRouter(tmp, provider={
            "rename": lambda p: {"changes": {
                "a.py": [{"op": "replace", "range": {"start_line": 2, "end_line": 2},
                          "new_text": "y"}]}}})
        plan = good.plan("rename", {"file": "a.py", "old_name": "x", "new_name": "y"})
        assert plan["source"] == "lsp" and plan["fallback_used"] is False

        broken = CodeActionRouter(tmp, provider={
            "rename": lambda p: {"changes": {"a.py": [{"op": "delete"}]}}})
        plan = broken.plan("rename", {"file": "a.py", "old_name": "x", "new_name": "y"})
        assert plan["fallback_used"] is True and plan["reason"] == "malformed_lsp_edit"

        evil = CodeActionRouter(tmp, provider={
            "rename": lambda p: {"changes": {"../outside.py": [
                {"op": "replace", "range": {"start_line": 1}, "new_text": "x"}]}}})
        plan = evil.plan("rename", {"file": "a.py", "old_name": "x", "new_name": "y"})
        assert plan["fallback_used"] is True, "LSP edits must not escape the workspace"


def test_x2_2_apply_revalidates_path_containment():
    with tempfile.TemporaryDirectory() as tmp:
        router = CodeActionRouter(tmp)
        seen = []
        edit = {"op": "replace", "range": {"start_line": 1, "end_line": 1},
                "new_text": "x"}
        for escaping in ("../../etc/passwd", "sub/../../escape.py",
                         str(Path(tmp).parent / "outside.py")):
            plan = {"changes": {escaping: [edit]}}
            with must_raise(BackendError):
                router.apply(plan, lambda f, e: seen.append(f))
        assert seen == [], "no edit outside the root may reach the executor"

        good = {"changes": {"a.py": [edit]}}
        result = router.apply(good, lambda f, e: seen.append(f))
        assert result["ok"] is True and seen == ["a.py"]


# ---------------------------------------------------------------------------
# X2.3 -- TDD loop with evidence
# ---------------------------------------------------------------------------
def test_x2_3_full_red_green_records_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        calls = []
        evidence = run_tdd(
            "test_login",
            {"failed": 1, "raw": "FAILED test_login"},
            lambda: calls.append("implemented"),
            {"passed": 4, "failed": 0},
            Path(tmp) / "tdd.json",
        )
        assert evidence["verified"] is True
        assert evidence["evidence"]["red"]["outcome"]["failed"] == 1
        assert evidence["evidence"]["green"]["outcome"]["passed"] == 4
        assert calls == ["implemented"]
        reloaded = TDDRunner(Path(tmp) / "tdd.json")
        assert reloaded.status()["verified"] is True


def test_x2_3_guards_reject_fake_evidence():
    runner = TDDRunner()
    runner.start("t")
    with must_raise(GuardError):
        runner.implement(lambda: None)
    with must_raise(BackendError):
        runner.record_red({"failed": 0, "passed": 1})
    assert runner.status()["has_red"] is False
    assert runner.evidence()["evidence"]["attempts"][-1]["accepted"] is False
    runner.record_red({"failed": 1})
    with must_raise(GuardError):
        runner.record_green({"failed": 0})
    with must_raise(RuntimeError):
        runner.implement(lambda: (_ for _ in ()).throw(RuntimeError("compile broke")))
    assert runner.status()["phase"] == "implementation_failed"
    runner.implement(lambda: 42)
    with must_raise(BackendError):
        runner.record_green({"failed": 2})
    assert runner.status()["verified"] is False
    runner.record_green({"failed": 0, "passed": 3})
    assert runner.status()["verified"] is True


# ---------------------------------------------------------------------------
# X2.4 -- Bug-repro gate
# ---------------------------------------------------------------------------
def test_x2_4_no_edit_without_failing_repro():
    with tempfile.TemporaryDirectory() as tmp:
        guard = BugReproGuard(Path(tmp) / "repro.json")
        with must_raise(BackendError):
            guard.require_repro("", "")
        guard.require_repro("bug-42", "login crashes on empty password")
        with must_raise(GuardError):
            guard.attempt_edit("fix login")
        with must_raise(BackendError):
            guard.confirm_repro({"failed": 0, "passed": 2})
        guard.confirm_repro({"failed": 1, "raw": "ValueError: empty password"})
        assert guard.status()["confirmed"] is True
        guard.attempt_edit("add guard clause")
        with must_raise(BackendError):
            guard.verify_fix({"failed": 1})
        guard.verify_fix({"failed": 0, "passed": 9})
        assert guard.status()["fix_verified"] is True
        guard.reopen()
        with must_raise(GuardError):
            guard.attempt_edit("second fix reusing old repro")
        assert BugReproGuard(Path(tmp) / "repro.json").status()["confirmed"] is False


# ---------------------------------------------------------------------------
# X2.5 -- Code review comments accepted as tasks
# ---------------------------------------------------------------------------
def test_x2_5_review_only_added_lines_and_task_acceptance():
    assert parse_unified_diff(DIFF)["src/app.py"] == [11, 12, 13]
    engine = CodeReviewEngine()
    inline = engine.review(DIFF)
    styles = [c for c in inline if c["category"] == "style"]
    assert styles and styles[0]["line"] == 12, inline
    assert not [c for c in inline if c["line"] in (10, 14)], "context lines are not reviewable"

    only_security = CodeReviewEngine().review(DIFF, categories=["security"])
    assert all(c["category"] == "security" for c in only_security)

    task = engine.accept(styles[0]["id"])
    again = engine.accept(styles[0]["id"])
    assert task["task_id"] == again["task_id"]
    assert len(engine.tasks()) == 1
    with must_raise(BackendError):
        engine.accept("does-not-exist")
    assert engine.dismiss(styles[0]["id"]) is True
    assert engine.tasks() == []


def test_x2_5_reviewer_failure_is_isolated():
    def bad(_file, _lines, _text):
        raise RuntimeError("reviewer crashed")

    def noisy(_file, _lines, _text):
        return [{"file": "src/app.py", "line": 11, "category": "bugs",
                 "severity": "major", "message": "suspicious"},
                {"file": "src/app.py", "line": 999, "category": "bugs",
                 "severity": "major", "message": "not an added line"}]

    engine = CodeReviewEngine(reviewers=[bad, noisy, noisy])
    comments = engine.review(DIFF)
    assert len(comments) == 1, comments
    assert comments[0]["line"] == 11


# ---------------------------------------------------------------------------
# X2.6 -- Merge queue
# ---------------------------------------------------------------------------
def test_x2_6_conflict_preview_and_land_gate():
    report = preview_conflicts({"a.py": {1, 2, 5}}, {"a.py": {5, 9}, "b.py": {3}})
    assert report["clean"] is False and report["conflicts"][0]["lines"] == [5]
    assert preview_conflicts({"a.py": {1}}, {"a.py": {2}})["clean"] is True
    assert preview_conflicts("+++ b/a.py\n@@ -1,1 +1,1 @@\n+x\n",
                             "+++ b/a.py\n@@ -1,1 +1,1 @@\n+x\n")["clean"] is False

    with tempfile.TemporaryDirectory() as tmp:
        queue = MergeQueue(Path(tmp) / "queue.json")
        queue.enqueue("t1", "agent/t1")
        queue.enqueue("t2", "agent/t2")
        with must_raise(BackendError):
            queue.enqueue("t1", "agent/t1-again")
        assert [e["task_id"] for e in queue.list()] == ["t1", "t2"]
        with must_raise(GuardError):
            queue.land("t1"), "preview is mandatory"
        queue.mark_green("t1", True)
        queue.preview("t1", {"a.py": {1}}, {"a.py": {4}})
        with must_raise(GuardError):
            queue.land("t1"), "green must be recorded after preview"
        queue.mark_green("t1", True)
        assert queue.land("t1")["status"] == "landed"
        with must_raise(GuardError):
            queue.land("t1")

        queue.preview("t2", {"a.py": {7}}, {"a.py": {7}})
        queue.mark_green("t2", True)
        with must_raise(GuardError):
            queue.land("t2"), "conflicts block landing even when green"
        assert queue.list()[1]["ci_green"] is False, "preview invalidates stale green"


# ---------------------------------------------------------------------------
# X2.7 -- Test-runner adapters
# ---------------------------------------------------------------------------
def test_x2_7_adapters_and_failure_digest():
    pytest_out = "\x1b[31mFAILED tests/test_a.py::test_x - AssertionError\x1b[0m\n" \
                 "1 failed, 5 passed, 2 skipped in 0.4s\n"
    summary = summarize(pytest_out, "pytest")
    assert summary.runner == "pytest" and summary.failed == 1 and summary.passed == 5
    assert summary.skipped == 2 and "test_x" in summary.failure_digest()
    assert "\x1b" not in summary.failure_digest()

    unit = summarize("Ran 4 tests in 0.1s\n\nFAILED (failures=1, errors=1)\n"
                     "FAIL: test_one\nERROR: test_two\n", "unittest")
    assert (unit.runner, unit.failed, unit.errors, unit.ok) == ("unittest", 1, 1, False)

    jest = summarize("Tests: 2 failed, 8 passed, 10 total\n  ● login works\n  ● signup works\n",
                     "jest")
    assert jest.failed == 2 and len(jest.failures) == 2

    go = summarize("--- FAIL: TestFoo (0.00s)\nok  \tpkg/a\t0.1s\nFAIL\n", "go test")
    assert go.runner == "go test" and go.failed == 1 and go.passed == 1

    cargo = summarize("test ok_test ... ok\ntest bad_test ... FAILED\n"
                      "test result: FAILED. 1 passed; 1 failed; 0 ignored\n", "cargo test")
    assert cargo.runner == "cargo test" and cargo.failed == 1 and cargo.ok is False

    junit = summarize(
        '<testsuite tests="2" failures="1" errors="0" skipped="0">'
        '<testcase name="ok"/><testcase name="bad"><failure message="boom"/></testcase>'
        '</testsuite>', "junit")
    assert junit.runner == "junit" and junit.failed == 1
    assert junit.failures[0]["name"] == "bad" and "boom" in junit.failures[0]["message"]


def test_x2_7_malformed_unknown_and_truncated():
    assert strip_ansi("\x1b[1mhello\x1b[0m") == "hello"
    assert detect_runner("garbage", "unknown") == "unknown"
    fallback = summarize("Traceback (most recent call last):\nERROR: something\n")
    assert fallback.guessed is True and fallback.failed >= 1

    broken = summarize("<testsuite><unclosed>", "junit")
    assert broken.guessed is True and "ParseError" in broken.note

    huge = summarize("FAILED x - y\n" * 30_000, "pytest")
    assert huge.truncated is True and huge.failed >= 1
    assert len(huge.to_dict()["failures"]) <= 50


def test_x2_7_no_evidence_is_never_fake_success():
    """summarize(None) and parse_unified_diff(123) must not report success."""
    for bad in (None, 123, {"out": "x"}):
        with must_raise(BackendError):
            summarize(bad)
    empty = summarize("")
    assert empty.ok is False and empty.guessed is True
    assert "no test output" in empty.note
    with must_raise(BackendError):
        parse_unified_diff(123)
    assert parse_unified_diff("") == {}


# ---------------------------------------------------------------------------
# X2.8 -- Coverage hints
# ---------------------------------------------------------------------------
def test_x2_8_uncovered_changed_lines():
    hints = CoverageHints().hint(
        {"a.py": [10, 11, 12, 20], "b.py": [3], "c.py": [1, 2, 3], "bad.py": ["x", -7]},
        {"a.py": {"executed_lines": [11]}, "b.py": [3]},
        max_hints=3,
    )
    a = next(h for h in hints["hints"] if h["file"] == "a.py")
    assert a["uncovered_lines"] == [10, 12, 20]
    assert {"start": 10, "end": 10} in a["ranges"]
    assert "c.py" in hints["files_without_coverage"]
    assert 1 <= len(hints["hints"]) <= 3, "max_hints must bound the result"
    assert hints["total_uncovered"] >= 3
    with must_raise(BackendError):
        CoverageHints().hint(["not", "a", "map"], {})


# ---------------------------------------------------------------------------
# X2.9 -- Dependency upgrade assistant
# ---------------------------------------------------------------------------
def test_x2_9_offline_changelog_and_rollback():
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp) / "cache"
        (cache / "libfoo").mkdir(parents=True)
        (cache / "libfoo" / "CHANGELOG.md").write_text("v2: breaking change", encoding="utf-8")
        assistant = DependencyUpgradeAssistant(cache, Path(tmp) / "journal.json")
        planned = assistant.plan([{"name": "libfoo", "from": "1", "to": "2"},
                                  {"name": "missing", "from": "1", "to": "2"}])
        assert planned[0]["changelog"]["found"] is True
        assert "breaking change" in planned[0]["changelog"]["excerpt"]
        assert planned[1]["changelog"]["found"] is False
        assert assistant.read_changelog("../secret")["found"] is False

        applied, rolled = [], []
        ok = assistant.upgrade_one(
            {"name": "libfoo"}, lambda p: applied.append(p["name"]),
            lambda p: {"failed": 0}, lambda p: rolled.append(p["name"]))
        assert ok["ok"] is True and applied == ["libfoo"] and rolled == []

        failed = assistant.upgrade_one(
            {"name": "libfoo"}, lambda p: None,
            lambda p: {"failed": 3, "raw": "tests broke"}, lambda p: rolled.append(p["name"]),
            verify=lambda p: {"failed": 0})
        assert failed["ok"] is False and failed["rolled_back"] is True
        assert failed["rollback_ok"] is True and rolled == ["libfoo"]
        assert [s["step"] for s in failed["steps"]] == ["apply", "test", "rollback", "verify_rollback"]

        def exploding_apply(pkg):
            with must_raise(GuardError):
                assistant.upgrade_one(pkg, lambda x: None, lambda x: {"failed": 0})
            raise RuntimeError("install failed")

        err = assistant.upgrade_one({"name": "libfoo"}, exploding_apply,
                                    lambda p: {"failed": 0}, lambda p: rolled.append("again"))
        assert err["ok"] is False and err["rolled_back"] is True
        assert "again" in rolled
        assert len(assistant.journal()) == 3
        assert DependencyUpgradeAssistant(cache, Path(tmp) / "journal.json").journal()


# ---------------------------------------------------------------------------
# X2.10 -- Migration skills
# ---------------------------------------------------------------------------
def test_x2_10_skill_order_and_verification():
    with tempfile.TemporaryDirectory() as tmp:
        assistant = MigrationAssistant(state_path=Path(tmp) / "migration.json")
        assert len(assistant.list_skills()) == len(MIGRATION_SKILLS)
        with must_raise(BackendError):
            assistant.get("no-such-skill")
        with must_raise(BackendError):
            assistant.register(MIGRATION_SKILLS[0])

        name = "python-3.8-to-3.11"
        plan = assistant.start(name)
        assert len(plan["steps"]) == 4
        with must_raise(GuardError):
            assistant.verify(name, {"tests": True, "imports": True, "type-check": True})
        with must_raise(GuardError):
            assistant.complete_step(name, 3)
        for index in range(4):
            assistant.complete_step(name, index)
        with must_raise(GuardError):
            assistant.complete_step(name, 4)
        partial = assistant.verify(name, {"tests": True})
        assert partial["status"] == "incomplete" and partial["checks"]["imports"] is False
        done = assistant.verify(name, {"tests": True, "imports": True, "type-check": True})
        assert done["status"] == "verified"
        assert MigrationAssistant(state_path=Path(tmp) / "migration.json").status(name)["status"] == "verified"

        custom = MigrationAssistant([
            MigrationSkill("x", "1", "2", ("one",), ("check",))])
        assert custom.get("x").to_version == "2"
        with must_raise(BackendError):
            custom.register(MigrationSkill("bad", "1", "2", (), ("check",)))


# ---------------------------------------------------------------------------
# X2.11 -- Notebook-aware editing
# ---------------------------------------------------------------------------
def test_x2_11_cell_diff_excludes_outputs():
    doc = NotebookDoc.from_json(json.dumps({"cells": [
        {"cell_type": "code", "id": "c1", "source": ["print(1)\n"], "outputs": [], "execution_count": None},
        {"cell_type": "markdown", "id": "c2", "source": "# hi", "outputs": [], "execution_count": None},
    ]}))
    same_source_new_outputs = NotebookDoc.from_json(json.dumps({"cells": [
        {"cell_type": "code", "id": "c1", "source": "print(1)\n",
         "outputs": [{"text": "1"}], "execution_count": 4},
        {"cell_type": "markdown", "id": "c2", "source": "# hi", "outputs": []},
    ]}))
    assert cell_diff(doc, same_source_new_outputs) == [], "outputs must not enter the diff"

    changed = NotebookDoc.from_json(json.dumps({"cells": [
        {"cell_type": "code", "id": "c1", "source": "print(2)", "outputs": []},
    ]}))
    assert cell_diff(doc, changed)[0]["change"] == "modified"
    assert cell_diff(doc, NotebookDoc.from_cells([]))[0]["change"] == "removed"
    with must_raise(BackendError):
        NotebookDoc.from_json("{not json")


def test_x2_11_run_cell_stores_outputs_outside_notebook():
    with tempfile.TemporaryDirectory() as tmp:
        doc = NotebookDoc.from_json(json.dumps({"cells": [
            {"cell_type": "code", "id": "compute", "source": "1+1", "outputs": []}]}))
        store = NotebookOutputStore(Path(tmp) / "outputs")
        result = run_cell(doc, 0, lambda src: {"outputs": [{"text": "2"}], "execution_count": 1}, store)
        assert result["outputs_count"] == 1
        assert store.load("compute")["outputs"][0]["text"] == "2"
        assert doc.cells[0]["outputs"] == [], "the notebook source document is untouched"
        assert cell_diff(doc, doc) == []
        with must_raise(BackendError):
            store.save("../../escape", [])
        with must_raise(BackendError):
            run_cell(doc, 99, lambda src: {}, store)


# ---------------------------------------------------------------------------
# X2.12 -- Commit hygiene
# ---------------------------------------------------------------------------
def test_x2_12_conventional_suggestions_secret_scan_and_hooks():
    hygiene = CommitHygiene(["feat(core): add cache", "fix(core): off-by-one", "feat: more"])
    suggestion = hygiene.suggest_type(["src/core/cache.py"], "feat(core): add cache")
    assert suggestion["type"] == "feat" and suggestion["source"] == "history"
    assert suggestion["scope"] == "core" and suggestion["subject"].startswith("feat(core):")
    assert CommitHygiene().suggest_type(["tests/test_x.py"])["type"] == "test"
    assert CommitHygiene().suggest_type(["src/a.py"], "fix the bug")["type"] == "fix"

    scan = CommitHygiene().scan_staged_diff(DIFF)
    assert scan["clean"] is False and len(scan["findings"]) == 1
    assert scan["findings"][0]["label"] == "aws_access_key"
    assert "AKIA" not in scan["findings"][0]["redacted"]
    benign = CommitHygiene().scan_staged_diff(
        "+++ b/a.py\n@@ -1,1 +1,1 @@\n+x = 'hello world'\n")
    assert benign["clean"] is True

    assert CommitHygiene().hook_aware(True)["mode"] == "delegate"
    gate = CommitHygiene().commit_gate(DIFF, has_precommit=True)
    assert gate["allowed"] is False and gate["hook"]["bypass"] is False
    assert CommitHygiene().commit_gate(benign and "+++ b/a.py\n@@ -1,1 +1,1 @@\n+y=1\n")["allowed"] is True


# ---------------------------------------------------------------------------
# X2.13 -- Monorepo task graph
# ---------------------------------------------------------------------------
def test_x2_13_affected_packages_and_cycles():
    graph = MonorepoGraph({
        "pkg": {"paths": ["packages/pkg"], "depends_on": [], "test_command": "pytest pkg"},
        "pkg2": {"paths": ["packages/pkg2"], "depends_on": ["pkg"], "test_command": "pytest pkg2"},
        "app": {"paths": ["apps/app"], "depends_on": ["pkg2"], "test_command": "pytest app"},
        "other": {"paths": ["apps/other"], "depends_on": [], "test_command": "pytest other"},
    })
    assert graph.package_for_path("packages/pkg/mod.py") == "pkg"
    assert graph.package_for_path("packages/pkg2/mod.py") == "pkg2", "prefix boundary matters"
    assert graph.package_for_path("nowhere/x.py") is None
    assert graph.affected(["packages/pkg/mod.py"]) == ["app", "pkg", "pkg2"]
    scoped = graph.scope_tests(["packages/pkg/mod.py", "packages/pkg/other.py"])
    assert scoped["packages"] == ["app", "pkg", "pkg2"]
    assert len(scoped["commands"]) == 3
    with must_raise(BackendError):
        MonorepoGraph({"a": {"depends_on": ["b"]}, "b": {"depends_on": ["a"]}})


# ---------------------------------------------------------------------------
# X2.14 -- Explanations with symbol-level citations
# ---------------------------------------------------------------------------
def test_x2_14_citations_and_uncited_lines():
    index = SymbolIndex({"src/app.py": [
        {"name": "main", "kind": "function", "start_line": 10, "end_line": 15},
        {"name": "bad", "kind": "function", "start_line": -3, "end_line": 1},
        "junk",
    ]})
    explanation = ExplanationBuilder(index).explain_change(DIFF)
    assert explanation["cited"] and explanation["cited"][0]["symbol"] == "main"
    assert any(c["line"] == 13 for c in explanation["cited"])
    assert explanation["uncited"] == [], "all changed lines here are inside main()"
    assert explanation["lines_examined"] == 3

    outside = ExplanationBuilder(index).explain_change(
        "+++ b/src/app.py\n@@ -90,1 +90,1 @@\n+x\n")
    assert outside["cited"] == [] and outside["uncited"][0]["line"] == 90
    assert ExplanationBuilder(index).explain_file("src/app.py")["summary"].startswith("main")


# ---------------------------------------------------------------------------
# X2.15 -- Language packs
# ---------------------------------------------------------------------------
def test_x2_15_packs_detection_and_test_commands():
    packs = LanguagePacks()
    assert len(packs.list()) == 10
    assert packs.detect("main.rs") == "rust" and packs.detect("script.zzz") is None
    copied = packs.get("go")
    copied["tools"].append("corrupted")
    assert "corrupted" not in packs.get("go")["tools"], "registry must not be mutable"
    assert "gopls" in packs.install_hints("go")[0]

    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "go.mod").write_text("module x\n", encoding="utf-8")
        assert packs.detect_test_command(Path(tmp))["command"] == "go test ./..."
    assert packs.detect_test_command(["pyproject.toml", "package.json"])["language"] == "python"
    assert packs.detect_test_command([])["guessed"] is True
    with must_raise(BackendError):
        packs.get("cobol")


# ---------------------------------------------------------------------------
# X2.16 -- Process supervisor
# ---------------------------------------------------------------------------
def test_x2_16_supervisor_jobs_and_crash_surface():
    with tempfile.TemporaryDirectory() as tmp:
        supervisor = ProcessSupervisor(Path(tmp) / "jobs", tail_limit=5)
        try:
            ok_job = supervisor.start(
                "hello", [sys.executable, "-c", "print('hello world')"])
            assert ok_job["status"] == "running"
            exited = supervisor.wait("hello")
            assert exited["status"] == "exited" and exited["returncode"] == 0
            assert "hello world" in supervisor.tail("hello", 2)["lines"][-1]

            crash = supervisor.start(
                "boom", [sys.executable, "-c",
                         "import sys; sys.stderr.write('boom-line\\n'); sys.exit(3)"])
            assert crash["pid"] > 0
            supervisor.wait("boom")
            crashes = supervisor.crashes()
            assert any(c["name"] == "boom" and c["returncode"] == 3 for c in crashes)
            assert any("boom-line" in line for c in crashes if c["name"] == "boom"
                       for line in c["output_tail"])

            long_job = supervisor.start(
                "sleeper", [sys.executable, "-c", "import time; time.sleep(30)"])
            assert long_job["status"] == "running"
            with must_raise(GuardError):
                supervisor.start("sleeper", [sys.executable, "-c", "pass"])
            restarted = supervisor.restart("sleeper")
            assert restarted["status"] == "running" and restarted["pid"] != long_job["pid"]
            assert supervisor.stop("sleeper")["status"] == "exited"
            with must_raise(BackendError):
                supervisor.tail("never-started")
        finally:
            supervisor.stop_all()

    with tempfile.TemporaryDirectory() as tmp:
        literal = ProcessSupervisor(Path(tmp) / "jobs")
        try:
            literal.start("argv", [sys.executable, "-c",
                                   "import sys; print(sys.argv[1])", "a; echo nope"])
            literal.wait("argv")
            lines = literal.tail("argv", 3)["lines"]
            assert any("a; echo nope" in line for line in lines), "argv must not be shell-expanded"
        finally:
            literal.stop_all()


def test_x2_all_16_ids_execute_real_behavior():
    """Behavioural replacement for the old ID-tuple equality guard.

    Every X2.* ID is executed through a real symbol with concrete inputs and
    its exact output asserted.  Replacing any implementation with a no-op now
    fails this test instead of passing on a tuple comparison.
    """

    def diag_probe():
        out = attach_diagnostics(
            {"ok": True}, ["a.py"],
            lambda p: [{"file": p, "line": 1, "code": "E",
                        "severity": "error", "message": "bad"}])
        return out["needs_resolution"], out["diagnostics"]["degraded"]

    def action_probe():
        with tempfile.TemporaryDirectory() as tmp:
            plan = CodeActionRouter(tmp).plan(
                "rename", {"file": "a.py", "old_name": "x", "new_name": "y",
                           "line": 7})
            return plan["fallback_used"], plan["source"], plan["requires_semantic_verification"]

    def repro_probe():
        with tempfile.TemporaryDirectory() as tmp:
            guard = BugReproGuard(Path(tmp) / "r.json")
            guard.require_repro("bug-42", "desc")
            guard.confirm_repro({"failed": 1})
            return guard.status()["confirmed"]

    def dependency_probe():
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            (cache / "libfoo").mkdir(parents=True)
            (cache / "libfoo" / "CHANGELOG.md").write_text(
                "v2: breaking change", encoding="utf-8")
            assistant = DependencyUpgradeAssistant(cache, Path(tmp) / "j.json")
            planned = assistant.plan([{"name": "libfoo", "from": "1", "to": "2"}])
            return (planned[0]["changelog"]["found"],
                    "breaking change" in planned[0]["changelog"]["excerpt"])

    def notebook_probe():
        old = NotebookDoc.from_json(json.dumps({"cells": [
            {"cell_type": "code", "id": "c1", "source": "print(1)\n", "outputs": []}]}))
        new = NotebookDoc.from_json(json.dumps({"cells": [
            {"cell_type": "code", "id": "c1", "source": "print(2)", "outputs": []}]}))
        return cell_diff(old, new)[0]["change"]

    def supervisor_probe():
        with tempfile.TemporaryDirectory() as tmp:
            sup = ProcessSupervisor(Path(tmp) / "jobs")
            try:
                job = sup.start("hello", [sys.executable, "-c", "print('hi')"])
                sup.wait("hello")
                return job["status"], sup.status("hello")["status"]
            finally:
                sup.stop_all()

    probes = {
        "X2.1": diag_probe,
        "X2.2": action_probe,
        "X2.3": lambda: run_tdd("t", {"failed": 1, "raw": "FAILED t"},
                                lambda: None, {"passed": 4, "failed": 0})["verified"],
        "X2.4": repro_probe,
        "X2.5": lambda: parse_unified_diff(DIFF)["src/app.py"],
        "X2.6": lambda: (lambda r: (r["clean"], r["conflicts"][0]["lines"]))(
            preview_conflicts({"a.py": {1, 2, 5}}, {"a.py": {5, 9}, "b.py": {3}})),
        "X2.7": lambda: (lambda s: (s.runner, s.failed, s.passed, s.skipped))(
            summarize("\x1b[31mFAILED tests/test_a.py::test_x\x1b[0m\n"
                      "1 failed, 5 passed, 2 skipped in 0.4s\n", "pytest")),
        "X2.8": lambda: next(
            h["uncovered_lines"] for h in CoverageHints().hint(
                {"a.py": [10, 11, 12, 20], "b.py": [3], "c.py": [1, 2, 3]},
                {"a.py": {"executed_lines": [11]}, "b.py": [3]}, max_hints=3)["hints"]
            if h["file"] == "a.py"),
        "X2.9": dependency_probe,
        "X2.10": lambda: len(MigrationAssistant().start("python-3.8-to-3.11")["steps"]),
        "X2.11": notebook_probe,
        "X2.12": lambda: (lambda s: (s["type"], s["source"]))(
            CommitHygiene(["feat(core): add cache"]).suggest_type(
                ["src/core/cache.py"], "feat(core): add cache")),
        "X2.13": lambda: MonorepoGraph({
            "pkg": {"paths": ["packages/pkg"], "depends_on": [], "test_command": "pytest pkg"},
            "pkg2": {"paths": ["packages/pkg2"], "depends_on": ["pkg"], "test_command": "pytest pkg2"},
            "app": {"paths": ["apps/app"], "depends_on": ["pkg2"], "test_command": "pytest app"},
            "other": {"paths": ["apps/other"], "depends_on": [], "test_command": "pytest other"},
        }).affected(["packages/pkg/mod.py"]),
        "X2.14": lambda: (lambda e: (e["cited"][0]["symbol"], e["lines_examined"]))(
            ExplanationBuilder(SymbolIndex({"src/app.py": [
                {"name": "main", "kind": "function", "start_line": 10, "end_line": 15}]}
            )).explain_change(DIFF)),
        "X2.15": lambda: (LanguagePacks().detect("main.rs"), len(LanguagePacks().list())),
        "X2.16": supervisor_probe,
    }
    expected = {
        "X2.1": (True, False),
        "X2.2": (True, "text_edit", True),
        "X2.3": True,
        "X2.4": True,
        "X2.5": [11, 12, 13],
        "X2.6": (False, [5]),
        "X2.7": ("pytest", 1, 5, 2),
        "X2.8": [10, 12, 20],
        "X2.9": (True, True),
        "X2.10": 4,
        "X2.11": "modified",
        "X2.12": ("feat", "history"),
        "X2.13": ["app", "pkg", "pkg2"],
        "X2.14": ("main", 3),
        "X2.15": ("rust", 10),
        "X2.16": ("running", "exited"),
    }
    assert set(probes) == set(FEATURE_IDS) == set(expected)
    for fid in FEATURE_IDS:
        assert probes[fid]() == expected[fid], fid


if __name__ == "__main__":
    tests = sorted((name, fn) for name, fn in list(globals().items())
                   if name.startswith("test_") and callable(fn))
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"{len(tests)} tests passed")
