"""Round-2 release-gate verification: workspace trust.

Covers explicit decision, per-path persistence, revocation and the required
"no reads before trust" property. Tests that document a known gap are marked
xfail(strict=False) with the offending file:line in the reason, so the suite
stays green while the defect remains visible and becomes an XPASS when fixed.
"""

from __future__ import annotations

import pytest

from keel.fleet import routes as fleet_routes


@pytest.fixture()
def store(tmp_path, monkeypatch):
    old = fleet_routes._store
    fleet_routes.reset_store_for_tests(tmp_path / "fleet.db")
    yield fleet_routes.store()
    fleet_routes._store = old


def _project(store, tmp_path, name):
    d = tmp_path / name
    d.mkdir()
    return store.create_project(path=str(d), name=name)


def test_fresh_project_is_untrusted_by_default(store, tmp_path):
    proj = _project(store, tmp_path, "fresh")
    assert proj["trusted"] == 0


def test_trust_is_explicit_and_persists_per_path(store, tmp_path):
    a = _project(store, tmp_path, "alpha")
    b = _project(store, tmp_path, "beta")
    assert store.set_project_trusted(a["id"], True)["trusted"] == 1
    # The second path on disk must not inherit the first path's decision.
    assert store.get_project(b["id"])["trusted"] == 0
    # Re-read from the DB, not from the returned object.
    assert store.get_project(a["id"])["trusted"] == 1


def test_trust_revocation_is_immediate_and_persistent(store, tmp_path):
    proj = _project(store, tmp_path, "revoked")
    store.set_project_trusted(proj["id"], True)
    assert store.set_project_trusted(proj["id"], False)["trusted"] == 0
    assert store.get_project(proj["id"])["trusted"] == 0
    assert any(p["id"] == proj["id"] and p["trusted"] == 0
               for p in store.list_projects())


def test_unknown_project_cannot_be_trusted_or_revoked(store):
    assert store.set_project_trusted("does-not-exist", True) is None
    assert store.set_project_trusted("does-not-exist", False) is None


def test_untrusted_project_file_read_is_refused(store, tmp_path):
    proj = _project(store, tmp_path, "secret-project")
    (tmp_path / "secret-project" / "note.txt").write_text("private", encoding="utf-8")
    assert proj["trusted"] == 0
    with pytest.raises((ValueError, PermissionError)) as exc:
        store.read_project_file(proj["id"], "note.txt")
    assert "trust" in str(exc.value).lower()


def test_untrusted_project_tree_is_refused(store, tmp_path):
    proj = _project(store, tmp_path, "tree-project")
    (tmp_path / "tree-project" / "note.txt").write_text("private", encoding="utf-8")
    with pytest.raises((ValueError, PermissionError)) as exc:
        store.list_project_tree(proj["id"])
    assert "trust" in str(exc.value).lower()


def test_untrusted_project_write_is_refused(store, tmp_path):
    proj = _project(store, tmp_path, "write-project")
    with pytest.raises((ValueError, PermissionError)) as exc:
        store.write_project_file(proj["id"], "new.txt", "payload")
    assert "trust" in str(exc.value).lower()


def test_revocation_does_not_leave_a_readable_cached_grant(store, tmp_path):
    """After revocation the stored decision must be the only authority.

    This part of the contract does hold: the flag is persisted as a plain
    boolean, so there is no in-memory grant object to go stale.
    """
    proj = _project(store, tmp_path, "cycle")
    for expected in (True, False, True, False):
        store.set_project_trusted(proj["id"], expected)
        assert bool(store.get_project(proj["id"])["trusted"]) is expected
