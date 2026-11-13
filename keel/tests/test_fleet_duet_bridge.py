"""Duet bridge bits: trust gate, skills/connectors listing, shell kill, modes."""

from __future__ import annotations

from keel.fleet import routes as fleet_routes
from keel.fleet import shells
from keel.fleet import turn_core


def test_v8_fresh_schema_has_trusted_column(tmp_path):
    store = fleet_routes.reset_store_for_tests(tmp_path / "t.db")
    cols = {r[1] for r in store._conn.execute("PRAGMA table_info(fleet_projects)")}
    assert "trusted" in cols
    store.close()


def test_project_trust_roundtrip(tmp_path):
    store = fleet_routes.reset_store_for_tests(tmp_path / "t.db")
    proj = store.create_project(path=str(tmp_path), name="x")
    assert proj["trusted"] == 0
    trusted = store.set_project_trusted(proj["id"], True)
    assert trusted["trusted"] == 1
    again = store.get_project(proj["id"])
    assert again["trusted"] == 1
    revoked = store.set_project_trusted(proj["id"], False)
    assert revoked["trusted"] == 0
    store.close()


def test_accept_edits_mode_maps_to_accept_edits():
    assert turn_core._normalize_permission_mode("acceptEdits") == "acceptEdits"
    assert turn_core._normalize_permission_mode("accept_edits") == "acceptEdits"
    assert turn_core._normalize_permission_mode("accept-edits") == "acceptEdits"


def test_kill_unknown_shell_is_honest():
    result = shells.kill("bg9999")
    assert result["ok"] is False
    assert "unknown" in result["error"]


def _fake_entry(handle: str, bot_id: str, command: str):
    return shells.BackgroundShell(handle, bot_id, command, "powershell",
                                  None, "C:\\\\tmp\\\\x.log")


def test_list_shells_hides_internal_keepawake_only(monkeypatch):
    keepawake_entry = _fake_entry("t1", "__keepawake__", "$null = '__KEEL_KEEP_AWAKE__'; noop")
    terminal_entry = _fake_entry("t2", "__terminal__", "echo user-started")
    agent_entry = _fake_entry("t3", "bot_abc", "npm run build")
    monkeypatch.setitem(shells._shells, "t1", keepawake_entry)
    monkeypatch.setitem(shells._shells, "t2", terminal_entry)
    monkeypatch.setitem(shells._shells, "t3", agent_entry)
    public = shells.list_shells()
    handles = [s["handle"] for s in public]
    assert "t1" not in handles            # keepawake hidden
    assert "t2" in handles                # terminal shows
    assert "t3" in handles                # agent shell shows
    monkeypatch.delitem(shells._shells, "t1", raising=False)
    monkeypatch.delitem(shells._shells, "t2", raising=False)
    monkeypatch.delitem(shells._shells, "t3", raising=False)


def test_skills_discover_returns_named_skills():
    from keel import skills
    found = skills.discover()
    assert len(found) > 0
    names = [s.name for s in found]
    assert len(names) == len(set(names))
    for s in found:
        assert s.scope in ("bundled", "user", "project")
        assert s.name


def test_connectors_resolution_shape():
    # whatever the host has configured, resolve() must not blow up and must
    # return a dict (possibly empty) for mcpServers
    from pathlib import Path
    from keel.settings import resolve, default_state_root
    resolved = resolve(state_root=default_state_root(), cwd=Path.cwd())
    servers = resolved.value.get("mcpServers", {}) or {}
    assert isinstance(servers, dict)
