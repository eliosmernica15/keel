"""Phase 0 — shell-AST spike tests against the shell-form corpus."""

from __future__ import annotations

import json
import os

import pytest

from keel.shell_ast import Decline, analyze, operations

CORPUS = os.path.join(os.path.dirname(__file__), "corpus", "shell_forms.json")


def _load():
    with open(CORPUS, "r", encoding="utf-8") as fh:
        return json.load(fh)


CASES = _load()


def test_corpus_is_balanced():
    shells = {c["shell"] for c in CASES}
    assert shells == {"posix", "powershell", "cmd"}
    assert len(CASES) >= 100


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_corpus_case(case):
    if case["expect"] == "decline":
        with pytest.raises(Decline):
            analyze(case["command"], case["shell"])
        return
    result = analyze(case["command"], case["shell"])
    assert set(result.operations) == set(case["expect"]), (
        f"{case['id']}: got {sorted(result.operations)}, "
        f"expected {sorted(case['expect'])}"
    )


def test_declining_is_total_not_partial():
    # a parse that drops a subcommand must never be returned
    with pytest.raises(Decline):
        analyze("rm a && $(evil)", "posix")


def test_redirect_to_file_marks_mutation():
    assert operations("echo hi > ~/.profile", "posix") == {"read", "mutate_local"}


def test_fd_dup_is_not_a_file_write():
    assert operations("ls 2>&1", "posix") == {"read"}


def test_wrapper_stripping_and_compound_split():
    assert operations("sudo nice rm /x && echo done", "posix") == {
        "irreversible", "read"}


def test_cmd_percent_var_declines():
    with pytest.raises(Decline):
        analyze("del %TEMP%\\*", "cmd")


def test_powershell_dynamic_command_declines():
    with pytest.raises(Decline):
        analyze("& $something", "powershell")


def test_unknown_command_is_mutate_local_per_literal_rule():
    # FINAL-APPROVAL-GATE §4.1: indeterminate -> mutate_local (documented)
    assert operations("definitelynotacommand123 x", "posix") == {"mutate_local"}
