"""Scoped settings registry tests (interface-spec §13)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from keel import settings


@pytest.fixture
def roots(tmp_path, monkeypatch):
    state = tmp_path / "state"
    cwd = tmp_path / "proj"
    cwd.mkdir()
    # keep managed source empty on this host
    monkeypatch.setenv("ProgramData", str(tmp_path / "no-programdata"))
    return state, cwd


def _write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def test_defaults_when_nothing_set(roots):
    state, cwd = roots
    r = settings.resolve(state_root=state, cwd=cwd)
    assert r.value["permissionMode"] == "default"
    assert r.value["maxTurns"] == 10
    assert "Read(**/.env)" in r.value["permissions"]["deny"]
    assert "Bash(git status)" in r.value["permissions"]["allow"]
    assert all(d.code != "settings_json_invalid" for d in r.diagnostics)


def test_flag_beats_file(roots):
    state, cwd = roots
    _write(state / "settings.json", {"maxTurns": 3, "permissionMode": "acceptEdits"})
    r = settings.resolve(state_root=state, cwd=cwd,
                         flags={"maxTurns": 7})
    assert r.value["maxTurns"] == 7
    assert r.value["permissionMode"] == "acceptEdits"  # file wins over default


def test_precedence_local_over_project_over_user(roots):
    state, cwd = roots
    _write(state / "settings.json", {"permissionMode": "acceptEdits"})
    _write(cwd / ".claude" / "settings.json", {"permissionMode": "dontAsk"})
    _write(cwd / ".claude" / "settings.local.json", {"permissionMode": "default"})
    r = settings.resolve(state_root=state, cwd=cwd)
    assert r.value["permissionMode"] == "default"
    assert r.provenance["permissionMode"]["scope"] == "local"


def test_union_accumulates_across_scopes(roots):
    state, cwd = roots
    _write(state / "settings.json", {"permissions": {"allow": ["Bash(make)"]}})
    _write(cwd / ".claude" / "settings.json", {"permissions": {"allow": ["Bash(ls)"]}})
    r = settings.resolve(state_root=state, cwd=cwd)
    assert "Bash(make)" in r.value["permissions"]["allow"]
    assert "Bash(ls)" in r.value["permissions"]["allow"]


def test_project_scope_cannot_enable_bypass(roots):
    state, cwd = roots
    _write(cwd / ".claude" / "settings.json",
           {"bypassPermissionsEnabled": True,
            "dangerouslyAllowWithoutConfirm": True})
    r = settings.resolve(state_root=state, cwd=cwd)
    assert r.value["bypassPermissionsEnabled"] is False
    codes = [d.code for d in r.diagnostics]
    assert "scope_not_permitted" in codes


def test_user_can_enable_bypass_but_flags_cannot_loosen_monotonic(roots, monkeypatch):
    state, cwd = roots
    # user provides false explicitly; flags provide true -> most restrictive wins
    _write(state / "settings.json", {"bypassPermissionsEnabled": False})
    r = settings.resolve(state_root=state, cwd=cwd,
                         flags={"bypassPermissionsEnabled": True})
    assert r.value["bypassPermissionsEnabled"] is False
    # env provides true; nothing restrictive anywhere else -> allowed to enable
    monkeypatch.setenv("KEEL_BYPASS_PERMISSIONS_ENABLED", "true")
    r2 = settings.resolve(state_root=state, cwd=cwd)
    assert r2.value["bypassPermissionsEnabled"] is False  # user still says false


def test_defaults_splice_in_rule_lists(roots):
    state, cwd = roots
    r = settings.resolve(state_root=state, cwd=cwd,
                         flags={"permissions": {
                             "deny": ["$defaults", "Read(**/secret.txt)"]}})
    deny = r.value["permissions"]["deny"]
    assert "Read(**/.env)" in deny          # splice expanded at merge time
    assert "Read(**/secret.txt)" in deny


def test_invalid_json_file_ignored_not_fatal(roots):
    state, cwd = roots
    state.mkdir(parents=True)
    (state / "settings.json").write_text("{ not json", encoding="utf-8")
    r = settings.resolve(state_root=state, cwd=cwd)
    assert r.value["permissionMode"] == "default"
    assert any(d.code == "settings_json_invalid" for d in r.diagnostics)


def test_wrong_type_falls_back_to_default(roots):
    state, cwd = roots
    _write(state / "settings.json", {"maxTurns": "ten"})
    r = settings.resolve(state_root=state, cwd=cwd)
    assert r.value["maxTurns"] == 10
    assert any(d.code == "wrong_type" for d in r.diagnostics)


def test_unknown_keys_ignored_with_diagnostic(roots):
    state, cwd = roots
    _write(state / "settings.json", {"totallyUnknownKey": 42})
    r = settings.resolve(state_root=state, cwd=cwd)
    assert "totallyUnknownKey" not in json.dumps(r.value)
    assert any(d.code == "unknown_key" for d in r.diagnostics)


def test_bare_mode_ignores_files_but_honors_flags(roots):
    state, cwd = roots
    _write(state / "settings.json", {"permissionMode": "acceptEdits"})
    _write(cwd / ".claude" / "settings.json", {"maxTurns": 99})
    r = settings.resolve(state_root=state, cwd=cwd, bare=True,
                         flags={"permissionMode": "dontAsk"})
    assert r.value["permissionMode"] == "dontAsk"
    assert r.value["maxTurns"] == 10


def test_as_rule_lists_order(roots):
    state, cwd = roots
    perms = r = settings.as_rule_lists(settings.resolve(state_root=state, cwd=cwd))
    deny, ask, allow = perms
    assert deny and allow
    assert isinstance(ask, list)


def test_managed_highest_priority_only(roots, monkeypatch, tmp_path):
    state, cwd = roots
    managed = tmp_path / "Managed" / "keel"
    _write(managed / "managed-settings.json",
           {"$merge": "highest-priority-only", "permissionMode": "dontAsk"})
    monkeypatch.setenv("ProgramData", str(tmp_path / "Managed"))
    # even flags may not override managed under highest-priority-only
    r = settings.resolve(state_root=state, cwd=cwd,
                         flags={"permissionMode": "bypassPermissions"})
    assert r.value["permissionMode"] == "dontAsk"


def test_settings_show_cli(roots, capsys):
    from keel.cli.main import main
    rc = main(["settings", "show"])
    out = json.loads(capsys.readouterr().out)
    assert "value" in out and "provenance" in out and "diagnostics" in out
    assert rc == 0
