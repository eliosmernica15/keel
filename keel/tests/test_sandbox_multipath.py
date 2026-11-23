"""Regression: multi-path filesystem mutations must not escape the sandbox."""

from __future__ import annotations

import tempfile
from pathlib import Path

from keel.sandbox_exec import run_python


def _escape_code(operation: str, outside: Path) -> str:
    return (
        "import os\n"
        "open('inside.txt','w').write('x')\n"
        f"{operation}\n"
        "print('MUTATION_DONE')\n")


def _outside_file():
    root = Path(tempfile.mkdtemp())
    target = root / "outside-marker.txt"
    return root, target


def test_rename_to_outside_denied():
    root, target = _outside_file()
    code = _escape_code(f"os.rename('inside.txt', {str(target)!r})", target)
    result = run_python(code, timeout_s=10)
    assert not target.exists()
    assert "PermissionError" in result.stderr or "sandbox:" in result.stderr
    assert "MUTATION_DONE" not in result.stdout


def test_replace_to_outside_denied():
    root, target = _outside_file()
    code = _escape_code(f"os.replace('inside.txt', {str(target)!r})", target)
    result = run_python(code, timeout_s=10)
    assert not target.exists()
    assert "sandbox:" in result.stderr


def test_symlink_to_outside_denied():
    root, target = _outside_file()
    code = _escape_code(f"os.symlink('inside.txt', {str(target)!r})", target)
    result = run_python(code, timeout_s=10)
    assert not target.exists()
    assert "sandbox:" in result.stderr


def test_link_to_outside_denied():
    root, target = _outside_file()
    code = _escape_code(f"os.link('inside.txt', {str(target)!r})", target)
    result = run_python(code, timeout_s=10)
    assert not target.exists()
    assert "sandbox:" in result.stderr


def test_workspace_rename_still_allowed(tmp_path):
    code = ("import os\nopen('a.txt','w').write('x')\n"
            "os.rename('a.txt','b.txt')\n"
            "print(open('b.txt').read())\n")
    result = run_python(code, timeout_s=10)
    assert result.ok and "x" in result.stdout
