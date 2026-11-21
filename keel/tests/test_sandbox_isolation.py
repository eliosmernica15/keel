"""Sandbox cwd isolation — the property actually enforced.

Honest scope: relative file operations are confined to a temp dir; absolute
paths remain reachable. This is not a hardened security boundary.
"""

from __future__ import annotations

from keel.sandbox_exec import run_python


def test_sandbox_relative_cwd_is_isolated():
    code = (
        "import os, pathlib; "
        "print('cwd=' + os.getcwd()); "
        "pathlib.Path('relative.txt').write_text('x'); "
        "print('made=' + str(pathlib.Path('relative.txt').exists()))"
    )
    result = run_python(code, timeout_s=10)
    assert result.ok
    assert "made=True" in result.stdout  # relative write succeeded in temp dir
    assert "keel-sandbox-" in result.stdout  # cwd is the isolated temp dir, not app


def test_sandbox_does_not_pollute_app_cwd(tmp_path, monkeypatch):
    # Change process cwd to a temp dir and verify sandboxed relative writes do
    # not land there.
    monkeypatch.chdir(tmp_path)
    code = "import pathlib; pathlib.Path('escaped.txt').write_text('x')"
    run_python(code, timeout_s=10)
    assert not (tmp_path / "escaped.txt").exists()


def test_sandbox_reports_isolated_cwd():
    result = run_python("print('ok')", timeout_s=5)
    assert result.limits.get("isolated_cwd") is True
