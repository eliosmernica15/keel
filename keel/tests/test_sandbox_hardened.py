"""Genuinely enforced sandbox policy — verify each boundary."""

from __future__ import annotations

from keel import sandbox_policy
from keel.sandbox_exec import run_python


def test_workspace_read_write_works():
    r = run_python(
        "import pathlib; pathlib.Path('a.txt').write_text('ok'); "
        "print(pathlib.Path('a.txt').read_text())", timeout_s=10)
    assert r.ok and "ok" in r.stdout


def test_stdlib_imports_work():
    r = run_python("import json, math; print(json.dumps({'a': math.floor(1.2)}))",
                   timeout_s=10)
    assert r.ok and '{"a": 1}' in r.stdout


def test_outside_file_read_denied(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET", encoding="utf-8")
    r = run_python(
        f"print(open({str(secret)!r}).read())", timeout_s=10)
    assert not r.ok
    assert "sandbox:" in r.stderr or "PermissionError" in r.stderr
    assert "TOP-SECRET" not in r.stdout


def test_outside_file_write_denied(tmp_path):
    target = tmp_path / "outside.txt"
    r = run_python(
        f"open({str(target)!r}, 'w').write('x')", timeout_s=10)
    assert not r.ok and not target.exists()
    assert "sandbox:" in r.stderr or "PermissionError" in r.stderr


def test_network_denied_by_default():
    r = run_python(
        "import socket; socket.create_connection(('127.0.0.1', 9), 0.5)",
        timeout_s=10)
    assert not r.ok
    assert "network" in r.stderr.lower() or "PermissionError" in r.stderr


def test_subprocess_denied():
    r = run_python(
        "import subprocess; subprocess.run(['echo','hi'])", timeout_s=10)
    assert not r.ok and "PermissionError" in r.stderr


def test_ctypes_denied():
    r = run_python(
        "import ctypes; ctypes.CDLL('libc.so.6')", timeout_s=10)
    assert not r.ok and "PermissionError" in r.stderr


def test_credentials_not_in_child_env():
    r = run_python(
        "import os; print('LEAK=' + str(any('KEY' in k for k in os.environ)))",
        timeout_s=10)
    assert r.ok and "LEAK=False" in r.stdout


def test_bootstrap_state_not_reachable_via_main(tmp_path):
    """Regression: untrusted code must not rewrite the audit hook's policy."""
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET", encoding="utf-8")
    root = str(tmp_path).replace("\\", "\\\\")
    target = str(secret).replace("\\", "\\\\")
    attacks = [
        f"import __main__; __main__._ROOT='{root}'; "
        f"print(open('{target}').read())",
        f"import __main__,sys; sys.modules['__main__']._LIB_DIRS=(); "
        f"print(open('{target}').read())",
        f"import __main__; print(hasattr(__main__,'_make_guard')); "
        f"print(open('{target}').read())",
    ]
    for code in attacks:
        result = run_python(code, timeout_s=10)
        assert "TOP-SECRET" not in result.stdout
        assert "PermissionError" in result.stderr or "sandbox:" in result.stderr


def test_status_is_honest():
    status = sandbox_policy.sandbox_status()
    assert status["filesystem"]["native_bypass"].startswith("NOT")
    assert status["os_level_isolation"]["seccomp_apparmor_containers"] is False
    assert status["resources"]["audit_hook"] if "audit_hook" in status["resources"] else True
